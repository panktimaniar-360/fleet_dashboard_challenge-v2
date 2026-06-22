"""
Fleet Dashboard Generator
Reads fleet_status.csv and produces a self-contained fleet_dashboard.html.
Uses Python Standard Library only.
"""

import csv
import math
import html
import os
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUS_COLOURS = {
    "active":      "#22c55e",   # green
    "idle":        "#f97316",   # orange
    "offline":     "#ef4444",   # red
    "low_battery": "#eab308",   # yellow
}

STATUS_BG = {
    "active":      "#dcfce7",
    "idle":        "#ffedd5",
    "offline":     "#fee2e2",
    "low_battery": "#fef9c3",
}

STATUS_TEXT = {
    "active":      "#15803d",
    "idle":        "#c2410c",
    "offline":     "#b91c1c",
    "low_battery": "#854d0e",
}

VALID_STATUSES = set(STATUS_COLOURS.keys())

# ---------------------------------------------------------------------------
# 1. Load & Validate CSV
# ---------------------------------------------------------------------------

def load_csv(path: str) -> list[dict]:
    """Load fleet data from CSV, applying validation and normalisation."""
    devices = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            device = {}

            # device_id – required
            device_id = (row.get("device_id") or "").strip()
            if not device_id:
                continue
            device["device_id"] = html.escape(device_id)

            # name – fallback to device_id
            name = (row.get("name") or "").strip()
            device["name"] = html.escape(name) if name else device["device_id"]

            # status – normalise; unknown statuses shown as "offline" visually
            status = (row.get("status") or "offline").strip().lower()
            device["status"] = status if status in VALID_STATUSES else "offline"
            device["status_raw"] = html.escape(status)   # for display

            # battery_pct – clamp 0-100; None if missing/invalid
            try:
                batt = float(row.get("battery_pct", ""))
                device["battery_pct"] = max(0, min(100, round(batt)))
                device["battery_valid"] = True
            except (ValueError, TypeError):
                device["battery_pct"] = None
                device["battery_valid"] = False

            # lat / lon – None if missing/invalid
            try:
                device["lat"] = float(row.get("lat", ""))
                device["lon"] = float(row.get("lon", ""))
                device["coords_valid"] = True
            except (ValueError, TypeError):
                device["lat"] = None
                device["lon"] = None
                device["coords_valid"] = False

            # last_seen – parse; None if invalid / in the future
            last_seen_str = (row.get("last_seen") or "").strip()
            try:
                dt = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
                # Reject future timestamps
                if dt > datetime.now():
                    device["last_seen"] = None
                    device["last_seen_str"] = "Invalid date"
                else:
                    device["last_seen"] = dt
                    device["last_seen_str"] = html.escape(last_seen_str)
            except ValueError:
                device["last_seen"] = None
                device["last_seen_str"] = "Unknown"

            # location
            device["location"] = html.escape((row.get("location") or "Unknown").strip())

            devices.append(device)

    return devices


# ---------------------------------------------------------------------------
# 2. Summary Statistics
# ---------------------------------------------------------------------------

def calculate_summary(devices: list[dict]) -> dict:
    """Count devices per status category."""
    summary = {
        "total":       len(devices),
        "active":      0,
        "idle":        0,
        "offline":     0,
        "low_battery": 0,
        "other":       0,
    }
    for d in devices:
        s = d["status"]
        if s in summary:
            summary[s] += 1
        else:
            summary["other"] += 1
    return summary


# ---------------------------------------------------------------------------
# 3. Human-readable "time since last seen"
# ---------------------------------------------------------------------------

def calculate_last_seen(dt) -> str:
    """Return a human-readable delta like '2 hours ago'."""
    if dt is None:
        return "Unknown"
    now = datetime.now()
    delta = now - dt
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return "Future date"
    if total_seconds < 60:
        return f"{total_seconds} second{'s' if total_seconds != 1 else ''} ago"
    if total_seconds < 3600:
        m = total_seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if total_seconds < 86400:
        h = total_seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = total_seconds // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


# ---------------------------------------------------------------------------
# 4. SVG Map
# ---------------------------------------------------------------------------

def generate_map(devices: list[dict]) -> str:
    """
    Project lat/lon onto a simple SVG canvas using a linear Mercator-like
    transform bounded to Australia's extent.
    """
    # Australia bounding box (with padding)
    AUS_LAT_MIN, AUS_LAT_MAX = -44.0, -10.0
    AUS_LON_MIN, AUS_LON_MAX = 112.0, 155.0

    SVG_W, SVG_H = 800, 500
    PAD = 30

    def project(lat, lon):
        x = PAD + (lon - AUS_LON_MIN) / (AUS_LON_MAX - AUS_LON_MIN) * (SVG_W - 2 * PAD)
        y = PAD + (1 - (lat - AUS_LAT_MIN) / (AUS_LAT_MAX - AUS_LAT_MIN)) * (SVG_H - 2 * PAD)
        return round(x, 1), round(y, 1)

    markers = []
    for d in devices:
        if not d["coords_valid"]:
            continue

        x, y = project(d["lat"], d["lon"])
        colour = STATUS_COLOURS.get(d["status"], "#94a3b8")
        batt_str = f"{d['battery_pct']}%" if d["battery_valid"] else "N/A"
        since = calculate_last_seen(d["last_seen"])

        # Tooltip content (escaped inside JS string via safe chars – already html.escaped)
        tooltip = (
            f"{d['device_id']} — {d['name']}\\n"
            f"Status: {d['status_raw']}\\n"
            f"Battery: {batt_str}\\n"
            f"Location: {d['location']}\\n"
            f"Last seen: {since}"
        )

        # Pulse ring for active devices
        pulse = ""
        if d["status"] == "active":
            pulse = f'<circle cx="{x}" cy="{y}" r="12" fill="{colour}" opacity="0.25" class="pulse-ring"/>'

        markers.append(
            f'{pulse}'
            f'<circle cx="{x}" cy="{y}" r="7" fill="{colour}" stroke="#fff" stroke-width="2" '
            f'class="map-marker" data-tip="{tooltip}" '
            f'onmouseenter="showTip(event,this)" onmouseleave="hideTip()"/>'
        )

    markers_svg = "\n    ".join(markers)

    return f"""
<div class="map-wrap">
  <svg viewBox="0 0 {SVG_W} {SVG_H}" xmlns="http://www.w3.org/2000/svg" class="fleet-map" aria-label="Fleet map">
    <!-- Background -->
    <rect width="{SVG_W}" height="{SVG_H}" rx="12" fill="#0f172a"/>
    <!-- Subtle grid -->
    <g stroke="#1e293b" stroke-width="1">
      {''.join(f'<line x1="{PAD + i*((SVG_W-2*PAD)//5)}" y1="{PAD}" x2="{PAD + i*((SVG_W-2*PAD)//5)}" y2="{SVG_H-PAD}"/>' for i in range(6))}
      {''.join(f'<line x1="{PAD}" y1="{PAD + i*((SVG_H-2*PAD)//4)}" x2="{SVG_W-PAD}" y2="{PAD + i*((SVG_H-2*PAD)//4)}"/>' for i in range(5))}
    </g>
    <!-- City labels (approximate positions) -->
    <g font-family="system-ui" font-size="11" fill="#475569">
      <text x="{project(-31.95, 115.86)[0]}" y="{project(-31.95, 115.86)[1]-15}">Perth</text>
      <text x="{project(-27.47, 153.03)[0]-10}" y="{project(-27.47, 153.03)[1]-15}">Brisbane</text>
      <text x="{project(-33.87, 151.21)[0]}" y="{project(-33.87, 151.21)[1]-15}">Sydney</text>
      <text x="{project(-37.81, 144.97)[0]-20}" y="{project(-37.81, 144.97)[1]-15}">Melbourne</text>
      <text x="{project(-34.93, 138.60)[0]}" y="{project(-34.93, 138.60)[1]-15}">Adelaide</text>
      <text x="{project(-42.88, 147.33)[0]}" y="{project(-42.88, 147.33)[1]-15}">Hobart</text>
      <text x="{project(-12.46, 130.84)[0]}" y="{project(-12.46, 130.84)[1]+18}">Darwin</text>
    </g>
    <!-- Device markers -->
    {markers_svg}
  </svg>
  <div id="map-tooltip" class="map-tooltip" style="display:none"></div>
</div>
"""


# ---------------------------------------------------------------------------
# 5. Device Table
# ---------------------------------------------------------------------------

def battery_bar(pct, valid: bool) -> str:
    """Return an inline SVG battery bar."""
    if not valid or pct is None:
        return '<span class="batt-na">N/A</span>'

    if pct >= 50:
        bar_colour = "#22c55e"
    elif pct >= 20:
        bar_colour = "#f97316"
    else:
        bar_colour = "#ef4444"

    fill_w = round(pct * 28 / 100)  # max 28px bar
    return (
        f'<span class="batt-wrap" title="{pct}%">'
        f'<svg width="36" height="14" viewBox="0 0 36 14" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="0" y="1" width="32" height="12" rx="2" fill="none" stroke="#475569" stroke-width="1.5"/>'
        f'<rect x="32" y="4" width="3" height="6" rx="1" fill="#475569"/>'
        f'<rect x="1.5" y="2.5" width="{fill_w}" height="9" rx="1.5" fill="{bar_colour}"/>'
        f'</svg>'
        f'<span class="batt-pct">{pct}%</span>'
        f'</span>'
    )


def status_badge(status: str, raw: str) -> str:
    bg = STATUS_BG.get(status, "#f1f5f9")
    txt = STATUS_TEXT.get(status, "#475569")
    label = raw.replace("_", " ").title()
    return f'<span class="badge" style="background:{bg};color:{txt}">{label}</span>'


def generate_table(devices: list[dict]) -> str:
    rows = []
    for i, d in enumerate(devices):
        since = calculate_last_seen(d["last_seen"])
        row_class = "row-even" if i % 2 == 0 else "row-odd"
        batt_html = battery_bar(d["battery_pct"], d["battery_valid"])
        badge_html = status_badge(d["status"], d["status_raw"])

        rows.append(f"""
        <tr class="{row_class}">
          <td class="mono">{d['device_id']}</td>
          <td>{d['name']}</td>
          <td>{badge_html}</td>
          <td>{batt_html}</td>
          <td>{d['location']}</td>
          <td class="mono small">{d['last_seen_str']}</td>
          <td class="small muted">{since}</td>
        </tr>""")

    rows_html = "".join(rows)

    return f"""
<div class="table-wrap">
  <table id="fleet-table" class="fleet-table">
    <thead>
      <tr>
        <th onclick="sortTable(0)" title="Sort">Device ID ⇅</th>
        <th onclick="sortTable(1)" title="Sort">Vehicle ⇅</th>
        <th onclick="sortTable(2)" title="Sort">Status ⇅</th>
        <th onclick="sortTable(3)" title="Sort">Battery ⇅</th>
        <th onclick="sortTable(4)" title="Sort">Location ⇅</th>
        <th onclick="sortTable(5)" title="Sort">Last Seen ⇅</th>
        <th>Since</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>
"""


# ---------------------------------------------------------------------------
# 6. KPI Cards
# ---------------------------------------------------------------------------

def generate_summary_cards(summary: dict) -> str:
    cards = [
        ("Total Devices",   summary["total"],       "#6366f1", "🚛"),
        ("Active",          summary["active"],       "#22c55e", "✅"),
        ("Idle",            summary["idle"],         "#f97316", "⏸"),
        ("Offline",         summary["offline"],      "#ef4444", "🔴"),
        ("Low Battery",     summary["low_battery"],  "#eab308", "🔋"),
    ]
    html_parts = []
    for label, count, colour, icon in cards:
        html_parts.append(f"""
    <div class="kpi-card" style="--accent:{colour}">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-count" style="color:{colour}">{count}</div>
      <div class="kpi-label">{label}</div>
    </div>""")
    return '<div class="kpi-grid">' + "".join(html_parts) + "</div>"


# ---------------------------------------------------------------------------
# 7. Full HTML
# ---------------------------------------------------------------------------

def generate_dashboard(devices: list[dict], summary: dict) -> str:
    now_str = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    cards_html = generate_summary_cards(summary)
    map_html = generate_map(devices)
    table_html = generate_table(devices)
    legend_items = "".join(
        f'<span class="leg-dot" style="background:{c}"></span>{s.replace("_"," ").title()}'
        for s, c in STATUS_COLOURS.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Fleet Command — Live Dashboard</title>
<style>
/* ---- Reset & Base ---- */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg:        #020818;
  --surface:   #0d1526;
  --surface2:  #141f35;
  --border:    #1e2d47;
  --text:      #e2e8f0;
  --muted:     #64748b;
  --accent:    #3b82f6;
  --radius:    12px;
  --font-mono: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  --font-body: "Inter", "Segoe UI", system-ui, sans-serif;
}}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.6;
  min-height: 100vh;
}}

/* ---- Layout ---- */
.shell {{ max-width: 1280px; margin: 0 auto; padding: 0 24px 48px; }}

/* ---- Header ---- */
.site-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 0 18px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 32px;
  flex-wrap: wrap;
  gap: 12px;
}}
.header-brand {{ display: flex; align-items: center; gap: 12px; }}
.brand-mark {{
  width: 38px; height: 38px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
}}
.brand-name {{
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.3px;
  color: #f1f5f9;
}}
.brand-sub {{ font-size: 12px; color: var(--muted); }}
.header-meta {{ font-size: 12px; color: var(--muted); text-align: right; }}
.live-dot {{
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #22c55e;
  margin-right: 6px;
  animation: pulse 2s infinite;
}}
@keyframes pulse {{
  0%, 100% {{ opacity: 1; }}
  50%  {{ opacity: 0.3; }}
}}

/* ---- Section labels ---- */
.section-label {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 14px;
}}

/* ---- KPI Cards ---- */
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 14px;
  margin-bottom: 36px;
}}
.kpi-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 3px solid var(--accent);
  border-radius: var(--radius);
  padding: 18px 16px 14px;
  display: flex; flex-direction: column; align-items: flex-start;
  gap: 4px;
  transition: transform 0.15s, box-shadow 0.15s;
}}
.kpi-card:hover {{
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}}
.kpi-icon {{ font-size: 20px; margin-bottom: 6px; }}
.kpi-count {{ font-size: 32px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }}
.kpi-label {{ font-size: 12px; color: var(--muted); }}

/* ---- Map ---- */
.map-section {{ margin-bottom: 36px; }}
.map-header {{
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
  margin-bottom: 12px;
}}
.map-legend {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--muted); }}
.leg-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}
.map-wrap {{ position: relative; }}
.fleet-map {{ width: 100%; border-radius: var(--radius); border: 1px solid var(--border); display: block; }}
.map-marker {{ cursor: pointer; transition: r 0.1s; }}
.map-marker:hover {{ r: 10; }}
.pulse-ring {{ animation: ring-pulse 2.5s ease-out infinite; }}
@keyframes ring-pulse {{ 0% {{ r:7; opacity:0.6; }} 100% {{ r:20; opacity:0; }} }}
.map-tooltip {{
  position: fixed;
  background: #1e2d47;
  border: 1px solid #2d4a6e;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre;
  pointer-events: none;
  z-index: 9999;
  color: #e2e8f0;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}}

/* ---- Table ---- */
.table-section {{ margin-bottom: 36px; }}
.table-controls {{
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 10px;
  margin-bottom: 12px;
}}
.search-box {{
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 7px 14px;
  font-size: 13px;
  width: 240px;
  outline: none;
  transition: border-color 0.2s;
}}
.search-box:focus {{ border-color: var(--accent); }}
.table-wrap {{
  overflow-x: auto;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}}
.fleet-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}}
.fleet-table thead tr {{
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
}}
.fleet-table th {{
  padding: 11px 14px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}}
.fleet-table th:hover {{ color: var(--text); }}
.fleet-table td {{
  padding: 10px 14px;
  border-bottom: 1px solid #111c30;
  vertical-align: middle;
}}
.row-even {{ background: var(--surface); }}
.row-odd  {{ background: #0a1220; }}
.fleet-table tr:last-child td {{ border-bottom: none; }}
.fleet-table tbody tr:hover {{ background: #162035; }}

/* Badges */
.badge {{
  display: inline-block;
  padding: 2px 9px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
  white-space: nowrap;
}}

/* Battery */
.batt-wrap {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
.batt-pct {{ font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }}
.batt-na {{ color: var(--muted); font-size: 12px; }}

/* Text helpers */
.mono  {{ font-family: var(--font-mono); font-size: 12px; }}
.small {{ font-size: 12px; }}
.muted {{ color: var(--muted); }}

/* ---- Footer ---- */
.site-footer {{
  border-top: 1px solid var(--border);
  padding-top: 18px;
  font-size: 12px;
  color: var(--muted);
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}}

/* ---- Responsive ---- */
@media (max-width: 640px) {{
  .kpi-count {{ font-size: 26px; }}
  .search-box {{ width: 100%; }}
  .site-header {{ flex-direction: column; align-items: flex-start; }}
}}
</style>
</head>
<body>
<div class="shell">

  <!-- Header -->
  <header class="site-header">
    <div class="header-brand">
      <div class="brand-mark">🚛</div>
      <div>
        <div class="brand-name">Fleet Command</div>
        <div class="brand-sub">GPS Tracking Dashboard</div>
      </div>
    </div>
    <div class="header-meta">
      <span class="live-dot"></span>Generated at {now_str}<br>
      {summary['total']} devices tracked
    </div>
  </header>

  <!-- KPI Summary -->
  <p class="section-label">Fleet Overview</p>
  {cards_html}

  <!-- Map -->
  <section class="map-section">
    <div class="map-header">
      <p class="section-label" style="margin-bottom:0">Live Map</p>
      <div class="map-legend">
        {legend_items}
      </div>
    </div>
    {map_html}
  </section>

  <!-- Table -->
  <section class="table-section">
    <div class="table-controls">
      <p class="section-label" style="margin-bottom:0">Device List</p>
      <input class="search-box" type="text" id="search-input"
             placeholder="Search by ID, name, location…"
             oninput="filterTable(this.value)"/>
    </div>
    {table_html}
  </section>

  <footer class="site-footer">
    <span>Fleet Command · Generated {now_str}</span>
    <span>{summary['active']} active · {summary['offline']} offline · {summary['low_battery']} low battery</span>
  </footer>

</div>

<script>
// ---- Tooltip ----
var tip = document.getElementById('map-tooltip');
function showTip(e, el) {{
  tip.textContent = el.getAttribute('data-tip');
  tip.style.display = 'block';
  moveTip(e);
}}
function moveTip(e) {{
  if (!tip || tip.style.display === 'none') return;
  var x = e.clientX + 14, y = e.clientY + 14;
  var w = tip.offsetWidth, h = tip.offsetHeight;
  if (x + w > window.innerWidth)  x = e.clientX - w - 14;
  if (y + h > window.innerHeight) y = e.clientY - h - 14;
  tip.style.left = x + 'px';
  tip.style.top  = y + 'px';
}}
function hideTip() {{ tip.style.display = 'none'; }}
document.addEventListener('mousemove', moveTip);

// ---- Table Sort ----
var sortDir = {{}};
function sortTable(col) {{
  var tbody = document.querySelector('#fleet-table tbody');
  var rows = Array.from(tbody.rows);
  sortDir[col] = sortDir[col] === 'asc' ? 'desc' : 'asc';
  rows.sort(function(a, b) {{
    var av = a.cells[col].textContent.trim().toLowerCase();
    var bv = b.cells[col].textContent.trim().toLowerCase();
    var an = parseFloat(av), bn = parseFloat(bv);
    var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
    return sortDir[col] === 'asc' ? cmp : -cmp;
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
  // re-apply stripe
  rows.forEach(function(r, i) {{
    r.className = i % 2 === 0 ? 'row-even' : 'row-odd';
  }});
}}

// ---- Table Search ----
function filterTable(q) {{
  q = q.toLowerCase();
  var rows = document.querySelectorAll('#fleet-table tbody tr');
  rows.forEach(function(r) {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 8. Save
# ---------------------------------------------------------------------------

def save_html(content: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    csv_path  = "fleet_status.csv"
    html_path = "fleet_dashboard.html"

    if not os.path.exists(csv_path):
        print(f"ERROR: '{csv_path}' not found. Place it in the same directory.")
        return

    print("Reading fleet data…")
    devices = load_csv(csv_path)
    print(f"  Loaded {len(devices)} valid device records.")

    print("Calculating summary…")
    summary = calculate_summary(devices)

    print("Generating dashboard…")
    html_content = generate_dashboard(devices, summary)

    print(f"Writing '{html_path}'…")
    save_html(html_content, html_path)

    print(f"\nDone! Open '{html_path}' in any browser.")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
