#!/usr/bin/env python3
"""
Berik bedriftsdata med kontaktinformasjon for samkjørings-pilot.

Bruk:
    python enrich_companies.py filtrerte_bedrifter.csv --output berikede_bedrifter.csv
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).parent
CACHE_FILE = SCRIPT_DIR / "company_cache.json"

# BRREG API for company details
BRREG_API = "https://data.brreg.no/enhetsregisteret/api/enheter"
BRREG_UNDERENHETER_API = "https://data.brreg.no/enhetsregisteret/api/underenheter"

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between requests


def load_cache() -> dict:
    """Load company info cache from disk."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    """Save company info cache to disk."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_brreg_info(orgnr: str, cache: dict) -> dict:
    """Fetch company info from BRREG API."""
    cache_key = f"brreg_{orgnr}"

    if cache_key in cache:
        return cache[cache_key]

    result = {
        "hjemmeside": None,
        "epostadresse": None,
        "telefon": None,
        "mobil": None,
    }

    # Try hovedenhet first
    try:
        response = requests.get(f"{BRREG_API}/{orgnr}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            result["hjemmeside"] = data.get("hjemmeside")
            result["epostadresse"] = data.get("epostadresse")
            result["telefon"] = data.get("telefon")
            result["mobil"] = data.get("mobil")
    except Exception:
        pass

    # If no website found, try underenhet
    if not result["hjemmeside"]:
        try:
            response = requests.get(f"{BRREG_UNDERENHETER_API}/{orgnr}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                result["hjemmeside"] = data.get("hjemmeside")
                result["epostadresse"] = result["epostadresse"] or data.get("epostadresse")
                result["telefon"] = result["telefon"] or data.get("telefon")
                result["mobil"] = result["mobil"] or data.get("mobil")
        except Exception:
            pass

    cache[cache_key] = result
    time.sleep(REQUEST_DELAY)
    return result


def normalize_url(url: str | None) -> str | None:
    """Normalize URL to include https://"""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def search_proff_no(company_name: str, orgnr: str, cache: dict) -> dict:
    """Search proff.no for company information."""
    cache_key = f"proff_{orgnr}"

    if cache_key in cache:
        return cache[cache_key]

    result = {
        "proff_url": f"https://www.proff.no/bransjesøk?q={orgnr}",
        "roles": []
    }

    # Note: Actually scraping proff.no would require handling their terms of service
    # For now, we just provide the search URL for manual lookup

    cache[cache_key] = result
    return result


def format_phone(phone: str | None) -> str | None:
    """Format phone number."""
    if not phone:
        return None
    # Remove spaces and format
    phone = re.sub(r'\s+', '', str(phone))
    if phone.startswith('47') and len(phone) == 10:
        phone = '+' + phone
    elif len(phone) == 8 and phone.isdigit():
        phone = '+47' + phone
    return phone



def clean_value(val) -> str:
    """Return empty string for NaN/None values, otherwise return string."""
    if pd.isna(val) or val is None or str(val).lower() == 'nan':
        return ""
    return str(val).strip()


def generate_html_report(df: pd.DataFrame, output_path: Path, title: str = "Bedriftsoversikt") -> Path:
    """Generate a beautiful HTML report with an interactive table and map."""
    html_path = output_path.with_suffix(".html")

    # Calculate stats
    total = len(df)
    total_employees = pd.to_numeric(df["antallAnsatte"], errors="coerce").sum()

    # Build table rows
    table_rows = []
    map_markers = []

    for _, row in df.iterrows():
        navn = clean_value(row.get("navn"))
        ansatte = clean_value(row.get("antallAnsatte"))
        adresse = clean_value(row.get("adresse"))
        lat = row.get("latitude")
        lon = row.get("longitude")
        bransje = clean_value(row.get("naeringskode_beskrivelse"))
        hjemmeside = clean_value(row.get("hjemmeside"))
        epost = clean_value(row.get("kontakt_epost")) or clean_value(row.get("epostadresse"))
        telefon = clean_value(row.get("kontakt_telefon")) or clean_value(row.get("telefon")) or clean_value(row.get("mobil"))
        proff_url = clean_value(row.get("proff_url"))

        # Contact person (from Claude research step)
        kontakt_navn = clean_value(row.get("kontakt_navn"))
        kontakt_rolle = clean_value(row.get("kontakt_rolle"))

        # Sales arguments
        salgsnotater = clean_value(row.get("salgsnotater"))

        # Website link
        website_cell = f'<a href="{hjemmeside}" target="_blank" class="link">Besøk</a>' if hjemmeside else ""

        # Contact info (email/phone)
        contact_parts = []
        if epost:
            contact_parts.append(f'<a href="mailto:{epost}" class="link">{epost}</a>')
        if telefon:
            contact_parts.append(f'<a href="tel:{telefon}" class="link">{telefon}</a>')
        contact_cell = "<br>".join(contact_parts)

        # Contact person
        kontakt_parts = []
        if kontakt_navn:
            kontakt_parts.append(f'<strong>{kontakt_navn}</strong>')
        if kontakt_rolle:
            kontakt_parts.append(f'<span class="role">{kontakt_rolle}</span>')
        kontakt_cell = "<br>".join(kontakt_parts)

        # Proff link
        proff_cell = f'<a href="{proff_url}" target="_blank" class="link-subtle">Proff</a>' if proff_url else ""

        # Truncate long values
        bransje_display = bransje[:50] + '...' if len(bransje) > 50 else bransje

        # Expandable sales notes
        if len(salgsnotater) > 80:
            salgs_cell = f'<div class="expandable" onclick="this.classList.toggle(\'expanded\')"><span class="truncated">{salgsnotater[:80]}...</span><span class="full">{salgsnotater}</span></div>'
        else:
            salgs_cell = salgsnotater

        table_rows.append(f"""
            <tr data-lat="{lat or ''}" data-lon="{lon or ''}">
                <td class="company-name">{navn}</td>
                <td class="text-right">{ansatte}</td>
                <td class="address">{adresse}</td>
                <td class="industry">{bransje_display}</td>
                <td class="text-center">{website_cell}</td>
                <td class="kontakt">{kontakt_cell}</td>
                <td class="contact">{contact_cell}</td>
                <td class="salgsnotater">{salgs_cell}</td>
                <td class="text-center">{proff_cell}</td>
            </tr>
        """)

        # Map marker
        if lat and lon:
            try:
                map_markers.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "name": navn,
                    "employees": ansatte,
                    "address": adresse
                })
            except (ValueError, TypeError):
                pass

    html_content = f'''<!DOCTYPE html>
<html lang="no">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {{
            --ruter-red: #E60000;
            --ruter-red-dark: #A20000;
            --ruter-red-light: #FDEBEB;
            --ruter-navy: #313663;
            --ruter-blue: #002B79;
            --ruter-gray: #6D7196;
            --ruter-gray-light: #F8F8F8;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--ruter-gray-light);
            color: var(--ruter-navy);
            line-height: 1.5;
        }}

        .header {{
            background: linear-gradient(135deg, var(--ruter-red) 0%, var(--ruter-red-dark) 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}

        .header h1 {{
            font-size: 1.75rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}

        .header p {{
            opacity: 0.9;
            font-size: 0.95rem;
        }}

        .stats {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 2rem;
            padding: 1.5rem;
            background: white;
            border-bottom: 1px solid #e5e7eb;
            flex-wrap: wrap;
        }}

        .stat {{
            text-align: center;
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--ruter-red);
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--ruter-gray);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .toggle-map, .sync-sheets-btn {{
            padding: 0.6rem 1.2rem;
            background: var(--ruter-red);
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.2s;
            margin-left: 1rem;
        }}

        .toggle-map:hover, .sync-sheets-btn:hover {{
            background: var(--ruter-red-dark);
        }}

        .sync-sheets-btn {{
            background: #2563eb;
        }}

        .sync-sheets-btn:hover {{
            background: #1d4ed8;
        }}

        /* Modal styles */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }}

        .modal.visible {{
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .modal-content {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            max-width: 600px;
            width: 90%;
            position: relative;
        }}

        .modal-content h2 {{
            margin-bottom: 1rem;
            color: var(--ruter-navy);
        }}

        .modal-content p {{
            margin-bottom: 1rem;
            color: #4b5563;
        }}

        .modal-close {{
            position: absolute;
            top: 1rem;
            right: 1rem;
            font-size: 1.5rem;
            cursor: pointer;
            color: #9ca3af;
        }}

        .modal-close:hover {{
            color: var(--ruter-navy);
        }}

        .command-box {{
            display: flex;
            gap: 0.5rem;
            background: #f1f5f9;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }}

        .command-box code {{
            flex: 1;
            font-family: monospace;
            font-size: 0.9rem;
            word-break: break-all;
        }}

        .copy-btn {{
            padding: 0.4rem 0.8rem;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8rem;
        }}

        .copy-btn:hover {{
            background: #1d4ed8;
        }}

        .hint {{
            font-size: 0.85rem;
            color: #6b7280;
        }}

        .hint code {{
            background: #f1f5f9;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-size: 0.8rem;
        }}

        #map {{
            height: 400px;
            display: none;
            margin: 1rem 2rem;
            border-radius: 8px;
            border: 1px solid #e5e7eb;
        }}

        #map.visible {{
            display: block;
        }}

        .table-container {{
            padding: 1rem 2rem 2rem;
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            font-size: 0.85rem;
        }}

        th {{
            background: #f8fafc;
            padding: 0.75rem 0.75rem;
            text-align: left;
            font-weight: 600;
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
            cursor: pointer;
            white-space: nowrap;
            user-select: none;
        }}

        th:hover {{
            background: #f1f5f9;
        }}

        th.sortable::after {{
            content: " ↕";
            opacity: 0.3;
            font-size: 0.7rem;
        }}

        th.sort-asc::after {{
            content: " ↑";
            opacity: 1;
        }}

        th.sort-desc::after {{
            content: " ↓";
            opacity: 1;
        }}

        td {{
            padding: 0.6rem 0.75rem;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: top;
        }}

        tr:hover {{
            background: var(--ruter-red-light);
        }}

        .company-name {{
            font-weight: 500;
            color: var(--ruter-navy);
            min-width: 180px;
        }}

        .address {{
            color: var(--ruter-gray);
            font-size: 0.8rem;
            min-width: 150px;
        }}

        .industry {{
            color: var(--ruter-gray);
            font-size: 0.8rem;
            max-width: 150px;
        }}

        .kontakt {{
            min-width: 120px;
        }}

        .kontakt .role {{
            color: var(--ruter-gray);
            font-size: 0.75rem;
        }}

        .contact {{
            font-size: 0.8rem;
            min-width: 140px;
        }}

        .salgsnotater {{
            font-size: 0.8rem;
            color: #374151;
            max-width: 300px;
        }}

        .expandable {{
            cursor: pointer;
        }}

        .expandable .truncated {{
            display: inline;
        }}

        .expandable .full {{
            display: none;
        }}

        .expandable.expanded .truncated {{
            display: none;
        }}

        .expandable.expanded .full {{
            display: inline;
        }}

        .text-right {{
            text-align: right;
        }}

        .text-center {{
            text-align: center;
        }}

        .link {{
            color: var(--ruter-blue);
            text-decoration: none;
        }}

        .link:hover {{
            color: var(--ruter-red);
            text-decoration: underline;
        }}

        .link-subtle {{
            color: #9ca3af;
            text-decoration: none;
            font-size: 0.75rem;
        }}

        .link-subtle:hover {{
            color: var(--ruter-red);
        }}

        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--ruter-gray);
            font-size: 0.8rem;
        }}

        @media (max-width: 768px) {{
            .table-container {{
                padding: 0 1rem 1rem;
            }}
            #map {{
                margin: 1rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p>Ruters samkjøringspilot</p>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{total}</div>
            <div class="stat-label">Bedrifter</div>
        </div>
        <div class="stat">
            <div class="stat-value">{int(total_employees):,}</div>
            <div class="stat-label">Ansatte totalt</div>
        </div>
        <button class="toggle-map" onclick="toggleMap()">Vis kart</button>
        <button class="sync-sheets-btn" onclick="showSyncModal()">Sync til Sheets</button>
    </div>

    <!-- Sync Modal -->
    <div id="sync-modal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeSyncModal()">&times;</span>
            <h2>Sync til Google Sheets</h2>
            <p>Kjor denne kommandoen i terminalen for a synkronisere til Sheets:</p>
            <div class="command-box">
                <code id="sync-command">python google_sheets.py sync "{output_path}"</code>
                <button class="copy-btn" onclick="copyCommand()">Kopier</button>
            </div>
            <p class="hint">Forste gang? Kjor <code>python google_sheets.py setup</code> forst.</p>
        </div>
    </div>

    <div id="map"></div>

    <div class="table-container">
        <table id="companies-table">
            <thead>
                <tr>
                    <th class="sortable" data-sort="string">Bedrift</th>
                    <th class="sortable" data-sort="number">Ansatte</th>
                    <th class="sortable" data-sort="string">Adresse</th>
                    <th class="sortable" data-sort="string">Bransje</th>
                    <th>Nettside</th>
                    <th>Kontaktperson</th>
                    <th>Kontaktinfo</th>
                    <th>Salgsargumenter</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {"".join(table_rows)}
            </tbody>
        </table>
    </div>

    <div class="footer">
        Generert {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")} · Data fra Brønnøysundregistrene
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const markers = {json.dumps(map_markers)};
        let map = null;
        let mapInitialized = false;

        function toggleMap() {{
            const mapEl = document.getElementById('map');
            const btn = document.querySelector('.toggle-map');

            if (mapEl.classList.contains('visible')) {{
                mapEl.classList.remove('visible');
                btn.textContent = 'Vis kart';
            }} else {{
                mapEl.classList.add('visible');
                btn.textContent = 'Skjul kart';

                if (!mapInitialized) {{
                    initMap();
                    mapInitialized = true;
                }} else {{
                    map.invalidateSize();
                }}
            }}
        }}

        function initMap() {{
            if (markers.length === 0) return;

            const bounds = markers.reduce((b, m) => {{
                return [[Math.min(b[0][0], m.lat), Math.min(b[0][1], m.lon)],
                        [Math.max(b[1][0], m.lat), Math.max(b[1][1], m.lon)]];
            }}, [[90, 180], [-90, -180]]);

            map = L.map('map').fitBounds(bounds, {{ padding: [20, 20] }});

            L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                attribution: '&copy; OpenStreetMap, &copy; CARTO'
            }}).addTo(map);

            markers.forEach(m => {{
                L.circleMarker([m.lat, m.lon], {{
                    radius: Math.min(Math.max(Math.sqrt(m.employees || 20) * 2, 5), 20),
                    fillColor: '#E60000',
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.7
                }}).addTo(map).bindPopup(
                    `<strong>${{m.name}}</strong><br>${{m.employees}} ansatte<br><small>${{m.address}}</small>`
                );
            }});
        }}

        // Sort
        document.querySelectorAll('th.sortable').forEach(th => {{
            th.addEventListener('click', function() {{
                const table = document.getElementById('companies-table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const colIndex = Array.from(th.parentNode.children).indexOf(th);
                const sortType = th.dataset.sort;
                const isAsc = th.classList.contains('sort-asc');

                document.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
                th.classList.add(isAsc ? 'sort-desc' : 'sort-asc');

                rows.sort((a, b) => {{
                    let aVal = a.children[colIndex].textContent.trim();
                    let bVal = b.children[colIndex].textContent.trim();

                    if (sortType === 'number') {{
                        aVal = parseInt(aVal) || 0;
                        bVal = parseInt(bVal) || 0;
                    }}

                    if (aVal < bVal) return isAsc ? 1 : -1;
                    if (aVal > bVal) return isAsc ? -1 : 1;
                    return 0;
                }});

                rows.forEach(row => tbody.appendChild(row));
            }});
        }});

        // Sync modal functions
        function showSyncModal() {{
            document.getElementById('sync-modal').classList.add('visible');
        }}

        function closeSyncModal() {{
            document.getElementById('sync-modal').classList.remove('visible');
        }}

        function copyCommand() {{
            const command = document.getElementById('sync-command').textContent;
            navigator.clipboard.writeText(command).then(() => {{
                const btn = document.querySelector('.copy-btn');
                btn.textContent = 'Kopiert!';
                setTimeout(() => btn.textContent = 'Kopier', 2000);
            }});
        }}

        // Close modal on outside click
        document.getElementById('sync-modal').addEventListener('click', function(e) {{
            if (e.target === this) closeSyncModal();
        }});

        // Close modal on Escape
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeSyncModal();
        }});
    </script>
</body>
</html>'''

    html_path.write_text(html_content, encoding="utf-8")
    return html_path


def enrich_company(row: pd.Series, cache: dict) -> dict:
    """Enrich a single company with contact information from BRREG."""
    orgnr = str(row.get("organisasjonsnummer", ""))
    company_name = row.get("navn", "")
    antall_ansatte = row.get("antallAnsatte")
    adresse = row.get("adresse")
    naeringskode = row.get("naeringskode")
    naeringskode_beskrivelse = row.get("naeringskode_beskrivelse")

    # Get BRREG info
    brreg = get_brreg_info(orgnr, cache)

    # Get proff.no info
    proff = search_proff_no(company_name, orgnr, cache)

    return {
        "organisasjonsnummer": orgnr,
        "navn": company_name,
        "antallAnsatte": antall_ansatte,
        "adresse": adresse,
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "naeringskode": naeringskode,
        "naeringskode_beskrivelse": naeringskode_beskrivelse,
        "hjemmeside": normalize_url(brreg.get("hjemmeside")),
        "epostadresse": brreg.get("epostadresse"),
        "telefon": format_phone(brreg.get("telefon")),
        "mobil": format_phone(brreg.get("mobil")),
        "proff_url": proff.get("proff_url"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Berik bedriftsdata med kontaktinformasjon"
    )
    parser.add_argument("input", help="Input CSV-fil med filtrerte bedrifter")
    parser.add_argument(
        "--output", "-o",
        default="enriched_companies.csv",
        help="Sti til output CSV-fil (standard: enriched_companies.csv)",
    )
    args = parser.parse_args()

    # Last inn data
    print(f"Laster bedrifter fra {args.input}...")
    df = pd.read_csv(args.input, dtype=str)

    # Fjern duplikater (behold unike org.nr., foretrekk hovedenhet)
    df = df.drop_duplicates(subset=["organisasjonsnummer"], keep="first")
    print(f"  {len(df)} unike bedrifter å behandle")

    # Last inn cache
    cache = load_cache()
    cached_count = sum(1 for _, row in df.iterrows()
                       if f"brreg_{row.get('organisasjonsnummer', '')}" in cache)
    api_calls_needed = len(df) - cached_count

    print(f"\nBeriker {len(df)} bedrifter med BRREG-data")
    print(f"  Cache: {cached_count} treff, {api_calls_needed} API-kall nødvendig")
    if api_calls_needed > 0:
        print(f"  (API-kall tar ca. 0.5 sek hver)")

    # Berik hver bedrift
    enriched = []
    with tqdm(
        total=len(df),
        desc="Beriker",
        unit="bedrift",
        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
    ) as pbar:
        for idx, (_, row) in enumerate(df.iterrows()):
            enriched.append(enrich_company(row, cache))
            pbar.update(1)

            # Save cache periodically
            if (idx + 1) % 20 == 0:
                save_cache(cache)

    # Lagre cache
    save_cache(cache)

    # Lag output DataFrame
    result_df = pd.DataFrame(enriched)

    # Lagre til CSV
    output_path = Path(args.output)
    result_df.to_csv(output_path, index=False)
    print(f"\nBeriket data lagret til {output_path}")

    # Generate HTML report
    report_title = output_path.stem.replace("_", " ").title()
    html_path = generate_html_report(result_df, output_path, title=report_title)
    print(f"HTML-rapport lagret til {html_path}")

    # Google Sheets sync prompt (kun i interaktiv modus)
    if sys.stdin.isatty():
        try:
            response = input("\nOppdatere Google Sheets? (Y/n): ").strip().lower()
            if response in ("", "y", "yes", "ja"):
                try:
                    from google_sheets import SheetsClient
                    # Utled område fra filnavn
                    area_name = output_path.stem.split("_")[0] if "_" in output_path.stem else output_path.stem
                    client = SheetsClient()
                    client.sync_companies(result_df, area_name)
                except ImportError:
                    print("Google Sheets-biblioteker mangler. Kjor: pip install -r requirements.txt")
                except Exception as e:
                    print(f"Kunne ikke synkronisere: {e}")
                    print("Kjor 'python google_sheets.py setup' for a konfigurere.")
        except (EOFError, KeyboardInterrupt):
            pass  # Ignorer hvis input ikke er tilgjengelig

    # Oppsummering
    with_website = result_df["hjemmeside"].notna().sum()
    with_email = result_df["epostadresse"].notna().sum()
    with_phone = (result_df["telefon"].notna() | result_df["mobil"].notna()).sum()

    print(f"\n{'─' * 50}")
    print(f"Oppsummering: {len(result_df)} bedrifter beriket")
    print(f"{'─' * 50}")
    print(f"  Med hjemmeside: {with_website}")
    print(f"  Med e-post:     {with_email}")
    print(f"  Med telefon:    {with_phone}")
    print(f"\nÅpne rapporten: open \"{html_path}\"")


if __name__ == "__main__":
    main()
