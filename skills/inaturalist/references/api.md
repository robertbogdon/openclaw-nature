# iNaturalist API v1 — Full Endpoint Reference

Base URL: `https://api.inaturalist.org/v1`
Auth: optional for GET (increases rate limits). Use `Authorization: Bearer {token}`.

## Observations

### Search Observations
```
GET /observations
```
**Key params:** `user_id`, `user_login` (or set via `INAT_USER_LOGIN` env), `project_id`, `place_id`, `taxon_id`, `taxon_name`, `iconic_taxa`, `quality_grade`, `captive`, `endemic`, `native`, `introduced`, `threatened`, `geo`, `lat`/`lng`, `radius` (m), `swlat`/`swlng`/`nelat`/`nelng` (bbox), `created_on`, `created_d1`/`created_d2`, `observed_on`, `d1`/`d2`, `hrank`/`lrank` (taxon rank), `id`, `not_id`, `id_above`/`id_below`, `term_id`/`term_value_id` (annotations), `photos`, `videos`, `sounds`, `acc`, `acc_below`/`acc_above`, `order` (asc|desc), `order_by` (observed_on|created_at|species|votes), `per_page` (max 200), `page`
**Response:** Object with `total_results`, `page`, `per_page`, `results` array.

> 💡 When `INAT_USER_LOGIN` is set via the skill config, use it as the default `user_login` for queries. Example: `curl -s "$INAT_BASE_URL/observations?user_login=$INAT_USER_LOGIN&per_page=50"` fetches the configured user's observations.

### Species Counts
```
GET /observations/species_counts
```
Same filters as Search Observations. Returns `count` + `taxon` objects.

### Observation by ID
```
GET /observations/{id}
```

### Observation IDs (above threshold)
```
GET /observations/id_above
```
**Opt:** `id_above`, `created_after`, `created_on`, `per_page`, plus observation search filters. Use for incremental sync.

### Observation Comments
```
GET /observations/{id}/comments
```

### Observation Identifications
```
GET /observations/{id}/identifications
```

### Observation Subscriptions
```
GET /observations/{id}/subscriptions
```

### Observation Updates
```
GET /observations/{id}/updates
```

## Taxa

### Search Taxa
```
GET /taxa
```
**Key params:** `q` (text search), `taxon_id` (ancestor), `is_active`, `rank` (exact, e.g. `species`), `rank_level` (numeric threshold), `iconic_taxa`, `taxon_name`, `exclude_ancestors`, `exclude_descendants`, `locale`, `preferred_place_id`, `per_page`, `page`

### Taxa Autocomplete
```
GET /taxa/autocomplete?q={query}
```
**Plus:** `is_active`, `rank`, `rank_level`, `iconic_taxa`, `locale`, `per_page` (default 10)

### Taxon by ID
```
GET /taxa/{id}
```
**Opt:** `locale`, `preferred_place_id`

## Places

### Search Places
```
GET /places?q={query}
```
**Opt:** `place_type` (see table below), `with_geom`, `per_page`, `page`

### Places Autocomplete
```
GET /places/autocomplete?q={query}
```

### Place by ID
```
GET /places/{id}
```

### Nearby Places
```
GET /places/nearby?lat={lat}&lng={lng}
```
**Opt:** `place_type`, `with_geom`, `per_page`

**Place types:** 0=Undefined, 1=Country, 2=State, 3=County, 4=Continent, 5=Protected Area, 9=Landmark, 10=Open Space, 11=Neighborhood, 12=Postal Code, 13=National Forest, 100=Traditional Knowledge Area

## Projects

### Search Projects
```
GET /projects
```
**Params:** `q`, `id`, `place_id`, `taxon_id`, `user_id`, `featured`, `location`, `lat`/`lng`, `radius`, `order_by`, `order`, `per_page`, `page`

### Project by ID
```
GET /projects/{id}
```

### Project Members
```
GET /projects/{id}/members
```

### Project Posts (Journal)
```
GET /projects/{id}/posts
```

### Project Observations
```
GET /projects/{id}/observations
```

## Users

### Authenticated User
```
GET /users/me
```
Requires auth token.

### User by ID
```
GET /users/{id}
```

### User by Login
```
GET /users/{login}
```

### User Autocomplete
```
GET /users/autocomplete?q={query}
```

## Identifications

### Search Identifications
```
GET /identifications
```
**Params:** `user_id`, `user_login`, `current`, `category` (improving|supporting|leading|maverick), `taxon_id`, `taxon_name`, `iconic_taxa`, `observation_id`, `own_observation`, `created_after`, `created_on`, `per_page`, `page`

### Identification by ID
```
GET /identifications/{id}
```

### Similar Species
```
GET /identifications/similar_species?observation_id={id}
```
Returns suggested identifications for an observation.

## Photos

### Photo by ID
```
GET /photos/{id}
```

## Controlled Terms (Annotations)

### List All Terms
```
GET /controlled_terms
```
Returns all available annotation terms and their values.

### Terms for Taxon
```
GET /controlled_terms/for_taxon?taxon_id={id}
```
Returns only annotation terms applicable to a specific taxon.

## Computer Vision

### Identify from Photo (POST)
```
POST /computervision/v2/identify
```
Requires API token. Accepts image file upload, returns scored taxon suggestions.

### Identify by Photo ID (GET)
```
GET /computervision/identify?photo_id={id}
```

## Full Curl Examples

```bash
# Western Bluebird observations this year
curl -s "$INAT_BASE_URL/observations?taxon_name=sialia+mexicana&quality_grade=research&d1=$(date +%Y)-01-01&d2=$(date +%Y-%m-%d)&per_page=10"

# Species counts near San Francisco last week
curl -s "$INAT_BASE_URL/observations/species_counts?lat=37.7749&lng=-122.4194&radius=5000&d1=$(date -d '7 days ago' +%Y-%m-%d)&d2=$(date +%Y-%m-%d)&per_page=20"

# Monarch Butterfly taxonomy
curl -s "$INAT_BASE_URL/taxa?q=monarch+butterfly&rank=species" | jq '.results[0] | {name, rank, iconic_taxon_name, ancestors: [.ancestors[].name]}'

# Dragonfly projects in California (place_id 14 = CA)
curl -s "$INAT_BASE_URL/projects?q=dragonfly&place_id=14&per_page=10" | jq '.results[] | {id, title, description}'

# Threatened plants near coordinates
curl -s "$INAT_BASE_URL/observations?lat=37.7749&lng=-122.4194&radius=10000&iconic_taxa=Plantae&threatened=true&per_page=20"

# Places near London
curl -s "$INAT_BASE_URL/places/nearby?lat=51.5074&lng=-0.1278"

# Available annotation terms
curl -s "$INAT_BASE_URL/controlled_terms" | jq '.results[] | {term: .label, values: [.values[].label]}'
```
