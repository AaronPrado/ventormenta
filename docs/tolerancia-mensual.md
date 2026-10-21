# Tolerancia mensual de la serie gallega

La serie gallega se contrasta cada mes con la producción eólica de Galicia que publica Red
Eléctrica. Ese contraste necesita una tolerancia, y el [diseño](ventormenta-presentacion.md)
la deriva de la península: se mide cuánto difieren cada mes el programa P48 eólico
peninsular y la producción eólica medida peninsular, y la tolerancia gallega es esa
diferencia más 3 puntos de margen para el mapeo, con un máximo del 5 %.

Este documento fija **la definición operativa de la regla antes de calcular ninguna
diferencia**, para que los números no influyan en cómo se mide. El valor resultante se
añadirá al final, sin cambiar la definición.

## Meses

Enero de 2025, junio de 2025 y enero de 2026: los tres meses de desarrollo del diseño.
Cada mes se corta en **hora peninsular** (Europe/Madrid): enero empieza a las 23:00
UTC del día anterior y junio, a las 22:00 UTC. Ninguno de los tres tiene cambio de hora.

## Datos

| Término | Definición | Fuente |
|---|---|---|
| P48 eólico peninsular (`P`) | Suma de la energía del P48 (MWh) de las unidades de programación de tipo «Eólica terrestre» o «Eólica marina» en el listado de unidades, en todos los cuartos de hora del mes | I90 (archivo 34, hoja del P48) de cada día del mes y listado de unidades de programación (archivo 82) capturado el 20 de octubre de 2026 |
| Producción medida peninsular (`M`) | Suma de la energía horaria (MWh) de todas las provincias, en todas las horas del mes | Indicador 10037 de e·sios («Generación medida Eólica»), sin parámetros de ámbito, descargado una vez por mes |

- **Unidades híbridas fuera de `P`.** El P48 da un valor por unidad de programación, y en una
  unidad híbrida no se puede separar la energía eólica de la solar o del almacenamiento.
  Su P48 se publica aparte, como cota.
- **Solo las unidades del listado.** El listado es la foto actual y le faltan unidades que
  existían en 2025. `P` se calcula con las listadas porque es el mismo conjunto de unidades
  con el que se construirá la serie gallega: así la tolerancia mide el método tal como se
  va a aplicar.
- **Horas sin valor en el 10037 = 0 MWh.** El indicador omite algunas horas en provincias
  con poca eólica; se cuentan como horas sin producción medida y se publica cuántas son.
- **El 10037 cubre solo la península:** sus 42 provincias son peninsulares (ni Baleares ni
  Canarias), así que `M` es la suma de todas, sin restar nada.

## Regla

Para cada mes `m`:

```
d_m = (P_m − M_m) / M_m
```

`d_m` se publica **con signo**: positivo si el programa supera a la medida.

```
tolerancia = mín( máx(|d_ene2025|, |d_jun2025|, |d_ene2026|) + 3 puntos , 5 % )
```

- **El máximo, no la media.** El criterio para continuar exige que los tres meses gallegos
  queden dentro de la tolerancia, así que esta debe cubrir el peor mes del propio método.
- La tolerancia se calcula con los valores sin redondear y **se aplica el valor publicado,
  con dos decimales** (en puntos porcentuales).
- **Aviso:** si el máximo de `|d_m|` pasa de 2 puntos, el tope deja para el mapeo menos de 3
  puntos de margen, y se dice al publicar el valor.

## Medidas de apoyo (no entran en la regla)

Se publican junto al resultado para interpretarlo:

- **P48 eólico de las unidades que faltan en el listado:** el indicador 10010 de e·sios
  («Generación programada P48 Eólica», cuartohorario, ámbito Península) menos `P`, por mes.
- **`d_m` con el 10010 en lugar de `P`:** cuánto de la diferencia es el método (programa
  frente a medida) y cuánto el hueco del listado.
- **P48 de las unidades híbridas** con alguna unidad física eólica, por mes.
- **Horas sin valor del 10037** por mes.

## Resultado

Medido el 21 de octubre de 2026 con los 92 I90 de los tres meses, el listado de unidades de
programación del 20 de octubre de 2026 y los indicadores 10037 y 10010, descargados ese mismo
día.

| Mes | `P` (GWh) | `M` (GWh) | `d` |
|---|---|---|---|
| Enero de 2025 | 6.777,1 | 7.492,2 | −9,54 % |
| Junio de 2025 | 2.770,7 | 3.077,2 | −9,96 % |
| Enero de 2026 | 7.963,1 | 8.208,8 | −2,99 % |

**Tolerancia: 5,00 %** (el tope: 9,96 % + 3 puntos lo supera).

**Aviso:** el máximo de `|d|` pasa de 2 puntos, y no solo recorta el margen del mapeo: los
dos meses de 2025 quedan, ya en la península, por encima del tope. El método construido con
las unidades del listado actual no cabe en su propia tolerancia en esos meses.

### Medidas de apoyo

| Mes | P48 fuera del listado | `d` con el 10010 | P48 de las híbridas | Horas sin valor del 10037 |
|---|---|---|---|---|
| Enero de 2025 | 9,88 % | +0,37 % | 12,5 GWh | 687 |
| Junio de 2025 | 7,88 % | −2,26 % | 2,7 GWh | 1.059 |
| Enero de 2026 | 5,91 % | +3,10 % | 19,6 GWh | 370 |

- **Casi toda la diferencia es el hueco del listado, no el método.** Con el P48 eólico que
  agrega Red Eléctrica (10010), programa y medida difieren entre −2,26 % y +3,10 %; con las
  unidades del listado, entre −2,99 % y −9,96 %.
- **El hueco es compatible con unidades que ya no están en el listado.** El P48 de las
  unidades de programación del I90 que no aparecen en el listado, con `Tipo Oferta` 2 o 10
  (los de las eólicas, compartidos con otras renovables, cogeneración y residuos), es una cota
  superior de la eólica que falta, y supera al hueco en los tres meses: 1.112,8 frente a
  743,1 GWh en enero de 2025, 928,4 frente a 236,9 en junio de 2025 y 640,8 frente a 499,9 en
  enero de 2026. Son 260, 228 y 133 unidades.
- **El hueco no se limita a 2025:** en enero de 2026 falta el 5,91 % del P48 eólico, más de
  lo que hacía esperar la cobertura de la energía total de un día de ese mes (99 %).
- Las horas sin valor del 10037 se cuentan como 0 MWh, como fija la regla.
