# Google Sheets Setup

Denne guiden beskriver hvordan du setter opp Google Sheets-integrasjon for salgsfunnel-tracking av bedrifter.

## Oversikt

Integrasjonen bruker en Google Service Account for å synkronisere bedriftsdata til et Google Sheet. Dette gjør at:
- Data kan synkroniseres automatisk fra kommandolinjen
- Flere personer kan jobbe i samme Sheet
- Salgskolonner (status, notater, ansvarlig) bevares mellom synkroniseringer

## Steg 1: Opprett Google Cloud-prosjekt

1. Gå til [Google Cloud Console](https://console.cloud.google.com/)
2. Klikk på prosjektvelgeren øverst og velg **"New Project"**
3. Gi prosjektet et navn (f.eks. "Bedrifter Salgsfunnel")
4. Klikk **"Create"**

## Steg 2: Aktiver Google Sheets API

1. I venstre meny, gå til **"APIs & Services" > "Library"**
2. Søk etter **"Google Sheets API"**
3. Klikk på den og trykk **"Enable"**

## Steg 3: Opprett Service Account

1. Gå til **"APIs & Services" > "Credentials"**
2. Klikk **"Create Credentials" > "Service Account"**
3. Fyll inn:
   - Service account name: `bedrifter-sync`
   - Service account ID: (autofylles)
4. Klikk **"Create and Continue"**
5. Hopp over rolle-valg (trykk **"Continue"**)
6. Klikk **"Done"**

## Steg 4: Last ned nøkkelfil

1. I listen over service accounts, klikk på den du nettopp opprettet
2. Gå til fanen **"Keys"**
3. Klikk **"Add Key" > "Create new key"**
4. Velg **"JSON"** og klikk **"Create"**
5. En JSON-fil lastes ned automatisk

## Steg 5: Plasser nøkkelfilen

1. Opprett mappen `.credentials` i prosjektmappen:
   ```bash
   mkdir -p .credentials
   ```

2. Flytt den nedlastede JSON-filen til:
   ```
   .credentials/service_account.json
   ```

## Steg 6: Opprett og del Google Sheet

1. Gå til [Google Sheets](https://sheets.google.com/) og opprett et nytt ark
2. Gi det et beskrivende navn (f.eks. "Bedrifter Salgsfunnel")
3. Klikk **"Share"** øverst til høyre
4. Legg til service account-emailen (finner du i JSON-filen under `client_email`)
   - Den ser ut som: `bedrifter-sync@prosjektnavn.iam.gserviceaccount.com`
5. Gi tilgangen **"Editor"**
6. Klikk **"Share"**

## Steg 7: Kjør setup-kommandoen

```bash
python google_sheets.py setup
```

Følg instruksjonene og lim inn Spreadsheet ID fra URL-en:
```
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
```

## Bruk

### Synkroniser manuelt fra CSV

```bash
python google_sheets.py sync output/skedsmo_20260129.csv
```

### Automatisk etter enrich

Når du kjører `enrich_companies.py`, blir du spurt om du vil synkronisere til Sheets:

```bash
python enrich_companies.py output/skedsmo_filtrert.csv -o output/skedsmo_beriket.csv
# ...
# Oppdatere Google Sheets? (Y/n): y
```

### Fra HTML-rapporten

Klikk på "Sync til Sheets"-knappen i HTML-rapporten for å få kommandoen du kan kjøre.

## Kolonnestruktur i Sheet

| Kolonne | Kilde | Beskrivelse |
|---------|-------|-------------|
| organisasjonsnummer | Script | Unik ID |
| navn | Script | Bedriftsnavn |
| antallAnsatte | Script | Antall ansatte |
| adresse | Script | Besøksadresse |
| hjemmeside | Script | Nettside |
| epostadresse | Script | E-post fra BRREG |
| telefon | Script | Telefon fra BRREG |
| kontakt_navn | Script | Kontaktperson (fra research) |
| kontakt_rolle | Script | Kontaktpersonens rolle |
| **status** | Manuell | Ny / Kontaktet / Interessert / Ikke interessert |
| **sist_kontaktet** | Manuell | Dato for siste kontakt |
| **neste_oppfolging** | Manuell | Dato for neste oppfølging |
| **interne_notater** | Manuell | Dine notater |
| **ansvarlig** | Manuell | Hvem som følger opp |
| **omrade** | Auto | Områdenavn fra filnavn |

**Merk:** Salgskolonnene (markert med **bold**) bevares ved sync - de blir aldri overskrevet av scriptet.

## Feilsøking

### "403 Forbidden" eller "permission denied"
- Sjekk at Sheet er delt med service account-emailen
- Sjekk at service account har "Editor"-tilgang

### "404 Not Found"
- Sjekk at Spreadsheet ID er korrekt
- Sjekk at sheet-navnet matcher (standard: "Bedrifter")

### "API not enabled"
- Gå til Google Cloud Console og aktiver Google Sheets API

## Sikkerhet

- **Aldri commit** `.credentials/` eller `sheets_config.json` til git
- Disse filene er allerede i `.gitignore`
- Hold nøkkelfilen trygg - den gir full tilgang til å redigere delte Sheets
