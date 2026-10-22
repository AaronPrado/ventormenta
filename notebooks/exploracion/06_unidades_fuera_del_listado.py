# Databricks notebook source
# MAGIC %md
# MAGIC # Unidades eólicas fuera del listado · parte 1: cierre con el 10010
# MAGIC
# MAGIC Parte 1 de la regla fijada antes de medir en `docs/unidades-fuera-del-listado.md`: se
# MAGIC ajusta un peso entre 0 y 1 a cada candidata, por mínimos cuadrados acotados contra el
# MAGIC residuo entre el 10010 y el P48 de las UP eólicas del listado. Las de peso al menos 0,5 son
# MAGIC eólicas, y el cierre `Q` tiene que quedar en el 1 % o menos en los tres meses.
# MAGIC
# MAGIC No hace ninguna petición: todo se lee del Volume. Sin cifras gallegas: solo el 10010
# MAGIC (ámbito Península), los I90 y el listado de unidades de programación.
# MAGIC
# MAGIC El paquete se instala desde el panel **Environment** (versión 6), con la ruta del wheel
# MAGIC que sube `databricks bundle deploy -t dev` a `artifacts/.internal/` del bundle: así llega
# MAGIC también a los ejecutores, que parsean los I90. La ruta cambia en cada despliegue. SciPy
# MAGIC viene en la base del entorno.

# COMMAND ----------

import json
import posixpath
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import scipy
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from scipy.optimize import lsq_linear

from ventormenta.closure import closure_error, closure_holds, residual, wind_by_weight
from ventormenta.units import UP_KEY, parse_listing, wind_units

print(f"ventormenta {version('ventormenta')} · scipy {scipy.__version__} · pandas {pd.__version__}")

# COMMAND ----------

files = WorkspaceClient().files
ESIOS_ROOT = "/Volumes/ventormenta/raw/esios"
ARCHIVES_DIR = posixpath.join(ESIOS_ROOT, "archives")
RANGES_DIR = posixpath.join(ESIOS_ROOT, "indicator_ranges")
MADRID = ZoneInfo("Europe/Madrid")
MONTHS = (date(2025, 1, 1), date(2025, 6, 1), date(2026, 1, 1))
QUARTER = timedelta(minutes=15)


def saved_files(directory: str) -> list[str]:
    """Ficheros guardados en ``directory``, en orden alfabético (el cronológico)."""
    try:
        # list() dentro del try: el listado es perezoso y NotFound llega al recorrerlo.
        entries = list(files.list_directory_contents(directory))
    except NotFound:
        return []
    names = sorted(e.name for e in entries if e.name and not e.is_directory)
    return [posixpath.join(directory, name) for name in names]


def read_bytes(path: str) -> bytes:
    """Contenido de un fichero del Volume."""
    contents = files.download(path).contents
    if contents is None:
        raise RuntimeError(f"descarga sin contenido: {path}")
    with contents:
        data: bytes = contents.read()
    return data


def load_json(path: str) -> dict[str, Any]:
    """Lee del Volume una respuesta JSON guardada."""
    return json.loads(read_bytes(path))


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


def month_bounds(month: date) -> tuple[datetime, datetime]:
    """Inicio y fin (excluido) del mes peninsular que empieza en ``month``, en UTC."""
    start = datetime(month.year, month.month, 1, tzinfo=MADRID)
    end = (start + timedelta(days=32)).replace(day=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def month_dir(indicator_id: int, month: date) -> str:
    """Carpeta de un indicador y un mes: ``<RANGES_DIR>/<id>/month=AAAA-MM``."""
    return posixpath.join(RANGES_DIR, str(indicator_id), f"month={month:%Y-%m}")


# COMMAND ----------

# MAGIC %md
# MAGIC ## Listado de unidades de programación
# MAGIC
# MAGIC UP eólicas (las de `P`), UP de tipo híbrido y códigos del listado. Los recuentos se
# MAGIC comparan con los documentados en `docs/fuentes-esios.md`.

# COMMAND ----------

ups = latest_listing(82, UP_KEY)
listed = frozenset(row["Código de UP"] for row in ups)
wind = wind_units(ups)
kinds = Counter(row["Tipo de producción"] for row in ups)

by_prefix = sorted(k for k in kinds if k.startswith("Híbrida"))
by_substring = sorted(k for k in kinds if "brid" in k.lower())
for kind in by_substring:
    print(f"{kind}: {kinds[kind]} UP")
if by_prefix != by_substring:
    raise RuntimeError(f"tipos híbridos sin el prefijo «Híbrida»: {by_substring}")

hybrids = frozenset(row["Código de UP"] for row in ups if row["Tipo de producción"] in by_prefix)
print(f"UP del listado: {len(listed)} · eólicas: {len(wind)} · híbridas: {len(hybrids)}")
if (len(wind), len(hybrids)) != (463, 38):
    raise RuntimeError("el listado no cuadra con docs/fuentes-esios.md (463 eólicas, 38 híbridas)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## P48 eólico peninsular de Red Eléctrica (10010)
# MAGIC
# MAGIC Una serie por mes, indexada por el instante UTC de inicio de cada cuarto de hora.

# COMMAND ----------

EXPECTED_QUARTERS = {"2025-01": 2976, "2025-06": 2880, "2026-01": 2976}


def quarter_series(indicator_id: int, month: date) -> dict[datetime, float]:
    """Energía (MWh) de cada cuarto de hora del mes, por instante UTC, de un indicador guardado.

    Comprueba que es energía, de una sola geo, sin nulos ni instantes repetidos, dentro del mes
    peninsular y con todos sus cuartos de hora seguidos.
    """
    envelope = load_json(saved_files(month_dir(indicator_id, month))[-1])
    indicator = json.loads(envelope["response"]["body"])["indicator"]
    key = f"{indicator_id} · {month:%Y-%m}"
    if [m["name"] for m in indicator["magnitud"]] != ["Energía"]:
        raise RuntimeError(f"{key}: no es energía")
    values = indicator["values"]
    if len({v["geo_id"] for v in values}) != 1:
        raise RuntimeError(f"{key}: más de una geo")
    start, end = month_bounds(month)
    series: dict[datetime, float] = {}
    for v in values:
        t = datetime.fromisoformat(v["datetime_utc"]).astimezone(UTC)
        if v["value"] is None or not start <= t < end or t in series:
            raise RuntimeError(f"{key}: valor nulo, fuera del mes o repetido en {t}")
        series[t] = float(v["value"])
    expected = [start + n * QUARTER for n in range((end - start) // QUARTER)]
    if sorted(series) != expected:
        raise RuntimeError(f"{key}: {len(series)} cuartos, se esperan {len(expected)} seguidos")
    return series


reference = {f"{m:%Y-%m}": quarter_series(10010, m) for m in MONTHS}
for key, series in reference.items():
    if len(series) != EXPECTED_QUARTERS[key]:
        raise RuntimeError(f"{key}: {len(series)} cuartos")
    print(
        f"{key}: {len(series)} cuartos · {min(series)} a {max(series)} · "
        f"{sum(series.values()) / 1000:,.1f} GWh"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## P48 de los I90, reducido en el ejecutor
# MAGIC
# MAGIC Cada zip se parsea una sola vez: la función devuelve ya reducido lo que necesita el
# MAGIC cierre. Con ramas de la API de DataFrame unidas, cada rama recalcularía su linaje y los
# MAGIC zips se parsearían más de una vez.

# COMMAND ----------

I90_DIR = posixpath.join(ARCHIVES_DIR, "34")
REDUCED_COLUMNS = ["kind", "data_date", "unit", "offer_type", "valid_time", "mwh"]
REDUCED_SCHEMA = (
    "kind string, data_date date, unit string, offer_type int, valid_time long, mwh double"
)
WIND_CODES = sorted(wind)
LISTED_CODES = sorted(listed)
HYBRID_CODES = sorted(hybrids)


def reduce_zips(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Parsea en el ejecutor cada zip de I90 y devuelve solo lo que necesita el cierre.

    Por día: ``P`` es la suma del P48 de las UP eólicas del listado en cada cuarto; ``C``, las
    filas no nulas de las candidatas (fuera del listado o híbridas), y ``U``, una fila por
    candidata con su tipo de oferta y su energía absoluta del día, también si es nula. Los
    instantes salen como segundos desde epoch: Spark no los convierte a ninguna zona.
    """
    from ventormenta.i90 import p48_rows, parse_p48

    for batch in batches:
        for data_date, content in zip(batch["data_date"], batch["content"], strict=True):
            day = pd.Timestamp(data_date).date()
            values = parse_p48(p48_rows(content, day), day)
            p48 = pd.DataFrame(
                {
                    "unit": [v.unit for v in values],
                    "offer_type": [v.offer_type for v in values],
                    "valid_time": [int(v.valid_time.timestamp()) for v in values],
                    "mwh": [v.mwh for v in values],
                }
            )
            listed_wind = (
                p48[p48["unit"].isin(WIND_CODES)].groupby("valid_time", as_index=False)["mwh"].sum()
            )
            candidates = p48[~p48["unit"].isin(LISTED_CODES) | p48["unit"].isin(HYBRID_CODES)]
            per_unit = (
                candidates.assign(mwh=candidates["mwh"].abs())
                .groupby(["unit", "offer_type"], as_index=False)["mwh"]
                .sum()
            )
            reduced = pd.concat(
                [
                    listed_wind.assign(kind="P", unit=None, offer_type=None),
                    candidates[candidates["mwh"] != 0].assign(kind="C"),
                    per_unit.assign(kind="U", valid_time=None),
                ]
            )
            yield reduced.assign(data_date=day)[REDUCED_COLUMNS].astype(
                {"offer_type": "Int32", "valid_time": "Int64"}
            )


# COMMAND ----------

EXPECTED_DAYS = {"2025-01": 31, "2025-06": 30, "2026-01": 31}
P_GWH_6_3 = {"2025-01": 6777.1, "2025-06": 2770.7, "2026-01": 7963.1}

zips = (
    spark.read.format("binaryFile")  # noqa: F821  (global de Databricks)
    .option("pathGlobFilter", "*.zip")
    .load(I90_DIR)
    .select("data_date", "content")
)
rows = zips.mapInPandas(reduce_zips, REDUCED_SCHEMA).toPandas()
rows["month"] = pd.to_datetime(rows["data_date"]).dt.strftime("%Y-%m")
print(f"{len(rows):,} filas")
print(rows.groupby(["month", "kind"]).size().unstack())


def to_series(frame: pd.DataFrame) -> dict[datetime, float]:
    """Serie por instante UTC a partir de filas con ``valid_time`` en segundos desde epoch."""
    if not frame["valid_time"].is_unique:
        raise RuntimeError("instantes repetidos: algún día tiene más de un zip")
    return {
        datetime.fromtimestamp(int(t), UTC): float(mwh)
        for t, mwh in zip(frame["valid_time"], frame["mwh"], strict=True)
    }


listed_p48 = {}
for key in reference:
    month_p = rows[(rows["kind"] == "P") & (rows["month"] == key)]
    days = month_p["data_date"].nunique()
    if days != EXPECTED_DAYS[key]:
        raise RuntimeError(f"{key}: {days} días con I90")
    listed_p48[key] = to_series(month_p)
    if listed_p48[key].keys() != reference[key].keys():
        raise RuntimeError(f"{key}: los cuartos del P48 no son los del 10010")
    p_gwh = sum(listed_p48[key].values()) / 1000
    e_gwh = sum(reference[key].values()) / 1000
    if abs(p_gwh - P_GWH_6_3[key]) > 0.05:
        raise RuntimeError(f"{key}: P = {p_gwh:,.1f} GWh, el 6.3 dio {P_GWH_6_3[key]:,.1f}")
    print(
        f"{key}: {days} días · P {p_gwh:,.1f} GWh · E - P {e_gwh - p_gwh:,.1f} GWh"
        f" ({(e_gwh - p_gwh) / e_gwh:.2%})"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pesos por mínimos cuadrados acotados
# MAGIC
# MAGIC Las candidatas con P48 nulo en todo el mes no entran en el ajuste (su peso no está
# MAGIC determinado y no cambian `Q`); se cuentan aparte.

# COMMAND ----------


def candidate_profiles(key: str) -> dict[str, dict[datetime, float]]:
    """Perfil de cada candidata con P48 no nulo en el mes, por instante UTC."""
    month_c = rows[(rows["kind"] == "C") & (rows["month"] == key)]
    return {str(unit): to_series(frame) for unit, frame in month_c.groupby("unit")}


fits = {}
for key in reference:
    profiles = candidate_profiles(key)
    units = sorted(profiles)
    instants = sorted(reference[key])
    outside = {t for p in profiles.values() for t in p} - set(instants)
    if outside:
        raise RuntimeError(f"{key}: {len(outside)} cuartos de candidatas fuera del mes")
    remaining = residual(reference[key], listed_p48[key])
    matrix = pd.DataFrame(
        {u: [profiles[u].get(t, 0.0) for t in instants] for u in units}, index=instants
    )
    result = lsq_linear(
        matrix.to_numpy(), [remaining[t] for t in instants], bounds=(0, 1), method="bvls"
    )
    if not result.success:
        raise RuntimeError(f"{key}: BVLS sin converger: {result.message}")
    fits[key] = (profiles, dict(zip(units, result.x.tolist(), strict=True)))
    all_candidates = rows[(rows["kind"] == "U") & (rows["month"] == key)]["unit"].nunique()
    print(
        f"{key}: {all_candidates} candidatas · {len(units)} con P48 no nulo en el ajuste ·"
        f" {all_candidates - len(units)} nulas · status {result.status} · {result.nit} iter ·"
        f" optimalidad {result.optimality:.2e}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cierre y condición 1

# COMMAND ----------

errors = {}
for key, (profiles, weights) in fits.items():
    wind_10010 = wind_by_weight(weights)
    errors[key] = closure_error(reference[key], listed_p48[key], profiles, wind_10010)
    print(f"{key}: {len(wind_10010)} eólicas según el 10010 · Q = {errors[key]:.4%}")

print(f"\nCondición 1 (Q ≤ 1 % en los tres meses): {closure_holds(errors.values())}")

# COMMAND ----------

# MAGIC %md
# MAGIC Control: `Q` en MWh, energía de las eólicas frente al residuo y, como control negativo,
# MAGIC `Q` sin ninguna eólica, que tiene que valer el hueco entero.

# COMMAND ----------

for key, (profiles, weights) in fits.items():
    wind_10010 = wind_by_weight(weights)
    energy = sum(reference[key].values())
    gap = sum(residual(reference[key], listed_p48[key]).values())
    explained = sum(sum(profiles[u].values()) for u in wind_10010)
    without_any = closure_error(reference[key], listed_p48[key], profiles, [])
    print(
        f"{key}: Q = {errors[key]:.3e} · sin explicar {errors[key] * energy:,.3f} MWh ·"
        f" R {gap:,.1f} MWh · eólicas según el 10010 {explained:,.1f} MWh ·"
        f" Q sin ninguna {without_any:.2%}"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Medidas de apoyo (no entran en la condición)

# COMMAND ----------

offer_types = (
    rows[rows["kind"] == "U"]
    .groupby(["month", "unit"])["offer_type"]
    .agg(lambda s: ",".join(str(o) for o in sorted(set(s))))
)
records = []
for key, (profiles, weights) in fits.items():
    wind_10010 = wind_by_weight(weights)
    for unit, weight in weights.items():
        records.append(
            {
                "month": key,
                "unit": unit,
                "weight": weight,
                "wind": unit in wind_10010,
                "hybrid": unit in hybrids,
                "offer_type": offer_types[(key, unit)],
                "gwh": sum(profiles[unit].values()) / 1000,
            }
        )
summary = pd.DataFrame(records)
summary["band"] = pd.cut(
    summary["weight"],
    [-float("inf"), 0.1, 0.9, float("inf")],
    right=False,
    labels=["< 0,1", "0,1-0,9", ">= 0,9"],
)

print("## 1 · Reparto de pesos (UP y GWh)")
bands = summary.groupby(["month", "band"], observed=False).agg(
    up=("unit", "size"), gwh=("gwh", "sum")
)
print(bands.round(1).unstack())

print("\n## 2 · Eólicas según el 10010 por Tipo Oferta")
print(summary[summary["wind"]].groupby(["month", "offer_type"]).size().unstack(fill_value=0))

print("\n## 3 · Pesos de las UP híbridas del listado")
print(summary[summary["hybrid"]].pivot(index="unit", columns="month", values="weight").round(3))

print("\n## 4 · UP con distinta clasificación según el mes")
classes = summary.pivot(index="unit", columns="month", values="wind")
print(classes[classes.apply(lambda r: r.dropna().nunique() > 1, axis=1)])

print("\n## 5 · Meses con P48 de las eólicas de fuera del listado")
outside = summary[summary["wind"] & ~summary["hybrid"]]
patterns = outside.groupby("unit")["month"].agg(lambda s: " + ".join(sorted(s)))
print(patterns.value_counts())
