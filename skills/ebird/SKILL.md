---
name: ebird
description: Retrieve bird observation data, hotspot information, taxonomy, and region details from the eBird API v2.0. Use when Codex needs bird sighting data, recent sightings by location, rare bird alerts, hotspot lists, species taxonomy lookups, or eBird checklist information. Also use for region hierarchy queries (countries, states, counties) and eBird/Clements taxonomy versions.
---

# eBird — OpenClaw Skill

## Configuration

The eBird API requires an API key sent as the `X-eBirdApiToken` HTTP header on every request.

### Setting the API Key

The API key must be available as the environment variable `EBIRD_API_KEY`.
There are two ways to provide it:

**1. Via skills.entries config (recommended):**
```json
{
  "skills": {
    "entries": {
      "ebird": {
        "enabled": true,
        "env": {
          "EBIRD_API_KEY": "your-api-key-here"
        }
      }
    }
  }
}
```

**2. Via agent env:** Add `EBIRD_API_KEY` to your agent's environment.

### Quick Start

Base URL defaults to `https://api.ebird.org/v2`.
Set `EBIRD_BASE_URL` to override.

Before making requests, resolve the API key:
```bash
# The key should be set as EBIRD_API_KEY in env/config
# Use $EBIRD_API_KEY for one-off checks (see examples below)
```

### Recent Birds in a Region

```bash
curl -s -H "X-eBirdApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/data/obs/{regionCode}/recent?maxResults=10&back=7"
```

### Rare Bird Alerts Nearby

```bash
curl -s -H "X-eBirdApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/data/obs/geo/recent/notable?lat={lat}&lng={lng}&dist=25&detail=full"
```

### Hotspots Near Coordinates

```bash
curl -s -H "X-eBirdApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/ref/hotspot/geo?lat={lat}&lng={lng}&dist=10"
```

### Checking if the key is available

Before making an API call, verify the key is present:
```bash
if [ -z "$EBIRD_API_KEY" ]; then
  echo "ERROR: EBIRD_API_KEY not set. See Configuration section above."
  exit 1
fi
```

## Region & Species Code Ref

eBird uses hierarchical region codes:

| Scope | Code Format | Example |
|-------|-------------|---------|
| Country | `US`, `GB`, `IN` | `US` |
| State | `{country}-{state}` | `US-CA` |
| County | `{state}-{county}` | `US-CA-075` |
| Location | `L{id}` | `L99381` (Central Park) |

Species codes are internal identifiers (e.g. `baleag` for Bald Eagle), not 4-letter banding codes.

## User Data Import

The skill includes a personal data browser flow and SQLite importer at `import/`. This lets you bootstrap a local database of the user's complete eBird observation history.

### Files

| File | Purpose |
|------|---------|
| `import/import_csv_to_sqlite.py` | Reads a `MyEBirdData.csv` export, normalises fields, writes into a local SQLite database using `INSERT OR REPLACE` on `submission_id`. Python 3 stdlib only — no pip packages needed. |
| `import/ebird.db` | Generated on first run. Schema includes `observations` table (all CSV fields), `metadata` table (record count, import timestamp, source file), and indexes on date, species, and location. Uses WAL journal mode. |

### Import Workflow

1. **Launch a managed browser** on a node where the user can log in to eBird:
   ```bash
   openclaw browser open "https://ebird.org/download"
   ```
2. **User logs in manually.** The managed Chrome session persists the login cookies.
3. **Request the data export:**
   ```bash
   openclaw browser navigate <tab-id> "https://ebird.org/downloadMyData"
   openclaw browser snapshot <tab-id>          # find the trigger button
   openclaw browser act <tab-id> click <ref>   # click "Request My Observations"
   ```
   Or navigate directly to the trigger URL:
   ```bash
   openclaw browser navigate <tab-id> "https://ebird.org/downloadMyData/start"
   ```
   The page shows a "Success!" confirmation. eBird then emails a download link.
4. **User provides the download URL** from the eBird email (`do-not-reply@ebird.org`).
5. **Download, extract, and import:**
   ```bash
   curl -sL -o /tmp/ebird_download.zip "<url-from-email>"
   cd /tmp && unzip -o ebird_download.zip
   python3 import/import_csv_to_sqlite.py
   ```

The import is **idempotent** — re-running on a newer export updates existing rows and adds new ones without duplicating.

### Agent Query Patterns for User Data

Once imported, query the local database with SQLite:
```bash
sqlite3 import/ebird.db "SELECT common_name, COUNT(*) AS cnt
  FROM observations
  WHERE obs_date >= date('now', '-30 days')
  GROUP BY common_name ORDER BY cnt DESC LIMIT 10;"
```

## API Endpoint Categories

See the reference files for full endpoint docs:

- **`references/api.md`** — All 26+ endpoints with parameters and curl examples for:
  - Observations (recent, historic, geo, notable, species-specific)
  - Hotspots (region list, nearby, info)
  - Taxonomy (versions, full taxonomy, forms/subspecies)
  - Regions (info, adjacent, subregions)
  - My eBird (checklist details, feed, stats, top 100)
  - Neotropical Birds (species reference)

- **`references/response-fields.md`** — Response field reference tables for observation objects, taxonomy region types, species categories, and rate limits.

## Agent Query Patterns

| User Intent | Endpoint / Pattern |
|---|---|
| "What birds were seen recently?" | `data/obs/{region}/recent` |
| "Any rare birds nearby?" | `data/obs/geo/recent/notable` |
| "What was seen on a specific date?" | `data/obs/{region}/historic/{y}/{m}/{d}` |
| "Where are the hotspots near me?" | `ref/hotspot/geo` |
| "Show me the taxonomy of [species]" | `ref/taxonomy/ebird?cat=species` + jq filter |
| "What subregions are in [country]?" | `ref/region/country/{code}/subregions` |
| "Tell me about this checklist" | `product/checklist/{subId}` |
| "What's the top 100 for [region]?" | `product/top100/{region}` |

## Rate Limits

Free tier: ~50 requests/minute. Check headers or https://ebird.org/api/keygen.
