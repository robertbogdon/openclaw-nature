# eBird — OpenClaw Skill
# v1.0.0

Agents should use this skill to interact with the **eBird API v2.0** for
bird observations, hotspots, taxonomy, and region data. eBird is a real-time,
online bird observation checklist program run by the Cornell Lab of Ornithology.

## Configuration

The following variables must be set in the agent's environment or config:

- `EBIRD_API_KEY` — eBird API token (get one at https://ebird.org/api/keygen)
- `EBIRD_BASE_URL` — defaults to `https://api.ebird.org/v2`

## Authentication

All endpoints require the `X-eBird-ApiToken` header set to `EBIRD_API_KEY`.

## Region Codes

eBird uses hierarchical region codes:
- **Country**: `US` (United States), `GB` (United Kingdom), `IN` (India), etc.
- **State/Province**: `US-CA` (California), `US-NY` (New York), `GB-ENG` (England)
- **County**: `US-CA-075` (San Francisco County)
- **Location**: Locality ID (from hotspot or location lookup)

## Species Codes

Species codes are eBird's internal identifiers (e.g. `ameavo` for American Avocet,
`mallar3` for Mallard). Not the same as 4-letter birding codes.

---

## API Endpoints

### Observations — Recent Data

#### Recent Observations in a Region
```
GET {EBIRD_BASE_URL}/data/obs/{regionCode}/recent
X-eBird-ApiToken: {EBIRD_API_KEY}
```

**Parameters:**
- `regionCode` (path, req) — Region code for the area of interest
- `back` (opt, int) — Number of days back to search (default: 14, max: 30)
- `maxResults` (opt, int) — Maximum results (default: 20, max: 10000)
- `includeProvisional` (opt, bool) — Include provisional observations
- `hotspot` (opt, bool) — Only observations from hotspots
- `sort` (opt, str) — `date` (default) or `species`
- `speciesCode` (opt, str) — Filter to a specific species

**Response:** Array of checklist observation objects.

#### Recent Notable Observations in a Region
```
GET {EBIRD_BASE_URL}/data/obs/{regionCode}/recent/notable
```

**Additional params:** `detail` (opt, str) — `simple` or `full`

Returns only observations flagged as notable (rarities, historically early/late, etc.).

#### Recent Observations of a Species in Region
```
GET {EBIRD_BASE_URL}/data/obs/{regionCode}/recent/{speciesCode}
```

Returns recent reports of a specific species in a region.

#### Recent Nearby Observations (Geographic)
```
GET {EBIRD_BASE_URL}/data/obs/geo/recent?lat={lat}&lng={lng}
```

**Parameters:**
- `lat`, `lng` (req) — Latitude and longitude in decimal degrees
- `dist` (opt, float) — Search radius in km (default: 25, max: 50)
- `back` (opt, int) — Days back (default: 14, max: 30)
- `maxResults` (opt, int) — Max results (default: 20, max: 10000)
- `includeProvisional` (opt, bool) — Include provisional observations
- `hotspot` (opt, bool) — Only hotspot observations
- `sort` (opt, str) — `date` or `species`

#### Recent Notable Nearby Observations
```
GET {EBIRD_BASE_URL}/data/obs/geo/recent/notable?lat={lat}&lng={lng}
```

**Additional params:** `detail` (opt, str) — `simple` or `full`

#### Recent Nearby Observations of a Species
```
GET {EBIRD_BASE_URL}/data/obs/geo/recent/{speciesCode}?lat={lat}&lng={lng}
```

#### Nearest Observations of a Species
```
GET {EBIRD_BASE_URL}/data/obs/geo/recent/{speciesCode}?lat={lat}&lng={lng}
```

Returns observations of a species sorted by distance from the given coordinates.

### Observations — Historic Data

#### Historic Observations in a Region
```
GET {EBIRD_BASE_URL}/data/obs/{regionCode}/historic/{y}/{m}/{d}
```

**Path params:** `y` (year, 4-digit), `m` (month 1-12), `d` (day 1-31)
**Opt params:** `maxResults`, `includeProvisional`, `hotspot`

#### Historic Nearby Observations
```
GET {EBIRD_BASE_URL}/data/obs/geo/historic/{y}/{m}/{d}?lat={lat}&lng={lng}
```

**Opt params:** `dist` (km), `maxResults`, `includeProvisional`

### Hotspots

#### List Hotspots in a Region
```
GET {EBIRD_BASE_URL}/ref/hotspot/{regionCode}
```

**Opt params:** `fmt` — response format

#### Nearby Hotspots
```
GET {EBIRD_BASE_URL}/ref/hotspot/geo?lat={lat}&lng={lng}
```

**Opt params:** `dist` (km), `back`, `maxResults`, `fmt`

#### Hotspot Details
```
GET {EBIRD_BASE_URL}/ref/hotspot/info/{locId}
```

**Opt params:** `fmt`

Get detailed information about a specific hotspot/location by its locId.

### Taxonomy

#### Taxonomy Versions
```
GET {EBIRD_BASE_URL}/ref/taxonomy/versions
```

Lists available eBird/Clements taxonomy versions with years and release dates.

#### Full Taxonomy
```
GET {EBIRD_BASE_URL}/ref/taxonomy/ebird
```

**Opt params:**
- `cat` (opt, str) — Species category filter (see table below)
- `locale` (opt, str) — Language locale (e.g. `en`, `fr`, `es`, `de`)
- `version` (opt, int) — Taxonomy version year
- `fmt` (opt, str) — Output format

#### Taxonomic Forms (Subspecies)
```
GET {EBIRD_BASE_URL}/ref/taxonomy/forms/{speciesCode}
```

**Opt params:** `locale`

Get subspecies/forms for a given species.

### Regions

#### Region Info
```
GET {EBIRD_BASE_URL}/ref/region/info/{regionType}/{regionCode}
```

`regionType` is one of: `country`, `subnational1`, `subnational2`

#### Adjacent Regions
```
GET {EBIRD_BASE_URL}/ref/region/adjacent/{regionType}/{regionCode}
```

Lists regions that border the given region.

#### Subregions
```
GET {EBIRD_BASE_URL}/ref/region/{regionType}/{regionCode}/subregions
```

Lists child regions. For `country/US` returns states; for `subnational1/US-CA` returns counties.

### My eBird (Checklist Data)

These endpoints retrieve data from specific checklist submissions.

#### Checklist Details
```
GET {EBIRD_BASE_URL}/product/checklist/{subId}
```

Get full checklist object by submission ID (found in observation data as `subId`).

#### Checklist Feed (Public View)
```
GET {EBIRD_BASE_URL}/product/checklist/view/{subId}
```

Get the public-facing view of a checklist.

#### Observations from a Checklist
```
GET {EBIRD_BASE_URL}/product/obs/{subId}
```

Get all observations from a specific checklist.

#### Checklist Stats
```
GET {EBIRD_BASE_URL}/product/stats/{subId}
```

Get statistics for a checklist.

#### Top 100
```
GET {EBIRD_BASE_URL}/product/top100/{regionCode}
```

**Opt params:** `date` (YYYY-MM-DD), `maxResults`

Top 100 birders (by species count) for a region on a specific date.

### Neotropical Birds

#### Neotropical Species Reference
```
GET {EBIRD_BASE_URL}/ref/nb/species/{speciesCode}
```

**Opt params:** `locale`

Get detailed species reference from the Neotropical Birds database.

---

## Example Agent Queries

### "What birds have been seen recently in Central Park?"

```
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/data/obs/L99381/recent?maxResults=10&back=7"
```
(Central Park's locId is L99381.)

### "Are there any rare birds near San Francisco right now?"

```
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/data/obs/geo/recent/notable?lat=37.7749&lng=-122.4194&dist=25&back=3&detail=full"
```

### "What birds were seen in California yesterday?"

```
Y=$(date -d yesterday +%Y)
M=$(date -d yesterday +%m)
D=$(date -d yesterday +%d)
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/data/obs/US-CA/historic/$Y/$M/$D?maxResults=50"
```

### "What hotspots are near my current location?"

```
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/ref/hotspot/geo?lat=51.5074&lng=-0.1278&dist=10"
```

### "Tell me about the taxonomy of the Bald Eagle."

```
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/ref/taxonomy/ebird?cat=species" | \
  jq '.[] | select(.speciesCode == "baleag")'
```

### "What states are in the US eBird region?"

```
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/ref/region/country/US/subregions"
```

### "Get my checklist info from a recent spotting."

```
curl -s -H "X-eBird-ApiToken: $EBIRD_API_KEY" \
  "$EBIRD_BASE_URL/product/stats/S123456789"
```

---

## Response Data Format

Observation responses are arrays of objects with these key fields:

| Field | Type | Description |
|-------|------|-------------|
| `speciesCode` | string | eBird species code |
| `comName` | string | Common name |
| `sciName` | string | Scientific name |
| `locId` | string | Location/hotspot ID |
| `locName` | string | Location name |
| `obsDt` | string | Observation date/time |
| `howMany` | int or null | Count (null if not provided) |
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

---

## Rate Limits

Free tier: approximately **50 requests per minute**.
Check current limits via response headers or at https://ebird.org/api/keygen.

---

## Region Types Reference

| Type | Code | Example |
|------|------|---------|
| Country | `country` | `US`, `GB`, `IN`, `AU` |
| State / Province | `subnational1` | `US-CA`, `GB-ENG`, `AU-NSW` |
| County | `subnational2` | `US-CA-075`, `GB-ENG-NRT` |
| Location | `locId` | `L99381` (Central Park) |

## Species Category Codes

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
