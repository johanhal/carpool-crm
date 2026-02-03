# Metode: Fra geografisk område til beriket salgsliste

## Oversikt over pipeline

```
GeoJSON-polygon → Filtrering → Beriking → Kontaktpersoner
     ↓                ↓            ↓            ↓
  geojson.io    filter_companies  enrich_    Claude med
                    .py          companies    WebSearch
                                    .py
```

## Steg 1: Definer geografisk område
- Tegn polygon på **geojson.io**
- Last ned som `.geojson`-fil

## Steg 2: Filtrer bedrifter (`filter_companies.py`)
1. **Finn postnummer** som ligger innenfor/nær polygonet (fra `postnummer.txt`)
2. **Last BRREG-data** (hovedenheter + underenheter) - filtrerer på postnummer
3. **Filtrer på ansatte** (standard: 20-200)
4. **Geokod adresser** via Kartverket API (med caching)
5. **Sjekk om punktet er innenfor polygonet** (Shapely `contains`)
6. **Dedupliser** på adresse

**Output:** `output/<område>_<tidspunkt>.csv`

## Steg 3: Berik med BRREG-data (`enrich_companies.py`)
1. **Hent kontaktinfo** fra BRREG API: hjemmeside, e-post, telefon
2. **Generer samkjøringspotensial** (0-100 score) basert på:
   - **Bransje** (NACE-kode) - offentlig, helse, IT, finans gir høy score
   - **Størrelse** - flere ansatte = høyere potensial
   - **Beliggenhet** - Fornebu, Lysaker, Skøyen etc. gir bonus
3. **Lag salgsargumenter** tilpasset hver bedrift

**Output:** `enriched_companies.csv` med potensial-score og argumenter

## Steg 4: Finn kontaktpersoner (manuelt/Claude)
Claude bruker WebSearch for å finne:
- Beste kontaktperson (HR, bærekraft, daglig leder)
- Navn, rolle, e-post, telefon

## Datakilder

| Kilde | Hva |
|-------|-----|
| BRREG (csv.gz) | Alle norske bedrifter med adresse og ansatte |
| BRREG API | Hjemmeside, e-post, telefon |
| Kartverket API | Geokoding av adresser |
| erikbolstad.no | Postnummer med koordinater |
