#!/usr/bin/env python3
"""
Google Sheets-integrasjon for salgsfunnel-tracking av bedrifter.

Bruk:
    python google_sheets.py setup              # Førstegangsoppsett
    python google_sheets.py sync <csv-fil>     # Synkroniser CSV til Sheets
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "sheets_config.json"
CREDENTIALS_DIR = SCRIPT_DIR / ".credentials"
SERVICE_ACCOUNT_FILE = CREDENTIALS_DIR / "service_account.json"

# Kolonner som scriptet oppdaterer (fra CSV)
SCRIPT_COLUMNS = [
    "cluster_id",       # Unik ID per cluster/område
    "cluster_name",     # Navn på geojson/område
    "import_timestamp", # Tidspunkt for import
    "organisasjonsnummer",
    "navn",
    "antallAnsatte",
    "adresse",
    "latitude",
    "longitude",
    "naeringskode",
    "naeringskode_beskrivelse",
    "hjemmeside",
    "epostadresse",
    "proff_url",
    "kontakt_navn",
    "kontakt_rolle",
    "kontakt_epost",
    "kontakt_telefon",
    "salgsnotater",
]

# Salgskolonner som bevares ved sync (redigeres manuelt i Sheet)
SALES_COLUMNS = [
    "status",           # not started yet, Kontaktet, Interessert, Ikke interessert
    "sist_kontaktet",   # Dato
    "neste_oppfolging", # Dato
    "interne_notater",  # Tekst
    "ansvarlig",        # Tekst
]

# Alle kolonner i rekkefølge
ALL_COLUMNS = SCRIPT_COLUMNS + SALES_COLUMNS


def load_config() -> dict:
    """Last inn konfigurasjon fra disk."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    """Lagre konfigurasjon til disk."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_sheets_client():
    """Opprett Google Sheets API-klient med service account."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("Feil: Google API-biblioteker mangler.")
        print("Kjør: pip install google-api-python-client google-auth")
        sys.exit(1)

    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"Feil: Service account-fil mangler: {SERVICE_ACCOUNT_FILE}")
        print("\nFølg instruksjonene i GOOGLE_SHEETS_SETUP.md for å sette opp.")
        sys.exit(1)

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )

    service = build("sheets", "v4", credentials=credentials)
    return service.spreadsheets()


class SheetsClient:
    """Klient for å synkronisere bedriftsdata til Google Sheets."""

    def __init__(self):
        config = load_config()
        self.spreadsheet_id = config.get("spreadsheet_id")
        self.sheet_name = config.get("sheet_name", "Bedrifter")

        if not self.spreadsheet_id:
            print("Feil: Spreadsheet ID ikke konfigurert.")
            print("Kjør først: python google_sheets.py setup")
            sys.exit(1)

        self.client = get_sheets_client()

    def _get_sheet_data(self) -> list[list]:
        """Hent alle data fra Sheet."""
        try:
            result = self.client.values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:Z"
            ).execute()
            return result.get("values", [])
        except Exception as e:
            if "404" in str(e) or "notFound" in str(e):
                return []
            raise

    def _ensure_headers(self):
        """Sørg for at Sheet har riktige kolonneoverskrifter."""
        data = self._get_sheet_data()

        if not data or data[0] != ALL_COLUMNS:
            # Sett headers
            self.client.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1",
                valueInputOption="RAW",
                body={"values": [ALL_COLUMNS]}
            ).execute()
            print(f"  Oppdaterte kolonneoverskrifter i '{self.sheet_name}'")

    def _setup_data_validation(self):
        """Sett opp dropdown for status-kolonnen."""
        # Finn sheet ID
        sheet_metadata = self.client.get(spreadsheetId=self.spreadsheet_id).execute()
        sheet_id = None
        for sheet in sheet_metadata.get("sheets", []):
            if sheet["properties"]["title"] == self.sheet_name:
                sheet_id = sheet["properties"]["sheetId"]
                break

        if sheet_id is None:
            return

        # Status-kolonne er index av "status" i ALL_COLUMNS
        status_col_index = ALL_COLUMNS.index("status")

        requests = [{
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": status_col_index,
                    "endColumnIndex": status_col_index + 1
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": "not started yet"},
                            {"userEnteredValue": "Kontaktet"},
                            {"userEnteredValue": "Interessert"},
                            {"userEnteredValue": "Ikke interessert"},
                        ]
                    },
                    "showCustomUi": True,
                    "strict": False
                }
            }
        }]

        try:
            self.client.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests}
            ).execute()
        except Exception:
            pass  # Ignorer feil ved data validation

    def sync_companies(self, df: pd.DataFrame, area_name: str = "", cluster_id: str = "") -> dict:
        """
        Synkroniser bedrifter til Google Sheets med smart merge.

        Args:
            df: DataFrame med bedriftsdata
            area_name: Navn på område/cluster (f.eks. "skedsmo")
            cluster_id: Unik ID for clusteret (genereres automatisk hvis tom)

        Returns:
            dict med statistikk over synkroniseringen
        """
        print(f"\nSynkroniserer til Google Sheets...")

        # Generer cluster_id hvis ikke oppgitt
        if not cluster_id and area_name:
            # Lag en kort hash basert på area_name
            import hashlib
            cluster_id = hashlib.md5(area_name.encode()).hexdigest()[:8].upper()

        # Tidsstempel for denne importen
        import_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Sørg for riktige headers
        self._ensure_headers()

        # Hent eksisterende data
        existing_data = self._get_sheet_data()

        # Bygg mapping fra orgnr til rad-data (bevar salgskolonner)
        existing_map = {}
        if len(existing_data) > 1:
            headers = existing_data[0]
            for row in existing_data[1:]:
                # Pad row to match headers length
                row_padded = row + [""] * (len(headers) - len(row))
                row_dict = dict(zip(headers, row_padded))
                orgnr = row_dict.get("organisasjonsnummer", "")
                if orgnr:
                    existing_map[orgnr] = row_dict

        # Bygg nye rader
        new_rows = []
        updated_count = 0
        new_count = 0

        for _, csv_row in df.iterrows():
            orgnr = str(csv_row.get("organisasjonsnummer", ""))
            if not orgnr:
                continue

            row_data = {}

            # Sett cluster-kolonner
            row_data["cluster_id"] = cluster_id
            row_data["cluster_name"] = area_name
            row_data["import_timestamp"] = import_timestamp

            # Kopier script-kolonner fra CSV
            for col in SCRIPT_COLUMNS:
                if col in ["cluster_id", "cluster_name", "import_timestamp"]:
                    continue  # Allerede satt
                val = csv_row.get(col, "")
                if pd.isna(val):
                    val = ""
                # Konverter navn til title case (stor forbokstav)
                if col == "navn" and val:
                    val = str(val).title()
                row_data[col] = str(val)

            # Bevar eller initialiser salgskolonner
            if orgnr in existing_map:
                # Bevar eksisterende salgsdata
                existing = existing_map[orgnr]
                for col in SALES_COLUMNS:
                    row_data[col] = existing.get(col, "")
                updated_count += 1
            else:
                # Ny bedrift - initialiser salgskolonner
                row_data["status"] = "not started yet"
                row_data["sist_kontaktet"] = ""
                row_data["neste_oppfolging"] = ""
                row_data["interne_notater"] = ""
                row_data["ansvarlig"] = ""
                new_count += 1

            # Konverter til liste i riktig rekkefølge
            new_rows.append([row_data.get(col, "") for col in ALL_COLUMNS])

        # Legg til bedrifter som var i Sheet men ikke i CSV (bevar dem)
        csv_orgnrs = set(str(csv_row.get("organisasjonsnummer", "")) for _, csv_row in df.iterrows())
        preserved_count = 0
        for orgnr, existing in existing_map.items():
            if orgnr not in csv_orgnrs:
                new_rows.append([existing.get(col, "") for col in ALL_COLUMNS])
                preserved_count += 1

        # Sorter etter bedriftsnavn
        new_rows.sort(key=lambda r: r[ALL_COLUMNS.index("navn")].lower())

        # Skriv alle data til Sheet (headers + rader)
        all_data = [ALL_COLUMNS] + new_rows

        self.client.values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.sheet_name}!A1",
            valueInputOption="RAW",
            body={"values": all_data}
        ).execute()

        # Sett opp data validation for status
        self._setup_data_validation()

        # Statistikk
        result = {
            "total": len(new_rows),
            "new": new_count,
            "updated": updated_count,
            "preserved": preserved_count,
        }

        print(f"  Totalt: {result['total']} bedrifter")
        print(f"  Nye: {result['new']}")
        print(f"  Oppdatert: {result['updated']}")
        if preserved_count > 0:
            print(f"  Bevart (ikke i CSV): {result['preserved']}")

        return result


def setup_credentials():
    """Interaktivt førstegangsoppsett."""
    print("=" * 50)
    print("Google Sheets Setup for Bedriftsoversikt")
    print("=" * 50)

    # Sjekk om credentials-mappe eksisterer
    if not CREDENTIALS_DIR.exists():
        CREDENTIALS_DIR.mkdir(parents=True)
        print(f"\nOpprettet mappe: {CREDENTIALS_DIR}")

    # Sjekk service account-fil
    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"\n1. Plasser service account JSON-filen her:")
        print(f"   {SERVICE_ACCOUNT_FILE}")
        print("\n   Se GOOGLE_SHEETS_SETUP.md for instruksjoner.")
        print("\n   Trykk Enter når filen er på plass...")
        input()

        if not SERVICE_ACCOUNT_FILE.exists():
            print("Feil: Filen ble ikke funnet. Avbryter.")
            sys.exit(1)

    # Les service account email
    with open(SERVICE_ACCOUNT_FILE) as f:
        sa_data = json.load(f)
        sa_email = sa_data.get("client_email", "")

    print(f"\n2. Service account funnet: {sa_email}")

    # Spør om spreadsheet ID
    print("\n3. Opprett et nytt Google Sheet (eller bruk et eksisterende)")
    print("   og del det med service account-emailen ovenfor.")
    print("\n   Sheet URL ser slik ut:")
    print("   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit")

    spreadsheet_id = input("\n   Lim inn Spreadsheet ID: ").strip()

    if not spreadsheet_id:
        print("Feil: Spreadsheet ID er påkrevd. Avbryter.")
        sys.exit(1)

    # Spør om sheet-navn
    sheet_name = input("\n   Sheet-navn (standard: Bedrifter): ").strip()
    if not sheet_name:
        sheet_name = "Bedrifter"

    # Lagre konfig
    config = {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "service_account_email": sa_email,
        "setup_date": datetime.now().isoformat(),
    }
    save_config(config)

    print(f"\n4. Konfigurasjon lagret til {CONFIG_FILE}")

    # Test tilkobling
    print("\n5. Tester tilkobling...")
    try:
        client = SheetsClient()
        client._ensure_headers()
        print("   Tilkobling OK!")
        print(f"\n   Sheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    except Exception as e:
        print(f"   Feil ved tilkobling: {e}")
        print("\n   Sjekk at Sheet er delt med service account-emailen.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("Setup fullført!")
    print("=" * 50)


def sync_from_csv(csv_path: str):
    """Synkroniser en CSV-fil til Google Sheets."""
    csv_file = Path(csv_path)

    if not csv_file.exists():
        print(f"Feil: Finner ikke fil: {csv_path}")
        sys.exit(1)

    # Les CSV
    print(f"Leser {csv_path}...")
    df = pd.read_csv(csv_file, dtype=str)
    print(f"  {len(df)} bedrifter lastet")

    # Utled område fra filnavn (f.eks. "skedsmo_20260129.csv" -> "skedsmo")
    area_name = csv_file.stem.split("_")[0] if "_" in csv_file.stem else csv_file.stem

    # Synkroniser
    client = SheetsClient()
    result = client.sync_companies(df, area_name)

    config = load_config()
    print(f"\nSheet: https://docs.google.com/spreadsheets/d/{config['spreadsheet_id']}/edit")


def main():
    parser = argparse.ArgumentParser(
        description="Google Sheets-integrasjon for bedriftsoversikt"
    )
    subparsers = parser.add_subparsers(dest="command", help="Kommandoer")

    # Setup-kommando
    subparsers.add_parser("setup", help="Førstegangsoppsett")

    # Sync-kommando
    sync_parser = subparsers.add_parser("sync", help="Synkroniser CSV til Sheets")
    sync_parser.add_argument("csv", help="CSV-fil å synkronisere")

    args = parser.parse_args()

    if args.command == "setup":
        setup_credentials()
    elif args.command == "sync":
        sync_from_csv(args.csv)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
