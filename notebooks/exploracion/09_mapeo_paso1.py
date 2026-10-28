# Databricks notebook source
# MAGIC %md
# MAGIC # Mapeo del listado: paso 1

# COMMAND ----------

# MAGIC %pip install osmium==4.3.2

# COMMAND ----------

import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import osmium
import pandas as pd
from databricks.sdk import WorkspaceClient
from osmium.filter import TagFilter
from pyspark.sql import functions as F

# Sin Spark en el cálculo: basta con que el driver vea el paquete que sube el bundle a dev.
user = WorkspaceClient().current_user.me().user_name
sys.path.insert(0, f"/Workspace/Users/{user}/.bundle/ventormenta/dev/files/src")
from ventormenta.mapping import (  # noqa: E402
    Park,
    UfClass,
    candidates,
    park_from_plant,
    step1_class,
    up_class,
)
from ventormenta.names import null_threshold  # noqa: E402
from ventormenta.osm import Plant, plant_from_tags  # noqa: E402
from ventormenta.units import UF_KEY, UP_KEY, parse_listing, parse_mw, wind_units  # noqa: E402

# COMMAND ----------

OSM_ROOT = Path("/Volumes/ventormenta/raw/osm/geofabrik")
ESIOS_ARCHIVES = Path("/Volumes/ventormenta/raw/esios/archives")
EXTRACT_DATE = date(2026, 10, 25)
TABLE = "ventormenta.mapeo.uf"
MAPPING_VERSION = "v1"
# Una versión congelada no se reescribe: se añade aquí al poner su tag.
FROZEN_VERSIONS: frozenset[str] = frozenset()
# Lo publicado en docs/mapeo-listado.md: si los datos o el código ya no lo reproducen, se para.
PUBLISHED_T = 0.4444
PUBLISHED_PARKS = {"galicia": 177, "resto": 887}
PUBLISHED_LISTING = {"uf": 1166, "up": 463, "mw": 32072.4}
PUBLISHED_AGGREGATORS = {"up": 24, "mw": 16667.3}
AGGREGATOR_MIN_UFS = 6

# COMMAND ----------

PBF = ".osm.pbf"


def extract_path(region: str) -> Path:
    """El extracto de ``region``, solo si su JSON dice que la descarga terminó."""
    folder = OSM_ROOT / region / f"extract_date={EXTRACT_DATE.isoformat()}"
    complete = [
        pbf
        for pbf in sorted(folder.glob(f"*{PBF}"))
        if pbf.with_name(pbf.name.removesuffix(PBF) + ".json").exists()
    ]
    if len(complete) != 1:
        raise RuntimeError(f"{folder}: se esperaba un extracto completo y hay {len(complete)}")
    return complete[0]


def read_wind_plants(path: Path) -> list[Plant]:
    """Los elementos con ``power=plant`` y «wind» en ``plant:source``, como al calibrar T."""
    processor = osmium.FileProcessor(str(path)).with_filter(TagFilter(("power", "plant")))
    plants = []
    for obj in processor:
        # El objeto solo vale durante su iteración: se copia lo que hace falta.
        tags = {tag.k: tag.v for tag in obj.tags}
        members = [(m.type, m.ref) for m in obj.members] if obj.is_relation() else []
        plant = plant_from_tags(obj.type_str(), obj.id, tags, members)
        if plant.source is not None and "wind" in plant.source:
            plants.append(plant)
    return plants


galicia_ids = {(p.osm_type, p.osm_id) for p in read_wind_plants(extract_path("galicia"))}
spain = read_wind_plants(extract_path("spain"))
if missing := galicia_ids - {(p.osm_type, p.osm_id) for p in spain}:
    raise RuntimeError(f"{len(missing)} parques de Galicia no están en el extracto de España")
parks = [park_from_plant(p, galicia=(p.osm_type, p.osm_id) in galicia_ids) for p in spain]

counts = {"galicia": sum(p.galicia for p in parks), "resto": sum(not p.galicia for p in parks)}
if counts != PUBLISHED_PARKS:
    raise RuntimeError(f"parques {counts}, publicados {PUBLISHED_PARKS}")
print(f"parques eólicos: {counts}")

# COMMAND ----------


def park_profile(park: Park) -> tuple[frozenset[str], ...]:
    """El perfil de ``names.profile``: los trigramas de sus nombres, sin repetir."""
    return tuple(dict.fromkeys(trigrams for _, trigrams in park.forms))


T = null_threshold(
    [park_profile(p) for p in parks if p.galicia],
    [park_profile(p) for p in parks if not p.galicia],
)
if round(T, 4) != PUBLISHED_T:
    raise RuntimeError(f"T = {T:.4f}, publicado {PUBLISHED_T}")
print(f"T = {T:.4f}")

# COMMAND ----------


def latest_listing(archive_id: int, key: str) -> tuple[date, list[dict[str, str]]]:
    """Fecha y registros de la última captura del listado ``archive_id`` en el Volume."""
    captures = sorted((ESIOS_ARCHIVES / str(archive_id)).glob("capture_date=*"))
    if not captures:
        raise RuntimeError(f"sin capturas del listado {archive_id}")
    bodies = sorted(captures[-1].glob("*.data.json"))
    if len(bodies) != 1:
        raise RuntimeError(f"{captures[-1]}: {len(bodies)} cuerpos, se espera uno")
    capture_date = date.fromisoformat(captures[-1].name.removeprefix("capture_date="))
    return capture_date, parse_listing(bodies[0].read_bytes(), key)


up_date, ups = latest_listing(82, UP_KEY)
uf_date, ufs = latest_listing(81, UF_KEY)
if up_date != uf_date:
    raise RuntimeError(f"listados de fechas distintas: UP {up_date}, UF {uf_date}")
LISTING_DATE = uf_date

wind_ups = wind_units(ups)
wind_ufs = [row for row in ufs if row["Vinculación con UP"] in wind_ups]
uf_mw = {row["Código de UF"]: parse_mw(row["Potencia máxima MW"]) for row in wind_ufs}
if len(uf_mw) != len(wind_ufs):
    raise RuntimeError("códigos de UF repetidos en el listado")

listing = {
    "uf": len(wind_ufs),
    "up": len({row["Vinculación con UP"] for row in wind_ufs}),
    "mw": round(sum(mw or 0.0 for mw in uf_mw.values()), 1),
}
if listing != PUBLISHED_LISTING:
    raise RuntimeError(f"listado {listing}, publicado {PUBLISHED_LISTING}")
unknown_mw = sum(mw is None for mw in uf_mw.values())
print(f"listado del {LISTING_DATE}: {listing} · UF sin potencia: {unknown_mw}")

# COMMAND ----------

ufs_by_up: defaultdict[str, list[str]] = defaultdict(list)
for row in wind_ufs:
    ufs_by_up[row["Vinculación con UP"]].append(row["Código de UF"])

matches = {row["Código de UF"]: candidates(row["Descripción larga"], parks, T) for row in wind_ufs}

uf_class: dict[str, UfClass] = {}
uf_step: dict[str, str] = {}
for code, found in matches.items():
    step1 = step1_class(found)
    # Sin ubicar por el paso 1 queda desconocida; el paso 2 reescribirá esta versión entera.
    uf_class[code] = step1 or UfClass.UNKNOWN
    uf_step[code] = "paso1" if step1 else "ninguno"

up_classes = {up: up_class(uf_class[code] for code in codes) for up, codes in ufs_by_up.items()}

# COMMAND ----------

if MAPPING_VERSION in FROZEN_VERSIONS:
    raise RuntimeError(f"la versión {MAPPING_VERSION} está congelada: no se reescribe")

computed_at = datetime.now(UTC)
records = []
for row in wind_ufs:
    code, up = row["Código de UF"], row["Vinculación con UP"]
    found = matches[code]
    best = found[0] if found else None
    records.append(
        {
            "mapping_version": MAPPING_VERSION,
            "uf_code": code,
            "up_code": up,
            "uf_description": row["Descripción larga"],
            "uf_mw": uf_mw[code],
            "listing_capture_date": LISTING_DATE,
            "osm_extract_date": EXTRACT_DATE,
            "uf_class": uf_class[code].value,
            "uf_step": uf_step[code],
            "best_osm_type": best.park.osm_type if best else None,
            "best_osm_id": best.park.osm_id if best else None,
            "best_osm_name": best.name if best else None,
            "best_similarity": best.similarity if best else None,
            "candidates_galicia": sum(c.park.galicia for c in found),
            "candidates_rest": sum(not c.park.galicia for c in found),
            "up_class": up_classes[up].value,
            "computed_at": computed_at,
        }
    )

# El esquema de la tabla fija el orden y los tipos; las filas se ordenan por él, no a mano.
schema = spark.table(TABLE).schema  # noqa: F821
rows = [tuple(record[name] for name in schema.fieldNames()) for record in records]
(
    spark.createDataFrame(rows, schema)  # noqa: F821
    .write.mode("overwrite")
    .option("replaceWhere", f"mapping_version = '{MAPPING_VERSION}'")
    .saveAsTable(TABLE)
)

written = (
    spark.table(TABLE)  # noqa: F821
    .where(F.col("mapping_version") == MAPPING_VERSION)
    .agg(F.count("*").alias("n"), F.countDistinct("uf_code").alias("codes"))
    .first()
)
if (written.n, written.codes) != (len(records), len(records)):
    raise RuntimeError(f"{written.n} filas y {written.codes} UF escritas, {len(records)} esperadas")
print(f"{TABLE}, versión {MAPPING_VERSION}: {written.n} filas")

# COMMAND ----------

mapping = pd.DataFrame(records)
mapping["ufs_in_up"] = mapping["up_code"].map(lambda up: len(ufs_by_up[up]))
mapping["unplaced"] = [
    None if step != "ninguno" else "sin candidatos" if galicia + rest == 0 else "mezclados"
    for step, galicia, rest in zip(
        mapping["uf_step"], mapping["candidates_galicia"], mapping["candidates_rest"], strict=True
    )
]
agg = mapping[mapping["ufs_in_up"] >= AGGREGATOR_MIN_UFS]

found_aggregators = {"up": agg["up_code"].nunique(), "mw": round(agg["uf_mw"].sum(), 1)}
if found_aggregators != PUBLISHED_AGGREGATORS:
    raise RuntimeError(f"agregadoras {found_aggregators}, publicadas {PUBLISHED_AGGREGATORS}")


def mw_table(frame: pd.DataFrame, by: str | list[str]) -> str:
    """Unidades y MW por ``by``, redondeados a una décima."""
    return frame.groupby(by)["uf_mw"].agg(["count", "sum"]).round(1).to_string()


print("== UF de las agregadoras por clase")
print(mw_table(agg, "uf_class"))
print("== UF sin ubicar de las agregadoras, por motivo")
print(mw_table(agg, "unplaced"))

ups_agg = agg.groupby("up_code").agg(up_class=("up_class", "first"), uf_mw=("uf_mw", "sum"))
print("== agregadoras por clase")
print(mw_table(ups_agg, "up_class"))

stuck = agg[agg["uf_class"].eq("gallega") & agg["up_class"].isin(["mixta", "desconocida"])]
print("== MW de UF gallegas en agregadoras mixtas o desconocidas")
print(mw_table(stuck, ["up_code", "up_class"]))
print(f"total: {stuck['uf_mw'].sum():.1f} MW en {len(stuck)} UF")
