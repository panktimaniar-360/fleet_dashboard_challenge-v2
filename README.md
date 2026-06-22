# fleet_dashboard_challenge-v2
# Fleet Dashboard Challenge — Submission

A Python script that reads `fleet_status.csv` and generates a fully self-contained `fleet_dashboard.html` for fleet managers — no server, no install, just open in a browser.

---

## How to Run

```bash
python3 fleet_dashboard.py
# → fleet_dashboard.html
```

Runs in under 2 seconds. Python standard library only.

---

## My Approach

### How I used AI to complete this task

I used Claude (Anthropic) as my primary tool throughout this challenge.

I started by feeding Claude the README and the CSV data together, then asked it to design and generate the full Python script and HTML output in one pass. Rather than accepting the first output blindly, I reviewed the generated code for correctness — checking the coordinate projection logic, data validation, and edge case handling (dirty rows like `TRK031`–`TRK035` with missing names, invalid lat values, future timestamps, and out-of-range battery percentages).

I then iterated with Claude on the visual design — specifically asking for a dark, professional dashboard aesthetic suited to a fleet operations context rather than a generic light-mode template. The final result reflects deliberate choices about layout, typography, and colour that I directed and reviewed.

### What colour/status logic I chose and why

| Status | Colour | Reasoning |
|---|---|---|
| **Active** | Green `#22c55e` | Universal "all good" signal — the device is moving and reporting |
| **Idle** | Amber `#f59e0b` | Attention warranted but not urgent — vehicle stopped, engine possibly running |
| **Offline** | Grey `#6b7280` | Muted rather than alarming — could be expected downtime, end of shift, or dead battery |
| **Low Battery** | Red `#ef4444` | Actionable urgency — if not addressed the device will go offline and tracking is lost |
| **Maintenance** | Blue `#3b82f6` | Neutral informational — vehicle is deliberately out of service |
| **Unknown** | Purple `#a855f7` | Unexpected/unrecognised status — flags data quality issues |

The battery bar uses the same traffic-light logic independently of status: red below 15%, amber below 35%, green above — so a fleet manager can spot charging issues at a glance without reading numbers.

Active devices show a pulsing dot on both the map and the list to draw the eye to live movement.

### One thing I would add if this were a real product

**Trip history / breadcrumb trails on the map.** A single point tells you where a vehicle *is* — a trail of the last 4–8 hours tells you where it's *been*, which is what most fleet managers actually need for compliance, route optimisation, and dispute resolution. I would store the last N pings per device and draw a fading polyline on the map behind each marker.

---

## Output Preview

The dashboard includes:

- **Interactive map** of Australia with each device plotted at its GPS coordinates, colour-coded by status. Hover for a tooltip; click to highlight in the list.
- **Device list panel** with real-time search, status filter chips, battery bar, and human-readable "last seen" times (e.g. *2h 14m ago*).
- **Summary bar** at the top showing counts per status — click any chip to filter both the list and map.
- **Data quality handling** — devices with invalid coordinates, future timestamps, out-of-range battery values, or unknown status are handled gracefully rather than crashing.
