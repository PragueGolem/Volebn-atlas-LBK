from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CITY = 563889
YEARS = (2022, 2026)

URLS = {
    2022: {
        "ros": "https://volby.gov.cz/opendata/kv2022/csv_od/kvros.csv",
        "rk": "https://volby.gov.cz/opendata/kv2022/csv_od/kvrk.csv",
        "t3": "https://volby.gov.cz/opendata/kv2022/csv_od/kvt3_csvod.zip",
        "hl": "https://volby.gov.cz/opendata/kv2022/csv_od/kvhl_csvod.zip",
        "geo": "https://volby.gov.cz/opendata/kv2022/geo/vol_okrsky_2022g100.geojson",
    },
    2026: {
        "ros": "https://volby.gov.cz/opendata/kv2026/csv_od/kvros.csv",
        "rk": "https://volby.gov.cz/opendata/kv2026/csv_od/kvrk.csv",
        "t3": "https://volby.gov.cz/opendata/kv2026/csv_od/kvt3_csvod.zip",
        "hl": "https://volby.gov.cz/opendata/kv2026/csv_od/kvhl_csvod.zip",
    },
}


def get_bytes(url: str) -> bytes:
    print("GET", url, flush=True)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 ElectionAtlasLiberec/1.0"})
    with urlopen(req, timeout=180) as r:
        data = r.read()
    print("  ->", len(data), "bytes", flush=True)
    return data


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def intval(v):
    try:
        return int(float(str(v).strip().replace(",", ".")))
    except Exception:
        return 0


def get(row, *names):
    idx = {norm(k): k for k in row}
    for name in names:
        k = idx.get(norm(name))
        if k is not None:
            return row.get(k)
    return None


def decode_csv(raw: bytes):
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:10000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        delim = dialect.delimiter
    except Exception:
        delim = ";"
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def csv_from_zip(raw: bytes):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError("ZIP does not contain CSV")
        print("ZIP members:", names[:10], flush=True)
        # T3/HL packages normally contain one CSV; if there are several, concatenate.
        rows = []
        for name in names:
            rows.extend(decode_csv(z.read(name)))
        return rows


def load_rows(url: str, zipped=False):
    raw = get_bytes(url)
    return csv_from_zip(raw) if zipped else decode_csv(raw)


def party_registry(year: int):
    rows = load_rows(URLS[year]["ros"])
    out = {}
    for r in rows:
        if intval(get(r, "KODZASTUP")) != CITY:
            continue
        p = intval(get(r, "POR_STR_HL", "POR_STR", "CISLO_STRANY"))
        if not p:
            continue
        name = str(get(r, "NAZEV_VS", "NAZEV_STRANY", "NAZEV") or f"Kandidátka {p}").strip()
        out[str(p)] = {"name": name, "candidates": {}}
    print(year, "parties", len(out), flush=True)
    return out


def candidate_registry(year: int, parties):
    rows = load_rows(URLS[year]["rk"])
    count = 0
    for r in rows:
        if intval(get(r, "KODZASTUP")) != CITY:
            continue
        p = intval(get(r, "POR_STR_HL", "POR_STR", "CISLO_STRANY"))
        c = intval(get(r, "PORCISLO", "POR_KAND", "PORCIS_KAND", "PORADI"))
        if not p or not c:
            continue
        parts = []
        for key in ("TITULPRED", "JMENO", "PRIJMENI", "TITULZA"):
            v = get(r, key)
            if v and str(v).strip():
                parts.append(str(v).strip())
        parties.setdefault(str(p), {"name": f"Kandidátka {p}", "candidates": {}})
        parties[str(p)]["candidates"][str(c)] = {
            "name": " ".join(parts) if parts else f"Kandidát {c}",
            "residence": str(get(r, "BYDLISTEN") or "").strip(),
            "occupation": str(get(r, "POVOLANI") or "").strip(),
        }
        count += 1
    print(year, "candidates", count, flush=True)


def process_year(year: int):
    parties = party_registry(year)
    candidate_registry(year, parties)

    t3 = load_rows(URLS[year]["t3"], zipped=True)
    print(year, "T3 headers", list(t3[0].keys()) if t3 else [], flush=True)
    precincts = {}
    for r in t3:
        if intval(get(r, "KODZASTUP")) != CITY:
            continue
        o = intval(get(r, "OKRSEK"))
        if not o:
            continue
        voters = intval(get(r, "VOL_SEZNAM"))
        envelopes = intval(get(r, "VYD_OBALKY"))
        precincts[str(o)] = {
            "voters": voters,
            "envelopes": envelopes,
            "cast": intval(get(r, "ODEVZ_OBAL")),
            "valid_ballots": intval(get(r, "PLAT_LISTKY")),
            "valid_votes": intval(get(r, "PL_HL_CELK")),
            "turnout": (100 * envelopes / voters if voters else 0),
            "party_results": {},
        }
    print(year, "precincts", len(precincts), flush=True)

    hl = load_rows(URLS[year]["hl"], zipped=True)
    print(year, "HL headers", list(hl[0].keys())[:20] if hl else [], flush=True)
    hcount = 0
    for r in hl:
        if intval(get(r, "KODZASTUP")) != CITY:
            continue
        o = intval(get(r, "OKRSEK"))
        p = intval(get(r, "POR_STR_HL", "POR_STR"))
        if not o or not p or str(o) not in precincts:
            continue
        q = precincts[str(o)]
        votes = intval(get(r, "POC_HLASU"))
        cv = {}
        for i in range(1, 71):
            v = get(r, f"HLASY_{i:02d}", f"HLASY_{i}")
            if v not in (None, "") or str(i) in parties.get(str(p), {}).get("candidates", {}):
                cv[str(i)] = intval(v)
        q["party_results"][str(p)] = {
            "votes": votes,
            "pct": (100 * votes / q["valid_votes"] if q["valid_votes"] else 0),
            "candidate_votes": cv,
        }
        hcount += 1
    print(year, "HL rows", hcount, flush=True)

    denom = sum(q["valid_votes"] for q in precincts.values())
    totals = {}
    for q in precincts.values():
        for p, rr in q["party_results"].items():
            totals[p] = totals.get(p, 0) + rr["votes"]
    for p, party in parties.items():
        party["city_pct"] = (100 * totals.get(p, 0) / denom if denom else 0)

    if year == 2026 and len(precincts) != 87:
        raise RuntimeError(f"Expected 87 Liberec precincts in 2026, got {len(precincts)}")
    if not precincts or not hcount:
        raise RuntimeError(f"No usable precinct data for {year}: precincts={len(precincts)}, HL={hcount}")

    return {"year": year, "parties": parties, "precincts": precincts}


def prop_matches_city(props):
    for k, v in props.items():
        nk = norm(k)
        if nk in {"OBEC", "KODOBCE", "OBECKOD", "KODOBEC", "ZUJ", "MUNICIPALITYCODE"} and intval(v) == CITY:
            return True
    return any(str(v).strip() == str(CITY) for v in props.values())


def subset_geo(g):
    feats = [f for f in g.get("features", []) if prop_matches_city(f.get("properties", {}))]
    return {"type": "FeatureCollection", "features": feats}


def main():
    result = {str(year): process_year(year) for year in YEARS}
    Path("liberec_results.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    # 2022 official precinct geometry.
    geo22 = json.loads(get_bytes(URLS[2022]["geo"]).decode("utf-8-sig"))
    geo22 = subset_geo(geo22)
    Path("precincts_liberec_2022.geojson").write_text(json.dumps(geo22, ensure_ascii=False), encoding="utf-8")
    print("2022 geo features", len(geo22["features"]), flush=True)

    # 2026 geometry already exists in the original LBK atlas; filter it to Liberec.
    geo26 = json.loads(Path("precincts_kv2026.geojson").read_text(encoding="utf-8"))
    geo26 = subset_geo(geo26)
    Path("precincts_liberec_2026.geojson").write_text(json.dumps(geo26, ensure_ascii=False), encoding="utf-8")
    print("2026 geo features", len(geo26["features"]), flush=True)

    meta = {
        "title": "Volební atlas Liberce 2022–2026",
        "city_code": CITY,
        "elections": [
            {"id": "kv2022", "label": "Komunální volby 2022", "geo": "precincts_liberec_2022.geojson"},
            {"id": "kv2026", "label": "Komunální volby 2026", "geo": "precincts_liberec_2026.geojson"},
        ],
    }
    Path("metadata_liberec.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("DONE", flush=True)


if __name__ == "__main__":
    main()
