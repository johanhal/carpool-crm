# Ruter Samkjøring CRM

## Prosjektoversikt
Salgsverktøy for Ruters samkjøringspilot rettet mot bedrifter i Hagan/Gjelleråsen industriområde.

**Live:** https://ruter-carpool-crm.vercel.app
**Passord:** `bevegelsesfrihet`

## Hva er bygget

### Salgsliste (HTML-rapport)
- **53 bedrifter** med kontaktinfo og samkjøringspotensial
- **Card-basert layout** med vertikal scrolling for enkel lesing
- **Samkjøringsscore (0-100%)** basert på:
  - Antall ansatte (0-50 poeng)
  - Bransje med skiftarbeid: industri, lager, sikkerhet, helse (0-30 poeng)
  - Offentlig sektor bonus (0-10 poeng)
  - Del av konsern bonus (0-10 poeng)
- **Sortering:** Potensial / Ansatte / Navn
- **Interaktivt kart** med Leaflet.js
- **Google Sheets sync** for salgsfunnel-tracking

### Topp 5 bedrifter for samkjøring
| # | Bedrift | Score | Ansatte |
|---|---------|-------|---------|
| 1 | Ringnes Supply Company | 90% | 764 |
| 2 | Nittedal Kommune | 80% | 407 |
| 3 | Garda Sikring | 80% | 371 |
| 4 | Diplom-Is | 80% | 298 |
| 5 | Würth Norge | 60% | 672 |

### Datainnsamling
- Bedriftsdata fra Brønnøysundregistrene
- Kontaktpersoner funnet via websøk (Proff.no, bedriftssider, LinkedIn)
- Kontaktprioritet: HR-direktør > Bærekraftsansvarlig > Kontorsjef > Daglig leder > Styreleder
- Skreddersydde salgsargumenter per bedrift

## Teknisk stack
- **Frontend:** Vanilla HTML/CSS/JS med Lucide icons
- **Kart:** Leaflet.js med CartoDB tiles
- **Hosting:** Vercel (statisk site)
- **Data:** CSV med Python-scripts for berikelse
- **CRM-sync:** Google Sheets API

## Filer
```
output/hagan/
├── index.html          # Hovedside (passordbeskyttet)
├── salgsliste.html     # Kopi av index.html
└── bedrifter.csv       # Rådata med kontaktinfo

Scripts:
├── filter_companies.py   # Filtrer bedrifter på geolokasjon
├── enrich_companies.py   # Berik med kontaktinfo
├── google_sheets.py      # Sync til Google Sheets
└── bedrift               # CLI-wrapper
```

## Google Sheets sync
```bash
python google_sheets.py sync "output/hagan/bedrifter.csv"
```

Kolonner i Sheet:
- Bedriftsinfo (orgnr, navn, ansatte, adresse, bransje)
- Kontaktinfo (navn, rolle, telefon, e-post)
- Salgsnotater
- **Salgskolonner** (redigeres manuelt): status, sist_kontaktet, neste_oppfølging, interne_notater, ansvarlig

## Deployment
```bash
cd output/hagan
vercel --prod
```

## Neste steg
- [ ] Legge til flere områder (Skedsmo, Lillestrøm, etc.)
- [ ] Automatisk oppdatering av kontaktinfo
- [ ] Integrasjon med CRM-system
- [ ] E-post templates for outreach
