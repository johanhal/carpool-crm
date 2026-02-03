#!/usr/bin/env python3
"""
Filtrer norske bedrifter etter geografisk område og antall ansatte.

Bruk:
    python filter_companies.py område.geojson --output filtrerte_bedrifter.csv

Tips: Lag GeoJSON-filer enkelt på https://geojson.io
"""

import argparse
import json
import re
import shlex
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from shapely.geometry import Point, shape
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
OUTPUT_DIR = SCRIPT_DIR / "output"
CACHE_FILE = SCRIPT_DIR / "geocode_cache.json"
POSTNUMMER_FILE = DATA_DIR / "postnummer.txt"

KARTVERKET_API = "https://ws.geonorge.no/adresser/v1/sok"


def generate_output_folder(geojson_path: str) -> tuple[Path, str]:
    """Generate output folder based on GeoJSON name. Returns (folder_path, area_name)."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Extract location name from GeoJSON filename
    geojson_name = Path(geojson_path).stem
    # Clean up common patterns like "map (1)" -> "map"
    geojson_name = re.sub(r'\s*\(\d+\)$', '', geojson_name)
    # Sanitize for filesystem
    area_name = re.sub(r'[^\w\-]', '_', geojson_name).strip('_').lower()
    if not area_name or area_name == "map":
        area_name = "omraade"

    # Create folder for this area
    area_folder = OUTPUT_DIR / area_name
    area_folder.mkdir(exist_ok=True)

    return area_folder, area_name


def load_geojson_polygon(geojson_path: str):
    """Last inn GeoJSON-fil og returner geometrien som Shapely-objekt."""
    with open(geojson_path) as f:
        data = json.load(f)

    if data["type"] == "FeatureCollection":
        geometry = data["features"][0]["geometry"]
    elif data["type"] == "Feature":
        geometry = data["geometry"]
    else:
        geometry = data

    return shape(geometry)


def load_postal_code_data() -> pd.DataFrame:
    """Last inn postnummer-koordinater fra lokal fil."""
    if not POSTNUMMER_FILE.exists():
        print(f"Advarsel: {POSTNUMMER_FILE} ikke funnet.", file=sys.stderr)
        return pd.DataFrame()

    df = pd.read_csv(
        POSTNUMMER_FILE,
        sep="\t",
        skiprows=4,
        dtype=str,
        on_bad_lines="skip",
    )
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
    return df


def get_postal_codes_in_polygon(polygon, postal_df: pd.DataFrame) -> set[str]:
    """Finn postnummer som ligger innenfor eller nær polygonet."""
    if postal_df.empty:
        return set()

    min_lon, min_lat, max_lon, max_lat = polygon.bounds
    buffer = 0.05

    bbox_mask = (
        (postal_df["LON"] >= min_lon - buffer) &
        (postal_df["LON"] <= max_lon + buffer) &
        (postal_df["LAT"] >= min_lat - buffer) &
        (postal_df["LAT"] <= max_lat + buffer)
    )
    candidates = postal_df[bbox_mask]

    postal_codes = set()
    for _, row in candidates.iterrows():
        if pd.notna(row["LAT"]) and pd.notna(row["LON"]):
            postal_codes.add(row["POSTNR"])

    return postal_codes


def load_cache() -> dict:
    """Last inn geokoding-cache fra disk."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    """Lagre geokoding-cache til disk."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def geocode_address(
    address: str,
    postal_code: str,
    city: str,
    municipality_code: str | None,
    cache: dict,
) -> tuple[float | None, float | None]:
    """Geokod en adresse via Kartverkets API."""
    cache_key = f"{address}|{postal_code}|{city}".lower().strip()

    if cache_key in cache:
        cached = cache[cache_key]
        return cached.get("lat"), cached.get("lon")

    search_query = f"{address}, {postal_code} {city}"
    params = {"sok": search_query, "treffPerSide": 1}

    if municipality_code:
        params["kommunenummer"] = municipality_code

    try:
        response = requests.get(KARTVERKET_API, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("adresser") and len(data["adresser"]) > 0:
            addr = data["adresser"][0]
            lat = addr["representasjonspunkt"]["lat"]
            lon = addr["representasjonspunkt"]["lon"]

            cache[cache_key] = {
                "lat": lat,
                "lon": lon,
                "timestamp": date.today().isoformat(),
            }
            return lat, lon

    except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
        print(f"  Geokoding-feil for '{search_query}': {e}", file=sys.stderr)

    cache[cache_key] = {"lat": None, "lon": None, "timestamp": date.today().isoformat()}
    return None, None


def load_company_data(postal_codes: set[str] | None = None) -> pd.DataFrame:
    """Last inn og kombiner datasett, eventuelt med postnummer-filtrering."""
    enheter_path = DATA_DIR / "enheter.csv.gz"
    underenheter_path = DATA_DIR / "underenheter.csv.gz"

    if not enheter_path.exists() or not underenheter_path.exists():
        print("Feil: Datafiler ikke funnet. Kjør download_data.sh først.", file=sys.stderr)
        sys.exit(1)

    enheter_cols_to_load = [
        "organisasjonsnummer", "navn", "antallAnsatte",
        "forretningsadresse.adresse", "forretningsadresse.postnummer",
        "forretningsadresse.poststed", "forretningsadresse.kommunenummer",
        "naeringskode1.kode", "naeringskode1.beskrivelse",
    ]

    underenheter_cols_to_load = [
        "organisasjonsnummer", "navn", "antallAnsatte",
        "beliggenhetsadresse.adresse", "beliggenhetsadresse.postnummer",
        "beliggenhetsadresse.poststed", "beliggenhetsadresse.kommunenummer",
        "naeringskode1.kode", "naeringskode1.beskrivelse",
    ]

    print("\nLaster bedriftsdata fra BRREG...")
    with tqdm(total=2, desc="Laster filer", unit="fil", bar_format="{desc}: {n}/{total} {bar}") as pbar:
        enheter = pd.read_csv(
            enheter_path,
            compression="gzip",
            usecols=lambda c: c in enheter_cols_to_load,
            dtype=str,
            low_memory=False,
            on_bad_lines="skip",
        )
        pbar.set_postfix_str(f"hovedenheter: {len(enheter):,}")
        pbar.update(1)

        underenheter = pd.read_csv(
            underenheter_path,
            compression="gzip",
            usecols=lambda c: c in underenheter_cols_to_load,
            dtype=str,
            low_memory=False,
            on_bad_lines="skip",
        )
        pbar.set_postfix_str(f"underenheter: {len(underenheter):,}")
        pbar.update(1)

    enheter = enheter.rename(columns={
        "forretningsadresse.adresse": "adresse",
        "forretningsadresse.postnummer": "postnummer",
        "forretningsadresse.poststed": "poststed",
        "forretningsadresse.kommunenummer": "kommunenummer",
        "naeringskode1.kode": "naeringskode",
        "naeringskode1.beskrivelse": "naeringskode_beskrivelse",
    })
    enheter["source"] = "hovedenhet"

    underenheter = underenheter.rename(columns={
        "beliggenhetsadresse.adresse": "adresse",
        "beliggenhetsadresse.postnummer": "postnummer",
        "beliggenhetsadresse.poststed": "poststed",
        "beliggenhetsadresse.kommunenummer": "kommunenummer",
        "naeringskode1.kode": "naeringskode",
        "naeringskode1.beskrivelse": "naeringskode_beskrivelse",
    })
    underenheter["source"] = "underenhet"

    combined = pd.concat([enheter, underenheter], ignore_index=True)
    print(f"Kombinert datasett: {len(combined)} bedrifter")

    if postal_codes:
        before = len(combined)
        combined = combined[combined["postnummer"].isin(postal_codes)]
        print(f"Filtrert på postnummer: {before} → {len(combined)} bedrifter")

    return combined


def main():
    parser = argparse.ArgumentParser(
        description="Filtrer norske bedrifter etter geografisk område og antall ansatte"
    )
    parser.add_argument("geojson", nargs="?", help="Sti til GeoJSON-fil som definerer området")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Sti til output CSV-fil (standard: output/<område>_<tidspunkt>.csv)",
    )
    parser.add_argument(
        "--min-employees",
        type=int,
        default=0,
        help="Minimum antall ansatte (inklusiv, standard: 0 = ingen grense)",
    )
    parser.add_argument(
        "--max-employees",
        type=int,
        default=99999,
        help="Maksimum antall ansatte (inklusiv, standard: 99999 = ingen grense)",
    )
    args = parser.parse_args()

    geojson_path = args.geojson
    if not geojson_path:
        print("=" * 60)
        print("  Ruter - bedriftsøk for samkjøring")
        print("  Lag GeoJSON på: https://geojson.io")
        print("=" * 60)
        print()
        geojson_path = input("Dra og slipp GeoJSON-fil her: ").strip()
        if not geojson_path:
            print("Feil: Ingen GeoJSON-fil oppgitt.")
            sys.exit(1)
        geojson_path = geojson_path.strip("'\"")
        # Handle shell-escaped characters from drag-and-drop (e.g., map\ \(1\).geojson)
        try:
            geojson_path = shlex.split(geojson_path)[0]
        except ValueError:
            # Fallback: manually unescape common characters
            geojson_path = geojson_path.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")

    if not Path(geojson_path).exists():
        print(f"Feil: Finner ikke filen: {geojson_path}")
        sys.exit(1)

    print(f"\n{'─' * 50}")
    print(f"Analyserer område: {Path(geojson_path).name}")
    print(f"{'─' * 50}")

    polygon = load_geojson_polygon(geojson_path)
    min_lon, min_lat, max_lon, max_lat = polygon.bounds
    print(f"Polygon-grenser: ({min_lat:.4f}, {min_lon:.4f}) - ({max_lat:.4f}, {max_lon:.4f})")

    postal_df = load_postal_code_data()
    postal_codes = get_postal_codes_in_polygon(polygon, postal_df)
    print(f"Postnummer i området: {len(postal_codes)} stk")

    if not postal_codes:
        print("Ingen postnummer funnet i målområdet.")
        return

    df = load_company_data(postal_codes=postal_codes)

    print(f"Filtrerer på antall ansatte ({args.min_employees} <= ansatte <= {args.max_employees})...")
    df["antallAnsatte_num"] = pd.to_numeric(df["antallAnsatte"], errors="coerce")
    df = df[(df["antallAnsatte_num"] >= args.min_employees) & (df["antallAnsatte_num"] <= args.max_employees)]
    print(f"  {len(df)} bedrifter matcher ansatt-kriteriet")

    if len(df) == 0:
        print("Ingen bedrifter matcher kriteriene.")
        return

    cache = load_cache()
    cached_count = len(cache)

    # Count how many addresses are already cached
    addresses_to_check = []
    for _, row in df.iterrows():
        address = row.get("adresse", "")
        postal_code = row.get("postnummer", "")
        city = row.get("poststed", "")
        if not pd.isna(address) and address:
            cache_key = f"{address}|{postal_code}|{city}".lower().strip()
            addresses_to_check.append((row, cache_key))

    cached_hits = sum(1 for _, key in addresses_to_check if key in cache)
    api_calls_needed = len(addresses_to_check) - cached_hits

    print(f"\nGeokoding: {len(addresses_to_check)} adresser")
    print(f"  Cache: {cached_hits} treff, {api_calls_needed} API-kall nødvendig")
    if api_calls_needed > 0:
        print(f"  (API-kall tar ca. 0.5-1 sek hver)")

    results = []
    with tqdm(
        total=len(addresses_to_check),
        desc="Geokoder",
        unit="adr",
        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
    ) as pbar:
        for row, cache_key in addresses_to_check:
            address = row.get("adresse", "")
            postal_code = row.get("postnummer", "")
            city = row.get("poststed", "")
            municipality = row.get("kommunenummer")

            lat, lon = geocode_address(address, postal_code, city, municipality, cache)

            if lat is not None and lon is not None:
                point = Point(lon, lat)

                if polygon.contains(point):
                    results.append({
                        "organisasjonsnummer": row.get("organisasjonsnummer"),
                        "navn": row.get("navn"),
                        "antallAnsatte": int(row["antallAnsatte_num"]),
                        "adresse": f"{address}, {postal_code} {city}",
                        "latitude": lat,
                        "longitude": lon,
                        "naeringskode": row.get("naeringskode"),
                        "naeringskode_beskrivelse": row.get("naeringskode_beskrivelse"),
                        "source": row.get("source"),
                    })

            pbar.update(1)

    save_cache(cache)
    print(f"Lagret {len(cache)} geokoding-resultater til cache")

    result_df = pd.DataFrame(results)

    # Show breakdown by source type
    if len(result_df) > 0:
        hovedenheter_count = len(result_df[result_df["source"] == "hovedenhet"])
        underenheter_count = len(result_df[result_df["source"] == "underenhet"])
        print(f"\nFordeling: {hovedenheter_count} hovedenheter, {underenheter_count} underenheter")

    before_dedup = len(result_df)
    result_df = result_df.sort_values("source", ascending=True)
    result_df = result_df.drop_duplicates(subset=["adresse"], keep="first")
    if before_dedup > len(result_df):
        print(f"Deduplisert på adresse: {before_dedup} → {len(result_df)} unike lokasjoner")

    # Final breakdown
    if len(result_df) > 0:
        final_hovedenheter = len(result_df[result_df["source"] == "hovedenhet"])
        final_underenheter = len(result_df[result_df["source"] == "underenhet"])
        print(f"\nFant {len(result_df)} bedrifter innenfor området:")
        print(f"  - {final_hovedenheter} hovedenheter (selvstendig eller foretrukket ved duplikat)")
        print(f"  - {final_underenheter} underenheter (filialer/avdelinger)")
    else:
        print(f"\nFant {len(result_df)} bedrifter innenfor området")

    if args.output:
        output_path = Path(args.output)
        area_name = output_path.stem
    else:
        area_folder, area_name = generate_output_folder(geojson_path)
        output_path = area_folder / "bedrifter_raa.csv"

    result_df.to_csv(output_path, index=False)
    print(f"Resultater lagret til {output_path}")
    # Print area_name and path for script chaining (last two lines)
    print(area_name)
    print(output_path)


if __name__ == "__main__":
    main()
