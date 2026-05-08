# eBird Response Fields & Reference Tables

## Observation Response Object

Observation endpoints return arrays of objects with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `speciesCode` | string | eBird species code |
| `comName` | string | Common name |
| `sciName` | string | Scientific name |
| `locId` | string | Location/hotspot ID |
| `locName` | string | Location name |
| `obsDt` | string | Observation date/time |
| `howMany` | int\|null | Count (null if not provided) |
| `lat` | float | Latitude |
| `lng` | float | Longitude |
| `obsValid` | bool | Whether observation is valid |
| `obsReviewed` | bool | Whether reviewed by moderator |
| `locationPrivate` | bool | Whether location is private |
| `subId` | string | Checklist submission ID |
| `subnational1Code` | string | State/province code |
| `subnational2Code` | string | County code |
| `countryCode` | string | Country code |
| `countryName` | string | Country name |
| `hasRichMedia` | bool | Has photos/sounds/recordings |
| `evidence` | string | Evidence type (`photo`, `audio`, `video`) |
| `firstName` | string | Observer's first name |
| `lastName` | string | Observer's last name |
| `obsId` | string | Observation ID |
| `exoticCategory` | string | Exotic status category |

## Region Types

| Type | Code | Example |
|------|------|---------|
| Country | `country` | `US`, `GB`, `IN`, `AU` |
| State / Province | `subnational1` | `US-CA`, `GB-ENG`, `AU-NSW` |
| County | `subnational2` | `US-CA-075`, `GB-ENG-NRT` |
| Location | `locId` | `L99381` (Central Park) |

## Species Category Codes (for `cat` param)

| Code | Meaning |
|------|---------|
| `species` | Full species |
| `hybrid` | Hybrid between two species |
| `variant` | Variant or domestic type |
| `spuh` | Genus-level identification |
| `slash` | Two-species uncertainty |
| `domestic` | Domestic animal |
| `issf` | Identified to subspecies/form |
| `intergrade` | Intergrade between subspecies |
| `form` | Named form/subspecies |

## Rate Limits

Free tier: approximately **50 requests per minute**.
Check current limits via response headers or at https://ebird.org/api/keygen.
