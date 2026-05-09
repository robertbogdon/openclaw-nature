#!/usr/bin/env python3
"""
OpenClaw Nature — Location Builder

Generates canonical locations from session data. The core rule:

  **All observations in a single session are at the same location.**

Approach:
  1. Collect raw location names from eBird and iNat for each session
  2. Group sessions by grid cell (~1.1 km) — same-place visits
  3. Parse raw names for "named place" (park, reserve, pier, etc.)
  4. Reverse-geocode the centroid via Nominatim (OSM) for neighborhood,
     city, and state
  5. Merge into canonical display name following the pattern:
         [Named Place], [Neighborhood], City, ST
     Each component is optional.

Usage:
    python3 import/build_locations.py
    python3 import/build_locations.py --session-db import/openclaw-nature.db
    python3 import/build_locations.py --dry-run    # don't write DB

Stdlib only — no external dependencies (geocoding via urllib).
Geo queries use Nominatim (OpenStreetMap) — please be respectful of
their usage policy (1 req/sec, identify yourself).
"""

import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict, Counter

# ── Paths ────────────────────────────────────────────────────────────

IMPORT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SESSION_DB = os.path.join(IMPORT_DIR, "openclaw-nature.db")

# Grid cell size (~1.1 km at San Diego latitude)
# Grid cell size (~1.7 km at San Diego latitude — large enough to
# group sessions in the same neighborhood even when centroids fall near
# grid boundaries)
GRID_DEGREES = 0.017

# State name → 2-letter abbreviation (Nominatim returns full names)
_STATE_ABBREV = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN",
    "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
    "puerto rico": "PR",
}

# Nominatim user agent — identifies this app to OSM
_GEO_USER_AGENT = "OpenClaw-Nature/1.0 (https://github.com/robertbogdon/openclaw-nature)"


# ── Schema ────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS locations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name  TEXT NOT NULL,
    centroid_lat  REAL,
    centroid_lng  REAL,
    grid_lat      REAL,
    grid_lng      REAL,
    user_label    TEXT,
    user_notes    TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(display_name)
);

CREATE TABLE IF NOT EXISTS location_aliases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id   INTEGER REFERENCES locations(id),
    source        TEXT,
    alias         TEXT,
    frequency     INTEGER DEFAULT 1,
    UNIQUE(location_id, source, alias)
);

CREATE TABLE IF NOT EXISTS session_location_map (
    session_num   INTEGER PRIMARY KEY,
    location_id   INTEGER REFERENCES locations(id),
    FOREIGN KEY (session_num) REFERENCES sessions(session_num)
);

CREATE INDEX IF NOT EXISTS idx_loc_cell   ON locations(grid_lat, grid_lng);
CREATE INDEX IF NOT EXISTS idx_loc_alias  ON location_aliases(location_id);
CREATE INDEX IF NOT EXISTS idx_loc_sess   ON session_location_map(location_id);
"""


# ── Helpers ───────────────────────────────────────────────────────────


def grid_cell(lat, lng):
    return (
        round(lat / GRID_DEGREES) * GRID_DEGREES,
        round(lng / GRID_DEGREES) * GRID_DEGREES,
    )


# ── Raw Name Parsing ──────────────────────────────────────────────────

_PLACE_KEYWORDS = [
    r"reserve", r"preserve", r"wilderness",
    r"state park", r"national park", r"botanic", r"garden", r"arboretum",
    r"sanctuary", r"natural area", r"nature center", r"visitor center",
    r"interpretive",
    r"lake", r"reservoir", r"river", r"creek", r"canyon", r"beach",
    r"bay", r"ocean", r"harbor", r"marina",
    r"forest", r"woodland", r"desert", r"mountain", r"hill", r"valley",
    r"trail", r"summit", r"overlook", r"point",
    r"park", r"playground",
    r"pier", r"wharf", r"dock", r"dam", r"bridge", r"canal", r"lagoon",
    r"estuary", r"marsh", r"springs", r"falls?",
    r"pond", r"golf course", r"cemetery",
    r"school", r"college", r"university", r"campus",
    r"grove", r"oaks", r"pines", r"meadow", r"field", r"pasture",
    r"vineyard", r"ranch",
    r"transit center", r"station", r"stop", r"terminal",
]


def extract_place_from_raw(raw_name):
    """Try to extract a named place from a raw location string.

    Looks for parts that contain place keywords or street intersections.
    Returns the extracted place name or None.
    """
    if not raw_name:
        return None

    name = raw_name.strip()
    # Strip trailing noise
    name = re.sub(r",\s*US-CA(?:,\s*US)?$", "", name)
    name = re.sub(r",\s*USA$", "", name).strip()
    name = re.sub(r",\s*US$", "", name).strip()
    name = re.sub(r"\s+\d{5}$", "", name).strip()

    # Split on commas
    parts = [p.strip() for p in name.split(",")]

    for part in parts:
        lower = part.lower()

        # Skip grid refs
        if re.match(r"^[A-Z0-9]+\+[A-Z0-9]+\s*,?\s*$", part):
            continue
        # Skip county-only
        if re.search(r"^[a-z\s]+ county$", lower) and "county" in lower:
            continue

        # Street intersection
        if "&" in part or " and " in lower:
            return part

        # Has a place keyword
        if any(re.search(p, lower) for p in _PLACE_KEYWORDS):
            return part

        # Has a numeric address component
        if re.search(r"\d", part):
            return part

    return None


# ── Geocoding ─────────────────────────────────────────────────────────


def _nominatim_request(url):
    """Make a Nominatim API request with proper headers and rate limiting."""
    req = urllib.request.Request(url, headers={"User-Agent": _GEO_USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError) as e:
        print(f"    [geo] Request failed: {e}", file=sys.stderr)
        return None


_LAT_GEO_CALL = 0


def _abbrev_state(state_name):
    """Convert a full state name to 2-letter abbreviation, if needed."""
    if not state_name or len(state_name) == 2:
        return state_name
    return _STATE_ABBREV.get(state_name.lower().strip(), state_name)


def reverse_geocode(lat, lng):
    """Reverse-geocode coordinates via Nominatim.

    Returns dict with {neighborhood, city, state} or None on failure.
    Respects 1 req/sec rate limit.
    """
    global _LAT_GEO_CALL
    elapsed = time.time() - _LAT_GEO_CALL
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lng}&format=json&addressdetails=1"
    )
    data = _nominatim_request(url)
    _LAT_GEO_CALL = time.time()

    if not data or "address" not in data:
        return None

    addr = data["address"]

    # Neighborhood: quarter > suburb > neighbourhood
    neighborhood = (
        addr.get("quarter")
        or addr.get("suburb")
        or addr.get("neighbourhood")
    )
    # City: city or town
    city = addr.get("city") or addr.get("town") or addr.get("village")
    # State
    state = addr.get("state")

    return {
        "neighborhood": neighborhood,
        "city": city,
        "state": state,
    }


def search_osm_place(name, lat, lng):
    """Search for a named place on OSM to get structured address info.

    Returns the address dict or None.
    """
    global _LAT_GEO_CALL
    elapsed = time.time() - _LAT_GEO_CALL
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    import urllib.parse
    q = urllib.parse.quote(name)
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={q}&format=json&addressdetails=1&limit=3"
    )
    results = _nominatim_request(url)
    _LAT_GEO_CALL = time.time()

    if not results:
        return None

    # Pick the result closest to our centroid
    best = None
    best_dist = float("inf")
    for r in results:
        rlat = float(r.get("lat", 0))
        rlng = float(r.get("lon", 0))
        dist = (rlat - lat) ** 2 + (rlng - lng) ** 2
        if dist < best_dist:
            best_dist = dist
            best = r

    # Allow up to ~5 km for named-place searches.  A reserve or park
    # that the user visited may have its OSM centroid a bit offset from
    # the observation centroid.
    if best and best_dist < 0.045:  # ~5 km at San Diego latitude
        return best.get("address")
    return None


# ── Data Collection ───────────────────────────────────────────────────


def collect_session_location_data(session_db_path, ebird_db_path=None):
    """For each session, collect raw location names from all sources.

    Returns list of dicts:
        {session_num, centroid_lat, centroid_lng, grid_lat, grid_lng, raw_names}
    """
    if not os.path.exists(session_db_path):
        print(f"  Session DB not found: {session_db_path}", file=sys.stderr)
        return []

    conn = sqlite3.connect(session_db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )]
    if 'sessions' not in tables or 'session_observations' not in tables:
        conn.close()
        print("  Session tables not found in DB", file=sys.stderr)
        return []

    # Pre-load eBird location names by submission_id
    ebird_locs_by_sid = {}
    if ebird_db_path and os.path.exists(ebird_db_path):
        try:
            eb = sqlite3.connect(ebird_db_path)
            for row in eb.execute(
                "SELECT DISTINCT submission_id, location_name FROM observations"
            ):
                sid = row[0]
                loc = row[1]
                if loc:
                    if sid not in ebird_locs_by_sid:
                        ebird_locs_by_sid[sid] = []
                    ebird_locs_by_sid[sid].append(loc)
            eb.close()
        except Exception as e:
            print(f"  Warning: could not read eBird DB: {e}", file=sys.stderr)

    result = []
    sessions = conn.execute(
        "SELECT id, session_num, centroid_lat, centroid_lng FROM sessions "
        "ORDER BY session_num"
    ).fetchall()

    for s_id, s_num, s_lat, s_lng in sessions:
        glat, glng = grid_cell(s_lat, s_lng)

        raw_names = []

        for row in conn.execute(
            "SELECT obs_id FROM session_observations "
            "WHERE session_id = ? AND source = 'ebird' AND obs_id IS NOT NULL",
            (s_id,),
        ):
            sid = row[0]
            for loc_name in ebird_locs_by_sid.get(sid, []):
                raw_names.append(loc_name)

        for row in conn.execute(
            "SELECT details_json FROM session_observations "
            "WHERE session_id = ? AND source = 'inaturalist' AND details_json IS NOT NULL",
            (s_id,),
        ):
            try:
                details = json.loads(row[0])
                pg = details.get("place_guess")
                if pg:
                    raw_names.append(pg)
            except (json.JSONDecodeError, TypeError):
                pass

        result.append({
            "session_num": s_num,
            "centroid_lat": s_lat,
            "centroid_lng": s_lng,
            "grid_lat": glat,
            "grid_lng": glng,
            "raw_names": raw_names,
        })

    conn.close()
    return result


# ── Location Assembly ────────────────────────────────────────────────


def build_location_name(sessions, centroid_lat, centroid_lng):
    """Build a canonical location name for a group of sessions.

    Strategy:
      1. Extract a named place from raw names (if any)
      2. Reverse-geocode the centroid for neighborhood, city, state
      3. If no place found from raw names, try OSM search

    Returns display_name string.
    """
    all_raw_names = []
    for sd in sessions:
        all_raw_names.extend(sd["raw_names"])

    # --- Step 1: Find a named place from raw names ---
    places_seen = []
    for raw in all_raw_names:
        p = extract_place_from_raw(raw)
        if p:
            places_seen.append(p)

    place_counter = Counter(places_seen)
    # --- Step 1b: Reverse-geocode centroid FIRST (needed for place selection) ---
    geo = reverse_geocode(centroid_lat, centroid_lng)

    if places_seen:
        top_count = place_counter.most_common(1)[0][1]
        threshold = max(top_count * 0.7, 1)  # at least 1 vote ensures single-item lists work
        candidates = [
            (name, count) for name, count in place_counter.items()
            if count >= threshold
        ]
        # Sort: most votes first.  Among close counts, prefer a name
        # that doesn't match the neighborhood (more descriptive).
        # Also: if the top candidate is a generic geofeature (canyon, creek,
        # beach, etc.) and a more specific named feature (reserve, park,
        # pier, etc.) exists, prefer the specific one.
        hood = (geo or {}).get("neighborhood") or ""
        hood_lower = hood.lower().strip()

        # Generic geofeature suffixes — if a place name consists mainly of
        # one of these, it's a generic description rather than a destination.
        _GENERIC_GEO = {
            "canyon", "creek", "river", "beach", "bay", "lagoon",
            "marsh", "slough", "ocean", "valley", "hill", "point",
        }

        def is_generic(name):
            """Check if a place name is a generic geofeature (not a specific destination)."""
            lower = name.lower().strip()
            # Split on whitespace and check the last word
            words = lower.split()
            if words and words[-1] in _GENERIC_GEO:
                # But keep if it contains a more specific keyword
                for kw in {"park", "reserve", "preserve", "pier", "dam",
                           "marina", "garden", "museum", "bridge",
                           "station", "center", "sanctuary"}:
                    if kw in lower:
                        return False
                return True
            return False

        # Detect which names are generic vs specific
        specific_names = [n for n, _ in candidates if not is_generic(n)]
        generic_names = [n for n, _ in candidates if is_generic(n)]

        def adjusted_count(item):
            name, count = item
            # Penalize if matches neighborhood
            if hood_lower:
                name_lower = name.lower().strip()
                if name_lower == hood_lower:
                    count -= 3
            # Penalize generic names when a specific alternative exists
            if is_generic(name) and specific_names:
                count -= 100  # heavy penalty — prefer specific destinations
            return count
        candidates.sort(key=lambda x: (-adjusted_count(x), -len(x[0])))
        place = candidates[0][0]
    else:
        place = None

    # --- Step 3: Build components from reverse-geocoding ---
    components = {"place": place, "neighborhood": None, "city": None, "state": None}

    if geo:
        components["neighborhood"] = geo.get("neighborhood")
        components["city"] = geo.get("city")
        components["state"] = _abbrev_state(geo.get("state"))

    # --- Step 4a: City fallback from raw names ---
    # When reverse-geocoding returns no city (county-level only), or
    # returns a village/hamlet rather than a proper city, fall back to
    # the most common proper city mentioned in raw location names.
    # The part just before "CA" in raw strings is usually the city.
    def _is_geofeature(name):
        """Check if a name is a geographic feature (canyon, beach, etc.)
        rather than a city or town."""
        geowords = {"canyon", "creek", "beach", "bay", "pines", "grove",
                     "oaks", "valley", "hill", "springs", "point",
                     "meadow", "field", "forest", "lake", "lagoon",
                     "marsh", "mount", "mountain"}
        lower = name.lower()
        words = lower.split()
        if len(words) >= 1 and words[-1] in geowords:
            return True
        return False

    if not components.get("city") or "county" in (components.get("city") or "").lower():
        city_mentions = Counter()
        for raw in all_raw_names:
            parts = [p.strip() for p in raw.split(",")]
            for i, p in enumerate(parts):
                if re.match(r"CA(?:\s+\d{5})?$", p, re.IGNORECASE) or p == "US-CA" or p == "CA":
                    if i > 0:
                        candidate = parts[i-1].strip()
                        if candidate and not re.search(r"county", candidate, re.IGNORECASE):
                            # Weight: proper city-like names get 2, geofeature names get 1
                            weight = 1 if _is_geofeature(candidate) else 2
                            city_mentions[candidate] += weight
                    break
            # For international entries
            if "Baja California" in raw and "Tijuana" in raw:
                city_mentions["Tijuana"] += 2
        if city_mentions:
            best_city = city_mentions.most_common(1)[0][0]
            # Only override if it's not the same as the neighborhood
            if best_city.lower() != (components.get("neighborhood") or "").lower():
                components["city"] = best_city

    # --- Step 4b: Dedup — if place matches neighborhood, suppress neighborhood ---
    place_str = (components.get("place") or "").lower().strip()
    hood_str = (components.get("neighborhood") or "").lower().strip()
    if hood_str and place_str and hood_str in place_str:
        components["neighborhood"] = None

    # --- Step 5: Format display name ---
    parts = []
    if components.get("place"):
        parts.append(components["place"])
    if components.get("neighborhood") and components.get("neighborhood") != components.get("place"):
        parts.append(components["neighborhood"])
    if components.get("city"):
        parts.append(components["city"])
    if components.get("state"):
        parts.append(components["state"])

    return ", ".join(parts) if parts else f"Grid ({grid_cell(centroid_lat, centroid_lng)[0]:.2f}, {grid_cell(centroid_lat, centroid_lng)[1]:.2f})"


def group_sessions_into_locations(session_data_list):
    """Group sessions by grid cell and build canonical location names."""
    cell_groups = defaultdict(list)
    for sd in session_data_list:
        key = (sd["grid_lat"], sd["grid_lng"])
        cell_groups[key].append(sd)

    locations = []
    total = len(cell_groups)
    for idx, (cell_key, sessions) in enumerate(sorted(cell_groups.items()), 1):
        glat, glng = cell_key

        centroids_lat = [sd["centroid_lat"] for sd in sessions]
        centroids_lng = [sd["centroid_lng"] for sd in sessions]

        avg_lat = sum(centroids_lat) / len(centroids_lat)
        avg_lng = sum(centroids_lng) / len(centroids_lng)

        print(f"    [{idx}/{total}] Geocoding grid cell ({glat:.3f}, {glng:.3f})...", end=" ")
        sys.stdout.flush()
        display = build_location_name(sessions, avg_lat, avg_lng)
        print(f"\"{display}\"")

        # Collect aliases — all unique cleaned displays
        all_raw_names = []
        for sd in sessions:
            all_raw_names.extend(sd["raw_names"])
        seen = set()
        aliases = []
        for raw in all_raw_names:
            # Just strip noise for alias display
            cleaned = raw
            cleaned = re.sub(r",\s*US-CA(?:,\s*US)?$", "", cleaned)
            cleaned = re.sub(r",\s*USA$", "", cleaned).strip()
            cleaned = re.sub(r",\s*US$", "", cleaned).strip()
            cleaned = re.sub(r"\s+\d{5}$", "", cleaned).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                aliases.append(cleaned)

        locations.append({
            "display_name": display,
            "centroid_lat": round(avg_lat, 6),
            "centroid_lng": round(avg_lng, 6),
            "grid_lat": glat,
            "grid_lng": glng,
            "session_nums": sorted(sd["session_num"] for sd in sessions),
            "aliases": aliases,
        })

    return locations


# ── Database Writer ───────────────────────────────────────────────────


def write_locations_db(session_db_path, locations):
    """Write locations + maps using upsert to preserve user metadata."""
    conn = sqlite3.connect(session_db_path)
    conn.executescript(SCHEMA_SQL)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(locations)")}
    if "user_label" not in cols:
        conn.execute("ALTER TABLE locations ADD COLUMN user_label TEXT")
    if "user_notes" not in cols:
        conn.execute("ALTER TABLE locations ADD COLUMN user_notes TEXT")

    existing_meta = {}
    for row in conn.execute(
        "SELECT display_name, user_label, user_notes FROM locations "
        "WHERE user_label IS NOT NULL OR user_notes IS NOT NULL"
    ):
        existing_meta[row[0]] = {"user_label": row[1], "user_notes": row[2]}

    conn.execute("DELETE FROM session_location_map")
    conn.execute("DELETE FROM location_aliases")

    for loc in locations:
        meta = existing_meta.get(loc["display_name"], {})
        conn.execute(
            """INSERT INTO locations
               (display_name, centroid_lat, centroid_lng, grid_lat, grid_lng,
                user_label, user_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(display_name) DO UPDATE SET
                centroid_lat=excluded.centroid_lat,
                centroid_lng=excluded.centroid_lng,
                grid_lat=excluded.grid_lat,
                grid_lng=excluded.grid_lng,
                user_label=COALESCE(locations.user_label, excluded.user_label),
                user_notes=COALESCE(locations.user_notes, excluded.user_notes)""",
            (loc["display_name"], loc["centroid_lat"], loc["centroid_lng"],
             loc["grid_lat"], loc["grid_lng"],
             meta.get("user_label"), meta.get("user_notes")),
        )

        loc_id = conn.execute(
            "SELECT id FROM locations WHERE display_name = ?",
            (loc["display_name"],),
        ).fetchone()[0]

        for alias in loc["aliases"]:
            conn.execute(
                "INSERT INTO location_aliases (location_id, source, alias, frequency) "
                "VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (loc_id, "variant", alias, 1),
            )

        for snum in loc["session_nums"]:
            conn.execute(
                "INSERT INTO session_location_map (session_num, location_id) "
                "VALUES (?, ?) ON CONFLICT(session_num) DO UPDATE SET "
                "location_id=excluded.location_id",
                (snum, loc_id),
            )

    conn.commit()
    conn.close()


# ── Report ────────────────────────────────────────────────────────────


def print_report(locations, session_count):
    print(f"\n  ── Location Report ──")
    print(f"  Sessions:       {session_count}")
    print(f"  Locations:      {len(locations)}")
    print()

    for loc in locations:
        s_display = ", ".join(f"#{s}" for s in loc["session_nums"])
        print(f"  {loc['display_name']}")
        print(f"    Sessions: {s_display}  |  ({loc['centroid_lat']:.4f}, {loc['centroid_lng']:.4f})")
        if loc["aliases"]:
            print(f"    Known as:")
            for a in loc["aliases"][:4]:
                print(f"      \"{a}\"")
            if len(loc["aliases"]) > 4:
                print(f"      ... and {len(loc['aliases']) - 4} more")
        print()


# ── Main ────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build canonical locations from session data"
    )
    parser.add_argument("--session-db", default=None)
    parser.add_argument("--ebird-db", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session_db = args.session_db or DEFAULT_SESSION_DB

    ebird_db = args.ebird_db
    if not ebird_db:
        candidates = [
            os.path.expanduser("~/.openclaw/workspace/zookeeper/modules/ebird/ebird.db"),
            os.path.join(os.path.dirname(IMPORT_DIR), "..", "ebird", "ebird.db"),
        ]
        for c in candidates:
            if os.path.exists(c):
                ebird_db = c
                break

    print(
        f"OpenClaw Nature — Location Builder\n"
        f"====================================\n"
        f"  Session DB:  {session_db}\n"
        f"  eBird DB:    {ebird_db or '(not found)'}\n"
    )

    if not os.path.exists(session_db):
        print(f"  ERROR: Session database not found: {session_db}")
        sys.exit(1)

    print("  Reading session location data...")
    session_data = collect_session_location_data(session_db, ebird_db)
    print(f"    Found {len(session_data)} sessions")

    if not session_data:
        print("  No session data to process.")
        return

    print("  Grouping into canonical locations...")
    locations = group_sessions_into_locations(session_data)
    print(f"    {len(locations)} locations from {len(session_data)} sessions")

    print_report(locations, len(session_data))

    if args.dry_run:
        print("  Dry run — no data written.\n")
        return

    print("  Writing to database...")
    write_locations_db(session_db, locations)
    print(f"    Done. Tables: locations, location_aliases, session_location_map\n")


if __name__ == "__main__":
    main()
