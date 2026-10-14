# Espacio de datos en Unity Catalog

Dónde guarda VenTormenta sus datos en Unity Catalog y cómo se organizan los ficheros
crudos. Los objetos se definen en [`infra/unity_catalog.sql`](../infra/unity_catalog.sql);
la arquitectura completa está en [el diseño](ventormenta-presentacion.md) (§8.1–8.2 y
§14).

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
    del vigilante de GitHub Actions (diseño §8.2).

  Borrar un Volume gestionado borra también sus ficheros: la protección frente a
  pérdidas es la copia privada de las instantáneas, no Unity Catalog.
- **Un Volume por fuente.** Cada fuente tiene su licencia y sus condiciones (diseño
  §14): los crudos de Red Eléctrica no se redistribuyen, Open-Meteo es CC BY 4.0 y
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
  instantánea (clase observada, diseño §7.1), y la fecha de modificación del fichero no
  sirve para eso. El formato del fichero se define con el job de instantáneas.

## Cómo se crean

Ejecutar [`infra/unity_catalog.sql`](../infra/unity_catalog.sql) en el editor SQL del
workspace con un usuario que tenga el privilegio `CREATE CATALOG` (en Free Edition, el
administrador del workspace). Es idempotente: volver a ejecutarlo no cambia nada.
