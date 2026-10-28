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

-- El comentario va aparte: el de un CREATE ... IF NOT EXISTS no cambia un Volume que ya existe.
CREATE VOLUME IF NOT EXISTS ventormenta.raw.osm;
COMMENT ON VOLUME ventormenta.raw.osm IS
'Extractos de OpenStreetMap de Geofabrik, tal como se descargan. ODbL: sus derivados se guardan aparte.';

-- Lectura de las instantáneas para el vigilante de GitHub Actions. Los privilegios van al
-- grupo, no al service principal: cambiar o rotar la identidad no toca este fichero. El
-- grupo se crea en la configuración del workspace (Identity and access).
-- USE CATALOG y USE SCHEMA solo permiten llegar al Volume. READ VOLUME se concede en el
-- propio Volume y no en el esquema, donde se heredaría a los Volumes que se añadan después.
GRANT USE CATALOG ON CATALOG ventormenta TO `ventormenta-watchers`;
GRANT USE SCHEMA ON SCHEMA ventormenta.raw TO `ventormenta-watchers`;
GRANT READ VOLUME ON VOLUME ventormenta.raw.esios TO `ventormenta-watchers`;

-- Mapeo de las unidades eólicas a Galicia (docs/mapeo-listado.md). Fuera del bundle por la
-- misma razón que los Volumes: una versión congelada no puede depender de un despliegue.
CREATE SCHEMA IF NOT EXISTS ventormenta.mapeo
COMMENT 'Mapeo de las unidades eólicas a Galicia, por versión. Una versión congelada no se reescribe.';

CREATE TABLE IF NOT EXISTS ventormenta.mapeo.uf (
  mapping_version      STRING    NOT NULL COMMENT 'Versión del mapeo (v1, v2...); la congelada lleva su tag en Git',
  uf_code              STRING    NOT NULL COMMENT 'Código de la unidad física en el listado',
  up_code              STRING    NOT NULL COMMENT 'UP a la que está vinculada',
  uf_description       STRING             COMMENT 'Descripción larga de la UF, la que se compara',
  uf_mw                DOUBLE             COMMENT 'Potencia de la UF en el listado (MW)',
  listing_capture_date DATE      NOT NULL COMMENT 'Captura de los listados de unidades usada',
  osm_extract_date     DATE      NOT NULL COMMENT 'Fecha de los extractos de Geofabrik usados',
  uf_class             STRING    NOT NULL COMMENT 'gallega, otra o desconocida',
  uf_step              STRING    NOT NULL COMMENT 'Lo que decide la clase: paso1, paso2 o ninguno',
  best_osm_type        STRING             COMMENT 'Mejor candidato: n, w o r',
  best_osm_id          BIGINT             COMMENT 'Mejor candidato: identificador',
  best_osm_name        STRING             COMMENT 'Mejor candidato: el nombre con el mejor parecido',
  best_similarity      DOUBLE             COMMENT 'Parecido con el mejor candidato, entre 0 y 1',
  candidates_galicia   INT       NOT NULL COMMENT 'Candidatos en T o más del extracto de Galicia',
  candidates_rest      INT       NOT NULL COMMENT 'Candidatos en T o más del resto de España',
  up_class             STRING    NOT NULL COMMENT 'gallega, otra, mixta o desconocida',
  computed_at          TIMESTAMP NOT NULL COMMENT 'Cuándo se calculó la fila (UTC)',
  CONSTRAINT uf_pk PRIMARY KEY (mapping_version, uf_code)
)
COMMENT 'Una fila por UF eólica y versión del mapeo, con su clase, su evidencia y la clase de su UP.';

-- Las CHECK de Delta solo se añaden sobre una tabla ya creada. Quitarlas y volver a ponerlas
-- deja el script idempotente, y al añadirlas Delta comprueba también las filas que ya hay.
-- La clave primaria de Unity Catalog es informativa: no impide duplicados.
ALTER TABLE ventormenta.mapeo.uf DROP CONSTRAINT IF EXISTS uf_class_valid;
ALTER TABLE ventormenta.mapeo.uf ADD CONSTRAINT uf_class_valid
  CHECK (uf_class IN ('gallega', 'otra', 'desconocida'));
ALTER TABLE ventormenta.mapeo.uf DROP CONSTRAINT IF EXISTS uf_step_valid;
ALTER TABLE ventormenta.mapeo.uf ADD CONSTRAINT uf_step_valid
  CHECK (uf_step IN ('paso1', 'paso2', 'ninguno'));
ALTER TABLE ventormenta.mapeo.uf DROP CONSTRAINT IF EXISTS up_class_valid;
ALTER TABLE ventormenta.mapeo.uf ADD CONSTRAINT up_class_valid
  CHECK (up_class IN ('gallega', 'otra', 'mixta', 'desconocida'));
ALTER TABLE ventormenta.mapeo.uf DROP CONSTRAINT IF EXISTS similarity_range;
ALTER TABLE ventormenta.mapeo.uf ADD CONSTRAINT similarity_range
  CHECK (best_similarity BETWEEN 0 AND 1);
