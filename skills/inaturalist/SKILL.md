---
name: inaturalist
description: Query biodiversity observations, species taxonomy, places, projects, users, identifications, and controlled terms from the iNaturalist API v1. Use when Codex needs species occurrence data, citizen science observations, species identification lookups, taxonomy searches, conservation status, place-based biodiversity queries, or project/community-based observation searches. Also for photo-based species identification via computer vision.
---

# iNaturalist — OpenClaw Skill

## Configuration

The iNaturalist API is open for GET requests without authentication. For personal queries (your observations, identifications) the skill recognises a `user_login` parameter.

### Setting the User Login

**Via skills.entries config (recommended):**
```json
{
  "skills": {
    "entries": {
      "inaturalist": {
        "enabled": true,
        "env": {
          "INAT_USER_LOGIN": "your-username-here",
          "INAT_BASE_URL": "https://api.inaturalist.org/v1"
        }
      }
    }
  }
}
```

**Via agent env:** Set `INAT_USER_LOGIN` to your iNaturalist username.

When `INAT_USER_LOGIN` is set, the skill uses it as the default `user_login` for observation queries — so you can search "my recent observations" without specifying the user each time.

You can also set `INAT_API_TOKEN` (with `Authorization: Bearer` header) for higher rate limits.

## Quick Start

Base URL defaults to `https://api.inaturalist.org/v1`.

### Search Recent Observations

```bash
curl -s "$INAT_BASE_URL/observations?user_login=${INAT_USER_LOGIN:-{username}}&taxon_name={species}&per_page=20"
```

### Species Counts (What's been seen here?)

```bash
curl -s "$INAT_BASE_URL/observations/species_counts?place_id={id}&per_page=20"
```

### Taxon Autocomplete

```bash
curl -s "$INAT_BASE_URL/taxa/autocomplete?q={search term}&per_page=5"
```

### Nearby Places

```bash
curl -s "$INAT_BASE_URL/places/nearby?lat={lat}&lng={lng}"
```

### My Recent Observations

```bash
curl -s "$INAT_BASE_URL/observations?user_login=${INAT_USER_LOGIN}&per_page=50"
```

### Observations in a Date Range

```bash
# Observations observed between two dates
curl -s "$INAT_BASE_URL/observations?d1=2025-06-01&d2=2025-06-30&per_page=50"

# Observations created (uploaded) today
curl -s "$INAT_BASE_URL/observations?user_login=${INAT_USER_LOGIN}&created_on=today&per_page=50"

# Observations created after a specific timestamp
curl -s "$INAT_BASE_URL/observations?created_after=2026-01-01T00:00:00%2B00:00&per_page=200"
```

### Incremental Sync (new observations only)

Use `id_above` with your last known observation ID to pull only newer records:

```bash
# Get observations newer than ID 123456789
curl -s "$INAT_BASE_URL/observations?id_above=123456789&user_login=${INAT_USER_LOGIN}&per_page=200&order=asc"
```

Paginate by looping `page` until `results` is empty.

## API Endpoint Categories

See the reference files for full endpoint docs:

- **`references/api.md`** — All 24+ endpoints with parameters:
  - Observations (search, species counts, by ID, incremental sync, comments, identifications)
  - Taxa (search, autocomplete, by ID)
  - Places (search, autocomplete, by ID, nearby)
  - Projects (search, by ID, members, journal posts, observations)
  - Users (profile, by ID, by login, autocomplete)
  - Identifications (search, by ID, similar species)
  - Photos (by ID)
  - Controlled Terms (list, for taxon)
  - Computer Vision (identify from photo)

- **`references/response-fields.md`** — Response field reference for Observation and Taxon objects, rank levels, quality grades, and iconic taxa groups.

## Agent Query Patterns

| User Intent | Endpoint / Pattern |
|---|---|
| "What species were seen here?" | `observations/species_counts?place_id={id}` |
| "Show me sightings of [species]" | `observations?taxon_name={name}` |
| "What's the scientific name for...?" | `taxa/autocomplete?q={query}` |
| "Rare plants near me?" | `observations?iconic_taxa=Plantae&threatened=true` |
| "Projects about [topic] in [place]" | `projects?q={topic}&place_id={id}` |
| "What taxonomy is [species]?" | `taxa?q={name}&rank=species` |
| "Research-grade observations?" | `observations?quality_grade=research` |
| "What annotations are available?" | `controlled_terms` / `controlled_terms/for_taxon` |
| "Identify this species from a photo" | `computervision/v2/identify` (POST) |

## Key Filters

**Quality grades:** `research` (>66% community ID agreement), `needs_id`, `casual`
**Iconic taxa:** `Animalia`, `Aves`, `Mammalia`, `Reptilia`, `Amphibia`, `Actinopterygii`, `Insecta`, `Arachnida`, `Mollusca`, `Fungi`, `Plantae`, `Protozoa`, `Chromista`

## User Data Import

The skill includes a Python 3 script at `import/inat_to_sqlite.py` that fetches all of a user's observations from the iNaturalist API and stores them in a local SQLite database.

### Files

| File | Purpose |
|------|---------|
| `import/inat_to_sqlite.py` | Fetches observations via the API (paginated, up to 200/page), flattens nested fields (taxon, user, photos), writes to SQLite using `INSERT OR REPLACE`. Stdlib only — no pip packages needed. |
| `import/inat.db` | Generated on first run. Schema includes `observations` table (all flattened fields), `metadata` table (record count, max id, import timestamp), and indexes on date, taxon, and user. |

### Usage

```bash
# Full import (all observations for the configured user)
python3 import/inat_to_sqlite.py

# Incremental sync — only fetch observations newer than your last known id
python3 import/inat_to_sqlite.py --id-above 350000000

# Override user for a different account
python3 import/inat_to_sqlite.py --user-login other_user

# Skip confirmation prompt (for automation)
python3 import/inat_to_sqlite.py --no-prompt
```

The script reads the `INAT_USER_LOGIN` env var (set automatically by the skill config).

### Querying the local database

```bash
# Recent observations
sqlite3 import/inat.db "SELECT observed_on, taxon_name, place_guess
  FROM observations ORDER BY observed_on DESC LIMIT 10;"

# Species count
sqlite3 import/inat.db "SELECT taxon_name, COUNT(*) AS cnt
  FROM observations WHERE taxon_name IS NOT NULL
  GROUP BY taxon_name ORDER BY cnt DESC LIMIT 10;"

# Observations from a specific month
sqlite3 import/inat.db "SELECT observed_on, taxon_name, place_guess
  FROM observations WHERE observed_on LIKE '2025-06-%' ORDER BY observed_on;"

# Observations as CSV (for sharing/external use)
sqlite3 -header -csv import/inat.db \
  "SELECT id, observed_on, taxon_name, latitude, longitude, place_guess
   FROM observations ORDER BY observed_on;" > observations.csv
```

### Rate Limits

Unauthenticated: ~100 req/min per IP. Authenticated: ~500 req/min.
Check response headers for `X-RateLimit-*`.
The script is polite (0.5s delay between pages) and won't hit rate limits for typical personal data sizes.
