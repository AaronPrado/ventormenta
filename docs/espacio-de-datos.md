# Espacio de datos en Unity Catalog

Dónde guarda VenTormenta sus datos en Unity Catalog y cómo se organizan los ficheros
crudos. Los objetos se definen en [`infra/unity_catalog.sql`](../infra/unity_catalog.sql);
la arquitectura completa y las licencias de las fuentes están en
[el diseño](ventormenta-presentacion.md).

## Objetos

| Objeto | Nombre | Contenido |
|---|---|---|
| Catálogo | `ventormenta` | Todo el proyecto |
| Esquema | `ventormenta.raw` | Ficheros crudos tal como llegan de cada fuente, un Volume por fuente |
| Volume gestionado | `ventormenta.raw.esios` | Respuestas crudas de e·sios |
| Volume gestionado | `ventormenta.raw.osm` | Extractos de OpenStreetMap de Geofabrik, tal como se descargan |
| Esquema | `ventormenta.mapeo` | Mapeo de las unidades eólicas a Galicia |
| Tabla Delta gestionada | `ventormenta.mapeo.uf` | Una fila por UF eólica y versión del mapeo, con su clase, su evidencia y la clase de su UP ([regla](mapeo-listado.md)) |

Se añadirán cuando llegue su ingesta o su fase:

- Volumes `open_meteo` y `redata` en `ventormenta.raw`.
- Un esquema por capa para las tablas (`ventormenta.bronze`, `ventormenta.silver`…),
  creados desde el bundle o el pipeline.

## Decisiones

- **Fuera del bundle.** Los objetos de `raw` se crean con un script SQL idempotente, no
  como recursos del bundle. Las instantáneas de la previsión de Red Eléctrica no se
  pueden volver a pedir, así que su almacenamiento no puede depender de un despliegue ni
  de un `bundle destroy`. El bundle solo referencia estos nombres, por variables.
- **Catálogo propio, esquema por capa.** El catálogo es el proyecto y el esquema, la
  capa. Un pipeline de Lakeflow puede escribir en varios esquemas con nombres completos
  ([documentación](https://docs.databricks.com/aws/en/ldp/target-schema)), así que
  separar las capas no obliga a tener varios pipelines.
- **Volume gestionado sobre el almacenamiento por defecto.** Free Edition no tiene
  cuenta en la nube propia ni admite ubicaciones de almacenamiento personalizadas
  ([limitaciones](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)),
  así que no hay dónde apoyar un Volume externo. Según la documentación del
  [almacenamiento por defecto](https://docs.databricks.com/aws/en/storage/default-storage):
  - solo el cómputo serverless puede leerlo;
  - los clientes externos pueden acceder a sus Volumes con la Files API, que es la vía
    del vigilante de GitHub Actions.

  Borrar un Volume gestionado borra también sus ficheros: la protección frente a
  pérdidas es la copia privada de las instantáneas, no Unity Catalog.
- **Un Volume por fuente.** Cada fuente tiene su licencia y sus condiciones: los crudos de Red Eléctrica no se redistribuyen, Open-Meteo es CC BY 4.0 y
  OpenStreetMap es ODbL, con los derivados aparte. Separarlas por Volume mantiene esa
  frontera y permite dar a cada credencial acceso solo a lo que necesita.
- **El mapeo, en el script y por versiones.** La tabla del mapeo tampoco depende del
  bundle: una versión congelada debe sobrevivir a cualquier despliegue. Su clave es
  `(mapping_version, uf_code)`: las filas de una versión se reescriben enteras mientras se
  trabaja en ella, no se tocan una vez congelada, y una versión nueva son filas nuevas. Los
  valores de las clases los comprueba Delta con restricciones `CHECK`; la clave primaria de
  Unity Catalog es informativa, así que la unicidad se comprueba antes de escribir.
- **Nombres en inglés**, como el código y las columnas bitemporales (`valid_time`,
  `available_at`).

## Rutas de los ficheros crudos

Patrón general:

```
/Volumes/ventormenta/raw/<fuente>/<conjunto>/<partición>/<fichero>
```

### Instantáneas de los indicadores de e·sios

```
/Volumes/ventormenta/raw/esios/indicators/<id>/capture_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.json
```

Por ejemplo, una captura del 541 hecha a las 11:30 hora peninsular del 14 de octubre de
2026 (09:30 UTC):

```
/Volumes/ventormenta/raw/esios/indicators/541/capture_date=2026-10-14/20261014T093000Z.json
```

- **Una carpeta por fecha de captura, no por día objetivo.** El crudo se ordena por el
  hecho que lo produjo, la captura; qué días cubre es contenido del fichero. Varias
  capturas del mismo día conviven sin pisarse, y el formato `clave=valor` permite a
  Auto Loader leer `capture_date` como columna.
- **UTC en la ruta.** `capture_date` es la fecha UTC de la captura, y el nombre del
  fichero, su instante UTC en formato ISO 8601 básico (sin `:`, que da problemas en las
  rutas). Así no hay ambigüedad en los días de cambio de hora.
- **Inmutables.** Un fichero no se sobrescribe nunca: repetir una captura crea otro
  fichero.
- **La hora de captura también va dentro del fichero.** Es el `available_at` de la
  instantánea (clase de disponibilidad observada), y la fecha de modificación del fichero no
  sirve para eso. El formato es el sobre descrito abajo.

### Formato de las instantáneas (sobre JSON, `format_version` 1)

Cada fichero es un sobre JSON en UTF-8 que guarda la respuesta de e·sios **literal**, sin
parsear, junto con los datos de la captura. Lo escribe `ventormenta.snapshots`.

```json
{
  "format_version": 1,
  "source": "esios",
  "indicator_id": 541,
  "target_date": "2026-10-15",
  "request": {
    "method": "GET",
    "url": "https://api.esios.ree.es/indicators/541",
    "params": {"start_date": "2026-10-15T00:00:00+02:00", "end_date": "2026-10-15T23:59:59+02:00"}
  },
  "requested_at": "2026-10-14T09:05:00.123456+00:00",
  "received_at": "2026-10-14T09:05:02.654321+00:00",
  "response": {
    "status_code": 200,
    "server_date": "Wed, 14 Oct 2026 09:05:01 GMT",
    "body_sha256": "…",
    "body_encoding": "utf-8",
    "body": "{\"indicator\": {…}}"
  }
}
```

- **`target_date`** es el día D pedido, en hora peninsular; la petición cubre ese día
  completo (23, 24 o 25 horas).
- **`received_at`** (UTC) es el `available_at` de la instantánea: se toma cuando ya ha
  llegado el cuerpo entero, así que nunca es anterior al momento en que se tuvo el dato.
  La ruta del fichero usa este mismo instante. `server_date` es la cabecera `Date` de
  e·sios, para contrastar con su reloj.
- **`body`** es el cuerpo tal como llegó. Se guarda como texto y no como objeto porque
  parsearlo y volver a serializarlo cambiaría los bytes (formato de los números,
  espacios). `body_sha256` es el hash de esos bytes, comprobable con el propio fichero. Si
  el cuerpo no fuera UTF-8 válido, iría en base64 con `body_encoding: "base64"`.
- **Sin cabeceras de la petición:** llevan el token de e·sios.
- **`format_version`** sube si cambia la estructura del sobre, para que la capa bronze
  sepa cómo leer cada fichero.

### Ficheros de archivos de e·sios (I90)

```
/Volumes/ventormenta/raw/esios/archives/<id>/data_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.zip
/Volumes/ventormenta/raw/esios/archives/<id>/data_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.json
```

Por ejemplo, el I90 (archivo 34) del 15 de enero de 2025, recibido a las 12:31:36 UTC del
19 de octubre de 2026:

```
/Volumes/ventormenta/raw/esios/archives/34/data_date=2025-01-15/20261019T123136Z.zip
/Volumes/ventormenta/raw/esios/archives/34/data_date=2025-01-15/20261019T123136Z.json
```

- **Una carpeta por día de los datos, no por fecha de descarga**, al revés que las
  instantáneas: cada día tiene un solo fichero, y saber si ya se descargó es listar una
  carpeta. Lo escribe `ventormenta.archives`, y una carpeta con algo dentro no se vuelve a
  pedir.
- **El zip tal como llega**, para que Auto Loader (`binaryFile`) lo lea sin desenvolverlo.
  El nombre es el instante UTC en que se recibió entero.
- **Al lado, un JSON con el mismo nombre** (`format_version` 1) con:
  - `archive_id` y `data_date`;
  - `detail`: la ficha del archivo (`/archives/<id>`) **literal**, con su SHA-256, y los
    datos de su petición (URL y parámetros, `requested_at`, `received_at`, código y cabecera
    `Date`). La ficha trae la fecha de publicación que declara e·sios;
  - `file`: los mismos datos de la petición del zip, el origen y la ruta a los que
    redirigió e·sios si lo hizo (sin la query, que en una URL prefirmada lleva la firma), y
    el tamaño y el SHA-256 del zip.
- **El JSON se escribe el último**: un zip sin su JSON es una descarga a medias, que se
  revisa a mano en lugar de repetirse.

### Listados de unidades de e·sios

```
/Volumes/ventormenta/raw/esios/archives/<id>/capture_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.data.json
/Volumes/ventormenta/raw/esios/archives/<id>/capture_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.json
```

Por ejemplo, el listado de unidades de programación (archivo 82) recibido a las 13:45:39 UTC
del 20 de octubre de 2026:

```
/Volumes/ventormenta/raw/esios/archives/82/capture_date=2026-10-20/20261020T134539Z.data.json
/Volumes/ventormenta/raw/esios/archives/82/capture_date=2026-10-20/20261020T134539Z.json
```

- **Una carpeta por fecha de captura, como las instantáneas, no por día de los datos.** Los
  listados de unidades (archivos 81 y 82) no tienen fecha: cada descarga es la foto del
  momento. Van junto a los demás archivos de e·sios, y `capture_date` frente a `data_date`
  dice cuál es cuál.
- **El cuerpo JSON tal como llega**, en `<instante>.data.json`.
- **Al lado, `<instante>.json`** (`format_version` 1), como el del I90: `archive_id`,
  `capture_date`, la ficha del archivo **literal** con su SHA-256 y la ruta en la que se
  guardó, y los datos de la petición del listado (URL y parámetros, `requested_at`,
  `received_at`, código, cabecera `Date`, tamaño y SHA-256). `received_at` es el vintage del
  listado.
- **Se escribe el último**, como en el I90: un cuerpo sin su JSON es una escritura a medias.
- En la exploración, un listado con alguna captura no se vuelve a pedir.

### Rangos de indicadores de e·sios

```
/Volumes/ventormenta/raw/esios/indicator_ranges/<id>/month=<AAAA-MM>/<AAAAMMDDTHHMMSSZ>.json
```

Un mes peninsular completo de un indicador, pedido una sola vez (por ejemplo, la producción
eólica medida, 10037, y el P48 eólico, 10010, de los meses de desarrollo).

- **Aparte de `indicators/`**, que guarda las instantáneas diarias de la previsión: esas
  llevan `target_date`, las lee el vigilante y su vintage es la hora de captura antes del
  corte. Un mes histórico es otra cosa, y mezclarlos confundiría a bronze.
- **El mismo sobre que las instantáneas** (`format_version` 1, cuerpo literal y su SHA-256,
  `requested_at` y `received_at`), con `month` en lugar de `target_date` y el rango en los
  parámetros de la petición. `received_at` es el vintage: la medida se revisa al llegar nuevas
  medidas.
- Una carpeta con algo dentro no se vuelve a pedir.

### Catálogos y fichas de e·sios

```
/Volumes/ventormenta/raw/esios/catalogs/indicators/<AAAAMMDDTHHMMSSZ>.json
/Volumes/ventormenta/raw/esios/catalogs/archives/<AAAAMMDDTHHMMSSZ>.json
/Volumes/ventormenta/raw/esios/catalogs/archives/<id>/<AAAAMMDDTHHMMSSZ>.json
/Volumes/ventormenta/raw/esios/catalogs/archives/<id>/date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.json
```

Respuestas de metadatos pedidas una sola vez en la exploración (los catálogos de indicadores
y de archivos y fichas sueltas), guardadas literales. Las fichas sin fecha (como las de los
listados de unidades) van directamente en la carpeta del archivo; las de un día, en su
`date=`. Van aparte de `archives/` para que esa carpeta solo tenga ficheros de datos.

### Extractos de OpenStreetMap (Geofabrik)

```
/Volumes/ventormenta/raw/osm/geofabrik/<región>/extract_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.osm.pbf
/Volumes/ventormenta/raw/osm/geofabrik/<región>/extract_date=<AAAA-MM-DD>/<AAAAMMDDTHHMMSSZ>.json
```

Por ejemplo, el extracto de Galicia del 25 de octubre de 2026, recibido a las 12:20:55 UTC
del 26 de octubre:

```
/Volumes/ventormenta/raw/osm/geofabrik/galicia/extract_date=2026-10-25/20261026T122055Z.osm.pbf
```

- **Una carpeta por fecha del extracto**, como los I90: cada día tiene un solo fichero, y
  una carpeta con algo dentro no se vuelve a pedir. Las regiones son `spain` y `galicia`,
  siempre de la misma fecha: un parque es gallego si está en los dos.
- **El `.osm.pbf` tal como llega**, después de comprobar su tamaño y su cabecera.
- **Al lado, un JSON con el mismo nombre** (`format_version` 1): región, fecha del extracto,
  URL, `requested_at` y `received_at`, código, cabeceras `Date` y `Last-Modified`, tamaño,
  SHA-256, la versión de `osmium` y el instante de los datos según la cabecera del PBF
  (`osmosis_replication_timestamp`), que es el vintage de la foto de OpenStreetMap.
- **El JSON se escribe el último**: un `.osm.pbf` sin su JSON es una descarga a medias.

## Cómo se crean

Ejecutar [`infra/unity_catalog.sql`](../infra/unity_catalog.sql) en el editor SQL del
workspace con un usuario que tenga el privilegio `CREATE CATALOG` (en Free Edition, el
administrador del workspace). Es idempotente: volver a ejecutarlo no cambia nada.

El grupo `ventormenta-watchers` debe existir antes: se crea en la configuración del
workspace (Identity and access), que en Free Edition crea grupos de cuenta, los únicos que
admite Unity Catalog.

## Acceso del vigilante

El workflow vigilante de GitHub Actions lee las instantáneas con un service principal
propio, `ventormenta-watchdog`, miembro del grupo `ventormenta-watchers`. Los privilegios
se conceden al grupo, no a la identidad, así que cambiarla o rotar su secreto no toca el
repositorio.

| Capa | Qué tiene | Qué impide |
|---|---|---|
| Unity Catalog (grupo) | `USE CATALOG` en `ventormenta`, `USE SCHEMA` en `ventormenta.raw` y `READ VOLUME` en `ventormenta.raw.esios` | Escribir en el Volume y leer cualquier otro |
| Scopes del secreto OAuth | `files` y `jobs` | Llamar a cualquier otra API, como la de secretos, donde vive el token de e·sios |
| Entitlement (grupo) | Workspace access | — |

- `READ VOLUME` va en el propio Volume y no en el esquema: en el esquema se heredaría a los
  Volumes que se añadan después.
- El SDK de Databricks pide por defecto un token con el scope `all-apis`, que el secreto
  rechaza: el cliente tiene que pedir sus scopes de forma explícita.
- El secreto caduca a los 365 días. Cuando caduque, el vigilante dejará de poder leer y lo
  avisará con un issue.
