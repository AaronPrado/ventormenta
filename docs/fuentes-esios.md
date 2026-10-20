# Fuentes de datos · e·sios

Caracterización de los indicadores, los ficheros I90 y los listados de unidades de e·sios
(Red Eléctrica) que usa VenTormenta, con lo observado en peticiones reales: qué publica cada
fuente, cuándo, en qué forma y si cambia después. Las decisiones que dependen de esto están en
[el diseño](ventormenta-presentacion.md) (§5.1, §7.1–7.2 y §8.3).

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

## Ficheros I90 (archivo 34)

Programas por unidad de programación de cada día, de los que sale la serie gallega. Primera
caracterización, sobre un día por época.

### Método

- Notebook [`notebooks/exploracion/02_archivos_esios.py`](../notebooks/exploracion/02_archivos_esios.py):
  catálogo de archivos y fichas del I90 de tres días, sin descargar los ficheros.
- Job `i90_backfill` ([`notebooks/jobs/i90_backfill.py`](../notebooks/jobs/i90_backfill.py),
  con la lógica en `ventormenta.archives`): descarga de los I90 del 15 de enero de 2025, el
  11 de junio de 2025 y el 14 de enero de 2026, cada uno una sola vez.
- Notebook [`notebooks/exploracion/03_estructura_i90.py`](../notebooks/exploracion/03_estructura_i90.py):
  contenido de los tres ficheros, leído del Volume, y prueba del parser del P48
  (`ventormenta.i90`) sobre ellos.
- Todo el 19 de octubre de 2026: 10 peticiones a e·sios (el catálogo, 3 fichas de
  exploración y, por cada día descargado, su ficha y su fichero).

### Descarga

- **El catálogo `/archives` sin parámetros no incluye el I90**: devuelve 26 archivos (con
  `meta.size` 26 y sin paginación), todos con fecha del día de la petición. El id 34
  (`I90DIA`, «Información de detalle por Unidad de Programación») se pide directamente.
- **Dos pasos por fichero.** La ficha,
  `GET /archives/34?date_type=datos&date=AAAA-MM-DDT00:00:00&locale=es`, trae
  `archive_type: zip`, `horizon: D`, `publication_date` y la URL de descarga. Esa URL es una
  ruta relativa de la API con la fecha como último segundo del día **en UTC** y una `T`
  sobrante antes del desfase:
  `/archives/34/download?date=2025-01-15T23%3A59%3A59T%2B00%3A00&date_type=datos&locale=es`.
  La misma forma en los tres días.
- **Redirección.** La descarga de los dos días de 2025 respondió con una redirección a una
  URL prefirmada de Amazon S3 (`s3.eu-west-1.amazonaws.com`, carpeta `temp/`); la de 2026
  se sirvió directamente. La redirección se sigue sin el token de e·sios
  (`ventormenta.archives`).
- **Tamaño:** zips de 7,9 MB y 11,7 MB (XLS de 35 MB y 53 MB descomprimidos) y de 2,1 MB
  (CSV). Cada día tarda unos 40 segundos en el job, incluida la puesta en marcha.

### Contenido

| | 2025-01-15 y 2025-06-11 | 2026-01-14 |
|---|---|---|
| Contenedor | Un libro `I90DIA_AAAAMMDD.xls` con 40 hojas (`I90DIA00` a `I90DIA39`) | 43 ficheros `I90DIAnn_AAAAMMDD.csv` (`00` a `42`), uno por hoja |
| Codificación | Tipos nativos de Excel (números, fechas) | UTF-8 con BOM, separador `;`, coma decimal, fin de línea CRLF |
| Índice (hoja 00) | Fecha del informe, fecha de publicación y contenido del libro | Igual, con las fechas en texto (`14-enero-2026`) |

- **La numeración de las hojas cambia entre épocas** (por ejemplo, la 26 es el PBF en el
  XLS y el PDBF en el CSV; la 04 está reservada en el XLS). El P48 es la **hoja 02,
  «Resultado de la programación del P48», en las dos**.
- Ninguna hoja agrega por provincia o zona, según sus títulos. Solo la 16
  («Indisponibilidades en Unidades Físicas») menciona unidades físicas.
- Candidatas para identificar redespachos, sin revisar: la 03 (restricciones técnicas del
  PDBF o del mercado diario) y la 08 (restricciones en tiempo real).

#### Hoja del P48

- Tres filas de cabecera (`Indicadores` → `Programa (MWh)`, `Dia` → fecha del informe,
  `Programa` → `P48`) y la fila de columnas: `Unidad de Programación`, `Tipo Oferta`,
  `Cuarto de Hora del dia`, `Total` y los cuartos de hora `1` a `96`.
- **Una fila por unidad de programación**, no por unidad física: 2.330, 2.516 y 2.713
  unidades en las tres fechas. Ninguna repetida.
- **Cuartohoraria en las tres fechas**, también en enero de 2025: el paso del mercado a
  cuartos de hora en octubre de 2025 no cambió la resolución del P48 en el I90; lo que
  cambia entre épocas es el contenedor.
- Energía en **MWh por cuarto de hora** (0,025 MWh en un cuarto equivalen a 0,1 MW).
  `Total` es la suma de los 96 cuartos en todas las filas, al milésimo.
- `Tipo Oferta` es un código numérico, uno por unidad: el 10 reúne más de la mitad de las
  unidades (1.554, 1.719 y 1.886), seguido del 8 (365–399) y el 2 (144–147). El 17 solo
  aparece en 2026. Su significado no figura en el fichero.
- El parser propio (`ventormenta.i90`) lee las tres fechas con las mismas comprobaciones:
  día del informe, número de cuartos según la duración real del día, unidades únicas y
  `Total` igual a la suma. `python-esios` lee el I90 en XLS (`I90Book`), pero no tiene
  lector para la época CSV.

### Fecha de publicación

| Día de los datos | `publication_date` de la ficha | Retraso |
|---|---|---|
| 2025-01-15 | 2025-12-29 | 348 días |
| 2025-06-11 | 2026-01-22 | 225 días |
| 2026-01-14 | 2026-06-11 | 148 días |
| 2026-07-15 | 2026-10-19 (el día de la petición) | 96 días |

- La fecha de la ficha coincide con la «Fecha de publicación» de la hoja 00 y con la fecha
  interna de los ficheros del zip. La del 15 de enero de 2025 era la misma en las dos fichas
  pedidas, con unas horas de diferencia.
- El título de la hoja 00 dice «Información a los tres meses (90 días)», pero el fichero que
  se sirve se generó entre 96 y 348 días después del día de los datos. Hay dos lecturas, sin
  resolver: que la fecha sea la de la **última regeneración** del fichero (la primera
  publicación habría sido hacia los 90 días y el fichero se rehace después), o que la
  publicación sea **más tardía** de lo que dice el título.
- Cada descarga guarda la ficha literal y la hora de recepción en el JSON lateral del zip,
  así que la evidencia queda junto a cada fichero.

### Implicaciones

- **La disponibilidad de la etiqueta gallega no puede darse por «D+90».** Si los ficheros
  se regeneran, lo descargado hoy de días antiguos es la última versión, no la que existía a
  los 90 días; si se publican más tarde, la latencia es mayor. Afecta a la clase de
  disponibilidad y al vintage de los I90 (honestidad temporal, en el diseño) y a la latencia
  del replay.
- **El parser es propio y lee las dos épocas**, en lugar de `python-esios`, que el diseño
  preveía para el parseo:
  la hoja del P48 tiene la misma forma en las dos, así que un solo camino de lectura sirve
  para ambas.
- **Del P48 por unidad de programación a la potencia por unidad física** hacen falta los
  listados de unidades, para el mapeo y la cobertura en potencia.

### Pendiente de observar

- La ficha del 15 de julio de 2026 de nuevo, una o dos semanas después de la primera: si su
  `publication_date` cambia, es una fecha de regeneración.
- Si el P48 de un día cambia entre regeneraciones.
- Desde cuándo llegan los I90 en CSV, y si los días antiguos pasan a CSV al regenerarse.
- Días de cambio de hora: si la hoja del P48 trae 92 o 100 cuartos.
- Celdas vacías en la hoja del P48 (el parser las lee como 0 MWh).
- El significado oficial de los códigos de `Tipo Oferta` (la lectura inferida de los
  listados de unidades está en la sección siguiente).

## Listados de unidades (archivos 81 y 82)

Identificación, tipo de producción y potencia de las unidades de programación (UP) y de las
unidades físicas (UF), para filtrar las UP eólicas del P48 y ponderar por MW. Primera
caracterización, sobre una sola captura.

### Método

- Notebook [`notebooks/exploracion/04_listados_unidades.py`](../notebooks/exploracion/04_listados_unidades.py):
  fichas y descarga de los dos listados, una vez cada uno, y caracterización leída del
  Volume, cruzada con el P48 de los tres I90 descargados (2025-01-15, 2025-06-11 y
  2026-01-14).
- Localización sin peticiones a ciegas: el catálogo `/archives` ya guardado no los incluye
  (sus 26 archivos son subastas, descargos, planes de mantenimiento, liquidaciones y totales
  del P48). Las páginas públicas [Unidades de programación](https://www.esios.ree.es/es/unidades-de-programacion)
  y [Unidades físicas](https://www.esios.ree.es/es/unidades-fisicas) de e·sios cargan sus
  tablas de `/archives/82/download_json?locale=es` y `/archives/81/download_json`.
- Todo el 20 de octubre de 2026: 5 peticiones a e·sios (las 2 fichas, 1 descarga fallida con
  la URL de la ficha y los 2 listados).

### Descarga

- **Fichas** (`GET /archives/{81,82}?locale=es`): `archive_type: json`, `horizon: NA`, sin
  `date_type`, `date_times` ni `publication_date`. Su `updated_at` (2015) es de la
  definición del archivo, no de los datos.
- **La URL de descarga de la ficha no funciona.** Trae
  `/archives/82/json_download_json?date=2026-10-20T23%3A59%3A59T%2B0200&locale=es` (fecha
  del día de la petición, en hora peninsular y con la `T` sobrante del I90), y responde
  **404**. Se usan las URL de la web, sin fecha.
- **Sin versiones por fecha:** nada en la ficha ni en la web indica que se pueda pedir el
  listado de un día pasado. Cada descarga es la foto del momento, y su vintage es la hora de
  recepción (disponibilidad observada).
- Respuestas JSON de 1,4 MB (UP) y 1,7 MB (UF), servidas directamente, sin redirección.

### Contenido

| | UP (archivo 82) | UF (archivo 81) |
|---|---|---|
| Registros | 3.931, bajo la clave `UnidadesProgramacion` | 6.673, bajo `UnidadesFisicas` |
| Campos | Código de UP, descripciones corta y larga, código EIC, tipo de producción, negocio (compra o venta), ámbito de actuación, zona de regulación, tipo de UP, sujeto del mercado, potencia máxima MW | Código de UF, código EIC, descripciones corta y larga, tipo de producción, vinculación con sujeto del mercado, vinculación con UP, potencia máxima MW |
| Forma | Un registro por código, sin repetidos; los mismos campos en todos; todo texto | Igual |

- **La potencia es texto con coma decimal y punto de miles** («3,8», «9.999,0»). Se lee con
  un formato estricto, que rechaza un punto sin coma por ambiguo (como en el P48): ningún
  valor de los dos listados se sale de él, y ninguno está vacío.
- «Ámbito de actuación» no sale en la tabla de la web: España (3.844 UP) y las
  interconexiones con Francia, Portugal, Marruecos y Andorra.
- **El tipo de producción se toma de la UP.** El de las UF es menos fiable: 3 UF tienen el
  tipo `'0'`, los nombres no coinciden con los de las UP («Ciclo combinado» frente a «Ciclo
  Combinado») e importación y exportación de Marruecos y Andorra aparecen intercambiadas
  entre los dos listados.

### UP eólicas y relación UP → UF

- **«Eólica terrestre»: 462 UP con 32.070,4 MW. «Eólica marina»: 1 UP de 2 MW.** Hay además
  tres tipos híbridos (38 UP en total), que no son eólicos en conjunto.
- **Cada UF apunta exactamente a una UP del listado**: ninguna sin UP ni con una UP que no
  esté en él.
- **En todas las UP eólicas e híbridas, la potencia de la UP es la suma de la de sus UF**
  (al décimo de MW).
- **Las UP eólicas tienen de 1 a 181 UF:** 365 de las 462 tienen una sola; el resto se
  reparte hasta una UP de 181 UF. Una UP con muchas UF puede reunir parques de varias
  comunidades.
- **Las UF eólicas suman 32.232,5 MW, 162,1 MW más que las UP eólicas:** son 4 UF eólicas
  dentro de UP híbridas (2 en «Híbrida renovable», 80,3 MW; 2 en «Híbrida renovable-
  almacenamiento», 81,8 MW). No hay UF de otros tipos dentro de UP eólicas.

### Cobertura de las UP del P48

Qué parte de las UP de cada P48 aparece en la captura del 20 de octubre de 2026, por número y
por energía (suma de |MWh| del día):

| Día | UP del P48 en el listado | Energía cubierta | UP eólicas encontradas |
|---|---|---|---|
| 2025-01-15 | 2.048 de 2.330 | 97,20 % | 288 |
| 2025-06-11 | 2.272 de 2.516 | 97,81 % | 304 |
| 2026-01-14 | 2.571 de 2.713 | 99,00 % | 356 |

- Las que faltan son sobre todo unidades de venta de generación (`Tipo Oferta` 10: 234, 206
  y 116), y faltan más cuanto más antiguo es el día: bajas y cambios de unidad desde
  entonces. Es el coste de usar la foto actual para días pasados.
- **No se sabe cuántas de las que faltan son eólicas**: sin el listado no hay tipo de
  producción, y el `Tipo Oferta` no basta (hay eólicas con el 10 y con el 2).

### `Tipo Oferta` del P48 (lectura inferida)

Cruzando el código de cada UP del P48 con su negocio y su tipo de UP en el listado, en los
tres días, y, para las de generación, con su tipo de producción en el P48 del 2026-01-14 (de
ahí los recuentos de eólicas). No es una definición oficial.

| Código | Unidades | Código | Unidades |
|---|---|---|---|
| 1 | Venta · generación convencional (ciclo combinado, gas natural, hidráulica UGH, nuclear, turbinación de bombeo, carbón) | 9 | Comercializador internacional |
| 2 | Venta · renovables, cogeneración y residuos (4 UP eólicas) | 10 | Venta · renovables, cogeneración y residuos (352 UP eólicas) y, en algún caso, unidades híbridas |
| 3 | Compra · consumo de bombeo | 11 | Compra · servicios auxiliares |
| 5 | Unidad instrumental internacional | 14 | Saldo de acoplamiento de mercado |
| 6 | Compra · comercializador de referencia | 15 | Compra · enlace con Baleares |
| 7 | Compra · consumo directo en mercado | 17 | Almacenamiento (solo en 2026) |
| 8 | Compra · comercializadores | 18 | Venta · unidades híbridas |

### Implicaciones

- **Filtro eólico:** las UP de tipo «Eólica terrestre» o «Eólica marina», más las UP
  híbridas con alguna UF eólica, contando solo la potencia de esas UF.
- **Ponderación por MW:** la potencia de la UP vale para las UP eólicas; en las híbridas, la
  de sus UF eólicas.
- **El mapeo tendrá que bajar a UF en las UP con varias UF**, que pueden ser mixtas entre
  comunidades.
- **El listado es una foto, no un historial.** Para los meses de 2025 faltan unidades que ya
  no existen. La capa de cobertura en potencia lo medirá; repetir la captura de forma
  periódica construiría el historial que la fuente no da.

### Pendiente de observar

- Si el listado incluye unidades fuera de la península (el ámbito «España» no lo distingue).
- La diferencia entre los `Tipo Oferta` 2 y 10.
- Si la `date` de `json_download_json` o de `download_json` da versiones pasadas: no se ha
  probado, porque sería una petición a ciegas.
