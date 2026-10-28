# Pista gallega con la producción medida

La pista gallega iba a sumar el P48 de las unidades de programación (UP) gallegas, y el
criterio para continuar del [diseño](ventormenta-presentacion.md) (sección 6.6) exigía una
cobertura en potencia por encima de su umbral. Con la versión 1 del mapeo, ya congelada, la
cobertura queda acotada por debajo de ese umbral.

Este documento fija, **antes de abrir ninguna cifra gallega**, la vía que la sustituye: la
producción eólica medida de las provincias gallegas como etiqueta, su criterio para continuar,
qué se publica de la versión 1 y qué se abandona. Los resultados se añadirán al final, sin
cambiar las definiciones.

## Por qué cambia

- **El P48 no deja sumar la potencia gallega de las agregadoras.** En la versión 1, ninguna de
  las 24 UP de 6 o más unidades físicas (UF) suma en la serie gallega, y 2.027,3 MW de UF
  gallegas quedan en UP mixtas o desconocidas. Con eso, la cobertura no llega en ningún día al
  93,7 %, frente a un umbral del 98,10 %, salvo que más del 70 % de esa potencia fueran falsos
  positivos ([mapeo-listado.md](mapeo-listado.md), «Agregadoras · paso 1», y
  [cobertura-potencia.md](cobertura-potencia.md)).
- **Es sobre todo estructural.** Una UP con UF gallegas y de otra comunidad no suma con ninguna
  evidencia, porque su P48 no las separa. Una versión nueva del mapeo solo cambiaría las UP
  cuyo único obstáculo son UF desconocidas.
- **Existe una producción eólica medida de Galicia, hora a hora.** El indicador 10037 de e·sios
  («Generación medida Eólica») da la energía horaria de cada provincia peninsular, también de
  las cuatro gallegas. Según su descripción, se publica desde el mes siguiente y se revisa al
  llegar nuevas medidas ([fuentes-esios.md](fuentes-esios.md)). Su papel se dejó para después
  de congelar el mapeo, para que no influyera en él.

## Alternativas

| Alternativa | Decisión |
|---|---|
| Plan de respaldo del diseño: núcleo peninsular y capítulo gallego mensual | Queda como respaldo de esta vía |
| Sumar las UP mixtas y desconocidas, prorrateadas por la potencia de sus UF gallegas | Descartada: reparte el P48 de agregadoras con parques de varias comunidades, y el error horario de ese reparto no se puede medir con el P48 |
| **Producción medida de las cuatro provincias gallegas como etiqueta** | **Elegida**, condicionada a su criterio |

La etiqueta pasa a ser una medida oficial y horaria, en lugar de una reconstrucción con su
propio error, y llega al mes siguiente, en vez de a los 90 días o más.

## Principio

Todo se fija **sin cifras gallegas**: ni la potencia eólica instalada en Galicia (indicador
1485), ni los valores gallegos del 10037, ni la producción mensual de Galicia de REData. La
única ya conocida es la de junio de 2025 de REData, que el diseño recoge como dato de
validación; ninguna regla de este documento depende de ella. El mapeo ya está congelado (tag
`mapeo-v1`) y estas cifras no pueden cambiarlo: lo que se protege ahora es esta regla.

## Etiqueta

| Término | Definición | Fuente |
|---|---|---|
| Etiqueta gallega (`y_h`) | Suma de la energía (MWh) de las cuatro provincias gallegas (A Coruña, Lugo, Ourense y Pontevedra) en la hora `h` | Indicador 10037 de e·sios, sin parámetros de ámbito, como en la tolerancia mensual |
| `valid_time` | Inicio de la hora `h`, en UTC | `datetime_utc` de cada valor |

- **Horas sin valor:** si en una hora falta alguna de las cuatro provincias, la hora queda
  **sin etiqueta**, no a 0, y se publica cuántas son. En la producción medida peninsular, las
  horas sin valor cuentan como 0 ([tolerancia-mensual.md](tolerancia-mensual.md)) porque
  faltan en provincias con poca eólica. En una provincia con parques, un hueco puede ser una
  medida pendiente, y eso sigue sin aclarar ([fuentes-esios.md](fuentes-esios.md), «Pendiente
  de observar»).
- **Ámbito:** el que tenga el 10037. No se corrige ni se completa con otras fuentes; lo que no
  se sabe de él está en «Pendiente de observar».
- **Versiones:** cada mes se guarda en un sobre con el cuerpo literal y su hora de recepción,
  como los meses ya descargados.
  - Meses capturados en vivo: clase **observada**. Cada captura es una versión, con
    `available_at` igual a su hora de recepción.
  - Meses anteriores a la primera captura en vivo: solo existe la versión ya revisada. Su
    disponibilidad es **inferida por regla**: el inicio del mes siguiente más una latencia que
    se fija al medirla, con análisis de sensibilidad (diseño, sección 7.2). Que sus valores
    sean los revisados es una limitación anotada. Su efecto es el de entrenar con etiquetas
    revisadas, que el catálogo de fugas recoge (sección 9.2) y que se mide cuando haya meses
    capturados en vivo.
  - **Para evaluar** se usa la última versión capturada, y se publica su fecha de captura.

## Criterio para continuar

Sustituye, para la pista gallega, al de la sección 6.6 del diseño. Se mide en los tres meses de
desarrollo (enero de 2025, junio de 2025 y enero de 2026), cortados en hora peninsular como en
la tolerancia mensual.

1. **Completa:** en cada mes, al menos el **99 %** de las horas tienen etiqueta, es decir,
   valor en las cuatro provincias.
2. **Coherente con REData:** en cada mes `m`,

   ```
   e_m = (Y_m − R_m) / R_m
   ```

   - `Y_m`: suma de la etiqueta en las horas del mes que la tienen.
   - `R_m`: producción eólica de Galicia del mes en REData, guardada con su fecha de descarga.

   `e_m` se publica **con signo**. Se cumple si `|e_m| ≤ 5,00 %` en los tres meses, con los
   valores sin redondear.
3. **Si no se cumple** alguna de las dos condiciones, la pista gallega pasa al plan de respaldo
   del diseño (sección 2.2).

**Por qué el 5,00 %:** es la tolerancia publicada del método
([tolerancia-mensual.md](tolerancia-mensual.md)), reutilizada a propósito. Aquí no se mide un
método, sino si la suma de las cuatro provincias es la eólica de Galicia que publica Red
Eléctrica. Dos medidas de la misma producción que difieren más de lo que difieren, en la
península, el programa y la medida (un 3,10 % como mucho, con el 10010) apuntan a un ámbito
distinto, como provincias atribuidas de otra forma u otro tipo de producción, y no a revisiones
o redondeos.

**Alcance (no decide nada):** desde cuándo hay etiqueta. Las ejecuciones archivadas de la
Single Runs API empiezan el 14 de marzo de 2024 (diseño, sección 6.1), así que la etiqueta hace
falta desde entonces. Se comprueba con una petición del 10037 de marzo de 2024, contando las
horas con valor de las cuatro provincias, sin mirar los valores. Si ese mes no tiene etiqueta,
la ventana de entrenamiento empieza en el primer mes que la tenga, y se documenta.

## Versión 1 del mapeo: qué se publica

La versión 1 se mide como estaba previsto y se publica como resultado. Nada de esto decide la
vía.

- **Cobertura en potencia**, con la regla y las medidas de apoyo de
  [cobertura-potencia.md](cobertura-potencia.md) y la potencia gallega del indicador 1485.
- **Serie de la versión 1** (`S_h`): suma horaria del P48 de las UP que la versión 1 clasifica
  como gallegas, con los I90 de los tres meses. La energía de una hora es la suma de sus cuatro
  cuartos.
  - Frente a la etiqueta, en las horas que la tienen: desviación mensual con signo,
    `(S_m − Y_m) / Y_m`, y correlación de Pearson de los valores horarios de cada mes.
  - Frente a REData, con todas las horas del mes: desviación mensual con signo,
    `(S_m − R_m) / R_m`. Es el contraste de cada versión del mapeo que pide el diseño
    (sección 6.3).
- **Medidas de la versión 1 entera** que prevé [mapeo-listado.md](mapeo-listado.md) en
  «Medidas» y que solo están publicadas para las agregadoras. Salen del listado y de
  OpenStreetMap.
- **Muestra de referencia** ([mapeo-listado.md](mapeo-listado.md)): deja de hacer falta para
  decidir. Si se hace, mide la precisión y la exhaustividad de la versión 1, ponderadas por la
  potencia.

## Qué se abandona

- **El paso 2 del mapeo y la parte 2 de las UP de fuera del listado**
  ([unidades-fuera-del-listado.md](unidades-fuera-del-listado.md)). Sus reglas quedan
  escritas, pero no se aplican: serían otra versión del mapeo, y la pista gallega ya no la
  necesita.
- **La cobertura en potencia como criterio para continuar y como expectation del pipeline.**
  Se mide una vez, para la versión 1.
- **El backfill de I90 para la etiqueta.** Con él deja de hacer falta, para la etiqueta, fijar
  la latencia de publicación de los I90 ([fuentes-esios.md](fuentes-esios.md), «Fecha de
  publicación»). Los I90 seguirían haciendo falta para identificar los redespachos (diseño,
  sección 6.4), si se usan.

## Qué no decide esta regla

- **El resto del diseño:** el objetivo de predicción, la etiqueta de la pista peninsular, las
  capas de validación de la etiqueta en el pipeline y los criterios de éxito (sección 10.5).
  Se rehacen después de medir el criterio, según su resultado.
- **La latencia de publicación del 10037 y cuántas veces se vuelve a pedir un mes** para
  captar sus revisiones, dentro del uso responsable de e·sios. Se fijan al medir la latencia.
- **Si los redespachos de los I90 estratifican las métricas.**

## Pendiente de observar

- Si el 10037 incluye la parte eólica de las unidades híbridas.
- Si la provincia del 10037 es la de la instalación. El contraste con REData lo pone a prueba.
- Cuánto tarda en publicarse un mes y cuánto duran sus revisiones.

## Resultado

Pendiente: se medirá con esta regla ya publicada.
