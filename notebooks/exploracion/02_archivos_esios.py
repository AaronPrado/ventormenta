# Databricks notebook source
# MAGIC %md
# MAGIC # Archivos de e·sios: catálogo y fichas del I90
# MAGIC
# MAGIC Exploración del spike de la serie gallega: qué archivos lista `/archives`, qué id
# MAGIC tiene el I90 y qué dicen sus fichas (URL de descarga y fecha de publicación) en días
# MAGIC de distintas épocas. Cada respuesta se pide una sola vez y se guarda literal en el
# MAGIC Volume; las celdas de análisis leen del Volume, así que el notebook entero se puede
# MAGIC volver a ejecutar sin hacer peticiones. La descarga de los ficheros está en
# MAGIC `ventormenta.archives`.

# COMMAND ----------

import json
import posixpath
import time
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import requests
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

ARCHIVES_URL = "https://api.esios.ree.es/archives"
ACCEPT = "application/json; application/vnd.esios-api-v1+json"
USER_AGENT = "VenTormenta/0.1"
TIMEOUT_SECONDS = 30
PAUSE_SECONDS = 2
CATALOG_DIR = "/Volumes/ventormenta/raw/esios/catalogs/archives"
I90_ID = 34

files = WorkspaceClient().files
token = dbutils.secrets.get("ventormenta", "esios_token")  # noqa: F821  (global de Databricks)


def saved_files(directory: str) -> list[str]:
    """Ficheros guardados en ``directory``, en orden alfabético.

    Los nombres son instantes UTC en formato ISO 8601 básico, así que el orden alfabético es
    el cronológico.
    """
    try:
        # list() dentro del try: el listado es perezoso y NotFound llega al recorrerlo.
        entries = list(files.list_directory_contents(directory))
    except NotFound:
        return []
    names = sorted(e.name for e in entries if e.name and not e.is_directory)
    return [posixpath.join(directory, name) for name in names]


def load_json(path: str) -> dict[str, Any]:
    """Lee del Volume una respuesta JSON guardada (un objeto en todas las de este notebook)."""
    contents = files.download(path).contents
    if contents is None:
        raise RuntimeError(f"descarga sin contenido: {path}")
    with contents:
        return json.load(contents)


def fetch_json_once(url: str, params: dict[str, str], directory: str) -> bool:
    """Pide ``url`` y guarda el cuerpo literal en ``directory``, si aún no hay nada guardado.

    Devuelve si ha hecho la petición, para pausar solo entre peticiones reales. Solo guarda
    un cuerpo JSON: otra cosa (una página de mantenimiento, por ejemplo) no es la respuesta
    pedida y, una vez guardada, bloquearía la buena.
    """
    if saved_files(directory):
        print(f"Ya guardado, no se pide de nuevo: {directory}")
        return False
    headers = {"Accept": ACCEPT, "User-Agent": USER_AGENT, "x-api-key": token}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as err:
        raise RuntimeError(f"e·sios, {url}: {err}") from err
    received_at = datetime.now(UTC)
    try:
        json.loads(response.content)
    except ValueError as err:
        raise RuntimeError(f"e·sios, {url}: no es JSON") from err
    path = posixpath.join(directory, f"{received_at:%Y%m%dT%H%M%SZ}.json")
    files.create_directory(directory)
    files.upload(path, BytesIO(response.content), overwrite=False)
    print(f"Guardado en {path} · {len(response.content)} bytes")
    return True


# COMMAND ----------

# MAGIC %md
# MAGIC ## Catálogo de archivos
# MAGIC
# MAGIC Sin parámetros, `/archives` no lista todos los archivos: el I90 no aparece.

# COMMAND ----------

fetch_json_once(ARCHIVES_URL, {}, CATALOG_DIR)

# COMMAND ----------

catalog = load_json(saved_files(CATALOG_DIR)[-1])
print("Claves de primer nivel:", sorted(catalog), "· meta:", catalog["meta"])
archives = catalog["archives"]
print(f"{len(archives)} archivos · campos del primero: {sorted(archives[0])}")
for archive in archives:
    print(f"{archive.get('id')} · {archive.get('name')}")

# COMMAND ----------

# totalp48 (29), con todo su detalle: candidato para comparar el P48 total con la producción.
for archive in archives:
    if archive.get("id") == 29:
        print(json.dumps(archive, ensure_ascii=False, indent=2))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fichas del I90 (archivo 34)
# MAGIC
# MAGIC Un día por época: enero de 2025 (horario), enero de 2026 (cuartohorario) y un día
# MAGIC reciente, cerca de su publicación. Las fichas no descargan el fichero.

# COMMAND ----------

I90_DAYS = ("2025-01-15", "2026-01-14", "2026-07-15")


def detail_dir(day: str) -> str:
    """Carpeta de la ficha del I90 de ``day``."""
    return posixpath.join(CATALOG_DIR, str(I90_ID), f"date={day}")


for day in I90_DAYS:
    params = {"date_type": "datos", "date": f"{day}T00:00:00", "locale": "es"}
    if fetch_json_once(f"{ARCHIVES_URL}/{I90_ID}", params, detail_dir(day)):
        time.sleep(PAUSE_SECONDS)

# COMMAND ----------

for day in I90_DAYS:
    archive = load_json(saved_files(detail_dir(day))[-1])["archive"]
    print(f"{day} · publicado {archive['publication_date']} · fecha {archive['date']['date']}")
    print(f"    {archive['download']['url']}")
