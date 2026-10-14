# Job de instantáneas de e·sios

Captura cada día la previsión eólica de Red Eléctrica para el día siguiente, tal como está
antes del corte de las 12:00 hora peninsular de D-1. La API de e·sios solo devuelve la
última versión de cada indicador, así que la comparación con Red Eléctrica solo puede
hacerse con estas instantáneas propias ([diseño](ventormenta-presentacion.md) §7.2). Qué
publica cada indicador y cuándo: [fuentes-esios.md](fuentes-esios.md). Dónde y en qué
formato se guarda: [espacio-de-datos.md](espacio-de-datos.md).

## Qué hace

- Job `esios_snapshots` del bundle ([`resources/esios_snapshots.job.yml`](../resources/esios_snapshots.job.yml)),
  con el notebook [`notebooks/jobs/esios_snapshot.py`](../notebooks/jobs/esios_snapshot.py)
  y el paquete `ventormenta` instalado como wheel en el entorno serverless 6.
- Una tarea por indicador, encadenadas: primero el **1777** (previsión D+1, candidato
  principal para la comparación) y después el **541** (previsión que se actualiza cada
  hora). La segunda se ejecuta aunque falle la primera.
- Cada tarea hace **una** petición por el día D completo, guarda la respuesta literal en el
  Volume sin sobrescribir y después comprueba que trae un valor por intervalo del día.

## Hora

- **11:00 hora peninsular** (`Europe/Madrid`, sigue solo los cambios de hora). El 1777 se
  publica hacia las 10:50–10:51 de D-1; quedan algo menos de 60 minutos hasta el corte para
  los reintentos.
- Consecuencia: la versión capturada del 541 es la de hacia las 10:40, no la que está
  vigente a las 12:00 (la de las 11:39–11:43). Una franja más tardía no deja margen para
  reintentar, y una segunda franja duplicaría las peticiones del 1777, que no cambia tras
  publicarse.
- El job se corta a los 60 minutos: una captura posterior al corte ya no sirve para el
  día D.

## Reintentos y presupuesto de peticiones

| Resultado de la captura | Qué hace la tarea | ¿Reintenta? |
|---|---|---|
| Error de red, tiempo de espera o código HTTP de error | Falla sin guardar nada | Sí |
| Respuesta sin valores del día (aún no publicado) | Guarda y falla | Sí |
| Respuesta ilegible (no es JSON, faltan claves) | Guarda y falla | Sí |
| Recuento inesperado (p. ej., en un cambio de hora) | Guarda y avisa | No: repetir devolvería lo mismo |
| Día completo | Guarda | — |

- Hasta 3 reintentos por tarea, separados 10 minutos.
- La auto-optimización de serverless está desactivada: añade reintentos sin número ni
  intervalo documentados, y cada uno sería una petición más a e·sios.
- Presupuesto: **2 peticiones al día** y, como mucho, 8 si fallan todos los intentos.
- Toda respuesta guardada es una observación con su hora: un reintento crea otro fichero y
  ninguno reemplaza a otro. La elección de la captura válida para cada día (la última
  completa anterior al corte) se hace después, por `available_at`.

## Despliegue

Con la CLI de Databricks y el perfil de cada máquina; el despliegue desde CI llegará en la
fase 1.

```bash
databricks bundle validate --strict -t prod
databricks bundle deploy -t prod
```

- El target `prod` solo se despliega desde `main` y deja el código en la carpeta del
  usuario que despliega.
- El target `dev` prefija el job con `[dev usuario]` y **pausa su programación**: sirve para
  probar con una ejecución manual (`databricks bundle run esios_snapshots -t dev`) sin
  dejar un job pidiendo a e·sios cada día. Después se borra con
  `databricks bundle destroy -t dev`, que no toca el Volume.
- Una ejecución manual hace peticiones reales a e·sios: úsese solo para verificar.
