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

## Rate Limits

Unauthenticated: ~100 req/min per IP. Authenticated: ~500 req/min.
Check response headers for `X-RateLimit-*`.
