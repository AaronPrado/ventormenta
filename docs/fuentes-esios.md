# Fuentes de datos · e·sios

Caracterización de los indicadores de e·sios (Red Eléctrica) que usa VenTormenta, con
lo observado en peticiones reales: qué publica cada indicador, cuándo y si cambia
después. Las decisiones que dependen de esto están en [el diseño](ventormenta-presentacion.md)
(§5.1, §7.1–7.2 y §8.3).

## Indicadores de previsión eólica 541 y 1777

### Método

- Notebook [`notebooks/exploracion/01_indicadores_esios.py`](../notebooks/exploracion/01_indicadores_esios.py),
  ejecutado en Databricks serverless.
- Cada ejecución hace una petición a `/indicators/{id}` por indicador, para ayer, hoy y
  mañana en hora peninsular y sin `time_trunc`. Imprime los metadatos del indicador y,
  por día, el número de valores, la primera y la última marca horaria y una huella
  SHA-256 de los valores. Comparar huellas entre capturas muestra si un día cambia sin
  sacar los valores crudos de Databricks.
- Capturas: sábado 10 de octubre de 2026 a las 13:44 y, del domingo 11 al martes 13,
  a las 09:40, 10:40 y 11:40 (job programado). En total, 10 ejecuciones y 20 peticiones.
- Todas las horas son peninsulares (CEST, UTC+2). No hubo cambio de hora en el periodo.

### Resultados

| | 541 | 1777 |
|---|---|---|
| Nombre oficial (`name`) | Previsión de la producción eólica peninsular | Previsión diaria D+1 eólica |
| Descripción (`description`) | Vacía en la API | Vacía en la API |
| Ámbito | Península (`geo_id` 8741) | Península (`geo_id` 8741) |
| Granularidad | 15 minutos (96 valores al día) | Horaria (24 valores al día) |
| Magnitud | Potencia (MW) | Energía (MWh) |
| Publicación del D+1 | Ya completo a las 09:40 de D-1 | Hacia las 10:50–10:51 de D-1 |
| Actualizaciones | Cada hora, hacia el minuto 39 | Una al día |
| ¿Cambian los valores ya publicados? | Sí, en cada actualización mientras el día es hoy o mañana | No en lo observado |

Para compararlos, la energía de una hora (MWh) equivale a la media en MW de sus cuatro
cuartos de hora.

#### 1777 · Previsión diaria D+1 eólica

| D-1 | D+1 a las 09:40 | a las 10:40 | a las 11:40 | `values_updated_at` |
|---|---|---|---|---|
| Sáb 10 | sin captura | sin captura | sin captura (sí estaba a las 13:44) | 10:51:14 |
| Dom 11 | No | No | Sí | 10:50:46 |
| Lun 12 | No | No | Sí | 10:50:52 |
| Mar 13 | No | No | Sí | 10:50:22 |

- El D+1 aparece cada día entre las 10:40 y las 11:40, y `values_updated_at` lo sitúa
  hacia las 10:50–10:51: algo más de una hora antes del corte de las 12:00. Igual en fin
  de semana que en laborable.
- `values_updated_at` solo cambia una vez al día.
- Ningún día cambió de huella después de publicarse. Los días 11 y 12 se siguieron
  unas 49 horas (7 capturas cada uno) y el 13, unas 25 horas (4 capturas). Más allá de
  ese plazo no se observó.

#### 541 · Previsión de la producción eólica peninsular

- El D+1 está completo (96 valores) desde la primera captura del día, a las 09:40 de
  D-1. No se pidió nada más allá del D+1.
- `values_updated_at` avanza cada hora entre el minuto 39 y el 43 (08:39, 09:39–09:43,
  10:39 y, el sábado, 13:39). En las capturas de las hh:40 nunca aparecía todavía la
  actualización de las hh:39; en la del sábado a las 13:44 sí estaba la de las 13:39.
- La cadencia no está garantizada: el martes 13 faltó la actualización de las 10:39
  (a las 11:40 seguía la de las 09:39, con las mismas huellas que a las 10:40).
- Cada actualización cambia las huellas de hoy y de mañana. La huella es por día, así
  que no distingue si cambian solo los cuartos de hora futuros o también los pasados.
- Un día ya pasado conserva la misma huella durante la mañana siguiente (días 10, 11 y
  12), distinta de la última vista mientras era «hoy»: siguió actualizándose después.

### Implicaciones

- **La versión del 541 vigente en el corte solo existe si se captura.** La API devuelve
  únicamente la última versión, así que la comparación con Red Eléctrica solo puede
  hacerse con instantáneas propias (diseño §7.2).
- **Ventana de la instantánea diaria:** después de la publicación del 1777 (hacia las
  10:51 de D-1) y antes del corte de las 12:00. Cuanto más tarde dentro de esa ventana,
  más reciente es la versión del 541 y menos margen queda para reintentar si algo falla.
- **Disponibilidad:** las instantáneas son de clase *observada*: su `available_at` es la
  hora de captura, no la de publicación (diseño §7.1).
- **Sin cambio de diseño por la estabilidad del 1777.** Que no cambie tras publicarse
  invitaría a reconstruir su histórico desde la API con disponibilidad inferida por
  regla. No se hace: cuatro publicaciones seguidas unas 49 horas no prueban que nunca se
  revise, comprobarlo exigiría reconsultar datos ya descargados (algo que el uso
  responsable de e·sios limita, §8.3) y la previsión de Red Eléctrica es solo una
  referencia informativa (§10.1 y §10.5).

### Pendiente de observar

- Días de cambio de hora (el próximo, el 25 de octubre de 2026): número de valores y
  marcas horarias de ambos indicadores.
- Revisiones del 1777 más allá de unas 49 horas.
- Horizonte del 541 más allá del D+1.

### Detalles de la respuesta de la API

- `start_date` y `end_date` en ISO 8601 con desfase horario delimitan el rango en hora
  peninsular.
- Sin `time_trunc`, la API devuelve la granularidad nativa del indicador.
- `values_updated_at` es del indicador entero, no de cada día, y va en hora peninsular
  con desfase.
- Cada valor trae, al menos, `datetime_utc`, `geo_id` y `value`.
- `description` llega vacía en estos dos indicadores; se toma `name` como descripción
  oficial.
