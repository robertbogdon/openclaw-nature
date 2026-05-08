# eBird API v2.0 — Full Endpoint Reference

All endpoints require the `x-api-key` header set to `$EBIRD_API_KEY`.
Base URL: `https://api.ebird.org/v2` (override via `$EBIRD_BASE_URL`).

Guards for every request:
```bash
if [ -z "$EBIRD_API_KEY" ]; then
  echo "ERROR: EBIRD_API_KEY not set"
  exit 1
fi
```

## Observations — Recent Data

### Recent Observations in a Region
```
GET /data/obs/{regionCode}/recent
```
**Params:** `back` (days, max 30), `maxResults` (max 10000), `includeProvisional`, `hotspot` (bool), `sort` (date|species), `speciesCode`

### Recent Notable Observations in a Region
```
GET /data/obs/{regionCode}/recent/notable
```
**Plus:** `detail` (simple|full)

### Recent Observations of a Species in Region
```
GET /data/obs/{regionCode}/recent/{speciesCode}
```

### Recent Nearby Observations (Geographic)
```
GET /data/obs/geo/recent?lat={lat}&lng={lng}
```
**Params:** `dist` (km, max 50), `back` (max 30), `maxResults` (max 10000), `includeProvisional`, `hotspot`, `sort`

### Recent Notable Nearby Observations
```
GET /data/obs/geo/recent/notable?lat={lat}&lng={lng}
```
**Plus:** `detail` (simple|full)

### Species Nearby (Distance-Sorted)
```
GET /data/obs/geo/recent/{speciesCode}?lat={lat}&lng={lng}
```
Returns observations of a specific species sorted by distance.

## Observations — Historic Data

### Historic Observations in a Region
```
GET /data/obs/{regionCode}/historic/{y}/{m}/{d}
```
**Path:** year (4-digit), month (1-12), day (1-31)
**Opt:** `maxResults`, `includeProvisional`, `hotspot`

### Historic Nearby Observations
```
GET /data/obs/geo/historic/{y}/{m}/{d}?lat={lat}&lng={lng}
```
**Opt:** `dist` (km), `maxResults`, `includeProvisional`

## Hotspots

### List Hotspots in Region
```
GET /ref/hotspot/{regionCode}
```
**Opt:** `fmt`

### Nearby Hotspots
```
GET /ref/hotspot/geo?lat={lat}&lng={lng}
```
**Opt:** `dist` (km), `back`, `maxResults`, `fmt`

### Hotspot Details
```
GET /ref/hotspot/info/{locId}
```
**Opt:** `fmt`

## Taxonomy

### List Taxonomy Versions
```
GET /ref/taxonomy/versions
```

### Full eBird Taxonomy
```
GET /ref/taxonomy/ebird
```
**Opt:** `cat` (species category), `locale` (language), `version` (year), `fmt`

### Taxonomic Forms (Subspecies)
```
GET /ref/taxonomy/forms/{speciesCode}
```
**Opt:** `locale`

## Regions

### Region Info
```
GET /ref/region/info/{regionType}/{regionCode}
```
`regionType`: `country`, `subnational1`, `subnational2`

### Adjacent Regions
```
GET /ref/region/adjacent/{regionType}/{regionCode}
```

### Subregions
```
GET /ref/region/{regionType}/{regionCode}/subregions
```
Lists child regions. e.g. `country/US` returns states.

## My eBird (Checklist Data)

### Checklist Details
```
GET /product/checklist/{subId}
```

### Checklist Feed (Public View)
```
GET /product/checklist/view/{subId}
```

### Observations from a Checklist
```
GET /product/obs/{subId}
```

### Checklist Stats
```
GET /product/stats/{subId}
```

### Top 100 Birders
```
GET /product/top100/{regionCode}
```
**Opt:** `date` (YYYY-MM-DD), `maxResults`

## Neotropical Birds

### Neotropical Species Reference
```
GET /ref/nb/species/{speciesCode}
```
**Opt:** `locale`

## Full Curl Examples

```bash
# Recent observations in California, last 7 days
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/data/obs/US-CA/recent?back=7&maxResults=20"

# Notable birds near London (50km radius, last 3 days)
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/data/obs/geo/recent/notable?lat=51.5&lng=-0.13&dist=50&back=3"

# Historic data for Central Park, March 15 2025
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/data/obs/L99381/historic/2025/3/15?maxResults=50"

# Look up Bald Eagle taxonomy
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/ref/taxonomy/ebird?cat=species" | \
  jq '.[] | select(.speciesCode == "baleag")'

# List US states
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/ref/region/country/US/subregions"

# Hotspot details
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/ref/hotspot/info/L99381"

# Checklist stats
curl -s -H "x-api-key: $EBIRD_API_KEY" \
  "https://api.ebird.org/v2/product/stats/{subId}"
```
