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
CITY_NAME = "Liberec"
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


def fetch_bytes(url: str) -> bytes:
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
        delim = csv.Sniffer().sniff(sample, delimiters=";,|\t").delimiter
    except Exception:
        delim = ";"
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def csv_from_zip(raw: bytes):
    rows = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError("ZIP neobsahuje CSV")
        for name in names:
            rows.extend(decode_csv(z.read(name)))
    return rows


def load_rows(url: str, zipped=False):
    raw = fetch_bytes(url)
    return csv_from_zip(raw) if zipped else decode_csv(raw)


def precinct_key(no: int) -> str:
    return f"{CITY}:{no}"


def load_registry(year: int):
    parties = {}
    for r in load_rows(URLS[year]["ros"]):
        if intval(get(r, "KODZASTUP")) != CITY:
            continue
        p = intval(get(r, "POR_STR_HL", "POR_STR", "CISLO_STRANY"))
        if not p:
            continue
        name = str(get(r, "NAZEV_VS", "NAZEV_STRANY", "NAZEV") or f"Kandidátka {p}").strip()
        parties[str(p)] = {"name": name, "candidates": {}}

    for r in load_rows(URLS[year]["rk"]):
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
            "occupation": str(get(r, "POVOLANI") or "").strip(),
            "residence": str(get(r, "BYDLISTEN") or "").strip(),
        }
    print(year, "kandidátky", len(parties), "kandidáti", sum(len(p["candidates"]) for p in parties.values()), flush=True)
    return parties


def process_year(year: int):
    parties = load_registry(year)
    t3 = load_rows(URLS[year]["t3"], zipped=True)

    # T/3 contains KODZASTUP, so use it to identify the exact municipal contest.
    # HL does NOT contain KODZASTUP; it is keyed by OBEC + TYPZASTUP + OKRSEK.
    contest_rows = [r for r in t3 if intval(get(r, "KODZASTUP")) == CITY]
    if not contest_rows:
        raise RuntimeError(f"Liberec {year}: T/3 neobsahuje KODZASTUP={CITY}")

    target_obec = intval(get(contest_rows[0], "OBEC"))
    target_typ = intval(get(contest_rows[0], "TYPZASTUP"))
    print(year, f"soutěž OBEC={target_obec}, TYPZASTUP={target_typ}", flush=True)

    precincts = {}
    for r in contest_rows:
        o = intval(get(r, "OKRSEK"))
        if not o:
            continue
        registered = intval(get(r, "VOL_SEZNAM"))
        issued = intval(get(r, "VYD_OBALKY"))
        precincts[str(o)] = {
            "registered_voters": registered,
            "issued_envelopes": issued,
            "valid_votes": intval(get(r, "PL_HL_CELK")),
            "turnout": (100 * issued / registered if registered else 0),
            "lists": {},
        }
    print(year, "okrsky", len(precincts), flush=True)

    hl = load_rows(URLS[year]["hl"], zipped=True)
    hcount = 0
    for r in hl:
        # Official HL structure has no KODZASTUP. Match the municipal contest
        # through the OBEC + TYPZASTUP pair obtained from T/3 above.
        if intval(get(r, "OBEC")) != target_obec:
            continue
        if intval(get(r, "TYPZASTUP")) != target_typ:
            continue
        o = intval(get(r, "OKRSEK"))
        p = intval(get(r, "POR_STR_HL", "POR_STR"))
        if not o or not p or str(o) not in precincts:
            continue
        q = precincts[str(o)]
        votes = intval(get(r, "POC_HLASU"))
        candidate_votes = {}
        for i in range(1, 71):
            v = get(r, f"HLASY_{i:02d}", f"HLASY_{i}")
            if v not in (None, "") or str(i) in parties.get(str(p), {}).get("candidates", {}):
                candidate_votes[str(i)] = intval(v)
        q["lists"][str(p)] = {"votes": votes, "candidate_votes": candidate_votes}
        hcount += 1
    print(year, "řádky HL", hcount, flush=True)

    if year == 2026 and len(precincts) != 87:
        raise RuntimeError(f"Liberec 2026: očekáváno 87 okrsků, nalezeno {len(precincts)}")
    if not precincts or not hcount:
        raise RuntimeError(f"Liberec {year}: chybí okrsková data (okrsky={len(precincts)}, HL={hcount})")

    rows = []
    for o, q in precincts.items():
        for p, rr in q["lists"].items():
            party = parties.get(p, {"name": f"Kandidátka {p}", "candidates": {}})
            rows.append({
                "election_id": f"kv{year}",
                "election_label": f"Komunální volby {year}",
                "municipality_code": str(CITY),
                "municipality_name": CITY_NAME,
                "precinct_no": int(o),
                "precinct_key": precinct_key(int(o)),
                "list_no": int(p),
                "list_name": party["name"],
                "votes": rr["votes"],
                "valid_votes": q["valid_votes"],
                "registered_voters": q["registered_voters"],
                "issued_envelopes": q["issued_envelopes"],
                "turnout": q["turnout"],
                "candidates": [
                    {
                        "no": int(cno),
                        "name": c["name"],
                        "votes": rr["candidate_votes"].get(cno, 0),
                        "occupation": c.get("occupation", ""),
                        "residence": c.get("residence", ""),
                    }
                    for cno, c in sorted(party["candidates"].items(), key=lambda x: int(x[0]))
                ],
            })
    return rows


def prop_city(props):
    for k, v in props.items():
        if norm(k) in {"OBEC", "KODOBCE", "OBECKOD", "KODOBEC", "ZUJ", "MUNICIPALITYCODE"} and intval(v) == CITY:
            return True
    return any(str(v).strip() == str(CITY) for v in props.values())


def find_precinct_no(props):
    preferred = ["OKRSEK", "CISLOOKRSKU", "PRECINCTNO", "OKRSEKC"]
    for name in preferred:
        for k, v in props.items():
            if norm(k) == norm(name):
                x = intval(v)
                if x:
                    return x
    for k, v in props.items():
        if "OKR" in norm(k):
            x = intval(v)
            if 1 <= x <= 999:
                return x
    return 0


def normalize_geo(g):
    feats = []
    for f in g.get("features", []):
        props = dict(f.get("properties") or {})
        if not prop_city(props):
            continue
        o = find_precinct_no(props)
        if not o:
            continue
        props.update({
            "municipality_code": str(CITY),
            "municipality_name": CITY_NAME,
            "precinct_no": o,
            "precinct_key": precinct_key(o),
        })
        f = dict(f)
        f["properties"] = props
        feats.append(f)
    return {"type": "FeatureCollection", "features": feats}


def main():
    rows = []
    for year in YEARS:
        rows.extend(process_year(year))
    Path("results.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    # 2022 geometry from ČSÚ
    g22 = json.loads(fetch_bytes(URLS[2022]["geo"]).decode("utf-8-sig"))
    g22 = normalize_geo(g22)
    Path("precincts_kv2022.geojson").write_text(json.dumps(g22, ensure_ascii=False), encoding="utf-8")
    print("2022 geo", len(g22["features"]), flush=True)

    # 2026 geometry is already present in this LBK repository.
    g26 = json.loads(Path("precincts_kv2026.geojson").read_text(encoding="utf-8"))
    g26 = normalize_geo(g26)
    Path("precincts_kv2026_liberec.geojson").write_text(json.dumps(g26, ensure_ascii=False), encoding="utf-8")
    print("2026 geo", len(g26["features"]), flush=True)

    metadata = {
        "region": "Liberec",
        "municipality_code": str(CITY),
        "elections": [
            {"id": "kv2022", "label": "Komunální volby 2022", "type": "komunální", "year": 2022, "geo": "precincts_kv2022.geojson"},
            {"id": "kv2026", "label": "Komunální volby 2026", "type": "komunální", "year": 2026, "geo": "precincts_kv2026_liberec.geojson"},
        ],
        "comparison": {
            "lol_pirati": {
                "label": "LOL + Piráti 2022 → společná kandidátka 2026",
                "from": ["Liberec otevřený lidem", "Česká pirátská strana"],
                "to": "Liberec otevřený lidem a Piráti",
            }
        },
    }
    Path("metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HOTOVO", flush=True)


if __name__ == "__main__":
    main()
