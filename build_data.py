#!/usr/bin/env python3
"""Build a neutral precinct-level election atlas for the Liberec Region.

Downloads official Czech Statistical Office election open data for:
- 2024 regional elections (KZ2024)
- 2025 Chamber of Deputies election (PS2025)
- 2026 municipal elections (KV2026)

Outputs normalized election results plus filtered precinct GeoJSON for a static
Leaflet web app. No individual-level data are used.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
PUBLIC_DATA = ROOT / "public" / "data"
CONFIG = ROOT / "config"
RAW.mkdir(exist_ok=True)
PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
CONFIG.mkdir(exist_ok=True)

# District codes of the Liberec Region: Česká Lípa, Jablonec n. N., Liberec, Semily.
LIBEREC_DISTRICTS = {"5101", "5102", "5103", "5104"}

URLS = {
    "kz2024": {
        "base": "https://volby.gov.cz/opendata/kz2024/csv_od/kzt6.zip",
        "party": "https://volby.gov.cz/opendata/kz2024/csv_od/kzt6p.zip",
        "places": "https://volby.gov.cz/opendata/kz2024/csv_od/kzcoco.csv",
        "lists": "https://volby.gov.cz/opendata/kz2024/csv_od/kzrkl.csv",
        "composition": "https://volby.gov.cz/opendata/kz2024/csv_od/kzrkl_slozeni.csv",
        "geometry": "https://volby.gov.cz/opendata/kz2024/geo/vol_okrsky_2024g100.geojson",
    },
    "ps2025": {
        "base": "https://volby.gov.cz/opendata/ps2025/csv_od/pst4.zip",
        "party": "https://volby.gov.cz/opendata/ps2025/csv_od/pst4p.zip",
        "places": "https://volby.gov.cz/opendata/ps2025/csv_od/pscoco.csv",
        "lists": "https://volby.gov.cz/opendata/ps2025/csv_od/psrkl.csv",
        "composition": "https://volby.gov.cz/opendata/ps2025/csv_od/psrkl_slozeni.csv",
        "geometry": "https://geodata.csu.gov.cz/as/data/distribuce/Hosted/Volebni_okrsky_2025_gdb/FeatureServer/0/geojson.zip",
    },
    "kv2026": {
        "base": "https://volby.gov.cz/opendata/kv2026/csv_od/kvt3_csvod.zip",
        "party": "https://volby.gov.cz/opendata/kv2026/csv_od/kvhl_csvod.zip",
        "councils": "https://volby.gov.cz/opendata/kv2026/csv_od/kvrzcoco.csv",
        "lists": "https://volby.gov.cz/opendata/kv2026/csv_od/kvros.csv",
        "geometry": "https://geodata.csu.gov.cz/as/data/distribuce/Hosted/Volebn%C3%AD_okrsky_ZO2026/FeatureServer/0/geojson.zip",
    },
}

LABELS = {
    "kz2024": ("Krajské volby 2024", "krajské", 2024),
    "ps2025": ("Poslanecká sněmovna 2025", "sněmovní", 2025),
    "kv2026": ("Komunální volby 2026", "komunální", 2026),
}


def log(msg: str) -> None:
    print(msg, flush=True)


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    log(f"↓ {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 election-atlas/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def local_file(election: str, kind: str) -> Path:
    url = URLS[election][kind]
    suffix = ".zip" if url.lower().endswith(".zip") else Path(url).suffix or ".dat"
    return RAW / f"{election}_{kind}{suffix}"


def read_bytes(path: Path) -> bytes:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            members = [n for n in z.namelist() if not n.endswith("/")]
            csvs = [n for n in members if n.lower().endswith(".csv")]
            geos = [n for n in members if n.lower().endswith((".geojson", ".json"))]
            chosen = csvs[0] if csvs else (geos[0] if geos else members[0])
            return z.read(chosen)
    return path.read_bytes()


def read_table(path: Path) -> pd.DataFrame:
    data = read_bytes(path)
    # Official election CSVs are normally semicolon-delimited. Be tolerant of
    # BOM/legacy encodings and occasional comma-delimited files.
    last = None
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        for sep in (";", ",", "\t"):
            try:
                df = pd.read_csv(io.BytesIO(data), sep=sep, dtype=str, encoding=enc, low_memory=False)
                if len(df.columns) > 1:
                    df.columns = [str(c).strip().upper() for c in df.columns]
                    return df
            except Exception as e:
                last = e
    raise RuntimeError(f"Could not parse {path}: {last}")


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def norm_code(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+(?:\.0+)?", s):
        return str(int(float(s)))
    return s


def normalize_cols(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].map(norm_code)
    return df


def safe_col(df: pd.DataFrame, *names: str, default: str = "") -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name].fillna(default).astype(str)
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    n = num(numer)
    d = num(denom)
    out = pd.Series([0.0] * len(n), index=n.index)
    ok = d > 0
    out.loc[ok] = n.loc[ok] / d.loc[ok] * 100
    return out


def prepare_kz() -> pd.DataFrame:
    e = "kz2024"
    for kind in URLS[e]:
        download(URLS[e][kind], local_file(e, kind))

    base = normalize_cols(read_table(local_file(e, "base")), ["OKRES", "OBEC", "OKRSEK"])
    party = normalize_cols(read_table(local_file(e, "party")), ["OKRES", "OBEC", "OKRSEK", "KSTRANA"])
    places = normalize_cols(read_table(local_file(e, "places")), ["OKRES", "OBEC", "KRZAST"])
    lists = normalize_cols(read_table(local_file(e, "lists")), ["KRZAST", "KSTRANA", "VSTRANA"])

    base = base[base["OKRES"].isin(LIBEREC_DISTRICTS)].copy()
    party = party[party["OKRES"].isin(LIBEREC_DISTRICTS)].copy()

    join = [c for c in ["OKRES", "OBEC", "OKRSEK"] if c in base.columns and c in party.columns]
    df = party.merge(base, on=join, how="left", suffixes=("", "_BASE"))

    pcols = [c for c in ["OKRES", "OBEC", "NAZEVOBCE", "KRZAST"] if c in places.columns]
    if pcols:
        p = places[pcols].drop_duplicates(subset=[c for c in ["OKRES", "OBEC"] if c in pcols])
        df = df.merge(p, on=[c for c in ["OKRES", "OBEC"] if c in pcols], how="left")

    ljoin = [c for c in ["KRZAST", "KSTRANA"] if c in df.columns and c in lists.columns]
    if not ljoin:
        ljoin = ["KSTRANA"]
    lcols = list(dict.fromkeys(ljoin + [c for c in ["VSTRANA", "NAZEVCELK", "NAZEV_STRK", "ZKRATKAK30", "ZKRATKAK8", "SLOZENI"] if c in lists.columns]))
    df = df.merge(lists[lcols].drop_duplicates(subset=ljoin), on=ljoin, how="left")

    df["contest_id"] = safe_col(df, "KRZAST", default="liberecky-kraj")
    return finalize_common(df, e, ballot="KSTRANA", votes="POC_HLASU")


def prepare_ps() -> pd.DataFrame:
    e = "ps2025"
    for kind in URLS[e]:
        download(URLS[e][kind], local_file(e, kind))

    base = normalize_cols(read_table(local_file(e, "base")), ["OKRES", "OBEC", "OKRSEK"])
    party = normalize_cols(read_table(local_file(e, "party")), ["OKRES", "OBEC", "OKRSEK", "KSTRANA"])
    places = normalize_cols(read_table(local_file(e, "places")), ["OKRES", "OBEC", "KRZAST"])
    lists = normalize_cols(read_table(local_file(e, "lists")), ["KSTRANA", "VSTRANA"])

    base = base[base["OKRES"].isin(LIBEREC_DISTRICTS)].copy()
    party = party[party["OKRES"].isin(LIBEREC_DISTRICTS)].copy()
    join = [c for c in ["OKRES", "OBEC", "OKRSEK"] if c in base.columns and c in party.columns]
    df = party.merge(base, on=join, how="left", suffixes=("", "_BASE"))

    pcols = [c for c in ["OKRES", "OBEC", "NAZEVOBCE", "KRZAST", "OBEC_PREZ"] if c in places.columns]
    if pcols:
        p = places[pcols].drop_duplicates(subset=[c for c in ["OKRES", "OBEC"] if c in pcols])
        df = df.merge(p, on=[c for c in ["OKRES", "OBEC"] if c in pcols], how="left")

    ljoin = ["KSTRANA"]
    lcols = list(dict.fromkeys(ljoin + [c for c in ["VSTRANA", "NAZEVCELK", "NAZEV_STRK", "ZKRATKAK30", "ZKRATKAK8", "SLOZENI"] if c in lists.columns]))
    df = df.merge(lists[lcols].drop_duplicates(subset=ljoin), on=ljoin, how="left")
    df["contest_id"] = "PS2025"
    return finalize_common(df, e, ballot="KSTRANA", votes="POC_HLASU")


def prepare_kv() -> pd.DataFrame:
    e = "kv2026"
    for kind in URLS[e]:
        download(URLS[e][kind], local_file(e, kind))

    base = normalize_cols(read_table(local_file(e, "base")), ["OKRES", "OBEC", "OKRSEK", "TYPZASTUP", "KODZASTUP", "COBVODU"])
    party = normalize_cols(read_table(local_file(e, "party")), ["OKRES", "OBEC", "OKRSEK", "TYPZASTUP", "POR_STR_HL"])
    councils = normalize_cols(read_table(local_file(e, "councils")), ["OKRES", "OBEC", "KODZASTUP", "COBVODU", "TYPZASTUP"])
    lists = normalize_cols(read_table(local_file(e, "lists")), ["OKRES", "KODZASTUP", "COBVODU", "POR_STR_HL", "VSTRANA", "OSTRANA"])

    base = base[base["OKRES"].isin(LIBEREC_DISTRICTS)].copy()
    party = party[party["OKRES"].isin(LIBEREC_DISTRICTS)].copy()

    join = [c for c in ["OKRES", "OBEC", "OKRSEK", "TYPZASTUP"] if c in base.columns and c in party.columns]
    df = party.merge(base, on=join, how="left", suffixes=("", "_BASE"))

    ljoin = [c for c in ["OKRES", "KODZASTUP", "COBVODU", "POR_STR_HL"] if c in df.columns and c in lists.columns]
    if len(ljoin) < 3:
        raise RuntimeError(f"Municipal list registry join keys missing. Found: {ljoin}")
    lcols = list(dict.fromkeys(ljoin + [c for c in ["VSTRANA", "OSTRANA", "NAZEVCELK", "ZKRATKAO30", "ZKRATKAO8", "SLOZENI"] if c in lists.columns]))
    df = df.merge(lists[lcols].drop_duplicates(subset=ljoin), on=ljoin, how="left")

    # The Liberec statutory-city council spans two territorial units in the
    # municipal-election registry: Liberec (neclenene mesto) and
    # Liberec-Vratislavice nad Nisou.  KODZASTUP+COBVODU alone is therefore
    # not enough to recover the territorial name: collapsing on those keys can
    # assign the Vratislavice name to both units.  Keep OBEC in the registry
    # join whenever it is available, so each precinct retains its real
    # territorial unit/name.
    cjoin = [c for c in ["OKRES", "KODZASTUP", "COBVODU", "OBEC"] if c in df.columns and c in councils.columns]
    ccols = list(dict.fromkeys(cjoin + [c for c in ["NAZEVZAST", "NAZEVOBCE", "DRUHZASTUP"] if c in councils.columns]))
    if cjoin:
        csmall = councils[ccols].drop_duplicates(subset=cjoin)
        df = df.merge(csmall, on=cjoin, how="left", suffixes=("", "_COUNCIL"))

    # In CSU municipal-election data TYPZASTUP=1 means the municipality/city/
    # statutory-city council; TYPZASTUP=2 is a city district / borough council.
    # Use the official type code rather than comparing KODZASTUP with OBEC: the
    # latter can exclude statutory cities such as Liberec.
    df["is_main_contest"] = safe_col(df, "TYPZASTUP").map(norm_code).eq("1")
    df["contest_id"] = safe_col(df, "KODZASTUP") + ":" + safe_col(df, "COBVODU")
    df["contest_name"] = safe_col(df, "NAZEVZAST", default="Zastupitelstvo")

    out = finalize_common(df, e, ballot="POR_STR_HL", votes="POC_HLASU")
    out["is_main_contest"] = df["is_main_contest"].astype(bool).values
    # If a municipal dataset variant does not mark main contests as expected,
    # fall back to all rows rather than producing an empty map.
    if not out["is_main_contest"].any():
        out["is_main_contest"] = True
    return out


def finalize_common(df: pd.DataFrame, election_id: str, ballot: str, votes: str) -> pd.DataFrame:
    label, etype, year = LABELS[election_id]
    out = pd.DataFrame(index=df.index)
    out["election_id"] = election_id
    out["election_label"] = label
    out["election_type"] = etype
    out["year"] = year
    out["district_code"] = safe_col(df, "OKRES").map(norm_code)
    out["municipality_code"] = safe_col(df, "OBEC").map(norm_code)
    out["municipality_name"] = safe_col(df, "NAZEVOBCE", "NAZ_OBCE", default="")
    out["precinct"] = safe_col(df, "OKRSEK").map(norm_code)
    out["precinct_key"] = out["municipality_code"] + ":" + out["precinct"]
    out["contest_id"] = safe_col(df, "contest_id", "KODZASTUP", default=election_id)
    out["contest_name"] = safe_col(df, "contest_name", "NAZEVZAST", default=label)
    out["ballot_no"] = safe_col(df, ballot).map(norm_code)
    out["vstrana"] = safe_col(df, "VSTRANA")
    out["composition_raw"] = safe_col(df, "SLOZENI")
    out["list_name"] = safe_col(df, "NAZEVCELK", "NAZEV_STRK", "ZKRATKAO30", "ZKRATKAK30", default="")
    out["list_short"] = safe_col(df, "ZKRATKAO30", "ZKRATKAK30", "ZKRATKAO8", "ZKRATKAK8", default="")
    # If full name is missing, fall back to short label / ballot number.
    blank = out["list_name"].str.strip().eq("")
    out.loc[blank, "list_name"] = out.loc[blank, "list_short"]
    blank = out["list_name"].str.strip().eq("")
    out.loc[blank, "list_name"] = "Kandidátka " + out.loc[blank, "ballot_no"]

    out["votes"] = num(safe_col(df, votes)).astype(int)
    out["valid_votes"] = num(safe_col(df, "PL_HL_CELK")).astype(int)
    out["registered_voters"] = num(safe_col(df, "VOL_SEZNAM")).astype(int)
    out["issued_envelopes"] = num(safe_col(df, "VYD_OBALKY")).astype(int)
    out["vote_share"] = ratio(safe_col(df, votes), safe_col(df, "PL_HL_CELK")).round(5)
    out["turnout_pct"] = ratio(safe_col(df, "VYD_OBALKY"), safe_col(df, "VOL_SEZNAM")).round(5)
    if "is_main_contest" in df.columns:
        out["is_main_contest"] = df["is_main_contest"].astype(bool).values
    else:
        out["is_main_contest"] = True

    out["mapping_key"] = (
        out["election_id"].astype(str) + "|" + out["vstrana"].astype(str) + "|" +
        out["list_name"].astype(str) + "|" + out["composition_raw"].astype(str)
    )
    return out


def load_geojson(path: Path) -> dict:
    data = read_bytes(path)
    for enc in ("utf-8-sig", "utf-8", "cp1250"):
        try:
            return json.loads(data.decode(enc))
        except Exception:
            pass
    raise RuntimeError(f"Could not decode GeoJSON {path}")


def _iter_xy(coords):
    """Yield x/y coordinate pairs from arbitrarily nested GeoJSON coordinates."""
    if isinstance(coords, (list, tuple)) and len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        yield float(coords[0]), float(coords[1])
        return
    if isinstance(coords, (list, tuple)):
        for item in coords:
            yield from _iter_xy(item)


def _declared_crs(gj: dict) -> str:
    crs = gj.get("crs") or {}
    props = crs.get("properties") or {}
    raw = str(props.get("name") or props.get("href") or "").strip()
    m = re.search(r"EPSG(?::|::|/)(\d+)", raw, flags=re.I)
    if m:
        return f"EPSG:{m.group(1)}"
    m = re.search(r"ESRI(?::|::|/)(\d+)", raw, flags=re.I)
    if m:
        return f"ESRI:{m.group(1)}"
    return raw


def _sample_geojson_xy(gj: dict, limit: int = 3000) -> list[tuple[float, float]]:
    pts = []
    for feature in gj.get("features", []):
        geom = feature.get("geometry") or {}
        for xy in _iter_xy(geom.get("coordinates", [])):
            if math.isfinite(xy[0]) and math.isfinite(xy[1]):
                pts.append(xy)
                if len(pts) >= limit:
                    return pts
    return pts


def _guess_crs(gj: dict, sample: list[tuple[float, float]]) -> str:
    declared = _declared_crs(gj)
    if declared:
        try:
            CRS.from_user_input(declared)
            return declared
        except Exception:
            pass
    if not sample:
        return "EPSG:4326"
    xs = sorted(abs(x) for x, _ in sample)
    ys = sorted(abs(y) for _, y in sample)
    mx = xs[len(xs)//2]
    my = ys[len(ys)//2]
    # RFC 7946 / ordinary lon-lat coordinates.
    if mx <= 180 and my <= 90:
        return "EPSG:4326"
    # Czech Web Mercator is roughly x=1.3–2.1m, y=6.1–6.8m.
    if 500_000 <= mx <= 3_000_000 and 4_000_000 <= my <= 8_000_000:
        return "EPSG:3857"
    # S-JTSK / Krovak East North typically uses negative values around
    # hundreds of thousands / one million in Czechia.
    signed_x = sorted(x for x, _ in sample)[len(sample)//2]
    signed_y = sorted(y for _, y in sample)[len(sample)//2]
    if -1_500_000 <= signed_x <= 0 and -1_500_000 <= signed_y <= 0:
        return "EPSG:5514"
    raise RuntimeError(
        f"Unknown coordinate system in precinct geometry (median |x|={mx:.1f}, |y|={my:.1f})."
    )


def _czech_score(points: list[tuple[float, float]]) -> float:
    if not points:
        return 0.0
    ok = sum(1 for lon, lat in points if 11.0 <= lon <= 19.5 and 47.5 <= lat <= 52.0)
    return ok / len(points)


def normalize_geojson_wgs84(gj: dict, label: str) -> dict:
    """Normalize downloaded precinct geometry to GeoJSON lon/lat (EPSG:4326).

    Some GIS download endpoints expose GeoJSON-like files in a projected CRS.
    Leaflet always expects longitude/latitude; projected coordinates make it
    zoom out to repeated world maps. Detect the common Czech CRSs and fix them.
    """
    sample = _sample_geojson_xy(gj)
    src = _guess_crs(gj, sample)

    if src.upper() == "EPSG:4326":
        normal = sample[:500]
        swapped = [(y, x) for x, y in normal]
        swap_axes = _czech_score(swapped) > _czech_score(normal)
        transformer = None
    else:
        transformer = Transformer.from_crs(CRS.from_user_input(src), CRS.from_epsg(4326), always_xy=True)
        normal = [transformer.transform(x, y) for x, y in sample[:500]]
        swapped = [transformer.transform(y, x) for x, y in sample[:500]]
        swap_axes = _czech_score(swapped) > _czech_score(normal)

    def transform_pair(x: float, y: float) -> tuple[float, float]:
        if swap_axes:
            x, y = y, x
        if transformer is not None:
            x, y = transformer.transform(x, y)
        return float(x), float(y)

    def transform_coords(coords):
        if isinstance(coords, list) and len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
            x, y = transform_pair(float(coords[0]), float(coords[1]))
            return [x, y] + list(coords[2:])
        if isinstance(coords, list):
            return [transform_coords(item) for item in coords]
        return coords

    for feature in gj.get("features", []):
        geom = feature.get("geometry") or {}
        if "coordinates" in geom:
            geom["coordinates"] = transform_coords(geom["coordinates"])
            feature["geometry"] = geom
    gj.pop("crs", None)

    after = _sample_geojson_xy(gj, limit=1000)
    score = _czech_score(after)
    if score < 0.90:
        raise RuntimeError(
            f"Geometry {label} could not be normalized safely to WGS84 (Czech-coordinate score {score:.1%})."
        )
    xs = [x for x, _ in after]
    ys = [y for _, y in after]
    log(
        f"  Geometry CRS {label}: {src}{' (swapped axes)' if swap_axes else ''} -> EPSG:4326; "
        f"sample bounds {min(xs):.3f},{min(ys):.3f}–{max(xs):.3f},{max(ys):.3f}"
    )
    return gj


def filter_geometry(election_id: str, result: pd.DataFrame) -> dict:
    path = local_file(election_id, "geometry")
    gj = normalize_geojson_wgs84(load_geojson(path), election_id)
    valid_areas = set(result["municipality_code"].dropna().astype(str).map(norm_code))
    valid_precincts = set(result["precinct_key"].dropna().astype(str))
    kept = []
    matched = set()

    for feature in gj.get("features", []):
        props = feature.setdefault("properties", {}) or {}
        # ArcGIS exports may vary in case.
        lower = {str(k).lower(): v for k, v in props.items()}
        mco = norm_code(lower.get("kod_mco"))
        obec = norm_code(lower.get("kod_obec"))
        precinct = norm_code(lower.get("cislo") or lower.get("okrsek") or lower.get("c_okrsek"))
        area = mco if mco and mco in valid_areas else obec
        if not area or area not in valid_areas or not precinct:
            continue
        key = f"{area}:{precinct}"
        if key not in valid_precincts:
            # Try parent municipality if municipal-part code did not match election coding.
            alt = f"{obec}:{precinct}" if obec else ""
            if alt in valid_precincts:
                area, key = obec, alt
            else:
                continue
        props["precinct_key"] = key
        props["municipality_code"] = area
        props["municipality_name"] = lower.get("naz_mco") or lower.get("naz_obec") or ""
        props["precinct"] = precinct
        feature["properties"] = props
        kept.append(feature)
        matched.add(key)

    coverage = len(matched) / max(1, len(valid_precincts)) * 100
    log(f"  Geometry {election_id}: {len(kept)} precinct polygons; result-key coverage {coverage:.1f}%")
    return {"type": "FeatureCollection", "features": kept}


def apply_harmonization(results: pd.DataFrame) -> pd.DataFrame:
    unique = (
        results[["mapping_key", "election_id", "list_name", "list_short", "vstrana", "composition_raw"]]
        .drop_duplicates()
        .sort_values(["election_id", "list_name"])
        .copy()
    )
    template = CONFIG / "harmonization.csv"
    if not template.exists():
        unique["family_name"] = unique["list_name"]
        unique["note"] = ""
        unique.to_csv(template, index=False, encoding="utf-8-sig")
        log(f"Created {template.relative_to(ROOT)}. Edit family_name to merge lists into political families, then rerun build_data.py.")

    harm = pd.read_csv(template, dtype=str, encoding="utf-8-sig").fillna("")
    if "mapping_key" not in harm.columns or "family_name" not in harm.columns:
        raise RuntimeError("config/harmonization.csv must contain mapping_key and family_name columns")
    mapping = dict(zip(harm["mapping_key"], harm["family_name"]))
    results["family_name"] = results["mapping_key"].map(mapping).fillna(results["list_name"])
    results.loc[results["family_name"].str.strip().eq(""), "family_name"] = results["list_name"]
    return results


def write_outputs(results: pd.DataFrame, geos: dict[str, dict]) -> None:
    # Reduce fields for browser payload, keeping the CSV richer for analysis.
    csv_path = PUBLIC_DATA / "results_normalized.csv"
    results.to_csv(csv_path, index=False, encoding="utf-8-sig")

    browser_cols = [
        "election_id", "election_label", "election_type", "year",
        "municipality_code", "municipality_name", "precinct", "precinct_key",
        "contest_id", "contest_name", "is_main_contest", "ballot_no",
        "list_name", "list_short", "family_name", "vstrana", "composition_raw",
        "votes", "valid_votes", "registered_voters", "issued_envelopes",
        "vote_share", "turnout_pct",
    ]
    browser = results[[c for c in browser_cols if c in results.columns]].copy()
    (PUBLIC_DATA / "results.json").write_text(
        json.dumps(browser.to_dict(orient="records"), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    for election_id, geo in geos.items():
        (PUBLIC_DATA / f"precincts_{election_id}.geojson").write_text(
            json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    metadata = {
        "region": "Liberecký kraj",
        "district_codes": sorted(LIBEREC_DISTRICTS),
        "elections": [
            {"id": k, "label": LABELS[k][0], "type": LABELS[k][1], "year": LABELS[k][2]}
            for k in ["kz2024", "ps2025", "kv2026"]
        ],
        "notes": {
            "municipal": "For the map, the app defaults to the main municipal council; all contests remain in results_normalized.csv.",
            "families": "Political-family groupings come from config/harmonization.csv and never split a joint list into component parties.",
        },
    }
    (PUBLIC_DATA / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✓ Wrote {len(results):,} normalized result rows to {csv_path.relative_to(ROOT)}")


def main() -> None:
    try:
        frames = [prepare_kz(), prepare_ps(), prepare_kv()]
        results = pd.concat(frames, ignore_index=True)
        results = apply_harmonization(results)
        geos = {}
        for eid in ["kz2024", "ps2025", "kv2026"]:
            geos[eid] = filter_geometry(eid, results[results["election_id"] == eid])
        write_outputs(results, geos)
        log("\nDone. Start the atlas with:  python -m http.server 8000 -d public")
        log("Then open: http://localhost:8000")
    except Exception as exc:
        log(f"\nERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
