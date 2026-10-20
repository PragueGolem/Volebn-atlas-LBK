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
        "t3": "https://volby.gov.cz/opendata/kv2022/csv_od/kvt3_csvod.zip",
        "hl": "https://volby.gov.cz/opendata/kv2022/csv_od/kvhl_csvod.zip",
        "geo": "https://volby.gov.cz/opendata/kv2022/geo/vol_okrsky_2022g100.geojson",
    },
    2026: {
        "ros": "https://volby.gov.cz/opendata/kv2026/csv_od/kvros.csv",
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


def load_parties(year: int):
    parties = {}
    rows = load_rows(URLS[year]["ros"])
    for r in rows:
        if intval(get(r, "KODZASTUP")) != CITY:
            continue
        p = intval(get(r, "POR_STR_HL", "POR_STR", "CISLO_STRANY"))
        if not p:
            continue
        # Official full list name is NAZEVCELK. ZKRATKAO30 is only a fallback.
        name = str(get(r, "NAZEVCELK", "ZKRATKAO30", "ZKRATKAO8") or f"Kandidátka {p}").strip()
        parties[str(p)] = name
    print(year, "kandidátky:", len(parties), flush=True)
    for p, name in sorted(parties.items(), key=lambda x: int(x[0])):
        print(f"  {p}: {name}", flush=True)
    return parties


def process_year(year: int):
    parties = load_parties(year)
    t3 = load_rows(URLS[year]["t3"], zipped=True)

    # T/3 explicitly identifies the chosen council by KODZASTUP.
    contest_rows = [r for r in t3 if intval(get(r, "KODZASTUP")) == CITY]
    if not contest_rows:
        raise RuntimeError(f"Liberec {year}: T/3 neobsahuje KODZASTUP={CITY}")

    precincts = {}
    # HL does not have KODZASTUP. Each T/3 row gives us the exact
    # OBEC + TYPZASTUP + OKRSEK tuple to retain. Do NOT use only the first
    # TYPZASTUP: Liberec contains precincts with more than one type, including
    # the Vratislavice 1001+ range, while all belong to the citywide contest.
    allowed = set()
    for r in contest_rows:
        o = intval(get(r, "OKRSEK"))
        if not o:
            continue
        obec = intval(get(r, "OBEC"))
        typ = intval(get(r, "TYPZASTUP"))
        allowed.add((obec, typ, o))
        registered = intval(get(r, "VOL_SEZNAM"))
        issued = intval(get(r, "VYD_OBALKY"))
        precincts[str(o)] = {
            "registered_voters": registered,
            "issued_envelopes": issued,
            "valid_votes": intval(get(r, "PL_HL_CELK")),
            "lists": {},
        }
    print(year, "okrsky:", len(precincts), flush=True)

    hl = load_rows(URLS[year]["hl"], zipped=True)
    hcount = 0
    for r in hl:
        key = (intval(get(r, "OBEC")), intval(get(r, "TYPZASTUP")), intval(get(r, "OKRSEK")))
        if key not in allowed:
            continue
        o = key[2]
        p = intval(get(r, "POR_STR_HL", "POR_STR"))
        if not p or str(o) not in precincts:
            continue
        precincts[str(o)]["lists"][str(p)] = intval(get(r, "POC_HLASU"))
        hcount += 1
    print(year, "řádky HL:", hcount, flush=True)

    if year == 2026 and len(precincts) != 87:
        raise RuntimeError(f"Liberec 2026: očekáváno 87 okrsků, nalezeno {len(precincts)}")
    if not precincts or hcount < len(precincts):
        raise RuntimeError(f"Liberec {year}: neúplná okrsková data (okrsky={len(precincts)}, HL={hcount})")

    rows = []
    for o, q in precincts.items():
        for p, votes in q["lists"].items():
            rows.append({
                "election_id": f"kv{year}",
                "election_label": f"Komunální volby {year}",
                "municipality_code": str(CITY),
                "municipality_name": CITY_NAME,
                "precinct_no": int(o),
                "list_no": int(p),
                "list_name": parties.get(p, f"Kandidátka {p}"),
                "votes": votes,
                "valid_votes": q["valid_votes"],
                "registered_voters": q["registered_voters"],
                "issued_envelopes": q["issued_envelopes"],
            })
    return rows


def main():
    rows = []
    for year in YEARS:
        rows.extend(process_year(year))
    Path("results.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    # Keep the official 2022 geometry intact. app.js performs the same Liberec
    # filtering used by the LBK atlas and matches polygons by precinct number.
    Path("precincts_kv2022.geojson").write_bytes(fetch_bytes(URLS[2022]["geo"]))

    # 2026 uses precincts_kv2026.geojson already present in the original LBK atlas.
    if not Path("precincts_kv2026.geojson").exists():
        raise RuntimeError("Chybí precincts_kv2026.geojson z původního atlasu LBK")

    metadata = {
        "region": "Liberec",
        "municipality_code": str(CITY),
        "elections": [
            {"id": "kv2022", "label": "Komunální volby 2022", "type": "komunální", "year": 2022, "geo": "precincts_kv2022.geojson"},
            {"id": "kv2026", "label": "Komunální volby 2026", "type": "komunální", "year": 2026, "geo": "precincts_kv2026.geojson"},
        ],
    }
    Path("metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    n22 = len([r for r in rows if r["election_id"] == "kv2022"])
    n26 = len([r for r in rows if r["election_id"] == "kv2026"])
    print("HOTOVO", flush=True)
    print("2022 řádků výsledků:", n22, flush=True)
    print("2026 řádků výsledků:", n26, flush=True)


if __name__ == "__main__":
    main()
