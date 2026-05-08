# iNaturalist — OpenClaw Skill
# v1.0.0

Agents should use this skill to interact with the **iNaturalist API v1** for
biodiversity observations, taxa, places, projects, and identification data.
iNaturalist is a citizen science platform for recording and identifying
biodiversity observations, run by the California Academy of Sciences and
the National Geographic Society.

## Configuration

The following variables must be set in the agent's environment or config:

- `INAT_BASE_URL` — defaults to `https://api.inaturalist.org/v1`
- `INAT_API_TOKEN` (opt) — OAuth2 API token (required for write operations)

## Authentication

Most GET endpoints work without authentication, but rate limits are higher
with a token. When an API token is available, include it as:

```
Authorization: Bearer {INAT_API_TOKEN}
```

Apply for tokens at https://www.inaturalist.org/oauth/applications.

---

## API Endpoints

### Observations

iNaturalist's core data type — a sighting of an organism at a time and place.

#### Search Observations
```
GET {INAT_BASE_URL}/observations
```

**Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `user_id` | int | Filter by observer user ID |
| `user_login` | string | Filter by observer login |
| `project_id` | int | Filter by project ID |
| `place_id` | int | Filter by place ID |
| `taxon_id` | int | Filter by taxon ID |
| `taxon_name` | string | Filter by taxon name (partial match) |
| `iconic_taxa` | string | Filter by iconic taxon group (e.g. `Aves`, `Mammalia`) |
| `quality_grade` | string | `research`, `needs_id`, `casual` |
| `captive` | bool | Include captive/cultivated observations |
| `endemic` | bool | Endemic species only |
| `native` | bool | Native species only |
| `introduced` | bool | Introduced species only |
| `threatened` | bool | Threatened species only |
| `geo` | bool | Has geospatial data |
| `lat`, `lng` | float | Coordinates for center point |
| `radius` | float | Search radius in meters |
| `swlat`, `swlng`, `nelat`, `nelng` | float | Bounding box |
| `created_on` | string | Created on date (YYYY-MM-DD) |
| `created_d1`, `created_d2` | string | Created date range |
| `observed_on` | string | Observed on date |
| `d1`, `d2` | string | Observed date range |
| `hrank`, `lrank` | string | Taxon rank filter (e.g. `species`, `genus`) |
| `id` | int | Return observation with this exact ID |
| `not_id` | int | Exclude observation with this ID |
| `id_above`, `id_below` | int | ID threshold |
| `term_id`, `term_value_id` | int | Annotation term/values |
| `photos` | bool | Has photos |
| `videos` | bool | Has videos |
| `sounds` | bool | Has sounds |
| `acc` | bool | Has accuracy information |
| `acc_below`, `acc_above` | float | Accuracy filters |
| `order` | string | `asc` or `desc` |
| `order_by` | string | `observed_on`, `created_at`, `species`, `votes` |
| `per_page` | int | Results per page (default: 30, max: 200) |
| `page` | int | Page number |

**Response:** Object with `total_results`, `page`, `per_page`, `results` array.

#### Species Counts for Observations
```
GET {INAT_BASE_URL}/observations/species_counts
```

Same filters as Search Observations, but returns species-level counts instead of
individual observations. Useful for answering "what species have been seen here?"

**Response:** Results array with `count`, `taxon` objects.

#### Observation by ID
```
GET {INAT_BASE_URL}/observations/{id}
```

Get a single observation by its integer ID.

#### Observation IDs (above threshold)
```
GET {INAT_BASE_URL}/observations/id_above
```

Returns only observation IDs matching filters with `id > id_above`.
Useful for incremental data sync — track the highest ID you've seen and
poll for new ones.

**Opt params:** `id_above`, `created_after`, `created_on`, `per_page`, plus
observation search filters.

#### Observation Comments
```
GET {INAT_BASE_URL}/observations/{id}/comments
```

#### Observation Identifications
```
GET {INAT_BASE_URL}/observations/{id}/identifications
```

#### Observation Subscriptions
```
GET {INAT_BASE_URL}/observations/{id}/subscriptions
```

#### Observation Updates
```
GET {INAT_BASE_URL}/observations/{id}/updates
```

### Taxa

iNaturalist's taxonomic classification system, aligned with Catalogue of Life.

#### Search Taxa
```
GET {INAT_BASE_URL}/taxa
```

**Key params:**
- `q` (string) — Text search query
- `taxon_id` (int) — Ancestor taxon to restrict results
- `is_active` (bool) — Currently accepted taxa only
- `rank` (string) — Exact rank (e.g. `species`, `genus`, `family`)
- `rank_level` (int) — Numeric rank threshold
- `iconic_taxa` (string) — Iconic taxon group
- `taxon_name` (string) — Name-based filter
- `exclude_ancestors`, `exclude_descendants` (bool)
- `locale` (string) — Language for common names
- `preferred_place_id` (int) — Region for preferred common name
- `per_page`, `page`

#### Taxa Autocomplete
```
GET {INAT_BASE_URL}/taxa/autocomplete?q={query}
```

Fast autocomplete for taxon names. **Key params:** `q`, `is_active`, `rank`,
`rank_level`, `iconic_taxa`, `locale`, `per_page` (default: 10).

#### Taxon by ID
```
GET {INAT_BASE_URL}/taxa/{id}
```

**Opt params:** `locale`, `preferred_place_id`

### Places

Geographic places (countries, states, counties, protected areas, etc.).

#### Search Places
```
GET {INAT_BASE_URL}/places?q={query}
```

**Opt params:** `place_type`, `with_geom`, `per_page`, `page`

Place types: 0=Undefined, 1=Country, 2=State, 3=County, 4=Continent,
5=Protected Area, 9=Landmark, 10=Open Space, 11=Neighborhood,
12=Postal Code, 13=National Forest, 100=Traditional Knowledge Area

#### Places Autocomplete
```
GET {INAT_BASE_URL}/places/autocomplete?q={query}
```

#### Place by ID
```
GET {INAT_BASE_URL}/places/{id}
```

#### Nearby Places
```
GET {INAT_BASE_URL}/places/nearby?lat={lat}&lng={lng}
```

**Opt params:** `place_type`, `with_geom`, `per_page`

### Projects

Community projects that group observations by theme, location, or taxon.

#### Search Projects
```
GET {INAT_BASE_URL}/projects
```

**Params:** `q`, `id`, `place_id`, `taxon_id`, `user_id`, `featured`,
`location`, `lat`, `lng`, `radius`, `order_by`, `order`, `per_page`, `page`

#### Project by ID
```
GET {INAT_BASE_URL}/projects/{id}
```

#### Project Members
```
GET {INAT_BASE_URL}/projects/{id}/members
```

#### Project Posts (Journal)
```
GET {INAT_BASE_URL}/projects/{id}/posts
```

#### Project Observations
```
GET {INAT_BASE_URL}/projects/{id}/observations
```

### Users

#### Authenticated User Profile
```
GET {INAT_BASE_URL}/users/me
```

Requires authentication.

#### User by ID
```
GET {INAT_BASE_URL}/users/{id}
```

#### User by Login
```
GET {INAT_BASE_URL}/users/{login}
```

#### User Autocomplete
```
GET {INAT_BASE_URL}/users/autocomplete?q={query}
```

### Identifications

Taxon identifications attached to observations.

#### Search Identifications
```
GET {INAT_BASE_URL}/identifications
```

**Params:** `user_id`, `user_login`, `current`, `category`, `taxon_id`,
`taxon_name`, `iconic_taxa`, `observation_id`, `own_observation`,
`created_after`, `created_on`, `per_page`, `page`

`category` values: `improving`, `supporting`, `leading`, `maverick`

#### Identification by ID
```
GET {INAT_BASE_URL}/identifications/{id}
```

#### Similar Species
```
GET {INAT_BASE_URL}/identifications/similar_species?observation_id={id}
```

Returns suggested identifications for an observation.

### Photos

#### Photo by ID
```
GET {INAT_BASE_URL}/photos/{id}
```

### Controlled Terms

Annotation fields (e.g. "Alive or Dead", "Sex", "Plant Phenology").

#### List Controlled Terms
```
GET {INAT_BASE_URL}/controlled_terms
```

Returns all available annotation terms and their values.

#### Controlled Terms for Taxon
```
GET {INAT_BASE_URL}/controlled_terms/for_taxon?taxon_id={id}
```

Returns only annotation terms applicable to a specific taxon.

### Computer Vision

#### Identify Species from Photo
```
POST {INAT_BASE_URL}/computervision/v2/identify
```

**Requires API token.** Accepts image file upload and returns scored taxon suggestions.

Also supports a GET variant:
```
GET {INAT_BASE_URL}/computervision/identify?photo_id={id}
```

---

## Example Agent Queries

### "What species were seen in Yosemite last week?"

```
curl -s "$INAT_BASE_URL/observations/species_counts?place_id=12345&d1=$(date -d '7 days ago' +%Y-%m-%d)&d2=$(date +%Y-%m-%d)&per_page=20" | jq '.results[] | {name: .taxon.name, common_name: .taxon.preferred_common_name, count: .count}'
```
(Yosemite place_id needs to be looked up first.)

### "What is the scientific name for a Red-tailed Hawk?"

```
curl -s "$INAT_BASE_URL/taxa/autocomplete?q=red-tailed+hawk&per_page=1" | jq '.results[0]'
```

### "What rare plants have been observed near my location?"

```
curl -s "$INAT_BASE_URL/observations?lat=37.7749&lng=-122.4194&radius=10000&iconic_taxa=Plantae&threatened=true&per_page=20"
```

### "Are there any iNaturalist projects about dragonflies in California?"

```
curl -s "$INAT_BASE_URL/projects?q=dragonfly&place_id=14&per_page=10" | jq '.results[] | {id, title, description}'
```
(Place ID 14 = California.)

### "What's the taxonomy of the Monarch Butterfly?"

```
curl -s "$INAT_BASE_URL/taxa?q=monarch+butterfly&rank=species" | jq '.results[0] | {name, rank, iconic_taxon_name, ancestors: [.ancestors[].name]}'
```

### "Show me research-grade observations of Western Bluebirds this year."

```
curl -s "$INAT_BASE_URL/observations?taxon_name=sialia+mexicana&quality_grade=research&d1=$(date +%Y)-01-01&d2=$(date +%Y-%m-%d)&per_page=10"
```

### "What conservation statuses does my local park have place data for?"

```
curl -s "$INAT_BASE_URL/places/nearby?lat=51.5074&lng=-0.1278"
```

---

## Response Data Format

### Observation Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Observation ID |
| `observed_on_string` | string | Human-readable observed date |
| `observed_on` | string | ISO date observed |
| `created_at` | string | ISO creation timestamp |
| `updated_at` | string | ISO last-updated timestamp |
| `quality_grade` | string | `research`, `needs_id`, `casual` |
| `time_observed_at` | string | ISO time observed |
| `time_zone_offset` | string | Timezone offset |
| `taxon` | object | Taxon object for the identification |
| `geojson` | object | GeoJSON point for coordinates |
| `geoprivacy` | string | `open`, `obscured`, `private` |
| `location_is_exact` | bool | Whether coordinates are exact |
| `photos` | array | Photo objects |
| `sounds` | array | Sound recording objects |
| `identifications` | array | Identification objects |
| `project_ids` | array | Associated project IDs |
| `place_ids` | array | Associated place IDs |
| `description` | string | Observation description text |
| `user` | object | Observer user object |
| `mappable` | bool | Has usable coordinates |
| `comments` | array | Comment objects |

### Taxon Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Taxon ID |
| `name` | string | Scientific name |
| `rank` | string | Rank (e.g. `species`, `genus`, `family`) |
| `rank_level` | int | Numeric rank level |
| `iconic_taxon_id` | int | Iconic taxon group ID |
| `iconic_taxon_name` | string | Iconic taxon group name (e.g. `Aves`) |
| `preferred_common_name` | string | Common name in requested locale |
| `ancestors` | array | Ancestor taxon objects |
| `children` | array | Child taxon objects (if applicable) |
| `is_active` | bool | Currently accepted |
| `conservation_statuses` | array | IUCN/regional statuses |
| `established_places` | array | Places where established |
| `matched_term` | string | Highlighted match |
| `wikipedia_url` | string | Wikipedia page URL |
| `wikipedia_summary` | string | Short Wikipedia summary |
| `image_url` | string | Default photo URL |

---

## Rank Levels Reference

| Rank | Level |
|------|-------|
| Kingdom | 70 |
| Phylum | 60 |
| Class | 50 |
| Order | 40 |
| Family | 30 |
| Genus | 20 |
| Species | 10 |
| Subspecies | 5 |

## Quality Grades

| Grade | Description |
|-------|-------------|
| `research` | Community ID > 66% agree, date + photo/sound, location not captive |
| `needs_id` | Needs more identifications to reach research grade |
| `casual` | Missing date/photo/location, or marked as captive/cultivated |

## Iconic Taxa

Common groups: `Animalia`, `Aves`, `Mammalia`, `Reptilia`, `Amphibia`,
`Actinopterygii`, `Insecta`, `Arachnida`, `Mollusca`, `Fungi`, `Plantae`,
`Protozoa`, `Chromista`

---

## Rate Limits

Without authentication: approximately **100 requests per minute** (per IP).
With OAuth token: approximately **500 requests per minute**.
Check response headers for `X-RateLimit-*`.
