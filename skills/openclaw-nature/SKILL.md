---
name: openclaw-nature
description: Merge eBird and iNaturalist observation data into unified "sessions" (groups of observations at the same place and time). Provides a session builder that reads from both local SQLite databases and produces consolidated outing reports.
---

# OpenClaw Nature — Session Builder

A skill that merges eBird and iNaturalist observations into unified **sessions** — outings grouped by proximity in time and space.

## Quick Start

Build sessions from Robert's eBird + iNaturalist data for a specific date range:

```bash
python3 import/build_sessions.py \
  --start-date 2026-05-04 \
  --end-date 2026-05-08 \
  --dist 1.0 \
  --time 120
```

The script auto-discovers the eBird and iNaturalist databases in the sibling skill directories.

### Output

```
  ── OpenClaw Nature Session Report ──
  Sessions:     35
  Observations: 239 (74 eBird, 165 iNaturalist)

  Session  Start (local)          End (local)            Location            Obs  eB  iNat
  #1       2026-05-04T05:00:00    2026-05-04T05:00:00    Tierrasanta...       9    0    9
  #2       2026-05-04T12:00:00    2026-05-04T12:00:00    Tierrasanta...       9    9    0
  ...
```

### Save outputs

```bash
# Write sessions database
python3 import/build_sessions.py --session-db import/sessions.db

# CSV report
python3 import/build_sessions.py --csv import/sessions.csv
```

## How Sessions Work

Observations from both sources are merged, sorted by UTC timestamp, then grouped:

1. **Start a session** with the first observation
2. **Keep adding** while:
   - Location is within `DISTANCE_THRESHOLD` (default 1 km) of the **last** observation
   - Time is within `TIME_THRESHOLD` (default 2 hours) of the **previous** observation's time
3. **Start a new session** when either threshold is exceeded

### Timezone Handling

- **eBird**: Times are local (assume America/Los_Angeles). Converts to UTC using DST-aware offset calculation. Observations with no time default to noon local.
- **iNaturalist**: `time_observed_at` is ISO 8601 with explicit UTC offset. Parsed directly to UTC. Observations with no time default to noon UTC.

### Distance

Haversine formula, stdlib only. Configurable threshold in km.

## Configuration

All settings are CLI arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| `--ebird-db` | `../ebird/import/ebird.db` | Path to eBird SQLite database |
| `--inat-db` | `../inaturalist/import/inat.db` | Path to iNaturalist SQLite database |
| `--start-date` | *all* | Filter start date (YYYY-MM-DD) |
| `--end-date` | *all* | Filter end date (YYYY-MM-DD) |
| `--dist` | `1.0` | Distance threshold in km |
| `--time` | `120` | Time threshold in minutes |
| `--session-db` | `import/sessions.db` | Output SQLite database path |
| `--csv` | *none* | Output CSV report file path |
| `--tz` | `America/Los_Angeles` | Display timezone for timestamps |
| `--no-db` | *false* | Skip writing to sessions.db |

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

After running with `--session-db`, query with Python or sqlite3:

```bash
# All sessions
python3 -c "
import sqlite3
conn = sqlite3.connect('import/sessions.db')
for r in conn.execute('SELECT session_num, start_utc, location_summary, num_obs, species_count FROM sessions ORDER BY session_num'):
    print(f'#{r[0]}: {r[3]} observations ({r[4]} species) at {r[2]} on {r[1]}')
"

# Biggest session (most observations)
python3 -c "
import sqlite3
conn = sqlite3.connect('import/sessions.db')
r = conn.execute('SELECT session_num, num_obs, location_summary FROM sessions ORDER BY num_obs DESC LIMIT 1').fetchone()
print(f'Biggest session: #{r[0]} with {r[1]} observations at {r[2]}')
"

# Observations in session #7
python3 -c "
import sqlite3
conn = sqlite3.connect('import/sessions.db')
for r in conn.execute('''SELECT source, species, lat, lng FROM session_observations 
    WHERE session_id = (SELECT id FROM sessions WHERE session_num = 7)'''):
    print(f'[{r[0]}] {r[1]}')
"
```

## Agent Query Patterns

| User Intent | Pattern |
|---|---|
| "What did I observe on May 4th?" | `build_sessions.py --start-date 2026-05-04 --end-date 2026-05-04` |
| "Show me all my outings last week" | `build_sessions.py --start-date <7 days ago> --end-date <today>` |
| "What was my biggest session?" | Query sessions.db: `ORDER BY num_obs DESC LIMIT 1` |
| "Merge all my recent observations" | `build_sessions.py --time 360 --dist 2.0` (wider grouping) |
| "What species did I see at Blue Sky?" | `grep 'Blue Sky' sessions.csv` or query sessions.db |

## Files

| File | Purpose |
|------|---------|
| `import/build_sessions.py` | The session builder script (stdlib only) |
| `import/sessions.db` | Generated session database |
| `import/sessions.csv` | Optional CSV export |
| `references/schema.md` | Session database and CSV schema reference |

## Data Sources

- **eBird**: `../ebird/import/ebird.db` — checklist-level observations
- **iNaturalist**: `../inaturalist/import/inat.db` — individual observations
