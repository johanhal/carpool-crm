# Ruter - bedriftsøk for samkjøring

## Hurtigstart

```bash
cd "/Users/johan/Dev/Beta Mobility/Ruter/Bedrifter"
source venv/bin/activate

# 1. Filtrer bedrifter etter område (lager filtered_companies.csv)
python filter_companies.py ditt_område.geojson -o filtered_companies.csv

# 2. Berik med BRREG-data (hjemmeside, e-post fra registeret)
python enrich_companies.py filtered_companies.csv -o enriched_companies.csv
```

## Lag GeoJSON

Tegn et område på kartet på **https://geojson.io** og last ned som GeoJSON-fil.

## Finn kontaktpersoner med Claude

Etter filtrering, be Claude om å finne kontakter:

```
Finn kontaktpersoner for bedriftene i enriched_companies.csv.
For hver bedrift, finn:
1. Bedriftens hjemmeside (hvis mangler)
2. Beste kontaktperson for en samkjøringspilot (HR, bærekraft, daglig leder)
3. Kontaktens navn, rolle, e-post, telefon

Lagre til companies_with_contacts.csv
```

Claude vil bruke sub-agenter med WebSearch for å finne kontaktpersoner.

## Filer

| Fil | Beskrivelse |
|-----|-------------|
| `filter_companies.py` | Filtrer etter GeoJSON-polygon + antall ansatte |
| `enrich_companies.py` | Legg til BRREG-data (hjemmeside, e-post, telefon) |
| `research_contacts.py` | Generer research-prompter |
| `execute_research.py` | Enkel web scraping (uten AI) |
| `data/postnummer.txt` | Norske postnummer med koordinater |
| `data/enheter.csv.gz` | Hovedenheter fra BRREG |
| `data/underenheter.csv.gz` | Underenheter fra BRREG |
| `geocode_cache.json` | Cached geokoding-resultater |
| `company_cache.json` | Cached bedriftsoppslag |

## Alternativer

```bash
python filter_companies.py område.geojson \
    --output resultater.csv \
    --min-employees 10 \
    --max-employees 500
```

## Datakilder

- Bedriftsdata: https://data.brreg.no/enhetsregisteret/api/
- Postnummer: https://www.erikbolstad.no/postnummer-koordinatar/
- Geokoding: https://ws.geonorge.no/adresser/v1/sok
- Lag GeoJSON: https://geojson.io
