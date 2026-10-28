# Mapeo de las unidades eólicas del listado

La serie gallega suma el P48 de las unidades de programación (UP) eólicas de Galicia. El P48
viene por UP, pero una UP puede reunir varias unidades físicas (UF), es decir, varios parques,
y estar en más de una comunidad. Este documento fija, **antes de cruzar ningún dato**, cómo se
ubica cada UF eólica del listado, cómo se deriva de ellas la clase de cada UP y qué se mide.
Los resultados se añadirán al final, sin cambiar las definiciones.

Las UP eólicas de fuera del listado siguen su propia regla
([unidades-fuera-del-listado.md](unidades-fuera-del-listado.md)), que usa como referencias
las UP de este mapeo.

## Principio

Todo se decide con los listados de unidades, con OpenStreetMap y con el P48 de cada unidad,
**sin cifras gallegas**: ni la producción eólica mensual de Galicia, ni el desglose
provincial de la producción medida, ni la potencia eólica instalada en Galicia. Son
referencias para validar la serie, y por eso no pueden influir en el mapeo antes de
congelarlo ([diseño](ventormenta-presentacion.md), sección 6.3).

## Unidades

Las UF que cuelgan de una UP de tipo «Eólica terrestre» o «Eólica marina» en los listados
capturados el 20 de octubre de 2026: **1.166 UF de 463 UP, con 32.072,4 MW**. El tipo se toma
de la UP. Las UP híbridas quedan fuera, porque su P48 no separa la parte eólica y el P48
eólico peninsular de Red Eléctrica (10010) tampoco las incluye.

| UF por UP | UP | MW |
|---|---|---|
| 1 | 366 | 10.130,1 |
| 2 a 5 | 73 | 5.275,0 |
| 6 a 20 | 14 | 3.740,5 |
| 21 o más | 10 | 12.926,8 |

## Clase de cada UF

Cada UF queda como **gallega**, **de otra comunidad** o **desconocida**, con la evidencia que
la decide anotada en la tabla del mapeo.

### Paso 1 · Nombre y OpenStreetMap

La descripción larga de la UF se compara con los nombres de los parques eólicos del extracto
de OpenStreetMap de España que publica Geofabrik: los elementos con `power=plant` y
`plant:source=wind`. Un parque es gallego si también está en el extracto de Galicia de la
misma fecha. La clase de la UF la decide la comunidad del parque, no qué parque es: dos
parques gallegos de nombre parecido (fases, ampliaciones) no cambian la clase; uno gallego y
otro de fuera, sí.

- **Nombres de cada lado:**
  - De la UF, solo la **descripción larga**. La corta es casi siempre un código de pocas
    letras, a menudo con el prefijo pegado («PEGALLE»), y como variante solo añadiría
    parecidos por azar.
  - De cada parque, **todas sus etiquetas de nombre**: `name`, `alt_name`, `official_name`,
    `old_name`, `short_name`, `loc_name`, `reg_name`, `nat_name`, `int_name` y
    `sorting_name`, con o sin sufijo (`name:gl`, `alt_name:es`…), con los valores partidos
    por «;», el separador de valores de OpenStreetMap.
  - Los elementos sin `plant:source` no entran, aunque su nombre lo sugiera.
- **Forma comparable**, la misma en los dos lados:
  1. Minúsculas, sin tildes (también «ñ» pasa a «n») y con los signos convertidos en
     espacios.
  2. Sin **palabras de tipo**: parque, parc, parke, eolico, eolica, eolic, eolikoa, eol, pe,
     p y uf. Están en casi todos los nombres de los dos lados («P.E.», «P. E.», «Parc
     Eòlic», «UF EOLICA»…) y harían parecerse a dos parques cualesquiera.
  3. Sin **palabras de unión**: de, del, d, la, las, el, los, lo, les, do, da, dos, das, o,
     os, a, as, y, e. Cambian entre las versiones de un mismo nombre en castellano, gallego
     o catalán («Sierra de los Lagos», «Serra dos Lagos»).
  4. Sin **numerales** (palabras solo de dígitos o solo de las letras i, v y x) ni
     **palabras de fase**: fase, ampliacion, repotenciacion, parte y extension. Distinguen
     fases de un mismo parque, que no cambian la clase.

  Las erratas no se corrigen («elico»): el nombre sigue siendo alcanzable por sus otras
  palabras. Un nombre cuya forma comparable queda vacía no tiene candidatos.
- **Parecido:** índice de Jaccard de los trigramas de caracteres de las dos formas
  comparables, con un espacio de relleno a cada lado, es decir, los trigramas que comparten
  sobre todos los que tienen entre los dos. Va de 0 a 1 y solo depende de los dos nombres:
  una descarga nueva de OpenStreetMap no cambia el parecido de los pares que siguen igual. El
  parecido de una UF y un parque, o de dos parques, es el máximo entre sus nombres.
- **Umbral `T`:** se calibra solo con OpenStreetMap, sin el listado. Para cada **parque
  gallego** con algún nombre de forma comparable no vacía se toma su mejor parecido con un
  parque del resto de España. `T` es el **percentil 95** de esos parecidos (con
  interpolación lineal entre los valores ordenados), el que alcanza por azar un parque
  gallego con otro que seguro que es distinto, justo en la confusión que cambia la clase de
  una UF gallega. Solo cuenta esa dirección: cada parque gallego busca su mejor parecido
  entre muchos más parques que uno de fuera entre los gallegos, así que, juntando las dos,
  los de fuera bajarían `T` y dejarían pasar por azar muchos más cruces en el lado que suma.
- **Candidatos:** los parques con un parecido de al menos `T`.
- **Clase (consenso de comunidad):** gallega si todos los candidatos son de Galicia, de otra
  comunidad si ninguno lo es y sin ubicar por el paso 1 si se mezclan o si no hay candidatos.
- **Evidencia:** el mejor candidato (identificador del elemento de OpenStreetMap, nombre y
  parecido) y el número de candidatos de Galicia y de fuera.

Los nombres, la forma comparable y las listas de palabras se fijaron **explorando cada lado
por separado** (los extractos del 25 de octubre de 2026 y el listado del 20 de octubre),
antes de cruzarlos. Con las palabras de tipo fuera, los prefijos frecuentes no obligan a
cambiar de medida. Si cambian la forma comparable o la medida, `T` se recalcula con la misma
regla.

La primera versión de la regla calibraba `T` con las dos direcciones juntas. Se cambió a la
de Galicia frente al resto **antes del cruce**, con datos solo de OpenStreetMap: con la
primera, 33 de los 168 parques gallegos con nombre tenían algún parque de fuera por encima de
`T`, casi siempre parques de una sola palabra genérica («El Monte», «La Peña»); con la
segunda, 14. Entre los nombres distintos de un mismo parque en OpenStreetMap, que son
coincidencias verdaderas, solo se dejan de reconocer dos que el listado no usa: una palabra de
tipo en alemán y una errata.

**Limitación de la medida:** un nombre corto con una o dos letras cambiadas («Acebo» y
«Acevo», «Soán» y «Xoán») no llega a `T` con ningún umbral razonable: en un nombre de cinco
letras, una letra cambiada rompe la mitad de sus trigramas.

Los parques eólicos sin nombre y las UF cuya descripción larga es solo un código («PICAL»,
«GRANADO») difícilmente se ubican por este paso: si son la única UF de su UP, pasan al
paso 2; si no, su UP queda desconocida.

### Paso 2 · Vecindad del P48

Solo para las UF que el paso 1 deja sin ubicar y que son la **única UF de su UP**, porque el
P48 de una UP con varias UF mezcla parques que pueden estar en sitios distintos.

- **Referencias:** las UP cuya clase sale entera del paso 1, como gallegas o de otra comunidad,
  con P48 en el mes. Las ubicadas por vecindad no son referencia de otras.
- **Parecido y regla:** los mismos que para las UP de fuera del listado. Se usa la
  correlación de Pearson del P48 horario. De las 5 referencias más correlacionadas, la UF es
  gallega si al menos 4 son gallegas, de otra comunidad si como mucho 1 lo es y desconocida
  en otro caso. También es desconocida si tiene P48 en menos de 7 días del mes.
- **Meses:** los tres de desarrollo, por separado. Si los meses en que se decide no
  coinciden, la UF queda desconocida.
- **Validación:** la regla se aplica a cada referencia de una sola UF, con las demás como
  vecinas, mes a mes. Se miden la precisión y la exhaustividad de «gallega» ponderadas por la
  potencia. Si alguna baja del 90 %, el paso 2 no se aplica y esas UF quedan desconocidas.

## Clase de cada UP

| Sus UF eólicas | Clase de la UP | En la serie gallega |
|---|---|---|
| Todas gallegas | Gallega | Suma |
| Todas de otra comunidad | De otra comunidad | No suma |
| Alguna gallega y alguna de otra comunidad | Mixta | No suma |
| Alguna desconocida | Desconocida | No suma |

Una UP con UF gallegas y desconocidas queda desconocida: no se puede descartar que las
desconocidas estén fuera de Galicia, y el P48 de la UP no las separa.

## Orden

1. **Primero, las UP de 6 o más UF** (24 UP, 16.667,3 MW). Son las que pueden salir
   mixtas, y su resultado dice pronto si la pista gallega es viable.
2. Después, el resto de UP, por el paso 1.
3. El paso 2, con su validación.
4. Las UP de fuera del listado (parte 2 de su regla), con las de este mapeo como
   referencias.

## Medidas (se publican con el resultado)

- Paso 1: valor de `T`, parques eólicos de OpenStreetMap sin nombre y con un homónimo al
  otro lado (misma forma comparable), y UF sin ubicar porque sus candidatos se mezclan o
  porque no tienen ninguno.
- UF y MW por clase y por evidencia: paso 1, paso 2 o ninguna.
- UP y MW por clase.
- **MW de UF gallegas en UP mixtas o desconocidas**, por tamaño de UP. Es la potencia gallega
  que el P48 no permite sumar: si es grande, la cobertura en potencia no llegará y habrá que
  decidir entre un cambio de diseño y el plan de respaldo.
- Validación del paso 2: precisión y exhaustividad con su intervalo.

## Muestra de referencia

Es la del diseño (sección 6.3): UF verificadas con evidencia que el mapeador no usa,
documentos públicos como las resoluciones del Diario Oficial de Galicia o las páginas de los
promotores, nunca OpenStreetMap ni el P48.

- **Estratos:** UF gallegas, de otra comunidad y desconocidas.
- **Sorteo fijado de antemano:** en cada estrato, las 20 UF con menor SHA-256 de
  `ventormenta-mapeo-v1:<código de UF>`. Es reproducible y no depende de quién sortea.
- **Medidas:** precisión y exhaustividad de «gallega» ponderadas por la potencia, con
  intervalo del 95 % por bootstrap sobre la muestra.

## Congelación

La tabla del mapeo (una fila por UF, con su clase, su evidencia y la clase de su UP) se
congela con su SHA-256 y un tag **antes** de calcular la cobertura en potencia o el contraste
con Red Eléctrica. Después solo cambia con evidencia externa anotada y como versión nueva.

## Qué no decide esta regla

- **El umbral de la cobertura en potencia**, que se fija antes de congelar el mapeo.
- **Si las UP mixtas suman de algún modo**, por ejemplo prorrateadas por potencia. Sería un
  cambio de diseño, que se plantearía con la medida de MW gallegos en UP mixtas.
- La ubicación de las UP de fuera del listado, que sigue su propia regla.
- Una UF en la frontera de Galicia queda con la ubicación que le da el extracto de Galicia:
  la regla no reparte un parque entre dos comunidades.

## Resultados

### Paso 1 · OpenStreetMap

Con los extractos de Geofabrik del 25 de octubre de 2026, solo con OpenStreetMap y antes de
cruzarlo con el listado.

- Parques eólicos: 177 en el extracto de Galicia y 887 en el resto de España. El extracto de
  España (1.064) contiene todos los de Galicia.
- Sin nombre útil, con la forma comparable vacía en todos sus nombres: 9 en Galicia y 48 en
  el resto.
- **`T` = 0,4444.**
- Homónimos, con la misma forma comparable a los dos lados: ninguno.
- Parques gallegos con nombre con algún parque del resto en `T` o más: 14 de 168.

### Frontera de Galicia

La pertenencia a Galicia se decide con el extracto de Galicia, que Geofabrik recorta con un
polígono algo más ancho que la comunidad. Esta medida dice cuánto se aparta ese recorte del
límite de Galicia en OpenStreetMap (relación 349036, `boundary=administrative`,
`admin_level=4`), contando solo elementos de OpenStreetMap, sin potencias ni parecidos con el
listado. No cambia la regla.

- **Puntos de un parque:** sus nodos miembro y los nodos de sus vías miembro, o los de su
  propia vía si el parque es una vía. Un punto sobre la línea del límite cuenta como dentro.
- **Clase:** dentro si lo están todos sus puntos, fuera si no lo está ninguno y cruza si unos
  sí y otros no.
- **Límite:** ensamblado desde el extracto de Galicia, es válido y tiene 594 polígonos, tierra
  firme e islas. Sigue la costa: no incluye el mar territorial.

| Parques eólicos | Dentro | Cruza | Fuera |
|---|---|---|---|
| Del extracto de Galicia (177) | 173 | 1 | 3 |
| Del resto de España (887) | 0 | 0 | 887 |

- Ningún parque de fuera del extracto tiene un punto dentro del límite: el extracto no deja
  fuera ningún parque gallego.
- Cabeço Alto, Mairos I y Mairos II están enteros fuera del límite, en el margen del recorte.
  Con la regla cuentan como gallegos. Se mantiene así: solo cambiarían la clase de una UF que
  se pareciera a uno de ellos por azar, y en la calibración de `T` pesan 3 de 168 parques.
- El Acebo cruza el límite (5 de sus 29 puntos están dentro) y es gallego por estar en el
  extracto, como cualquier parque de la frontera.
- Sin ubicar quedan 6 referencias de 5 parques, sin efecto en la tabla. En Cabeço Alto, 2
  nodos que no están ni en el extracto de España. En 4 parques del resto, una relación dentro
  de la relación del parque, que esta medida no resuelve; sus demás puntos están todos fuera.
