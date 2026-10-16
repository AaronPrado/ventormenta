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

-- Lectura de las instantáneas para el vigilante de GitHub Actions. Los privilegios van al
-- grupo, no al service principal: cambiar o rotar la identidad no toca este fichero. El
-- grupo se crea en la configuración del workspace (Identity and access).
-- USE CATALOG y USE SCHEMA solo permiten llegar al Volume. READ VOLUME se concede en el
-- propio Volume y no en el esquema, donde se heredaría a los Volumes que se añadan después.
GRANT USE CATALOG ON CATALOG ventormenta TO `ventormenta-watchers`;
GRANT USE SCHEMA ON SCHEMA ventormenta.raw TO `ventormenta-watchers`;
GRANT READ VOLUME ON VOLUME ventormenta.raw.esios TO `ventormenta-watchers`;
