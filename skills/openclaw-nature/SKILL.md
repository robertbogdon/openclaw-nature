---
name: openclaw-nature
description: Merge eBird and iNaturalist observation data into unified "sessions" (groups of observations at the same place and time). Provides a session builder that reads from both local SQLite databases and produces consolidated outing reports.
---

# OpenClaw Nature — Session Builder

A skill that merges eBird and iNaturalist observations into unified **sessions** — outings grouped by proximity in time and space.

## How It Works (Two-Phase Algorithm)

**Phase 1 — Cluster iNaturalist observations** (they have accurate timestamps):
- Observations sorted by UTC timestamp
- Same session if within `DISTANCE_KM` (default 1 km) of the *last* observation
- AND within `TIME_MINUTES` (default 120 min) of the *previous* observation's time
- Otherwise, start a new session

**Phase 2 — Overlay eBird checklists onto iNat sessions:**
- eBird CSV only has dates (times are unreliable)
- For each eBird checklist, find the best-matching iNat session on the same date
  within `DISTANCE_KM` of any observation in that session
- If matched: eBird species are **merged into the iNat session** and assigned the
  session's **end time** (they happened during the outing, recorded later)
- If no match: the checklist becomes a standalone eBird-only session
- **Original data is never modified** — the overlay is stored in
  `openclaw-nature.db` with an `is_overlay` flag on each observation

## Quick Start

```bash
python3 import/build_sessions.py \
  --start-date 2026-05-04 \
  --end-date 2026-05-08 \
  --dist 1.0 \
  --time 120
```

### Output

```
  ── OpenClaw Nature Session Report ──
  Sessions:     9
  Observations: 239 (74 eBird, 165 iNaturalist)
  Merged:       6 sessions (both sources)
  iNat-only:    3 sessions
  eBird-only:   0 sessions

  Session  Start (local)          End (local)            Duration   ... Obs   eB   iNat  Species
  #1       2026-05-04T05:00:00    2026-05-04T05:00:00    00:00:00  ... 18   9    9     16
  #3       2026-05-05T05:00:00    2026-05-05T05:00:00    00:00:00  ... 12   9    3     12
  #4       2026-05-06T05:00:00    2026-05-06T05:00:00    00:00:00  ... 23   18   5     22
  #8       2026-05-07T05:00:00    2026-05-07T05:00:00    00:00:00  ... 82   15   67    69
  #9       2026-05-08T05:00:00    2026-05-08T05:00:00    00:00:00  ... 45   5    40    37
```

### Save outputs

```bash
python3 import/build_sessions.py --session-db import/openclaw-nature.db
python3 import/build_sessions.py --csv import/sessions.csv
```

## Configuration

| Argument | Default | Description |
|----------|---------|-------------|
| `--ebird-db` | `../ebird/import/ebird.db` | Path to eBird SQLite database |
| `--inat-db` | `../inaturalist/import/inat.db` | Path to iNaturalist SQLite database |
| `--start-date` | *all* | Filter start date (YYYY-MM-DD) |
| `--end-date` | *all* | Filter end date (YYYY-MM-DD) |
| `--dist` | `1.0` | Distance threshold in km |
| `--time` | `120` | Time threshold in minutes |
| `--session-db` | `import/openclaw-nature.db` | Output SQLite database path |
| `--csv` | *none* | Output CSV report file path |
| `--tz` | `America/Los_Angeles` | Display timezone for timestamps |
| `--no-db` | *false* | Skip writing to openclaw-nature.db |

## Examples

```bash
# All data with wider thresholds
python3 import/build_sessions.py --dist 5.0 --time 360

# Specific date range, CSV only
python3 import/build_sessions.py \
  --start-date 2026-05-04 \
  --end-date 2026-05-08 \
  --csv /tmp/sessions-report.csv \
  --no-db

# Custom DB paths
python3 import/build_sessions.py \
  --ebird-db /path/to/ebird.db \
  --inat-db /path/to/inat.db
```

## Querying Sessions

```bash
# All sessions
python3 -c "
import sqlite3
conn = sqlite3.connect('import/openclaw-nature.db')
for r in conn.execute('SELECT session_num, start_utc, location, num_obs, species_count FROM sessions ORDER BY session_num'):
    print(f'#{r[0]}: {r[3]} observations ({r[4]} species) at {r[2]} on {r[1]}')
"

# Only eBird overlay observations in a session
python3 -c "
import sqlite3
conn = sqlite3.connect('import/openclaw-nature.db')
for r in conn.execute('''SELECT species FROM session_observations
    WHERE session_id = (SELECT id FROM sessions WHERE session_num = 1)
    AND source = \"ebird\"'''):
    print(f'  eBird: {r[0]}')
"

# Observations that are NOT overlays (direct observations)
python3 -c "
import sqlite3
conn = sqlite3.connect('import/openclaw-nature.db')
count = conn.execute('SELECT COUNT(*) FROM session_observations WHERE is_overlay = 0').fetchone()[0]
print(f'Direct observations: {count}')
overlay = conn.execute('SELECT COUNT(*) FROM session_observations WHERE is_overlay = 1').fetchone()[0]
print(f'Overlay (eBird assigned) observations: {overlay}')
"
```

## Timezone Handling

- **eBird**: Times are local (assume America/Los_Angeles). Only used for eBird-only sessions (fallback noon). In overlay mode, eBird times are replaced by the session's end time.
- **iNaturalist**: `time_observed_at` is ISO 8601 with explicit UTC offset. Parsed directly to UTC. This drives the session clustering.
- **Display**: Always shown in the configured timezone (default America/Los_Angeles / Pacific).

## Distance

Haversine formula, stdlib only. Configurable km threshold.

## Files

| File | Purpose |
|------|---------|
| `import/build_sessions.py` | The session builder script (stdlib only) |
| `import/openclaw-nature.db` | Generated session database (contains sessions + observations) |
| `import/sessions.csv` | Optional CSV export |
| `references/schema.md` | Database schema reference |

## Data Sources

- **eBird**: `../ebird/import/ebird.db` — checklist-level observations (never modified)
- **iNaturalist**: `../inaturalist/import/inat.db` — individual observations (never modified)
- **Overlay data**: stored in `openclaw-nature.db` with `is_overlay=1` flag
