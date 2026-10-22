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

La descripción de la UF se empareja con el nombre de un parque eólico de OpenStreetMap. La UF
es gallega si el parque está entre los de Galicia según Overpass, y de otra comunidad si está
en España fuera de ellos. La evidencia es el identificador del elemento de OpenStreetMap, su
nombre y la medida de parecido.

La normalización de los nombres, la medida de parecido, su umbral y el tratamiento de los
empates **se fijan cuando se conozca la forma de los nombres en la descarga de
OpenStreetMap, antes de cruzar ninguno con el listado**, y se añaden a esta sección.

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
- Una UF en la frontera de Galicia queda con la ubicación que le da Overpass: la regla no
  reparte un parque entre dos comunidades.
