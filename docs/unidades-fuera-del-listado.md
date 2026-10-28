# Unidades eólicas fuera del listado

La serie gallega suma el P48 de las unidades de programación (UP) eólicas de Galicia, y qué
UP son eólicas lo dice el listado de unidades de e·sios, que es la foto del día en que se
descarga. En los tres meses de desarrollo, el P48 de las UP eólicas del listado se queda corto
frente al P48 eólico peninsular que publica Red Eléctrica (indicador 10010): le falta el
9,88 %, el 7,88 % y el 5,91 % ([tolerancia-mensual.md](tolerancia-mensual.md)). Con ese
hueco, el método no cabe en su propia tolerancia en los dos meses de 2025, y la serie gallega
perdería las UP que estaban activas entonces y ya no están en el listado.

Este documento fija, **antes de medir**, cómo se decide qué UP de fuera del listado son
eólicas, cómo se ubican y cuándo entran en el mapeo. Los resultados se añadirán al final, sin
cambiar las definiciones.

## Principio

Todo se decide con datos peninsulares o de cada unidad, **sin cifras gallegas**: ni la
producción eólica mensual de Galicia, ni el desglose provincial de la producción medida, ni
la potencia eólica instalada en Galicia. Son referencias para validar la serie, y por eso no
pueden influir en el mapeo antes de congelarlo.

## Meses y datos

Los meses de la tolerancia (enero de 2025, junio de 2025 y enero de 2026), cortados en hora
peninsular. No hace falta ninguna petición nueva:

| Dato | Fuente |
|---|---|
| P48 por UP y cuarto de hora, `p_u(t)` | I90 de cada día de los tres meses |
| Tipo de producción y potencia de las UP | Listado de unidades de programación capturado el 20 de octubre de 2026 |
| P48 eólico peninsular por cuarto de hora, `E(t)` | Indicador 10010, descargado el 21 de octubre de 2026 |

## Parte 1 · Qué UP de fuera del listado son eólicas

El 10010 suma el P48 de las UP eólicas según la clasificación de Red Eléctrica. Si el hueco
son UP eólicas que ya no están en el listado, el residuo de cada cuarto de hora tiene que ser
la suma del P48 de esas UP; un perfil solar, de cogeneración o de consumo, con otra forma, no
encaja.

- `P(t)`: P48 de las UP de tipo «Eólica terrestre» o «Eólica marina» del listado (la `P` de
  la tolerancia).
- **Candidatas:** las UP del P48 del mes que no están en el listado, y las UP de tipo híbrido
  del listado, por si el 10010 las incluye.
- **Pesos:** por mes, un `x_u` entre 0 y 1 por candidata, por mínimos cuadrados sobre todos
  los cuartos de hora del mes.
- Una candidata es **eólica según el 10010** si `x_u ≥ 0,5`.
- **Cierre (`Q`):** lo que queda sin explicar, cuarto a cuarto, con las eólicas redondeadas a
  peso 1 y las demás a 0, sobre el P48 eólico del mes.

```
R(t) = E(t) − P(t)
R(t) ≈ Σ_u x_u · p_u(t),     0 ≤ x_u ≤ 1
Q    = Σ_t |R(t) − Σ_{u eólica} p_u(t)| / Σ_t E(t)
```

**Condición 1:** `Q ≤ 1 %` en los tres meses. Si se cumple, el hueco son UP eólicas de fuera
del listado y se pasa a la parte 2. Si no, el mapeo se hace solo con las UP del listado y la
causa del hueco se investiga aparte.

El umbral es un orden de magnitud menor que el hueco y deja margen a diferencias de versión
entre el P48 de los I90 y el del 10010.

## Parte 2 · Dónde están

Una UP de fuera del listado no tiene descripción ni unidades físicas, así que su ubicación
sale de su propio P48: el de parques cercanos se mueve a la par, porque los mueve el mismo
viento. Cada UP eólica según el 10010 se ubica por sus **vecinas**: las UP del listado ya
mapeadas cuyo P48 se le parece más.

Se hace **después de mapear las UP del listado y antes de congelar el mapeo**, porque las
vecinas necesitan su ubicación.

- **Referencias:** UP eólicas del listado mapeadas como gallegas o de otra comunidad (no las
  mixtas ni las desconocidas), con P48 en el mes.
- **Parecido:** correlación de Pearson del P48 horario (la suma de sus cuatro cuartos), en las
  horas del mes en que las dos UP tienen P48.
- **Regla:** de las 5 referencias más correlacionadas, la UP es **gallega** si al menos 4 son
  gallegas, **de otra comunidad** si como mucho 1 lo es y **desconocida** en otro caso. También
  es desconocida si tiene P48 en menos de 7 días del mes.
- **Validación:** la misma regla aplicada a cada referencia, con las demás como vecinas, mes a
  mes. Se miden la precisión y la exhaustividad de «gallega» ponderadas por la potencia del
  listado, con intervalo del 95 % por bootstrap sobre las referencias.
- **Sin ubicar (`U`):** el P48 eólico de fuera del listado que no queda ubicado (ni en Galicia
  ni en otra comunidad), sobre el P48 eólico del mes. Incluye lo que el cierre no explica.

```
U = (Σ_t R(t) − Σ_t Σ_{u ubicada} p_u(t)) / Σ_t E(t)
```

**Condición 2:** en los tres meses, precisión y exhaustividad de al menos el 90 % (estimación
puntual) y `U ≤ 1,90 puntos`. Si se cumple, las UP ubicadas entran en el mapeo con la
vecindad como evidencia. Si no, todas las de fuera del listado quedan como desconocidas y no
suman en la serie gallega.

- **1,90 puntos** es lo que la tolerancia (5,00 %) deja al mapeo en el peor mes aunque estén
  todas las UP eólicas: con el 10010, programa y medida difieren hasta un 3,10 % (enero de
  2026). Lo que quede sin ubicar resta energía a la serie gallega si Galicia pierde la misma
  parte que la península, algo que no se puede comprobar antes del contraste.
- **El 90 % basta** porque la vecindad solo decide lo de fuera del listado, como mucho un 9,9 %
  del P48 eólico: un 10 % de error sobre esa parte mueve la serie alrededor de un punto.

## Qué no deciden estas condiciones

- Son **necesarias, no suficientes**. La pista gallega sigue dependiendo del criterio para
  continuar del [diseño](ventormenta-presentacion.md): cobertura en potencia por encima del
  umbral y los tres meses dentro de la tolerancia.
- **La tolerancia se recalcula con la misma regla** si las UP de fuera del listado entran en
  el mapeo, porque mide el método tal como se aplica.
- **La vecindad ubica, no identifica:** no dice qué UP actual sucede a la que falta ni con qué
  potencia. En la cobertura en potencia cuentan con una cota inferior de la suya
  ([cobertura-potencia.md](cobertura-potencia.md)).
- Una UP de fuera del listado que reunía parques de varias comunidades queda en la que domina
  su P48: la regla no detecta las mixtas.

## Medidas de apoyo (no entran en las condiciones)

- Número de candidatas y de eólicas según el 10010, y reparto de los pesos (por debajo de 0,1,
  entre 0,1 y 0,9 y por encima de 0,9), con su energía.
- Eólicas según el 10010 por `Tipo Oferta`.
- Pesos de las UP híbridas del listado: si el 10010 las incluye.
- UP presentes en varios meses con distinta clasificación.
- En qué meses tiene P48 cada eólica de fuera del listado.
- P48 de fuera del listado ubicado en Galicia, en otra comunidad y sin ubicar.

## Resultado de la parte 1

Medido el 22 de octubre de 2026 con los 92 I90 de los tres meses, el listado de unidades de
programación del 20 de octubre de 2026 y el indicador 10010 descargado el 21 de octubre de
2026. Los pesos se ajustaron con `scipy.optimize.lsq_linear` (método `bvls`, SciPy 1.16.3),
que convergió en los tres meses.

| Mes | Candidatas | Eólicas según el 10010 | Residuo `R` | `Q` |
|---|---|---|---|---|
| Enero de 2025 | 305 | 67 | 743,1 GWh | 0,00 % |
| Junio de 2025 | 270 | 60 | 236,9 GWh | 0,00 % |
| Enero de 2026 | 175 | 39 | 499,9 GWh | 0,00 % |

**Se cumple la condición 1.** El cierre es exacto: lo que queda sin explicar es del orden de
10⁻¹⁷ del P48 eólico del mes, el error de redondeo de la coma flotante. El hueco del listado
es, cuarto a cuarto, el P48 de UP eólicas que ya no están en él. Como control, sin ninguna
eólica `Q` vale el hueco entero: 9,88 %, 7,88 % y 5,91 %.

### Medidas de apoyo

- **Pesos:** ninguna candidata queda entre 0,1 y 0,9. Por debajo de 0,1 quedan 238, 210 y 136
  UP, con 615,6, 710,2 y 165,5 GWh. Ninguna candidata tiene P48 nulo en todo el mes, así que
  ninguna quedó fuera del ajuste por ese motivo.
- **`Tipo Oferta`:** todas las eólicas según el 10010 tienen el 10, salvo una con el 2 en
  cada mes de 2025.
- **Híbridas:** 21 de las 38 UP híbridas del listado tienen P48 en alguno de los meses, y
  todas tienen peso 0 en todos ellos: el 10010 no incluye las híbridas.
- **Clasificación estable:** ninguna UP cambia de clasificación de un mes a otro.
- **75 UP eólicas distintas de fuera del listado:** 30 tienen P48 en los tres meses, 25 en
  los dos de 2025, 11 solo en enero de 2025, 5 en junio de 2025 y enero de 2026, 3 solo en
  enero de 2026 y 1 en enero de 2025 y enero de 2026.
