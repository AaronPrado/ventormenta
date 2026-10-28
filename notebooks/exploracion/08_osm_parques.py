# Databricks notebook source
# MAGIC %md
# MAGIC # Parques eólicos de OpenStreetMap
# MAGIC
# MAGIC Descarga única de los extractos fechados de Geofabrik de España y de Galicia en el Volume
# MAGIC `raw.osm`. Un parque es gallego si también está en el extracto de Galicia de la misma fecha
# MAGIC (`docs/mapeo-listado.md`). OpenStreetMap es ODbL: lo que se derive de estos ficheros se
# MAGIC guarda aparte.
# MAGIC
# MAGIC Sin Spark: el paquete se lee desde los ficheros que sube `databricks bundle deploy -t dev`.
# MAGIC Tras cada despliegue, ejecutar todo (relee España en unos minutos sin pedir nada).

# COMMAND ----------

# MAGIC %pip install osmium==4.3.2 shapely==2.1.2

# COMMAND ----------

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import quantiles

import osmium
import pandas as pd
import requests
import shapely
from databricks.sdk import WorkspaceClient
from osmium.filter import IdFilter, TagFilter
from osmium.geom import WKBFactory

# Sin Spark basta con que el driver vea el paquete: los ficheros que sube el bundle a dev.
user = WorkspaceClient().current_user.me().user_name
sys.path.insert(0, f"/Workspace/Users/{user}/.bundle/ventormenta/dev/files/src")
from ventormenta.names import (  # noqa: E402
    best_matches,
    best_similarity,
    comparable,
    normalize,
    null_threshold,
    profile,
)
from ventormenta.osm import (  # noqa: E402
    BorderClass,
    Plant,
    border_class,
    member_ids,
    name_variants,
    plant_from_tags,
    plant_points,
)
from ventormenta.units import UF_KEY, UP_KEY, parse_listing, wind_units  # noqa: E402

print(
    f"osmium {version('osmium')} · shapely {version('shapely')} · numpy {version('numpy')}"
    f" · pandas {pd.__version__}"
)

# COMMAND ----------

USER_AGENT = "VenTormenta/0.1"
GEOFABRIK_URL = "https://download.geofabrik.de/europe"
EXTRACT_DATE = "2026-10-25"
EXTRACTS = {"spain": "spain", "galicia": "spain/galicia"}
OSM_ROOT = "/Volumes/ventormenta/raw/osm/geofabrik"
FORMAT_VERSION = 1
TIMEOUT_SECONDS = 60
PAUSE_SECONDS = 5
CHUNK_BYTES = 8 * 1024 * 1024


def extract_url(path: str) -> str:
    """URL del extracto fechado: Geofabrik nombra los ficheros por día con ``AAMMDD``."""
    day = date.fromisoformat(EXTRACT_DATE)
    return f"{GEOFABRIK_URL}/{path}-{day:%y%m%d}.osm.pbf"


def download_extract_once(region: str, path: str) -> bool:
    """Descarga el extracto de ``region`` si su carpeta está vacía; True si ha pedido algo.

    Una carpeta con algo dentro no se vuelve a pedir: un ``.osm.pbf`` sin su JSON es una
    descarga a medias y se revisa a mano. El fichero se baja por trozos a un temporal, se
    valida (tamaño y cabecera PBF) y solo entonces se copia al Volume; el JSON va el último.
    """
    directory = f"{OSM_ROOT}/{region}/extract_date={EXTRACT_DATE}"
    os.makedirs(directory, exist_ok=True)
    if os.listdir(directory):
        print(f"{region}: la carpeta ya tiene ficheros, no se pide")
        return False
    url = extract_url(path)
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory() as scratch:
        local = os.path.join(scratch, "extract.osm.pbf")
        requested_at = datetime.now(UTC)
        try:
            with requests.get(
                url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=TIMEOUT_SECONDS
            ) as response:
                response.raise_for_status()
                expected = int(response.headers["Content-Length"])
                with open(local, "wb") as out:
                    for chunk in response.iter_content(CHUNK_BYTES):
                        out.write(chunk)
                        digest.update(chunk)
                status_code = response.status_code
                server_date = response.headers.get("Date")
                last_modified = response.headers.get("Last-Modified")
        except requests.RequestException as err:
            raise RuntimeError(f"Geofabrik, {region}: {err}") from err
        received_at = datetime.now(UTC)
        size = os.path.getsize(local)
        if size != expected:
            raise RuntimeError(f"Geofabrik, {region}: {size} bytes de {expected}")
        # Abrir solo la cabecera valida que es un PBF y da el instante de los datos.
        reader = osmium.io.Reader(local, osmium.osm.osm_entity_bits.NOTHING)
        try:
            data_timestamp = reader.header().get("osmosis_replication_timestamp")
        finally:
            reader.close()
        stem = f"{received_at:%Y%m%dT%H%M%SZ}"
        shutil.copyfile(local, f"{directory}/{stem}.osm.pbf")
    sidecar = {
        "format_version": FORMAT_VERSION,
        "source": "geofabrik",
        "region": region,
        "extract_date": EXTRACT_DATE,
        "request": {"method": "GET", "url": url},
        "requested_at": requested_at.isoformat(),
        "received_at": received_at.isoformat(),
        "status_code": status_code,
        "server_date": server_date,
        "last_modified": last_modified,
        "size": size,
        "sha256": digest.hexdigest(),
        "osmosis_replication_timestamp": data_timestamp or None,
        "osmium_version": version("osmium"),
    }
    with open(f"{directory}/{stem}.json", "x", encoding="utf-8") as out:
        json.dump(sidecar, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(f"{region}: {size} bytes, datos hasta {data_timestamp}, {stem}")
    return True


# COMMAND ----------

for index, (region, path) in enumerate(EXTRACTS.items()):
    if download_extract_once(region, path) and index < len(EXTRACTS) - 1:
        time.sleep(PAUSE_SECONDS)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Primera pasada: elementos con power=plant
# MAGIC
# MAGIC Sin ubicaciones: tipo, identificador, `plant:source`, etiquetas de nombre y lista de claves,
# MAGIC sin sus valores. Sin cruzar con el listado de unidades y sin ninguna cifra de los parques.

# COMMAND ----------

PBF = ".osm.pbf"


def extract_path(region: str) -> Path:
    """El extracto de ``region``, solo si su JSON dice que la descarga terminó."""
    folder = Path(OSM_ROOT, region, f"extract_date={EXTRACT_DATE}")
    complete = [
        pbf
        for pbf in sorted(folder.glob(f"*{PBF}"))
        if pbf.with_name(pbf.name.removesuffix(PBF) + ".json").exists()
    ]
    if len(complete) != 1:
        raise RuntimeError(f"{folder}: se esperaba un extracto completo y hay {len(complete)}")
    return complete[0]


def read_plants(path: Path) -> list[Plant]:
    """Primera pasada, sin ubicaciones: los elementos con ``power=plant``."""
    processor = osmium.FileProcessor(str(path)).with_filter(TagFilter(("power", "plant")))
    plants = []
    for obj in processor:
        # El objeto solo vale durante su iteración: se copia lo que hace falta.
        tags = {tag.k: tag.v for tag in obj.tags}
        members = [(m.type, m.ref) for m in obj.members] if obj.is_relation() else []
        plants.append(plant_from_tags(obj.type_str(), obj.id, tags, members))
    return plants


def key_inventory(plants: pd.DataFrame) -> pd.Series:
    """Cuántos elementos de ``plants`` tienen cada clave, de más a menos."""
    counts = Counter(key for keys in plants["keys"] for key in keys)
    return pd.Series(counts, name="elementos").sort_values(ascending=False)


# COMMAND ----------

galicia = pd.DataFrame(read_plants(extract_path("galicia")))
wind = galicia["source"].str.contains("wind", na=False)
named = galicia["names"].map(bool)

repeated = galicia.duplicated(["osm_type", "osm_id"]).sum()
print(f"power=plant: {len(galicia)} · repetidos por (tipo, id): {repeated}")
print(pd.crosstab(galicia["source"].fillna("(sin plant:source)"), galicia["osm_type"]).to_string())
print(f"con «wind» en plant:source: {wind.sum()} · de ellos con nombre: {(wind & named).sum()}")
print(key_inventory(galicia[wind]).to_string())

# COMMAND ----------

wind_relations = galicia[wind & (galicia["osm_type"] == "r")]
member_types = Counter(kind for members in wind_relations["members"] for kind, _ in members)
print(f"miembros de las relaciones eólicas, por tipo: {dict(member_types)}")
print(wind_relations["members"].map(len).describe().to_string())

print("sin plant:source:")
print(galicia.loc[galicia["source"].isna(), ["osm_type", "osm_id", "names"]].to_string())
print("eólicos sin nombre:")
print(galicia.loc[wind & ~named, ["osm_type", "osm_id", "keys"]].to_string())

# COMMAND ----------

spain = pd.DataFrame(read_plants(extract_path("spain")))
spain_wind = spain["source"].str.contains("wind", na=False)
spain_named = spain["names"].map(bool)

repeated = spain.duplicated(["osm_type", "osm_id"]).sum()
print(f"power=plant: {len(spain)} · repetidos por (tipo, id): {repeated}")
print(pd.crosstab(spain["source"].fillna("(sin plant:source)"), spain["osm_type"]).to_string())
print(
    f"con «wind» en plant:source: {spain_wind.sum()} · "
    f"de ellos con nombre: {(spain_wind & spain_named).sum()}"
)

galicia_ids = set(zip(galicia["osm_type"], galicia["osm_id"], strict=True))
spain_ids = set(zip(spain["osm_type"], spain["osm_id"], strict=True))
print(f"elementos de Galicia que no están en España: {len(galicia_ids - spain_ids)}")

# COMMAND ----------

unsourced = spain[spain["source"].isna()]
print(unsourced[["osm_type", "osm_id", "names"]].to_string())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Nombres de los parques eólicos, cada lado por separado
# MAGIC
# MAGIC Solo OpenStreetMap, sin el listado de unidades: palabras frecuentes, prefijos, fases y
# MAGIC numerales, homónimos y variantes de nombre. Sirve para fijar las palabras de tipo y las
# MAGIC variantes del paso 1 antes de cruzar nada.

# COMMAND ----------

ROMAN = re.compile(r"[ivx]+")
PHASE_WORDS = ("fase", "ampliacion", "repotenciacion", "extension")

parks = spain[spain_wind].copy()
parks["galicia"] = [
    (kind, osm_id) in galicia_ids
    for kind, osm_id in zip(parks["osm_type"], parks["osm_id"], strict=True)
]
parks["norm"] = parks["names"].map(lambda names: normalize(names.get("name", "")))
parks["words"] = parks["norm"].map(str.split)
named_parks = parks[parks["norm"] != ""]
SIDES = {
    "Galicia": named_parks[named_parks["galicia"]],
    "resto": named_parks[~named_parks["galicia"]],
}


def word_share(words: pd.Series) -> pd.Series:
    """En qué fracción de los nombres sale cada palabra (una vez por nombre)."""
    counts = Counter(word for name in words for word in set(name))
    return (pd.Series(counts) / len(words)).sort_values(ascending=False)


for side, group in SIDES.items():
    print(f"== {side}: {len(group)} parques con name")
    print(word_share(group["words"]).head(40).round(3).to_string())
    print("primeras dos palabras:")
    print(group["words"].map(lambda w: " ".join(w[:2])).value_counts().head(15).to_string())

# COMMAND ----------

for side, group in SIDES.items():
    last = group["words"].map(lambda w: w[-1])
    numeral = last.str.fullmatch(r"\d+") | last.map(lambda w: bool(ROMAN.fullmatch(w)))
    phase = group["words"].map(lambda w: any(p in w for p in PHASE_WORDS))
    print(f"== {side}: acaban en numeral {numeral.sum()} · con palabra de fase {phase.sum()}")
    print(group.loc[numeral | phase, "norm"].head(20).to_string())

print("== homónimos (mismo name normalizado en los dos lados)")
both = set(SIDES["Galicia"]["norm"]) & set(SIDES["resto"]["norm"])
print(sorted(both))
print("== repetidos dentro de cada lado")
for side, group in SIDES.items():
    print(side, group["norm"].value_counts().loc[lambda c: c > 1].to_dict())

print("== variantes: parques con más etiquetas de nombre que name")
variants = parks[parks["names"].map(lambda names: set(names) - {"name"} != set())]
print(variants[["galicia", "osm_type", "osm_id", "names"]].to_string())
with_semicolon = parks["names"].map(lambda names: any(";" in v for v in names.values()))
print(f"con «;» en algún valor: {with_semicolon.sum()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Descripciones del listado, sin cruzarlas con nada
# MAGIC
# MAGIC Forma de las descripciones corta y larga de las UF de las UP eólicas: abreviaturas, palabras
# MAGIC frecuentes, prefijos, numerales y fases. Solo para cerrar la normalización común a los dos
# MAGIC lados; ningún parecido con OpenStreetMap.

# COMMAND ----------

ESIOS_ARCHIVES = Path("/Volumes/ventormenta/raw/esios/archives")


def latest_listing(archive_id: int, key: str) -> list[dict[str, str]]:
    """Registros de la última captura del listado ``archive_id`` guardada en el Volume."""
    captures = sorted((ESIOS_ARCHIVES / str(archive_id)).glob("capture_date=*"))
    if not captures:
        raise RuntimeError(f"sin capturas del listado {archive_id}")
    bodies = sorted(captures[-1].glob("*.data.json"))
    if len(bodies) != 1:
        raise RuntimeError(f"{captures[-1]}: {len(bodies)} cuerpos, se espera uno")
    return parse_listing(bodies[0].read_bytes(), key)


wind_ups = wind_units(latest_listing(82, UP_KEY))
wind_ufs = pd.DataFrame(
    [row for row in latest_listing(81, UF_KEY) if row["Vinculación con UP"] in wind_ups]
)
desc_keys = [key for key in wind_ufs.columns if key.startswith("Descripción")]
print(f"UF eólicas: {len(wind_ufs)} de {wind_ufs['Vinculación con UP'].nunique()} UP")
print(f"campos: {list(wind_ufs.columns)}")
print(f"descripciones: {desc_keys}")

# COMMAND ----------

for key in desc_keys:
    raw = wind_ufs[key].str.strip()
    norms = raw.map(normalize)
    words = norms[norms != ""].map(str.split)
    print(f"== {key}: vacías {(norms == '').sum()} · caracteres (mediana) {raw.str.len().median()}")
    print("primera palabra tal cual:")
    print(raw.str.split().str[0].value_counts().head(20).to_string())
    print("palabras más frecuentes (fracción de descripciones):")
    print(word_share(words).head(40).round(3).to_string())
    print("primeras dos palabras normalizadas:")
    print(words.map(lambda w: " ".join(w[:2])).value_counts().head(20).to_string())
    last = words.map(lambda w: w[-1])
    numeral = last.str.fullmatch(r"\d+") | last.map(lambda w: bool(ROMAN.fullmatch(w)))
    phase = words.map(lambda w: any(p in w for p in PHASE_WORDS))
    print(f"acaban en numeral: {numeral.sum()} · con palabra de fase: {phase.sum()}")

same = (wind_ufs[desc_keys[0]].map(normalize) == wind_ufs[desc_keys[1]].map(normalize)).sum()
print(f"== corta y larga iguales tras normalizar: {same} de {len(wind_ufs)}")
sample = wind_ufs.sort_values("Código de UF").iloc[:: max(len(wind_ufs) // 25, 1)]
print(sample[["Código de UF", *desc_keys]].to_string())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Umbral T, solo con OpenStreetMap
# MAGIC
# MAGIC Mejor parecido de cada parque eólico gallego con nombre útil con los del resto de España,
# MAGIC con la forma comparable y todas las etiquetas de nombre. T es el percentil 95 de esos
# MAGIC parecidos (`docs/mapeo-listado.md`, paso 1).

# COMMAND ----------

parks["variants"] = parks["names"].map(name_variants)
parks["profile"] = parks["variants"].map(profile)
parks["forms"] = parks["variants"].map(lambda names: {comparable(n) for n in names} - {""})
galicia_profiles = parks.loc[parks["galicia"], "profile"].tolist()
rest_profiles = parks.loc[~parks["galicia"], "profile"].tolist()

T = null_threshold(galicia_profiles, rest_profiles)
for side, profiles in (("Galicia", galicia_profiles), ("resto", rest_profiles)):
    unnamed = sum(not p for p in profiles)
    print(f"{side}: {len(profiles)} parques eólicos · sin nombre útil: {unnamed}")
print(f"T = {T:.4f}")
null = pd.Series(best_matches(galicia_profiles, rest_profiles))
print(null.describe(percentiles=[0.5, 0.9, 0.95, 0.99]).round(3).to_string())

# COMMAND ----------

named = parks[parks["profile"].map(bool)]
galicia_named, rest_named = named[named["galicia"]], named[~named["galicia"]]
rest_forms = set().union(*rest_named["forms"])
homonyms = galicia_named[galicia_named["forms"].map(lambda forms: bool(forms & rest_forms))]
print(f"== homónimos (misma forma comparable a los dos lados): {len(homonyms)}")
print(homonyms["variants"].to_string())

pairs = []
for galicia_park in galicia_named.itertuples():
    scores = [best_similarity(galicia_park.profile, other) for other in rest_named["profile"]]
    best = max(range(len(scores)), key=scores.__getitem__)
    pairs.append((scores[best], galicia_park.variants[0], rest_named["variants"].iloc[best][0]))
top = pd.DataFrame(pairs, columns=["parecido", "Galicia", "resto"])
print("== pares Galicia-resto más parecidos")
print(top.sort_values("parecido", ascending=False).head(25).round(3).to_string(index=False))

# COMMAND ----------


def cross_hits(side: pd.DataFrame, other: pd.DataFrame) -> tuple[int, Counter[str]]:
    """Parques de ``side`` con algún parque de ``other`` en T o más, y qué parques son."""
    with_hit, culprits = 0, Counter[str]()
    for park in side.itertuples():
        over = [
            o.variants[0]
            for o in other.itertuples()
            if best_similarity(park.profile, o.profile) >= T
        ]
        with_hit += bool(over)
        culprits.update(over)
    return with_hit, culprits


SIDE_PAIRS = (("Galicia", galicia_named, rest_named), ("resto", rest_named, galicia_named))
for label, side, other in SIDE_PAIRS:
    with_hit, culprits = cross_hits(side, other)
    print(f"== {label}: {with_hit} de {len(side)} con algún parque del otro lado en T o más")
    table = pd.DataFrame(culprits.most_common(15), columns=["parque del otro lado", "veces"])
    table["forma comparable"] = table["parque del otro lado"].map(comparable)
    print(table.to_string(index=False))

# COMMAND ----------

galicia_best = best_matches(galicia_profiles, rest_profiles)
T_GALICIA = quantiles(galicia_best, n=100, method="inclusive")[94]
same_park = [
    best_similarity((a,), (b,))
    for prof in parks["profile"]
    for i, a in enumerate(prof)
    for b in prof[i + 1 :]
]
for label, threshold in (("T actual", T), ("T solo Galicia frente al resto", T_GALICIA)):
    print(f"== {label}: {threshold:.4f}")
    for side_label, side, other in SIDE_PAIRS:
        hits = sum(
            any(best_similarity(p.profile, o.profile) >= threshold for o in other.itertuples())
            for p in side.itertuples()
        )
        print(f"   {side_label}: {hits} de {len(side)} con algún parque del otro lado")
    kept = sum(s >= threshold for s in same_park)
    print(f"   nombres distintos de un mismo parque que se reconocen: {kept} de {len(same_park)}")
print(pd.Series(same_park).describe().round(3).to_string())

# COMMAND ----------

rows = []
for variants in parks["variants"]:
    forms = list(dict.fromkeys(form for form in map(comparable, variants) if form))
    rows += [
        (best_similarity(profile([a]), profile([b])), a, b)
        for i, a in enumerate(forms)
        for b in forms[i + 1 :]
    ]
same = pd.DataFrame(rows, columns=["parecido", "forma a", "forma b"])
same["T actual"] = same["parecido"] >= T
same["T Galicia"] = same["parecido"] >= T_GALICIA
print(same.sort_values("parecido", ascending=False).round(3).to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Frontera de Galicia
# MAGIC
# MAGIC Dónde quedan los parques eólicos respecto al límite oficial de Galicia
# MAGIC (`boundary=administrative`, `admin_level=4`), contando solo elementos de OpenStreetMap: ni
# MAGIC potencias ni parecidos con el listado. No cambia la regla: un parque sigue siendo gallego si
# MAGIC está en el extracto de Galicia.

# COMMAND ----------

GALICIA_BOUNDARY = {"boundary": "administrative", "admin_level": "4", "name": "Galicia"}
ADMIN_LEVEL_4 = TagFilter(("admin_level", "4"))


def read_boundary(path: Path) -> tuple[int, shapely.MultiPolygon]:
    """El límite de Galicia en ``path``: el id de su relación y su geometría ensamblada.

    ``with_areas`` ensambla en C++ las relaciones que pasan su filtro (y cada vía cerrada), y
    ``with_filter`` solo deja llegar a Python lo que tiene ``admin_level=4``. Si el extracto
    no trae la relación entera, el anillo no cierra, no sale el área y se lanza el error.
    """
    processor = osmium.FileProcessor(str(path)).with_areas(ADMIN_LEVEL_4).with_filter(ADMIN_LEVEL_4)
    wkb = WKBFactory()
    found, seen = [], []
    for obj in processor:
        if obj.type_str() != "a" or obj.from_way():
            continue
        tags = {tag.k: tag.v for tag in obj.tags}
        seen.append(tags.get("name"))
        if all(tags.get(k) == v for k, v in GALICIA_BOUNDARY.items()):
            found.append((obj.orig_id(), shapely.from_wkb(wkb.create_multipolygon(obj))))
    if len(found) != 1:
        raise RuntimeError(f"{path.name}: {len(found)} áreas de Galicia; admin_level=4: {seen}")
    return found[0]


relation_id, boundary = read_boundary(extract_path("galicia"))
shapely.prepare(boundary)
min_lon, min_lat, max_lon, max_lat = boundary.bounds
print(f"relación r{relation_id} · válido: {boundary.is_valid} · polígonos: {len(boundary.geoms)}")
print(f"lon {min_lon:.3f} a {max_lon:.3f} · lat {min_lat:.3f} a {max_lat:.3f}")
# Unos 5 km al oeste del cabo Fisterra: mar territorial (12 millas), no tierra.
SEA_POINT = (-9.33, 42.88)
print(f"incluye el mar territorial: {shapely.intersects_xy(boundary, *SEA_POINT)}")

# COMMAND ----------

plants = [
    Plant(row.osm_type, int(row.osm_id), row.source, row.names, row.keys, row.members)
    for row in parks.itertuples()
]
node_ids, way_ids = member_ids(plants)


def point(location: osmium.osm.Location) -> tuple[float, float] | None:
    """Longitud y latitud de una ubicación, o None si no es válida."""
    return (location.lon, location.lat) if location.valid() else None


started = time.monotonic()
# El índice de ubicaciones va antes que el filtro: las vías filtradas llegan con coordenadas.
processor = (
    osmium.FileProcessor(str(extract_path("spain")), osmium.osm.NODE | osmium.osm.WAY)
    .with_locations()
    .with_filter(IdFilter(node_ids | way_ids))
)
nodes, ways = {}, {}
for obj in processor:
    # IdFilter no distingue tipos: cada elemento se separa con el conjunto de su tipo.
    if obj.is_node() and obj.id in node_ids:
        nodes[obj.id] = point(obj.location)
    elif obj.is_way() and obj.id in way_ids:
        ways[obj.id] = [point(ref.location) for ref in obj.nodes]
print(f"{time.monotonic() - started:.0f} s")
print(f"nodos: {len(nodes)} de {len(node_ids)} · vías: {len(ways)} de {len(way_ids)}")

# COMMAND ----------

rows = []
for plant, in_galicia, names in zip(plants, parks["galicia"], parks["names"], strict=True):
    located = plant_points(plant, nodes, ways)
    xs = [lon for lon, _ in located.points]
    ys = [lat for _, lat in located.points]
    inside = shapely.intersects_xy(boundary, xs, ys)
    rows.append(
        {
            "elemento": f"{plant.osm_type}{plant.osm_id}",
            "name": names.get("name", ""),
            "galicia": in_galicia,
            "clase": border_class(inside).value,
            "puntos": len(located.points),
            "dentro": int(inside.sum()),
            "sin_ubicar": located.unlocated,
        }
    )
border = pd.DataFrame(rows)

print(pd.crosstab(border["galicia"], border["clase"], margins=True).to_string())
print(border.groupby("galicia")["sin_ubicar"].agg(["sum", lambda s: (s > 0).sum()]).to_string())
print("== del extracto de Galicia, no enteros dentro")
print(border[border["galicia"] & (border["clase"] != BorderClass.INSIDE)].to_string(index=False))
print("== del resto, con algún punto dentro (control: se espera ninguno)")
print(border[~border["galicia"] & (border["dentro"] > 0)].to_string(index=False))

# COMMAND ----------

for plant, names, in_galicia in zip(plants, parks["names"], parks["galicia"], strict=True):
    refs = plant.members if plant.osm_type == "r" else ((plant.osm_type, plant.osm_id),)
    reasons = {
        "nodo no leído": sum(k == "n" and r not in nodes for k, r in refs),
        "nodo no válido": sum(k == "n" and r in nodes and nodes[r] is None for k, r in refs),
        "vía no leída": sum(k == "w" and r not in ways for k, r in refs),
        "nodo de vía no válido": sum(
            loc is None for k, r in refs if k == "w" and r in ways for loc in ways[r]
        ),
        "relación anidada": sum(k == "r" for k, _ in refs),
    }
    if any(reasons.values()):
        found = {reason: n for reason, n in reasons.items() if n}
        label = f"{plant.osm_type}{plant.osm_id} {names.get('name', '')!r}"
        print(f"{label} galicia={in_galicia} {found}")
