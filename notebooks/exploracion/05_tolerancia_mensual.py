# Databricks notebook source
# MAGIC %md
# MAGIC # Diferencia mensual entre el P48 y la producción eólica peninsular
# MAGIC
# MAGIC Spike de la serie gallega: mide en los tres meses de prueba la diferencia entre el P48
# MAGIC eólico peninsular de los I90 y la producción eólica real peninsular de e·sios, de la que
# MAGIC sale la tolerancia mensual gallega. Cada respuesta de e·sios se pide una sola vez y se
# MAGIC guarda literal en el Volume; las celdas de análisis leen del Volume.
# MAGIC
# MAGIC El paquete se instala desde el panel **Environment** (versión 6), con la ruta del wheel
# MAGIC que sube `databricks bundle deploy -t dev` a `artifacts/.internal/` del bundle: así llega
# MAGIC también a los ejecutores, que parsean los I90. La ruta cambia en cada despliegue.

# COMMAND ----------

import hashlib
import json
import posixpath
import re
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from pyspark.sql import functions as F

from ventormenta.tolerance import margin_reduced, relative_difference, tolerance
from ventormenta.units import UF_KEY, UP_KEY, hybrid_wind_units, parse_listing, wind_units

# COMMAND ----------

ACCEPT = "application/json; application/vnd.esios-api-v1+json"
USER_AGENT = "VenTormenta/0.1"
TIMEOUT_SECONDS = 30
PAUSE_SECONDS = 2
INDICATORS_URL = "https://api.esios.ree.es/indicators"
INDICATOR_CATALOG_DIR = "/Volumes/ventormenta/raw/esios/catalogs/indicators"

files = WorkspaceClient().files
token = dbutils.secrets.get("ventormenta", "esios_token")  # noqa: F821  (global de Databricks)


def saved_files(directory: str) -> list[str]:
    """Ficheros guardados en ``directory``, en orden alfabético (el cronológico)."""
    try:
        # list() dentro del try: el listado es perezoso y NotFound llega al recorrerlo.
        entries = list(files.list_directory_contents(directory))
    except NotFound:
        return []
    names = sorted(e.name for e in entries if e.name and not e.is_directory)
    return [posixpath.join(directory, name) for name in names]


def load_json(path: str) -> dict[str, Any]:
    """Lee del Volume una respuesta JSON guardada."""
    contents = files.download(path).contents
    if contents is None:
        raise RuntimeError(f"descarga sin contenido: {path}")
    with contents:
        return json.load(contents)


def fetch_json_once(url: str, params: dict[str, str], directory: str) -> bool:
    """Pide ``url`` y guarda el cuerpo literal en ``directory``, si aún no hay nada guardado."""
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
# MAGIC ## Catálogo de indicadores
# MAGIC
# MAGIC Una sola petición: el indicador de producción real se elige leyendo el catálogo, no
# MAGIC probando ids.

# COMMAND ----------

fetch_json_once(INDICATORS_URL, {"locale": "es"}, INDICATOR_CATALOG_DIR)

# COMMAND ----------

catalog = load_json(saved_files(INDICATOR_CATALOG_DIR)[-1])
if "indicators" not in catalog:
    raise RuntimeError(f"catálogo con otra forma; claves: {sorted(catalog)}")
indicators = catalog["indicators"]
print(f"{len(indicators)} indicadores · campos: {sorted(indicators[0])}")

wind_indicators = sorted(
    (i for i in indicators if re.search(r"e[óo]lic", i["name"], re.IGNORECASE)),
    key=lambda i: i["id"],
)
print(f"{len(wind_indicators)} con «eólic» en el nombre")
for indicator in wind_indicators:
    print(f"{indicator['id']:>6} · {indicator['name']}")

# COMMAND ----------

CANDIDATES = (551, 1745, 2038, 10037, 1159, 1160, 10010, 82, 83)
by_id = {i["id"]: i for i in indicators}
for indicator_id in CANDIDATES:
    indicator = by_id[indicator_id]
    description = re.sub(r"<[^>]+>", " ", indicator["description"] or "")
    print(f"## {indicator_id} · {indicator['name']} ({indicator['short_name']})")
    print(" ".join(description.split()) or "(sin descripción)")
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Producción medida (10037) y P48 eólico de Red Eléctrica (10010)
# MAGIC
# MAGIC Una petición por indicador y mes, sin parámetros de ámbito ni `time_trunc`, guardada en
# MAGIC un sobre con el cuerpo literal. El 10037 llega desglosado por provincias: aquí solo se
# MAGIC usan sus totales peninsulares, y la descripción de la respuesta no imprime valores.

# COMMAND ----------

MADRID = ZoneInfo("Europe/Madrid")
INDICATOR_URL = "https://api.esios.ree.es/indicators/{indicator_id}"
RANGES_DIR = "/Volumes/ventormenta/raw/esios/indicator_ranges"
MONTHS = (date(2025, 1, 1), date(2025, 6, 1), date(2026, 1, 1))


def month_params(month: date) -> dict[str, str]:
    """``start_date`` y ``end_date`` que cubren el mes peninsular que empieza en ``month``.

    Mismo criterio que los días del job de instantáneas: el fin es el último segundo del
    mes, con su desfase horario explícito, para que el corte sea el peninsular y no el UTC.
    """
    start = datetime(month.year, month.month, 1, tzinfo=MADRID)
    next_month = (start + timedelta(days=32)).replace(day=1)
    last_second = next_month - timedelta(seconds=1)
    return {"start_date": start.isoformat(), "end_date": last_second.isoformat()}


def month_dir(indicator_id: int, month: date) -> str:
    """Carpeta de un indicador y un mes: ``<RANGES_DIR>/<id>/month=AAAA-MM``."""
    return posixpath.join(RANGES_DIR, str(indicator_id), f"month={month:%Y-%m}")


def fetch_month_once(indicator_id: int, month: date) -> str | None:
    """Pide el indicador para el mes y guarda el sobre literal, si el mes aún no está.

    Devuelve la ruta guardada, o ``None`` si ya había algo y no se ha pedido nada.
    """
    directory = month_dir(indicator_id, month)
    if saved_files(directory):
        print(f"Ya guardado, no se pide de nuevo: {directory}")
        return None
    url = INDICATOR_URL.format(indicator_id=indicator_id)
    params = month_params(month)
    headers = {"Accept": ACCEPT, "User-Agent": USER_AGENT, "x-api-key": token}
    requested_at = datetime.now(UTC)
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as err:
        raise RuntimeError(f"e·sios, indicador {indicator_id}: {err}") from err
    received_at = datetime.now(UTC)
    try:
        json.loads(response.content)
    except ValueError as err:
        raise RuntimeError(f"e·sios, indicador {indicator_id}: no es JSON") from err
    envelope = {
        "format_version": 1,
        "source": "esios",
        "indicator_id": indicator_id,
        "month": f"{month:%Y-%m}",
        "request": {"method": "GET", "url": url, "params": params},
        "requested_at": requested_at.isoformat(),
        "received_at": received_at.isoformat(),
        "response": {
            "status_code": response.status_code,
            "server_date": response.headers.get("Date"),
            "body_sha256": hashlib.sha256(response.content).hexdigest(),
            "body_encoding": "utf-8",
            "body": response.content.decode("utf-8"),
        },
    }
    path = posixpath.join(directory, f"{received_at:%Y%m%dT%H%M%SZ}.json")
    data = (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files.create_directory(directory)
    files.upload(path, BytesIO(data), overwrite=False)
    print(f"Guardado en {path} · {len(response.content)} bytes de cuerpo")
    return path


# COMMAND ----------

for indicator_id in (10037, 10010):
    for month in MONTHS:
        if fetch_month_once(indicator_id, month):
            time.sleep(PAUSE_SECONDS)

# COMMAND ----------


def describe_month(indicator_id: int, month: date) -> None:
    """Forma de la respuesta guardada de un mes, sin imprimir ningún valor."""
    envelope = load_json(saved_files(month_dir(indicator_id, month))[-1])
    indicator = json.loads(envelope["response"]["body"])["indicator"]
    values = indicator["values"]
    names = {g["geo_id"]: g["geo_name"] for g in indicator["geos"]}
    per_geo = Counter(v["geo_id"] for v in values)
    instants = sorted({v["datetime_utc"] for v in values})
    print(f"## {indicator_id} · {month:%Y-%m} · recibido {envelope['received_at']}")
    print(f"tiempo: {indicator['tiempo']} · actualizado: {indicator['values_updated_at']}")
    print(
        f"{len(values)} valores · {len(per_geo)} geos · {len(instants)} instantes,"
        f" de {instants[0]} a {instants[-1]}"
    )
    if len(per_geo) <= 5:
        print(f"geos: {[names.get(g, g) for g in sorted(per_geo)]}")
    incomplete = sorted((names.get(g, g), n) for g, n in per_geo.items() if n < len(instants))
    print(f"geos sin todos los instantes: {incomplete or 'ninguna'}")
    print()


for indicator_id in (10037, 10010):
    for month in MONTHS:
        describe_month(indicator_id, month)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lectura del P48 con Spark
# MAGIC
# MAGIC Prueba previa: el paquete y el lector del XLS tienen que estar instalados en los
# MAGIC ejecutores, que son los que parsean los zips.

# COMMAND ----------


def executor_versions(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Versiones que ve cada ejecutor: prueba que el paquete y el lector están instalados allí.

    Los imports van dentro de la función a propósito: así se ejecutan en el ejecutor, no
    en el driver, y un paquete que falte allí da error aquí y no en mitad del cálculo.
    """
    import platform
    from importlib.metadata import version

    import python_calamine  # noqa: F401

    import ventormenta.i90  # noqa: F401

    for _ in batches:
        yield pd.DataFrame(
            {
                "ventormenta": [version("ventormenta")],
                "calamine": [version("python-calamine")],
                "machine": [platform.machine()],
            }
        )


schema = "ventormenta string, calamine string, machine string"
(
    spark.range(8)  # noqa: F821  (global de Databricks)
    .repartition(8)
    .mapInPandas(executor_versions, schema)
    .distinct()
    .show(truncate=False)
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## P48 de los 92 días
# MAGIC
# MAGIC Los zips se leen con `binaryFile` y cada ejecutor parsea los suyos con el parser del
# MAGIC paquete. Se agrega por unidad y día antes de traer nada al driver.

# COMMAND ----------

I90_DIR = "/Volumes/ventormenta/raw/esios/archives/34"

zips = (
    spark.read.format("binaryFile")  # noqa: F821  (global de Databricks)
    .option("pathGlobFilter", "*.zip")
    .load(I90_DIR)
    .select("data_date", "content")
)

per_day = zips.groupBy("data_date").count()
per_month = (
    per_day.groupBy(F.date_format("data_date", "yyyy-MM").alias("month")).count().orderBy("month")
)
print(f"zips: {zips.count()} · días: {per_day.count()}")
print(f"días con más de un zip: {per_day.filter('count > 1').count()}")
per_month.show()

# COMMAND ----------

P48_SCHEMA = "data_date date, unit string, offer_type int, valid_time timestamp, mwh double"


def parse_zips(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Parsea en el ejecutor cada zip de I90 a filas del P48, una por unidad y cuarto de hora.

    El día de cada zip sale de su carpeta ``data_date=``, y el parser comprueba que coincide
    con el de la hoja. Un zip con otra forma lanza ``I90FormatError`` y para el cálculo.
    """
    from ventormenta.i90 import p48_rows, parse_p48

    for batch in batches:
        for data_date, content in zip(batch["data_date"], batch["content"], strict=True):
            day = pd.Timestamp(data_date).date()
            values = parse_p48(p48_rows(content, day), day)
            yield pd.DataFrame(
                {
                    "data_date": [day] * len(values),
                    "unit": [v.unit for v in values],
                    "offer_type": [v.offer_type for v in values],
                    "valid_time": [v.valid_time for v in values],
                    "mwh": [v.mwh for v in values],
                }
            )


# COMMAND ----------

daily = (
    zips.mapInPandas(parse_zips, P48_SCHEMA)
    .groupBy("data_date", "unit", "offer_type")
    .agg(F.sum("mwh").alias("mwh"), F.count("*").alias("quarters"))
    .toPandas()
)

print(f"{len(daily)} filas (unidad y día) · {daily['data_date'].nunique()} días")
print(f"cuartos por unidad y día: {sorted(daily['quarters'].unique())}")
units_per_day = daily.groupby("data_date")["unit"].nunique()
for known in ("2025-01-15", "2025-06-11", "2026-01-14"):
    print(f"{known}: {units_per_day[date.fromisoformat(known)]} unidades")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Diferencia mensual y tolerancia
# MAGIC
# MAGIC Regla fijada antes de medir en `docs/tolerancia-mensual.md`. Solo totales peninsulares.

# COMMAND ----------

ARCHIVES_DIR = "/Volumes/ventormenta/raw/esios/archives"


def read_bytes(path: str) -> bytes:
    """Contenido de un fichero del Volume."""
    contents = files.download(path).contents
    if contents is None:
        raise RuntimeError(f"descarga sin contenido: {path}")
    with contents:
        data: bytes = contents.read()
    return data


def latest_listing(archive_id: int, key: str) -> list[dict[str, str]]:
    """Registros de la última captura del listado ``archive_id``."""
    root = posixpath.join(ARCHIVES_DIR, str(archive_id))
    captures = sorted(
        posixpath.join(root, e.name)
        for e in files.list_directory_contents(root)
        if e.is_directory and e.name and e.name.startswith("capture_date=")
    )
    if not captures:
        raise RuntimeError(f"sin capturas del listado {archive_id}")
    bodies = [p for p in saved_files(captures[-1]) if p.endswith(".data.json")]
    if len(bodies) != 1:
        raise RuntimeError(f"{captures[-1]}: {len(bodies)} cuerpos, se espera uno")
    return parse_listing(read_bytes(bodies[0]), key)


ups = latest_listing(82, UP_KEY)
ufs = latest_listing(81, UF_KEY)
wind = wind_units(ups)
hybrids = hybrid_wind_units(ups, ufs)
print(f"UP eólicas: {len(wind)} · UP híbridas con UF eólica: {len(hybrids)}")

# COMMAND ----------

daily["month"] = pd.to_datetime(daily["data_date"]).dt.strftime("%Y-%m")
wind_daily = daily[daily["unit"].isin(wind)]
p48_wind = wind_daily.groupby("month")["mwh"].sum()
hybrid_daily = daily[daily["unit"].isin(hybrids)]
p48_hybrid = hybrid_daily.groupby("month")["mwh"].sum()
print("UP eólicas con P48 por mes:", wind_daily.groupby("month")["unit"].nunique().to_dict())
print("UP híbridas con P48 por mes:", hybrid_daily.groupby("month")["unit"].nunique().to_dict())

# COMMAND ----------


def indicator_month(indicator_id: int, month: date) -> tuple[float, int]:
    """Energía del mes (MWh) y huecos (instantes que faltan por geo) de un indicador guardado.

    Comprueba que es energía y que todos los valores caen dentro del mes peninsular pedido:
    así un rango mal pedido o un indicador en MW no se suman sin avisar.
    """
    envelope = load_json(saved_files(month_dir(indicator_id, month))[-1])
    indicator = json.loads(envelope["response"]["body"])["indicator"]
    magnitudes = [m["name"] for m in indicator["magnitud"]]
    if magnitudes != ["Energía"]:
        raise RuntimeError(f"{indicator_id}: magnitud {magnitudes}, se espera energía")
    params = month_params(month)
    start = datetime.fromisoformat(params["start_date"])
    end = datetime.fromisoformat(params["end_date"])
    values = indicator["values"]
    if any(v["value"] is None for v in values):
        raise RuntimeError(f"{indicator_id} · {month:%Y-%m}: valores nulos")
    times = [datetime.fromisoformat(v["datetime_utc"]) for v in values]
    if not all(start <= t <= end for t in times):
        raise RuntimeError(f"{indicator_id} · {month:%Y-%m}: valores fuera del mes")
    instants = len(set(times))
    geos = len({v["geo_id"] for v in values})
    return sum(v["value"] for v in values), geos * instants - len(values)


# COMMAND ----------

rows = []
for month in MONTHS:
    key = f"{month:%Y-%m}"
    measured, gaps = indicator_month(10037, month)
    p48_reference, _ = indicator_month(10010, month)
    rows.append(
        {
            "month": key,
            "P (MWh)": p48_wind[key],
            "M (MWh)": measured,
            "d": relative_difference(p48_wind[key], measured),
            "P48 10010 (MWh)": p48_reference,
            "fuera del listado": (p48_reference - p48_wind[key]) / p48_reference,
            "d con el 10010": relative_difference(p48_reference, measured),
            "híbridas (MWh)": p48_hybrid.get(key, 0.0),
            "huecos 10037": gaps,
        }
    )
result = pd.DataFrame(rows).set_index("month")
print(result.to_string(float_format=lambda x: f"{x:,.4f}"))

differences = result["d"].tolist()
print(f"\ntolerancia: {tolerance(differences) * 100:.2f} %")
print(f"margen del mapeo recortado por el tope: {margin_reduced(differences)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## De dónde sale el hueco del listado
# MAGIC
# MAGIC El P48 de las UP que no están en el listado, por `Tipo Oferta`. Las eólicas tienen el 2
# MAGIC o el 10, compartidos con otras renovables, cogeneración y residuos: su energía es una
# MAGIC cota superior de la eólica que falta.

# COMMAND ----------

kind_by_up = {row["Código de UP"]: row["Tipo de producción"] for row in ups}
daily["kind"] = daily["unit"].map(kind_by_up).fillna("(fuera del listado)")
unlisted = daily[daily["kind"] == "(fuera del listado)"]

print("## P48 de las UP fuera del listado, por Tipo Oferta (MWh)")
print(unlisted.groupby(["month", "offer_type"])["mwh"].sum().unstack(fill_value=0).round(0))
print("\n## UP fuera del listado, por Tipo Oferta")
print(unlisted.groupby(["month", "offer_type"])["unit"].nunique().unstack(fill_value=0))
print("\n## Hueco 10010 - P (MWh)")
print((result["P48 10010 (MWh)"] - result["P (MWh)"]).round(0).to_dict())
