# Vigilante de las instantáneas

Workflow de GitHub Actions que comprueba cada día, desde fuera de Databricks, que hay una
instantánea completa de la previsión eólica de Red Eléctrica anterior al corte, guarda una
copia privada y abre un issue si algo falla. Las instantáneas no se pueden volver a pedir
([instantaneas-esios.md](instantaneas-esios.md)): un día sin captura se pierde para
siempre, y alguien tiene que enterarse.

Vigila desde fuera porque Databricks solo abre conexiones hacia las fuentes de datos: todo
flujo hacia fuera lo inicia GitHub Actions ([diseño](ventormenta-presentacion.md)). Así,
además, detecta la caída del propio Databricks.

## Qué hace

Workflow [`.github/workflows/watchdog.yml`](../.github/workflows/watchdog.yml), que ejecuta
`python -m ventormenta.watchdog_main`:

1. **Lee la ventana.** Con la Files API, descarga del Volume `raw.esios` las carpetas de
   captura que pueden contener los últimos 7 días D cuyo corte ya ha pasado.
2. **Copia.** Escribe en la copia privada los ficheros que aún no están.
3. **Decide.** Para cada día D e indicador (541 y 1777), busca una captura completa
   recibida antes del corte, con la misma lógica que usa el job
   (`ventormenta.snapshots.check_completeness`) y comprobando el hash de cada sobre.
4. **Diagnostica.** Con la API de Jobs, lista las ejecuciones de `esios_snapshots` entre
   la medianoche peninsular de D-1 y el corte.
5. **Avisa.** Escribe el informe en el resumen de la ejecución y abre los issues.

## Hora y ventana

- **12:17 hora peninsular** (`timezone: Europe/Madrid`): 17 minutos después del corte
  durante todo el año, cuando el veredicto de D ya es definitivo (el job se corta a las
  12:00), y lejos de la hora en punto, cuando GitHub más retrasa o descarta las ejecuciones
  programadas.
- **Ventana de 7 días.** GitHub puede descartar una ejecución programada; la siguiente
  revisa también ese día.
- **Inicio de la operación: D 2026-10-16**, el primer día capturado por el job programado.
  La ventana no mira antes.
- El día D se calcula a partir del último corte ya pasado, no de la fecha de hoy: un
  retraso de GitHub, incluso pasada la medianoche peninsular, no cambia qué días se revisan.

## Veredicto

| Situación | Veredicto |
|---|---|
| Hay una captura completa recibida antes de las 12:00 de D-1 | ✅ ok |
| Solo hay capturas con un recuento inesperado | ⚠️ aviso |
| Ninguna captura completa antes del corte (e·sios no había publicado o la respuesta era ilegible) | ❌ fallo |
| Solo capturas posteriores al corte, aunque estén completas | ❌ fallo |
| Sin capturas | ❌ fallo |
| Un fichero que no es un sobre válido o cuyo cuerpo no cuadra con su hash | ❌ fallo |
| Un fichero de la copia con otro contenido que en el Volume | ❌ fallo |

Una captura completa recibida a las 12:00 o después no sirve: usarla sería una fuga
temporal. La ejecución termina con error si hay algún fallo, así que también llega el
correo de GitHub; los avisos no la hacen fallar.

## Issues

- **Uno por problema, nunca repetido.** El título lo identifica («Vigilante: instantáneas
  del 2026-10-16», o la ruta del fichero en los de integridad). Antes de abrir, se leen los
  issues con la etiqueta `vigilante`, abiertos o cerrados: si ya hay uno con ese título, no
  se abre otro. Cerrar un issue significa «revisado».
- **Etiquetas:** `vigilante` en todos y `fallo` o `aviso` según la gravedad.
- **Sin acceso:** si no puede leer Databricks (caída, secreto caducado o permisos
  cambiados), abre «Vigilante: sin acceso a Databricks el <fecha>» y termina con error.
- **Solo metadatos.** El repositorio es público y los datos de Red Eléctrica no se
  redistribuyen: los issues, el log y el resumen llevan estados, recuentos, instantes,
  rutas y huellas, nunca valores. Tampoco llevan mensajes de error del SDK de Databricks ni
  la URL de las ejecuciones, que incluyen datos de la cuenta, porque el enmascarado de
  secretos de GitHub protege los logs, pero no el cuerpo de un issue.

## Copia privada

- Repositorio privado aparte, con la misma estructura que el Volume:
  `esios/indicators/<id>/capture_date=<fecha>/<instante>.json`.
- **Diaria**, en la misma ejecución que la comprobación: los ficheros ya están descargados.
- **Inmutable**, como el Volume: un fichero ya copiado no se sobrescribe, y si llega con
  otro contenido se abre un issue de integridad sin tocar ninguno de los dos.
- Se escribe con una deploy key que solo da acceso a ese repositorio, y que no se puede
  usar para ejecutar nada en él porque tiene Actions desactivado.
- Nunca en artefactos ni en la caché de Actions: en un repositorio público son públicos.

## Credenciales y permisos

| Credencial | Dónde vive | Qué permite |
|---|---|---|
| Service principal `ventormenta-watchdog` (OAuth M2M) | Secretos `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` y `DATABRICKS_CLIENT_SECRET` del environment `watchdog` | Leer el Volume `raw.esios` y ver el job `esios_snapshots`; el secreto está limitado a los scopes `files` y `jobs` |
| Deploy key | Secreto `BACKUP_DEPLOY_KEY` del environment `watchdog` | Escribir en el repositorio de la copia |
| `GITHUB_TOKEN` | Lo da GitHub en cada ejecución | Leer el código y abrir issues |

- El environment `watchdog` solo admite la rama `main`, sin excepción para
  administradores: un PR o una rama no reciben estos secretos.
- Los permisos en Databricks se conceden al grupo `ventormenta-watchers`, no al service
  principal: los de Unity Catalog en [`infra/unity_catalog.sql`](../infra/unity_catalog.sql)
  (detalle en [espacio-de-datos.md](espacio-de-datos.md)) y `CAN_VIEW` sobre el job en
  [`resources/esios_snapshots.job.yml`](../resources/esios_snapshots.job.yml).
- El cliente pide los scopes de forma explícita (`ventormenta.watchdog_main.SCOPES`): el
  SDK pide `all-apis` por defecto y el secreto lo rechaza.

## Ejecutarlo a mano

Desde la pestaña Actions, «Run workflow» sobre `main`. Con `target_date` revisa solo ese
día D, aunque sea anterior al inicio de la operación: con un día sin capturas produce un
fallo real, útil para comprobar que los issues llegan.

En local, sin abrir issues ni tocar la copia, con un secreto propio del service principal
y sin el perfil de la CLI, para no usar otras credenciales sin darse cuenta:

```bash
env -u DATABRICKS_CONFIG_PROFILE DATABRICKS_CONFIG_FILE=/dev/null DATABRICKS_AUTH_TYPE=oauth-m2m DATABRICKS_HOST=… DATABRICKS_CLIENT_ID=… DATABRICKS_CLIENT_SECRET=… uv run --locked python -m ventormenta.watchdog_main --dry-run
```

Con `--dry-run`, el informe lista los issues que se abrirían. Sin `--backup-dir`, la copia
no se toca.

## Mantenimiento

- **El secreto del service principal caduca a los 365 días.** Cuando caduque, el vigilante
  abrirá el issue de «sin acceso». Para renovarlo: generar uno nuevo con los mismos scopes,
  sustituir `DATABRICKS_CLIENT_SECRET` en el environment y borrar el anterior.
- **GitHub desactiva los workflows programados** de un repositorio público tras 60 días sin
  actividad.
- **Riesgo aceptado:** en los repositorios privados de GitHub Free no hay rulesets, así que
  quien tuviera la deploy key podría reescribir el historial de la copia. Para perder datos
  haría falta, además, perder el Volume.
