# iNaturalist Response Fields & Reference Tables

## Observation Response Object

Key fields on observation objects:

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

## Taxon Response Object

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

## Rank Levels

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

| Grade | Requirements |
|-------|--------------|
| `research` | Community ID >66% agree, date + photo/sound, location not captive |
| `needs_id` | Needs more identifications to reach research grade |
| `casual` | Missing date/photo/location, or marked captive/cultivated |

## Iconic Taxa Groups

Common groups used in `iconic_taxa` filters:
`Animalia`, `Aves`, `Mammalia`, `Reptilia`, `Amphibia`, `Actinopterygii`, `Insecta`, `Arachnida`, `Mollusca`, `Fungi`, `Plantae`, `Protozoa`, `Chromista`

## Rate Limits

Unauthenticated: ~100 req/min per IP. Authenticated (OAuth): ~500 req/min.
Check response headers for `X-RateLimit-*`.
