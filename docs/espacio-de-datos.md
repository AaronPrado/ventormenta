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

Se añadirán cuando llegue su ingesta o su fase:

- Volumes `open_meteo`, `redata` y `osm` en `ventormenta.raw`.
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
