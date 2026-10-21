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
- **Aviso:** si el máximo de `|d_m|` llega a 2 puntos, el margen que queda para el mapeo es
  menor que 3 puntos, y se dice al publicar el valor.

## Medidas de apoyo (no entran en la regla)

Se publican junto al resultado para interpretarlo:

- **P48 eólico de las unidades que faltan en el listado:** el indicador 10010 de e·sios
  («Generación programada P48 Eólica», cuartohorario, ámbito Península) menos `P`, por mes.
- **`d_m` con el 10010 en lugar de `P`:** cuánto de la diferencia es el método (programa
  frente a medida) y cuánto el hueco del listado.
- **P48 de las unidades híbridas** con alguna unidad física eólica, por mes.
- **Horas sin valor del 10037** por mes.

## Resultado

Pendiente de medir.
