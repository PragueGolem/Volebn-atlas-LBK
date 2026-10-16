# Volební atlas Libereckého kraje – Vercel-ready verze

Tato verze obsahuje `vercel.json` a návod `VERCEL.md` pro statické nasazení na Vercel. Nejprve je nutné lokálně vytvořit data pomocí `1_VYTVORIT_DATA.bat`.

# V5 – oprava více Pythonů ve Windows

## Změny ve v6

- Opravena identifikace hlavního zastupitelstva v komunálních volbách 2026: používá se oficiální `TYPZASTUP = 1`, takže se správně zahrne i statutární město Liberec.
- Po výběru obce v komunálních volbách se nabídka kandidátek zúží jen na kandidátky, které v dané obci skutečně kandidovaly.
- Kliknutí na volební okrsek v komunální mapě automaticky vybere jeho obec a přefiltruje nabídku kandidátek.
- Reset zobrazení vrátí nabídku kandidátek za celý Liberecký kraj.


Pokud má Windows více instalací Pythonu, `py -m pip` a `py build_data.py` mohou skončit v různých interpretech. Launcher V5 nejdřív zjistí konkrétní `python.exe` a ten samý používá pro instalaci balíčků, kontrolní import i sestavení dat. Varování, že `Scripts` není v PATH, nevadí.

# Volební atlas Libereckého kraje

## Důležité před spuštěním ve Windows

ZIP je nutné nejprve **celý rozbalit** (`pravé tlačítko → Extrahovat vše…`). Nespouštějte `.bat` soubory přímo z náhledu ZIP archivu; Windows by mohl do dočasné složky zpřístupnit jen spouštěný soubor a ostatní soubory projektu by nebyly viditelné.


Statická interaktivní mapa agregovaných veřejných volebních výsledků za volební okrsky v Libereckém kraji.

## Zahrnuté volby

- Krajské volby 2024
- Volby do Poslanecké sněmovny 2025
- Komunální volby 2026

Atlas načítá **všechny kandidátky, které jsou v oficiálních datech ČSÚ**, a umožňuje přepínat mezi volbami, kandidátkami a okrsky. U komunálních voleb se v normalizovaném souboru uchovávají všechna zastupitelstva; hlavní mapový pohled standardně používá hlavní obecní/městské zastupitelstvo, aby se překrývající volby do městských částí nepočítaly dvakrát.

## Co umí webová mapa

- přepínat Kraj 2024 / PS 2025 / Komunál 2026;
- zobrazit libovolnou oficiální kandidátku;
- přepnout na uživatelsky definované **politické rodiny**;
- ad hoc vybrat více kandidátek a zobrazit jejich součet;
- zobrazit podíl hlasů, absolutní počet hlasů a volební účast;
- u krajských a sněmovních voleb zobrazit index relativní síly, kde Liberecký kraj = 100;
- filtrovat jednu obec nebo zobrazit celý kraj;
- kliknout na okrsek a zobrazit výsledky všech kandidátek v daném okrsku.

## Nejjednodušší spuštění ve Windows

1. Nainstaluj Python 3, pokud jej ještě nemáš.
2. Dvakrát klikni na `1_VYTVORIT_DATA.bat`.
3. Po dokončení spusť `2_SPUSTIT_ATLAS.bat`.
4. Atlas se otevře na `http://localhost:8000`.

## Ruční instalace

Potřebuješ Python 3.10+.

```bash
pip install -r requirements.txt
python build_data.py
```

Skript stáhne oficiální data ČSÚ a vytvoří soubory v `public/data/`.

Potom spusť lokální webserver:

```bash
python -m http.server 8000 -d public
```

A otevři:

```text
http://localhost:8000
```

> Důvod pro lokální server: webový prohlížeč z bezpečnostních důvodů obvykle nedovolí `fetch()` datových souborů při otevření `index.html` přímo jako `file://`.

## Slučování stran a koalic

Při prvním spuštění `build_data.py` vznikne:

```text
config/harmonization.csv
```

Každý řádek obsahuje jednu oficiální kandidátku a sloupec `family_name`.

Výchozí stav je:

```text
family_name = oficiální název kandidátky
```

Pokud chceš například několik **samostatně kandidujících** subjektů zobrazovat jako jeden srovnávací blok, nastav jim stejné `family_name` a znovu spusť:

```bash
python build_data.py
```

Příklad principu:

```csv
list_name,family_name
ODS,SPOLU-family
TOP 09,SPOLU-family
KDU-ČSL,SPOLU-family
SPOLU,SPOLU-family
```

Důležité: pokud ODS, TOP 09 a KDU-ČSL kandidovaly **společně na jedné kandidátce**, atlas její hlasy nijak nerozděluje mezi členské strany. Společná kandidátka je jeden skutečný volební výsledek. Harmonizace pouze umožňuje seskupit již existující kandidátky pro srovnávací pohled.

## Vlastní součet bez změny dat

V mapě lze zvolit režim **„Vlastní součet kandidátek“** a označit více kandidátek najednou. Jejich hlasy se v každém okrsku sečtou. Tento režim je užitečný pro rychlé deskriptivní srovnání bez zásahu do `harmonization.csv`.

## Výstupní data

Po sestavení projektu vzniknou mj.:

```text
public/data/results_normalized.csv
public/data/results.json
public/data/precincts_kz2024.geojson
public/data/precincts_ps2025.geojson
public/data/precincts_kv2026.geojson
```

`results_normalized.csv` je zároveň použitelný v QGISu, Tableau, Power BI nebo pro další statistickou analýzu.

## Zdrojová data

Používají se oficiální otevřená data Českého statistického úřadu / volby.gov.cz a oficiální polygonové vrstvy volebních okrsků.

Projekt je záměrně deskriptivní: pracuje pouze s agregovanými veřejnými volebními výsledky, nikoli s individuálními údaji o voličích.

## Změny ve verzi 4
- mapa nezobrazuje žádný světový/OSM podklad; viditelné jsou pouze oficiální okrsky Libereckého kraje,
- polygonová vrstva používá SVG a reaguje na hover i kliknutí,
- výběr obce přiblíží a zvýrazní obec, ale zbytek Libereckého kraje zůstává v mapě,
- procentní ukazatele jsou barevně tříděny po 1 procentním bodu (0–1 %, 1–2 %, ...), nikoli podle kvantilů.


## Liberec a Vratislavice (v7)

U komunálních voleb je statutární město Liberec v územních datech rozděleno na dvě jednotky: **Liberec (nečleněné město)** a **Liberec‑Vratislavice nad Nisou**. Verze v7 opravuje spojení registru ČSÚ tak, aby se tyto dvě jednotky nezobrazovaly omylem obě pod názvem Vratislavice. Hlavní volba do Zastupitelstva statutárního města Liberec se přitom týká obou jednotek; Vratislavice mají navíc vlastní volbu do zastupitelstva městského obvodu, která zůstává v plném normalizovaném CSV.
