# Nasazení atlasu na Vercel

Atlas je čistě statická webová aplikace. Vercel servíruje obsah složky `public`.

## Nejdříve vytvoř data

Na Windows spusť `1_VYTVORIT_DATA.bat`.

Po úspěšném běhu musí existovat alespoň:

- `public/data/metadata.json`
- `public/data/results.json`
- `public/data/precincts_kz2024.geojson`
- `public/data/precincts_ps2025.geojson`
- `public/data/precincts_kv2026.geojson`

Bez složky `public/data` se web sice nasadí, ale mapa nebude mít co zobrazit.

## Varianta A – GitHub + Vercel (doporučená)

1. Nahraj celou složku projektu do GitHub repozitáře, včetně vygenerované `public/data`.
2. Ve Vercelu zvol Add New → Project a importuj repozitář.
3. Root Directory nech `./`.
4. Framework Preset nastav na Other / žádný framework.
5. Build Command není potřeba.
6. Output Directory je `public` (je zároveň uvedena ve `vercel.json`).
7. Deploy.

Při další úpravě dat znovu spusť `1_VYTVORIT_DATA.bat`, commitni změny v `public/data` a pushni je na GitHub. Vercel automaticky vytvoří novou verzi.

## Varianta B – Vercel CLI

Pokud používáš Vercel CLI, spusť jej v kořenové složce projektu a proveď deployment. `vercel.json` nastavuje jako statický výstup složku `public`.

## Poznámka k soukromí

Pokud atlas obsahuje interní analytické vrstvy nebo pracovní klasifikaci koalic, nepoužívej veřejně sdílený deployment bez nastavení přístupu.
