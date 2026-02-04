#!/usr/bin/env python3
"""
Generate HTML reports for all areas from their CSV data.
Uses a shared template so changes apply to all areas.

Usage:
    python generate_report.py              # Generate all areas
    python generate_report.py hagan        # Generate specific area
    python generate_report.py --list       # List available areas
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import argparse

# Area configuration - add new areas here
AREAS = {
    'hagan': {
        'name': 'Hagan/Gjelleråsen',
        'description': 'Gjelleråsen industriområde, Nittedal',
        'folder': 'hagan'
    },
    'a_s': {
        'name': 'Ås',
        'description': 'Campus Ås, universitets- og forskningsmiljø',
        'folder': 'a_s'
    }
}

def calculate_score(row):
    """Calculate carpool potential score (0-100)."""
    score = 0
    employees = int(row.get('antallAnsatte', 0) or 0)
    industry = str(row.get('naeringskode_beskrivelse', '')).lower()

    # Employee score (0-50)
    if employees >= 500: score += 50
    elif employees >= 200: score += 40
    elif employees >= 100: score += 30
    elif employees >= 50: score += 20
    elif employees >= 20: score += 10

    # Industry score (0-30) - shift work industries
    shift_keywords = ['produksjon', 'industri', 'lager', 'logistikk', 'sikkerhet', 'vakt',
                      'helse', 'sykehus', 'pleie', 'omsorg', 'renhold', 'transport']
    if any(kw in industry for kw in shift_keywords):
        score += 30

    # Public sector bonus (0-10)
    public_keywords = ['kommune', 'stat', 'offentlig', 'universitet', 'skole', 'barnehage']
    name = str(row.get('navn', '')).lower()
    if any(kw in industry or kw in name for kw in public_keywords):
        score += 10

    # Research/campus bonus (0-10)
    research_keywords = ['forskning', 'institutt', 'universitet', 'vitenskapelig']
    if any(kw in industry or kw in name for kw in research_keywords):
        score += 10

    return min(score, 100)

def get_score_class(score):
    if score >= 70: return 'score-high'
    if score >= 40: return 'score-medium'
    return 'score-low'

def escape_html(text):
    if pd.isna(text) or text is None:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def generate_card_html(row, rank):
    """Generate HTML for a single company card."""
    score = row['_score']
    score_class = get_score_class(score)
    employees = row.get('antallAnsatte', '0') or '0'

    # Build contact persons (supports multiple: kontakt_navn, kontakt2_navn, etc.)
    contacts_html = ''
    contact_fields = [
        ('kontakt_navn', 'kontakt_rolle', 'kontakt_telefon', 'kontakt_epost'),
        ('kontakt2_navn', 'kontakt2_rolle', 'kontakt2_telefon', 'kontakt2_epost'),
        ('kontakt3_navn', 'kontakt3_rolle', 'kontakt3_telefon', 'kontakt3_epost'),
        ('kontakt4_navn', 'kontakt4_rolle', 'kontakt4_telefon', 'kontakt4_epost'),
    ]

    contacts = []
    for name_f, role_f, phone_f, email_f in contact_fields:
        name = str(row.get(name_f, '') or '').strip()
        if not name or name.lower() == 'nan':
            continue
        contact_links = []
        if row.get(phone_f) and str(row[phone_f]).strip():
            phone = str(row[phone_f]).replace(' ', '')
            contact_links.append(f'<a href="tel:{phone}" class="contact-link"><i data-lucide="phone"></i>{escape_html(row[phone_f])}</a>')
        if row.get(email_f) and str(row[email_f]).strip():
            contact_links.append(f'<a href="mailto:{row[email_f]}" class="contact-link"><i data-lucide="mail"></i>{escape_html(row[email_f])}</a>')

        role = str(row.get(role_f, '') or '').strip()
        role_html = f'<div class="contact-role">{escape_html(role)}</div>' if role else ''
        links_html = f'<div class="contact-links">{"".join(contact_links)}</div>' if contact_links else ''

        contacts.append(f'''<div class="contact-card">
            <div class="contact-header">
                <span class="contact-name">{escape_html(name)}</span>
                {role_html}
            </div>
            {links_html}
        </div>''')

    if contacts:
        contacts_html = f'<div class="contacts-section">{"".join(contacts)}</div>'

    # General links (website, email, proff)
    general_links = []
    if row.get('hjemmeside'):
        general_links.append(f'<a href="{row["hjemmeside"]}" target="_blank" class="general-link"><i data-lucide="globe"></i>Nettside</a>')
    if row.get('epost_generell'):
        general_links.append(f'<a href="mailto:{row["epost_generell"]}" class="general-link"><i data-lucide="mail"></i>Kontakt</a>')
    if row.get('proff_url'):
        general_links.append(f'<a href="{row["proff_url"]}" target="_blank" class="general-link"><i data-lucide="external-link"></i>Proff</a>')
    elif row.get('organisasjonsnummer'):
        general_links.append(f'<a href="https://www.proff.no/bransjesøk?q={row["organisasjonsnummer"]}" target="_blank" class="general-link"><i data-lucide="external-link"></i>Proff</a>')

    general_html = f'<div class="general-links">{"".join(general_links)}</div>' if general_links else ''

    # Sales argument
    sales_html = ''
    if row.get('salgsnotater'):
        sales_html = f'''
        <div class="sales-argument">
            <i data-lucide="lightbulb"></i>
            <p>{escape_html(row["salgsnotater"])}</p>
        </div>'''

    return f'''
        <article class="company-card" data-score="{score}" data-employees="{employees}" data-name="{escape_html(row.get('navn', ''))}">
            <div class="card-main">
                <div class="card-header">
                    <div class="rank-badge">#{rank}</div>
                    <div class="header-content">
                        <h2 class="company-name">{escape_html(row.get('navn', ''))}</h2>
                        <div class="meta-row">
                            <span class="employee-count"><i data-lucide="users"></i>{employees} ansatte</span>
                            <span class="score-badge {score_class}"><i data-lucide="target"></i>{score}%</span>
                            {general_html}
                        </div>
                    </div>
                </div>

                <div class="card-body">
                    <div class="info-row">
                        <span class="info-item"><i data-lucide="map-pin"></i>{escape_html(row.get('adresse', ''))}</span>
                        <span class="info-item"><i data-lucide="briefcase"></i>{escape_html(row.get('naeringskode_beskrivelse', ''))}</span>
                    </div>
                    {contacts_html}
                </div>
            </div>
            {sales_html}
        </article>'''

def generate_html(df, area_name, area_folder):
    """Generate complete HTML report."""
    # Calculate scores and sort
    df['_score'] = df.apply(calculate_score, axis=1)
    df = df.sort_values('_score', ascending=False).reset_index(drop=True)

    total_companies = len(df)
    total_employees = df['antallAnsatte'].astype(int).sum()

    # Generate cards
    cards_html = '\n'.join(generate_card_html(row, i+1) for i, row in df.iterrows())

    # Generate map markers
    markers = []
    for _, row in df.iterrows():
        if row.get('latitude') and row.get('longitude'):
            markers.append({
                'lat': float(row['latitude']),
                'lon': float(row['longitude']),
                'name': str(row.get('navn', '')),
                'employees': str(row.get('antallAnsatte', '0')),
                'address': str(row.get('adresse', '')),
                'score': int(row['_score'])
            })

    markers_json = json.dumps(markers, ensure_ascii=False)
    generated_date = datetime.now().strftime('%Y-%m-%d %H:%M')

    return f'''<!DOCTYPE html>
<html lang="no">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carpool CRM - {area_name}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root {{
            --ruter-red: #E60000;
            --ruter-red-dark: #A20000;
            --ruter-red-light: #FDEBEB;
            --ruter-navy: #313663;
            --ruter-blue: #002B79;
            --ruter-gray: #6D7196;
            --ruter-gray-light: #F8F8F8;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
            --radius: 12px;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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

        .header h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }}
        .header p {{ opacity: 0.9; }}
        .header .back-link {{
            position: absolute;
            left: 1rem;
            top: 50%;
            transform: translateY(-50%);
            color: white;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.25rem;
            opacity: 0.9;
            font-size: 0.9rem;
        }}
        .header .back-link:hover {{ opacity: 1; }}
        .header {{ position: relative; }}

        .stats-bar {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 2rem;
            padding: 1rem 2rem;
            background: white;
            border-bottom: 1px solid #e5e7eb;
            flex-wrap: wrap;
            position: sticky;
            top: 0;
            z-index: 100;
        }}

        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 1.25rem; font-weight: 700; color: var(--ruter-red); }}
        .stat-label {{ font-size: 0.7rem; color: var(--ruter-gray); text-transform: uppercase; }}

        .controls {{ display: flex; gap: 0.5rem; align-items: center; }}

        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.5rem 1rem;
            background: var(--ruter-navy);
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.15s;
        }}
        .btn:hover {{ background: var(--ruter-blue); }}
        .btn.active {{ background: var(--ruter-red); }}
        .btn i {{ width: 16px; height: 16px; }}

        .sort-group {{ display: flex; gap: 0.25rem; }}
        .sort-btn {{
            padding: 0.4rem 0.75rem;
            background: #e5e7eb;
            color: var(--ruter-navy);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.15s;
        }}
        .sort-btn:hover {{ background: #d1d5db; }}
        .sort-btn.active {{ background: var(--ruter-red); color: white; }}

        #map {{
            height: 350px;
            display: none;
            margin: 1rem auto;
            max-width: 800px;
            border-radius: var(--radius);
            border: 1px solid #e5e7eb;
        }}
        #map.visible {{ display: block; }}

        .cards-container {{
            padding: 1.5rem;
            max-width: 800px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .company-card {{
            background: white;
            border-radius: var(--radius);
            box-shadow: var(--shadow-md);
            overflow: hidden;
        }}

        .card-main {{ padding: 1rem 1.25rem; }}

        .card-header {{
            display: flex;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }}

        .rank-badge {{
            width: 36px;
            height: 36px;
            background: var(--ruter-red);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.85rem;
            flex-shrink: 0;
        }}

        .header-content {{ flex: 1; }}
        .company-name {{ font-size: 1rem; font-weight: 600; color: var(--ruter-navy); margin-bottom: 0.2rem; }}

        .meta-row {{
            display: flex;
            gap: 0.75rem;
            align-items: center;
            flex-wrap: wrap;
        }}

        .employee-count {{
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            font-size: 0.8rem;
            color: var(--ruter-gray);
        }}
        .employee-count i {{ width: 14px; height: 14px; }}

        .score-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.2rem;
            padding: 0.15rem 0.5rem;
            border-radius: 10px;
            font-size: 0.7rem;
            font-weight: 600;
        }}
        .score-badge i {{ width: 11px; height: 11px; }}
        .score-high {{ background: #dcfce7; color: #166534; }}
        .score-medium {{ background: #fef3c7; color: #92400e; }}
        .score-low {{ background: #f3f4f6; color: #6b7280; }}

        .card-body {{ border-top: 1px solid #f1f5f9; padding-top: 0.75rem; }}

        .info-row {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.4rem 1.25rem;
            margin-bottom: 0.5rem;
        }}

        .info-item {{
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            font-size: 0.8rem;
            color: var(--ruter-gray);
        }}
        .info-item i {{ width: 14px; height: 14px; flex-shrink: 0; }}

        .general-links {{
            display: inline-flex;
            gap: 0.4rem;
            margin-left: auto;
        }}

        .general-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.2rem;
            font-size: 0.75rem;
            color: var(--ruter-blue);
            text-decoration: none;
        }}
        .general-link:hover {{ color: var(--ruter-red); }}
        .general-link i {{ width: 12px; height: 12px; }}

        .contacts-section {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 0.5rem;
            margin-top: 0.5rem;
        }}

        .contact-card {{
            padding: 0.6rem 0.75rem;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
        }}

        .contact-header {{
            margin-bottom: 0.35rem;
        }}

        .contact-name {{
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--ruter-navy);
        }}

        .contact-role {{
            font-size: 0.7rem;
            color: var(--ruter-gray);
        }}

        .contact-links {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
        }}

        .contact-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.2rem 0.5rem;
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            font-size: 0.7rem;
            color: var(--ruter-navy);
            text-decoration: none;
            transition: all 0.15s;
        }}
        .contact-link:hover {{ background: var(--ruter-red-light); border-color: var(--ruter-red); color: var(--ruter-red); }}
        .contact-link i {{ width: 12px; height: 12px; flex-shrink: 0; }}

        .sales-argument {{
            display: flex;
            gap: 0.75rem;
            padding: 1rem 1.25rem;
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-top: 1px solid #fcd34d;
        }}
        .sales-argument i {{ width: 18px; height: 18px; color: #b45309; flex-shrink: 0; margin-top: 2px; }}
        .sales-argument p {{ font-size: 0.85rem; color: #78350f; }}

        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--ruter-gray);
            font-size: 0.8rem;
        }}

        @media (max-width: 640px) {{
            .cards-container {{ padding: 1rem; }}
            .stats-bar {{ gap: 1rem; padding: 0.75rem 1rem; }}
            .header .back-link {{ position: static; transform: none; margin-bottom: 0.5rem; justify-content: center; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <a href="../" class="back-link"><i data-lucide="arrow-left" style="width:16px;height:16px"></i> Alle områder</a>
        <h1>{area_name}</h1>
    </div>

    <div class="stats-bar">
        <div class="stat">
            <div class="stat-value">{total_companies}</div>
            <div class="stat-label">Bedrifter</div>
        </div>
        <div class="stat">
            <div class="stat-value">{total_employees:,}</div>
            <div class="stat-label">Ansatte</div>
        </div>
        <div class="controls">
            <span style="font-size:0.8rem;color:var(--ruter-gray)">Sorter:</span>
            <div class="sort-group">
                <button class="sort-btn active" onclick="sortCards('score')">Potensial</button>
                <button class="sort-btn" onclick="sortCards('employees')">Ansatte</button>
                <button class="sort-btn" onclick="sortCards('name')">Navn</button>
            </div>
            <button class="btn" onclick="toggleMap()"><i data-lucide="map"></i>Kart</button>
            <button class="btn" onclick="showSyncModal()" style="background:#2563eb"><i data-lucide="upload-cloud"></i>Sheets</button>
        </div>
    </div>

    <div id="sync-modal" style="display:none;position:fixed;z-index:1000;left:0;top:0;width:100%;height:100%;background:rgba(0,0,0,0.5);align-items:center;justify-content:center">
        <div style="background:white;padding:2rem;border-radius:12px;max-width:500px;width:90%;position:relative">
            <span onclick="closeSyncModal()" style="position:absolute;top:1rem;right:1rem;font-size:1.5rem;cursor:pointer;color:#9ca3af">&times;</span>
            <h2 style="margin-bottom:1rem;color:var(--ruter-navy)">Sync til Google Sheets</h2>
            <p style="margin-bottom:1rem;color:#4b5563">Kjør denne kommandoen i terminalen:</p>
            <div style="display:flex;gap:0.5rem;background:#f1f5f9;padding:1rem;border-radius:8px;margin-bottom:1rem">
                <code id="sync-command" style="flex:1;font-family:monospace;font-size:0.85rem;word-break:break-all">python google_sheets.py sync "output/{area_folder}/bedrifter.csv"</code>
                <button class="btn" onclick="copyCommand()">Kopier</button>
            </div>
        </div>
    </div>

    <div id="map"></div>

    <div id="cards" class="cards-container">
{cards_html}
    </div>

    <div class="footer">
        Generert {generated_date} · Data fra Brønnøysundregistrene<br>
        <small>Score basert på: ansatte, bransje (skiftarbeid), offentlig sektor, forskning/campus</small>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        lucide.createIcons();

        const markers = {markers_json};
        let map = null;

        function toggleMap() {{
            const mapEl = document.getElementById('map');
            if (mapEl.classList.contains('visible')) {{
                mapEl.classList.remove('visible');
            }} else {{
                mapEl.classList.add('visible');
                if (!map) initMap();
                else map.invalidateSize();
            }}
        }}

        function initMap() {{
            const bounds = markers.reduce((b, m) => [[Math.min(b[0][0], m.lat), Math.min(b[0][1], m.lon)], [Math.max(b[1][0], m.lat), Math.max(b[1][1], m.lon)]], [[90, 180], [-90, -180]]);
            map = L.map('map').fitBounds(bounds, {{ padding: [20, 20] }});
            L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png').addTo(map);
            markers.forEach(m => {{
                L.circleMarker([m.lat, m.lon], {{
                    radius: Math.min(Math.max(Math.sqrt(m.employees || 20) * 2, 5), 20),
                    fillColor: '#E60000', color: '#fff', weight: 2, fillOpacity: 0.7
                }}).addTo(map).bindPopup(`<strong>${{m.name}}</strong><br>${{m.employees}} ansatte<br>Score: ${{m.score}}%`);
            }});
        }}

        function sortCards(by) {{
            document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');

            const container = document.getElementById('cards');
            const cards = Array.from(container.children);

            cards.sort((a, b) => {{
                if (by === 'score') return parseInt(b.dataset.score) - parseInt(a.dataset.score);
                if (by === 'employees') return parseInt(b.dataset.employees) - parseInt(a.dataset.employees);
                return a.dataset.name.localeCompare(b.dataset.name, 'no');
            }});

            cards.forEach((card, i) => {{
                card.querySelector('.rank-badge').textContent = '#' + (i + 1);
                container.appendChild(card);
            }});
        }}

        function showSyncModal() {{
            document.getElementById('sync-modal').style.display = 'flex';
        }}

        function closeSyncModal() {{
            document.getElementById('sync-modal').style.display = 'none';
        }}

        function copyCommand() {{
            navigator.clipboard.writeText(document.getElementById('sync-command').textContent);
        }}

        document.getElementById('sync-modal').addEventListener('click', e => {{
            if (e.target.id === 'sync-modal') closeSyncModal();
        }});
    </script>
</body>
</html>'''

def generate_area(area_id, output_dir):
    """Generate report for a single area."""
    if area_id not in AREAS:
        print(f"Unknown area: {area_id}")
        return False

    area = AREAS[area_id]
    area_path = output_dir / area['folder']
    csv_path = area_path / 'bedrifter.csv'

    if not csv_path.exists():
        print(f"  Skipping {area['name']}: no bedrifter.csv found")
        return False

    print(f"  Generating {area['name']}...")
    df = pd.read_csv(csv_path, dtype=str)
    df['antallAnsatte'] = pd.to_numeric(df['antallAnsatte'], errors='coerce').fillna(0).astype(int)

    html = generate_html(df, area['name'], area['folder'])

    html_path = area_path / 'index.html'
    html_path.write_text(html, encoding='utf-8')
    print(f"    -> {html_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description='Generate HTML reports for Carpool CRM areas')
    parser.add_argument('area', nargs='?', help='Specific area to generate (default: all)')
    parser.add_argument('--list', action='store_true', help='List available areas')
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    output_dir = script_dir / 'output'

    if args.list:
        print("Available areas:")
        for area_id, area in AREAS.items():
            csv_exists = (output_dir / area['folder'] / 'bedrifter.csv').exists()
            status = "ready" if csv_exists else "no data"
            print(f"  {area_id}: {area['name']} ({status})")
        return

    print("Generating Carpool CRM reports...")

    if args.area:
        generate_area(args.area, output_dir)
    else:
        for area_id in AREAS:
            generate_area(area_id, output_dir)

    print("Done!")

if __name__ == '__main__':
    main()
