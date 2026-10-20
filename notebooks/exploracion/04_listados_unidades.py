# Databricks notebook source
# MAGIC %pip install "python-calamine==0.8.3"

# COMMAND ----------

# MAGIC %md
# MAGIC # Listados de unidades de e·sios
# MAGIC
# MAGIC Exploración del spike de la serie gallega: el listado de unidades de programación
# MAGIC (archivo 82) y el de unidades físicas (archivo 81), que no salen en el catálogo
# MAGIC `/archives` y que la web pública de e·sios carga con `/archives/<id>/download_json`.
# MAGIC Primero las fichas, para saber si los listados se piden por fecha o solo existe la
# MAGIC foto actual; después, la descarga de esa foto y su caracterización, cruzada con el P48
# MAGIC de los I90 del Volume. Cada respuesta se pide una sola vez y se guarda literal en el
# MAGIC Volume; las celdas de análisis leen del Volume, así que el notebook entero se puede
# MAGIC volver a ejecutar sin hacer peticiones. El parser del P48 se importa de la copia del
# MAGIC paquete que sube `databricks bundle deploy -t dev` al workspace.

# COMMAND ----------

import hashlib
import json
import posixpath
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any

import requests
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

# COMMAND ----------

ARCHIVES_URL = "https://api.esios.ree.es/archives"
ACCEPT = "application/json; application/vnd.esios-api-v1+json"
USER_AGENT = "VenTormenta/0.1"
TIMEOUT_SECONDS = 30
PAUSE_SECONDS = 2
CATALOG_DIR = "/Volumes/ventormenta/raw/esios/catalogs/archives"
# Ids de las páginas «Unidades de programación» y «Unidades físicas» de la web de e·sios.
UNIT_ARCHIVES = {82: "unidades de programación", 81: "unidades físicas"}

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
# MAGIC ## Fichas de los archivos 81 y 82
# MAGIC
# MAGIC Sin fecha, como los pide la web. La ficha dice si el listado se pide por fecha, cuándo
# MAGIC se publicó y desde qué URL se descarga.

# COMMAND ----------


def detail_dir(archive_id: int) -> str:
    """Carpeta de la ficha sin fecha del archivo ``archive_id``."""
    return posixpath.join(CATALOG_DIR, str(archive_id))


for archive_id in UNIT_ARCHIVES:
    if fetch_json_once(f"{ARCHIVES_URL}/{archive_id}", {"locale": "es"}, detail_dir(archive_id)):
        time.sleep(PAUSE_SECONDS)

# COMMAND ----------

for archive_id, name in UNIT_ARCHIVES.items():
    detail = load_json(saved_files(detail_dir(archive_id))[-1])
    print(f"## {archive_id} · {name}")
    print(json.dumps(detail, ensure_ascii=False, indent=2))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Descarga de los listados
# MAGIC
# MAGIC Solo la foto actual. Las fichas no traen fecha de publicación ni versiones por fecha, y
# MAGIC su URL de descarga (`json_download_json`) responde 404, así que se piden las URL que
# MAGIC usa la web. Cada listado se guarda en `archives/<id>/capture_date=<AAAA-MM-DD>/`: el
# MAGIC cuerpo literal (`<instante>.data.json`) y un JSON lateral (`<instante>.json`) con la
# MAGIC ficha literal y los datos de la petición. El vintage es la hora de recepción.

# COMMAND ----------

API_BASE = "https://api.esios.ree.es"
RAW_DIR = "/Volumes/ventormenta/raw/esios"
SIDECAR_FORMAT_VERSION = 1
# La URL de descarga de la ficha («json_download_json») responde 404: estas son las que usa
# la web pública de e·sios en sus páginas de unidades.
WEB_DOWNLOADS = {
    82: (f"{API_BASE}/archives/82/download_json", {"locale": "es"}),
    81: (f"{API_BASE}/archives/81/download_json", {}),
}


def archive_root(archive_id: int) -> str:
    """Carpeta de las capturas del archivo ``archive_id``: ``<raw>/archives/<id>``."""
    return posixpath.join(RAW_DIR, "archives", str(archive_id))


def captures(archive_id: int) -> list[str]:
    """Carpetas ``capture_date=…`` del archivo ``archive_id``, en orden cronológico."""
    root = archive_root(archive_id)
    try:
        entries = list(files.list_directory_contents(root))
    except NotFound:
        return []
    names = sorted(
        e.name for e in entries if e.is_directory and e.name and e.name.startswith("capture_date=")
    )
    return [posixpath.join(root, name) for name in names]


def read_bytes(path: str) -> bytes:
    """Bytes de un fichero del Volume."""
    contents = files.download(path).contents
    if contents is None:
        raise RuntimeError(f"descarga sin contenido: {path}")
    with contents:
        return contents.read()


def download_listing_once(archive_id: int) -> str | None:
    """Descarga el listado actual del archivo ``archive_id`` si aún no hay ninguna captura.

    Devuelve la ruta del cuerpo guardado, o ``None`` sin pedir nada si ya hay una captura.
    Pide la URL de la web sin seguir redirecciones: la respuesta es JSON de la propia API,
    y seguir una llevaría el token a otro host. El JSON lateral se escribe el último: un
    cuerpo sin lateral es una escritura a medias, que se revisa a mano.
    """
    existing = captures(archive_id)
    if existing:
        print(f"Ya capturado, no se pide de nuevo: {existing}")
        return None
    detail_path = saved_files(detail_dir(archive_id))[-1]
    detail_body = read_bytes(detail_path)
    url, params = WEB_DOWNLOADS[archive_id]

    headers = {"Accept": ACCEPT, "User-Agent": USER_AGENT, "x-api-key": token}
    requested_at = datetime.now(UTC)
    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=TIMEOUT_SECONDS, allow_redirects=False
        )
        response.raise_for_status()
    except requests.RequestException as err:
        raise RuntimeError(f"e·sios, archivo {archive_id}: {err}") from err
    received_at = datetime.now(UTC)
    if response.status_code != requests.codes.ok:
        raise RuntimeError(f"e·sios, archivo {archive_id}: código {response.status_code}")
    try:
        json.loads(response.content)
    except ValueError as err:
        raise RuntimeError(f"e·sios, archivo {archive_id}: no es JSON") from err

    capture_date = f"{received_at:%Y-%m-%d}"
    sidecar = {
        "format_version": SIDECAR_FORMAT_VERSION,
        "source": "esios",
        "archive_id": archive_id,
        "capture_date": capture_date,
        "detail": {
            "path": detail_path,
            "body_sha256": hashlib.sha256(detail_body).hexdigest(),
            "body": detail_body.decode("utf-8"),
        },
        "file": {
            "request": {"method": "GET", "url": url, "params": params},
            "requested_at": requested_at.isoformat(),
            "received_at": received_at.isoformat(),
            "status_code": response.status_code,
            "server_date": response.headers.get("Date"),
            "size": len(response.content),
            "sha256": hashlib.sha256(response.content).hexdigest(),
        },
    }
    capture_dir = posixpath.join(archive_root(archive_id), f"capture_date={capture_date}")
    stem = f"{received_at:%Y%m%dT%H%M%SZ}"
    data_path = posixpath.join(capture_dir, f"{stem}.data.json")
    files.create_directory(capture_dir)
    files.upload(data_path, BytesIO(response.content), overwrite=False)
    sidecar_bytes = (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files.upload(
        posixpath.join(capture_dir, f"{stem}.json"), BytesIO(sidecar_bytes), overwrite=False
    )
    print(f"Guardado en {data_path} · {len(response.content)} bytes")
    return data_path


# COMMAND ----------

for archive_id in UNIT_ARCHIVES:
    if download_listing_once(archive_id):
        time.sleep(PAUSE_SECONDS)

# COMMAND ----------


def describe(value: object, depth: int = 0) -> None:
    """Imprime la forma de un JSON (tipos, claves y longitudes), sin sus valores."""
    pad = "    " * depth
    if isinstance(value, dict):
        for key, item in value.items():
            size = f" ({len(item)})" if isinstance(item, list | dict) else ""
            print(f"{pad}{key}: {type(item).__name__}{size}")
            if depth < 2:
                describe(item, depth + 1)
    elif isinstance(value, list) and value:
        print(f"{pad}[0]:")
        describe(value[0], depth + 1)


for archive_id, name in UNIT_ARCHIVES.items():
    paths = saved_files(captures(archive_id)[-1])
    print(f"## {archive_id} · {name} · {[posixpath.basename(p) for p in paths]}")
    describe(json.loads(read_bytes(next(p for p in paths if p.endswith(".data.json")))))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Caracterización
# MAGIC
# MAGIC Campos, tipos de producción y potencias de los dos listados, relación UP → UF y cobertura
# MAGIC de las UP del P48 de los tres días del Volume. Solo lee del Volume. Imprime recuentos y
# MAGIC sumas, nunca valores por unidad.

# COMMAND ----------

user = WorkspaceClient().current_user.me().user_name
sys.path.insert(0, f"/Workspace/Users/{user}/.bundle/ventormenta/dev/files/src")
from ventormenta.i90 import p48_rows, parse_p48  # noqa: E402

WIND = ("Eólica terrestre", "Eólica marina")
I90_DIR = "/Volumes/ventormenta/raw/esios/archives/34"
P48_DAYS = ("2025-01-15", "2025-06-11", "2026-01-14")
# Coma decimal obligatoria si hay punto de miles: «9.999» sin coma sería ambiguo.
MW_FORMAT = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+|\d+(?:,\d+)?")


def parse_mw(text: str) -> float | None:
    """Potencia en MW de un listado: coma decimal y, opcionalmente, punto de miles.

    Un texto vacío es una potencia sin informar (``None``). Cualquier otro formato lanza
    ``ValueError``: adivinar si un punto es decimal o de miles cambiaría la escala.
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    if not MW_FORMAT.fullmatch(cleaned):
        raise ValueError(f"potencia con formato inesperado: {text!r}")
    return float(cleaned.replace(".", "").replace(",", "."))


def load_listing(archive_id: int, key: str) -> list[dict[str, str]]:
    """Registros de la última captura del listado ``archive_id``, bajo la clave ``key``."""
    paths = saved_files(captures(archive_id)[-1])
    data = json.loads(read_bytes(next(p for p in paths if p.endswith(".data.json"))))
    rows: list[dict[str, str]] = data[key]
    return rows


ups = load_listing(82, "UnidadesProgramacion")
ufs = load_listing(81, "UnidadesFisicas")
for name, rows, code in (("UP", ups, "Código de UP"), ("UF", ufs, "Código de UF")):
    shapes = Counter(tuple(row) for row in rows)
    non_text = sum(not isinstance(v, str) for row in rows for v in row.values())
    codes = Counter(row[code] for row in rows)
    print(f"{name}: {len(rows):,} registros · {len(codes):,} códigos distintos")
    print(f"    conjuntos de campos: {len(shapes)} · valores que no son texto: {non_text}")
    print(f"    códigos repetidos: {sum(n > 1 for n in codes.values())}")

# COMMAND ----------


def production_summary(rows: list[dict[str, str]]) -> None:
    """Recuento y MW por «Tipo de producción», de mayor a menor recuento."""
    count: Counter[str] = Counter()
    mw: defaultdict[str, float] = defaultdict(float)
    blank: Counter[str] = Counter()
    for row in rows:
        kind = row["Tipo de producción"]
        count[kind] += 1
        value = parse_mw(row["Potencia máxima MW"])
        if value is None:
            blank[kind] += 1
        else:
            mw[kind] += value
    for kind, n in count.most_common():
        print(f"{n:6,} · {mw[kind]:12,.1f} MW · sin potencia: {blank[kind]:4} · {kind!r}")


print("## UP por tipo de producción")
production_summary(ups)
print("## UF por tipo de producción")
production_summary(ufs)
for field in ("Tipo de UP", "Negocio", "Ámbito de actuación"):
    print(f"## UP por {field}:", dict(Counter(row[field] for row in ups).most_common()))

# COMMAND ----------

up_by_code = {row["Código de UP"]: row for row in ups}
links = Counter(row["Vinculación con UP"] for row in ufs)
separators = Counter(ch for link in links for ch in set(link) if not ch.isalnum())
print("Caracteres no alfanuméricos en «Vinculación con UP»:", dict(separators))
print(f"UF sin UP: {links['']:,} · UF con UP fuera del listado: ", end="")
print(sum(n for link, n in links.items() if link and link not in up_by_code))

uf_mw: defaultdict[str, float] = defaultdict(float)
for row in ufs:
    value = parse_mw(row["Potencia máxima MW"])
    if value is not None:
        uf_mw[row["Vinculación con UP"]] += value

for kind in (*WIND, "Híbrida renovable"):
    codes = [code for code, row in up_by_code.items() if row["Tipo de producción"] == kind]
    per_up = Counter(links[code] for code in codes)
    comparison: Counter[str] = Counter()
    for code in codes:
        up_value = parse_mw(up_by_code[code]["Potencia máxima MW"])
        if up_value is None or code not in uf_mw:
            comparison["sin dato"] += 1
        elif abs(up_value - uf_mw[code]) < 0.05:
            comparison["igual"] += 1
        else:
            comparison["UP mayor" if up_value > uf_mw[code] else "UP menor"] += 1
    print(f"## {kind}: {len(codes):,} UP")
    print("    UF por UP:", dict(sorted(per_up.items())))
    print("    potencia de la UP frente a la suma de sus UF:", dict(comparison))

# COMMAND ----------


def latest_zip(day: str) -> str:
    """Ruta del zip más reciente del I90 del día ``day``."""
    zips = [p for p in saved_files(f"{I90_DIR}/data_date={day}") if p.endswith(".zip")]
    return zips[-1]


offer_kinds: Counter[tuple[int, str, str]] = Counter()
for day in P48_DAYS:
    data_date = date.fromisoformat(day)
    values = parse_p48(p48_rows(read_bytes(latest_zip(day)), data_date), data_date)
    energy: defaultdict[str, float] = defaultdict(float)
    offer: dict[str, int] = {}
    for value in values:
        energy[value.unit] += abs(value.mwh)
        offer[value.unit] = value.offer_type
    found = [unit for unit in energy if unit in up_by_code]
    missing = [unit for unit in energy if unit not in up_by_code]
    share = sum(energy[unit] for unit in found) / sum(energy.values())
    wind = [unit for unit in found if up_by_code[unit]["Tipo de producción"] in WIND]
    print(f"## {day}: {len(found):,} de {len(energy):,} UP en el listado")
    print(f"    {share:.2%} de la energía (|MWh|) · eólicas encontradas: {len(wind):,}")
    print("    Tipo Oferta de las que faltan:", dict(Counter(offer[u] for u in missing)))
    for unit in found:
        row = up_by_code[unit]
        offer_kinds[(offer[unit], row["Negocio"], row["Tipo de UP"])] += 1

print("## Tipo Oferta del P48 frente al listado (UP·día, tres días)")
for (code, business, kind), n in sorted(offer_kinds.items()):
    print(f"{code:3} · {business:6} · {kind}: {n:,}")

# COMMAND ----------

# Tipo Oferta de las UP de generación, por tipo de producción, con el P48 del último día.
production_by_offer: Counter[tuple[int, str]] = Counter()
for unit, code in offer.items():
    row = up_by_code.get(unit)
    if row is not None and row["Tipo de UP"] == "Generación":
        production_by_offer[(code, row["Tipo de producción"])] += 1
print(f"## Tipo Oferta de las UP de generación ({P48_DAYS[-1]})")
for (code, kind), n in sorted(production_by_offer.items()):
    print(f"{code:3} · {kind}: {n:,}")

# UF y UP de tipos distintos: de dónde salen los MW eólicos que no están en UP eólicas.
mixed: Counter[tuple[str, str]] = Counter()
mixed_mw: defaultdict[tuple[str, str], float] = defaultdict(float)
for row in ufs:
    uf_kind = row["Tipo de producción"]
    up_kind = up_by_code[row["Vinculación con UP"]]["Tipo de producción"]
    if (uf_kind in WIND) != (up_kind in WIND):
        value = parse_mw(row["Potencia máxima MW"])
        if value is None:
            raise ValueError("UF sin potencia en un cruce eólico")
        mixed[(uf_kind, up_kind)] += 1
        mixed_mw[(uf_kind, up_kind)] += value
print("## UF eólicas en UP no eólicas, y al revés (UF · UP)")
for (uf_kind, up_kind), n in mixed.most_common():
    print(f"{n:4} · {mixed_mw[(uf_kind, up_kind)]:8,.1f} MW · {uf_kind!r} en {up_kind!r}")
