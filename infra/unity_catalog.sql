-- Espacio de datos crudos de VenTormenta en Unity Catalog.
--
-- Idempotente: volver a ejecutarlo no cambia nada. Queda fuera del bundle a
-- propósito: las instantáneas de la previsión no se pueden volver a pedir, así que
-- su almacenamiento no puede depender de un despliegue ni de un `bundle destroy`.
-- El bundle solo referencia estos nombres.

CREATE CATALOG IF NOT EXISTS ventormenta
COMMENT 'VenTormenta: eólica programada en Galicia, reconstruida y predicha con datos públicos.';

CREATE SCHEMA IF NOT EXISTS ventormenta.raw
COMMENT 'Ficheros crudos tal como llegan de cada fuente; inmutables. Un Volume por fuente.';

CREATE VOLUME IF NOT EXISTS ventormenta.raw.esios
COMMENT 'Respuestas crudas de e·sios. Datos de Red Eléctrica: no se redistribuyen.';
