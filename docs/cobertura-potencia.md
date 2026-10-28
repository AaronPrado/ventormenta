# Cobertura en potencia de la serie gallega

La serie gallega solo suma las unidades de programación (UP) que el mapeo clasifica como
gallegas. La capa de cobertura en potencia del [diseño](ventormenta-presentacion.md)
(sección 6.4) mide qué parte de la potencia eólica de Galicia queda dentro de esa suma, cada
día, y el criterio para continuar (sección 6.6) exige que esté por encima de un umbral.

Este documento fija **la definición de la cobertura y su umbral antes de mapear ninguna UP**,
para que ni el mapeo ni ninguna cifra gallega influyan en el valor. Los resultados se añadirán
al final, sin cambiar las definiciones.

## Principio

El umbral se deduce de la tolerancia mensual
([tolerancia-mensual.md](tolerancia-mensual.md)) y de medidas peninsulares, sin la potencia
eólica instalada en Galicia, sin la producción gallega y sin el mapeo. El indicador de
potencia gallega solo entra al medir la cobertura, con el mapeo ya congelado.

## Por qué el umbral depende de la tolerancia

La serie no se escala: se contrasta con la producción gallega de Red Eléctrica tal como sale
de la suma (sección 6.6 del diseño). Si los parques que no suman producen, en proporción a su
potencia, como los que suman, la serie queda por debajo de la producción real en
`1 − cobertura`, y esa diferencia se añade a la del propio método en el contraste mensual.

La tolerancia ya reparte su margen: el método (programa frente a medida, con todas las UP
eólicas) consume una parte y el resto queda para el mapeo. Un umbral que dejara más hueco de
cobertura que ese resto no decidiría nada, porque el contraste mensual lo rechazaría igual.

## Datos

| Término | Definición | Fuente |
|---|---|---|
| Potencia gallega (`G_D`) | Valor del día `D` para Galicia, en MW | Indicador 1485 de e·sios («Potencia instalada de generación eólica»), con el valor publicado al medir |
| Potencia de una UF del listado | Potencia de la unidad física, en MW | Listado de unidades físicas (archivo 81) capturado el 20 de octubre de 2026 |
| Potencia de una UP de fuera del listado | Máximo, en el mes de `D`, de la potencia media de su P48 en un cuarto de hora (energía del cuarto × 4), en MW | I90 (archivo 34, hoja del P48) de cada día del mes |
| UP operativa el día `D` | UP con P48 distinto de cero en algún cuarto de hora de `D` o de los 6 días anteriores | I90 de esos días |
| Potencia mapeada operativa (`C_D`) | Suma de la potencia de las UF de las UP **gallegas** operativas el día `D`, más la de las UP de fuera del listado ubicadas como gallegas y operativas ese día | Tabla del mapeo congelada y las tres fuentes anteriores |

- **Solo las UP que suman.** Las UF gallegas de UP mixtas o desconocidas no cuentan: la capa
  mide la serie que se contrasta, no lo que se ha identificado.
- **Las UP de fuera del listado cuentan con una cota inferior.** No tienen potencia
  publicada; la máxima potencia programada en el mes no llega a la instalada, así que su
  aportación queda por debajo de la real y la cobertura, del lado prudente.
- **Operativa por la UP, con una semana de margen.** El P48 viene por UP, así que una UP
  operativa cuenta con todas sus UF. La ventana de 7 días evita que un día de calma, con el
  programa a cero, cuente como parada. Una UP del listado actual que aún no existía en el día
  medido no tiene P48 y no cuenta.
- **Las UP híbridas no cuentan**, como en la serie: su P48 no separa la parte eólica.

## Regla

Para cada día `D`:

```
cobertura_D = C_D / G_D
```

El umbral sale de la tolerancia publicada y de la mayor diferencia mensual entre el P48
eólico peninsular de Red Eléctrica (indicador 10010) y la producción medida peninsular, en
valor absoluto, en los tres meses de desarrollo:

```
umbral = 100 % − ( tolerancia − máx |d con el 10010| )
```

- **Con el 10010**, no con las UP del listado: así mide el método con todas las UP eólicas,
  que es como se construye la serie con las de fuera del listado ya ubicadas.
- **El valor absoluto del peor mes**, como en la tolerancia: el umbral debe valer también en
  el mes en que el método deja menos margen.
- Con los valores publicados (tolerancia 5,00 %; `d` con el 10010 de +0,37 %, −2,26 % y
  +3,10 %): **umbral = 100 − (5,00 − 3,10) = 98,10 %.**
- Si la tolerancia o las diferencias se recalculan con su propia regla, el umbral se
  recalcula con esta fórmula, antes de medir la cobertura.
- La cobertura se compara sin redondear con el umbral publicado, con dos decimales.

## Uso

- **Criterio para continuar:** la cobertura está en el umbral o por encima **todos los días**
  de los tres meses de desarrollo. Basta un día por debajo para que no se cumpla.
- **En el pipeline:** el mismo umbral es la expectation diaria de la capa de cobertura; un día
  por debajo va a cuarentena.

## Medidas de apoyo (no entran en la regla)

Se publican junto al resultado para interpretarlo:

- Cobertura mínima, mediana y máxima de cada mes, y días por debajo del umbral.
- Cobertura sumando también las UF gallegas de UP mixtas o desconocidas: la potencia gallega
  identificada que el P48 no deja sumar.
- Cobertura con las UP de fuera del listado a 0 MW.
- Valor del indicador 2273 de e·sios («Potencia instalada de generación eólica hibridada») de
  Galicia, junto a `G_D`.

## Qué no decide esta regla

- **Escalar la serie por la cobertura.** Permitiría un umbral más bajo, pero la serie pasaría
  a extrapolar los parques que no suman. Sería un cambio de diseño y no se adopta.
- **La hora a la que se toma `G_D` en el pipeline** (su disponibilidad y su vintage), que se
  decide al construir esa capa.

## Resultado

Pendiente: se medirá con el mapeo congelado.
