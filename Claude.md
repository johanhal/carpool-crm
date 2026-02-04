# Carpool CRM

## Overview
Sales tool for Ruter's carpooling pilot targeting companies in specific geographic areas.

**Live:** https://ruter-carpool-crm.vercel.app
**Password:** `bevegelsesfrihet`

## Areas

| Area | Companies | Employees | Description |
|------|-----------|-----------|-------------|
| Hagan/Gjelleråsen | 53 | ~4,900 | Industrial area, Nittedal |
| Ås | 12 | ~4,300 | Campus Ås, university & research |

## Project Structure

```
output/
├── index.html              # Area picker (password protected)
├── hagan/
│   ├── index.html          # Generated report
│   └── bedrifter.csv       # Company data
└── a_s/
    ├── index.html          # Generated report
    └── bedrifter.csv       # Company data

Scripts:
├── generate_report.py      # Shared HTML report generator
├── filter_companies.py     # Filter companies by geolocation
├── enrich_companies.py     # Enrich with contact info
├── google_sheets.py        # Sync to Google Sheets
└── bedrift                 # CLI wrapper for full pipeline
```

## Generate Reports

All areas use a shared template via `generate_report.py`. Changes to the template apply to all areas.

```bash
# Generate all areas
python generate_report.py

# Generate specific area
python generate_report.py hagan
python generate_report.py a_s

# List available areas
python generate_report.py --list
```

## Add New Area

1. Add area config to `AREAS` dict in `generate_report.py`
2. Create folder in `output/` with `bedrifter.csv`
3. Run `python generate_report.py`
4. Area automatically appears in the picker

## CSV Schema

Required columns:
- `organisasjonsnummer`, `navn`, `antallAnsatte`, `adresse`
- `latitude`, `longitude`
- `naeringskode_beskrivelse`

Contact columns (supports up to 4 contacts):
- `kontakt_navn`, `kontakt_rolle`, `kontakt_telefon`, `kontakt_epost`
- `kontakt2_navn`, `kontakt2_rolle`, `kontakt2_telefon`, `kontakt2_epost`
- `kontakt3_navn`, `kontakt3_rolle`, `kontakt3_telefon`, `kontakt3_epost`
- `kontakt4_navn`, `kontakt4_rolle`, `kontakt4_telefon`, `kontakt4_epost`

Optional:
- `hjemmeside`, `proff_url`, `salgsnotater`

## Scoring Algorithm

Carpool potential score (0-100%):
- **Employees** (0-50 pts): 500+ = 50, 200+ = 40, 100+ = 30, 50+ = 20, 20+ = 10
- **Shift work industry** (0-30 pts): production, warehouse, security, health, cleaning, transport
- **Public sector** (0-10 pts): kommune, state, university, school
- **Research/campus** (0-10 pts): research, institute, university

## Tech Stack

- **Frontend:** Vanilla HTML/CSS/JS, Lucide icons
- **Map:** Leaflet.js with CartoDB tiles
- **Hosting:** Vercel (static site)
- **Data:** CSV with Python scripts

## Deployment

```bash
cd output
vercel --prod
```

## Google Sheets Sync

```bash
python google_sheets.py sync "output/hagan/bedrifter.csv"
```
