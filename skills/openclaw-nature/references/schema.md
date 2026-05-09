# Session Schema Reference

## sessions Table (`sessions.db`)

The `sessions` table stores one row per session (outing).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key, auto-increment |
| `session_num` | INTEGER | 1-based session number in the current build |
| `start_utc` | TEXT | ISO 8601 UTC datetime of first observation |
| `end_utc` | TEXT | ISO 8601 UTC datetime of last observation |
| `duration_seconds` | REAL | Duration in seconds (end - start) |
| `centroid_lat` | REAL | Average latitude of all observations |
| `centroid_lng` | REAL | Average longitude of all observations |
| `location_summary` | TEXT | Semicolon-separated location names (up to 3) |
| `num_obs` | INTEGER | Total observations in session |
| `ebird_count` | INTEGER | Number of eBird observations |
| `inat_count` | INTEGER | Number of iNaturalist observations |
| `species_count` | INTEGER | Number of unique species |
| `species_list` | TEXT | Comma-separated list of all species |

## session_observations Table (`sessions.db`)

Links each observation to its parent session.

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | INTEGER | Foreign key to `sessions.id` |
| `source` | TEXT | `'ebird'` or `'inaturalist'` |
| `obs_id` | TEXT | Observation ID (submission_id for eBird, id for iNat) |
| `species` | TEXT | Common name (eBird) or scientific name (iNat) |
| `lat` | REAL | Latitude |
| `lng` | REAL | Longitude |
| `utc_time` | TEXT | ISO 8601 UTC datetime of this observation |
| `location_name` | TEXT | Human-readable location |

## metadata Table (`sessions.db`)

Build metadata.

| Key | Value |
|-----|-------|
| `built_at` | ISO 8601 build timestamp |
| `num_sessions` | Total sessions built |
| `dist_km` | Distance threshold used |
| `time_min` | Time threshold used |

## CSV Output Schema

The CSV export (`--csv`) contains one row per session:

| Column | Description |
|--------|-------------|
| `session_num` | 1-based session number |
| `start_local` | Start time in configured local timezone |
| `end_local` | End time in configured local timezone |
| `duration` | ISO 8601 duration string |
| `location` | Human-readable location summary |
| `centroid_lat` | Average latitude |
| `centroid_lng` | Average longitude |
| `num_obs` | Total observations |
| `ebird_count` | eBird observations count |
| `inat_count` | iNaturalist observations count |
| `species_count` | Unique species in session |
| `species_list` | Comma-separated species names |
