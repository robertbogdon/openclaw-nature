#!/usr/bin/env python3
"""Fetch observations from iNaturalist API into a local SQLite database.

Usage:
    python3 import/inat_to_sqlite.py                     # all observations
    python3 import/inat_to_sqlite.py --id-above 1000000  # incremental sync

Config:
    Uses INAT_USER_LOGIN env var. Falls back to the value set in
    skills.entries.inaturalist.env if available.
"""

import csv
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "inat.db")
USER_LOGIN = os.environ.get("INAT_USER_LOGIN")
if not USER_LOGIN:
    print("ERROR: INAT_USER_LOGIN is not set. Configure it via skills.entries.inaturalist.env.INAT_USER_LOGIN")
    sys.exit(1)
BASE_URL = os.environ.get("INAT_BASE_URL", "https://api.inaturalist.org/v1")
PER_PAGE = 200  # max per the API

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id                      INTEGER PRIMARY KEY,
    uuid                    TEXT,
    quality_grade           TEXT,
    observed_on             TEXT,
    time_observed_at        TEXT,
    created_at              TEXT,
    updated_at              TEXT,
    species_guess           TEXT,
    description             TEXT,
    place_guess             TEXT,
    latitude                REAL,
    longitude               REAL,
    positional_accuracy     INTEGER,
    captive                 INTEGER,
    obscured                INTEGER,
    geoprivacy              TEXT,
    license_code            TEXT,
    uri                     TEXT,
    place_ids               TEXT,
    user_id                 INTEGER,
    user_login              TEXT,
    taxon_id                INTEGER,
    taxon_name              TEXT,
    taxon_rank              TEXT,
    taxon_preferred_common_name TEXT,
    taxon_iconic_taxon_name TEXT,
    community_taxon_id      INTEGER,
    identifications_count   INTEGER,
    comments_count          INTEGER,
    faves_count             INTEGER,
    cached_votes_total      INTEGER,
    tags                    TEXT,
    annotations             TEXT,
    photos_json             TEXT,
    identifications_json    TEXT
);

CREATE INDEX IF NOT EXISTS idx_inat_obs_date   ON observations(observed_on);
CREATE INDEX IF NOT EXISTS idx_inat_taxon_id   ON observations(taxon_id);
CREATE INDEX IF NOT EXISTS idx_inat_user_id    ON observations(user_id);
CREATE INDEX IF NOT EXISTS idx_inat_created_at ON observations(created_at);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def api_get(path, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def safe(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def extract_id_above(db):
    """Return the max observation id we already have."""
    row = db.execute("SELECT MAX(id) FROM observations").fetchone()
    return row[0] if row[0] else 0


def build_params(id_above=None):
    params = {"user_login": USER_LOGIN, "per_page": PER_PAGE, "order": "asc"}
    if id_above:
        params["id_above"] = id_above
    return params


def fetch_all_observations(id_above=None):
    """Fetch all observation pages, return flat list of dicts."""
    params = build_params(id_above)
    all_obs = []
    page = 1

    while True:
        params["page"] = page
        print(f"  Fetching page {page}...", end="", flush=True)
        data = api_get("/observations", params)
        results = data.get("results", [])
        total = data.get("total_results", len(results))
        print(f" got {len(results)} obs (total: {total})", flush=True)

        if not results:
            break

        all_obs.extend(results)
        page += 1
        time.sleep(0.5)  # be polite

    return all_obs


def flatten_obs(o):
    """Flatten a nested observation dict into a flat tuple matching the schema."""
    loc = o.get("location") or ""

    taxon = o.get("taxon") or {}

    return (
        safe_int(o.get("id")),
        safe(o.get("uuid")),
        safe(o.get("quality_grade")),
        safe(o.get("observed_on")),
        safe(o.get("time_observed_at")),
        safe(o.get("created_at")),
        safe(o.get("updated_at")),
        safe(o.get("species_guess")),
        safe(o.get("description")),
        safe(o.get("place_guess")),
        safe_float(loc.split(",")[0].strip()) if "," in loc else None,
        safe_float(loc.split(",")[1].strip()) if "," in loc else None,
        safe_int(o.get("positional_accuracy")),
        1 if o.get("captive") else 0,
        1 if o.get("obscured") else 0,
        safe(o.get("geoprivacy")),
        safe(o.get("license_code")),
        safe(o.get("uri")),
        json.dumps(o.get("place_ids", [])) if o.get("place_ids") else None,
        safe_int(o.get("user", {}).get("id")),
        safe(o.get("user", {}).get("login")),
        safe_int(taxon.get("id")),
        safe(taxon.get("name")),
        safe(taxon.get("rank")),
        safe(taxon.get("preferred_common_name")),
        safe(taxon.get("iconic_taxon_name")),
        safe_int(o.get("community_taxon_id")),
        safe_int(o.get("identifications_count")),
        safe_int(o.get("comments_count")),
        safe_int(o.get("faves_count")),
        safe_int(o.get("cached_votes_total")),
        json.dumps(o.get("tags", [])) if o.get("tags") else None,
        json.dumps(o.get("annotations", [])) if o.get("annotations") else None,
        json.dumps(o.get("photos", [])) if o.get("photos") else None,
        json.dumps(o.get("identifications", [])) if o.get("identifications") else None,
    )


OBS_COLS = [
    "id", "uuid", "quality_grade", "observed_on", "time_observed_at",
    "created_at", "updated_at", "species_guess", "description", "place_guess",
    "latitude", "longitude", "positional_accuracy", "captive", "obscured",
    "geoprivacy", "license_code", "uri", "place_ids",
    "user_id", "user_login",
    "taxon_id", "taxon_name", "taxon_rank", "taxon_preferred_common_name",
    "taxon_iconic_taxon_name",
    "community_taxon_id", "identifications_count", "comments_count",
    "faves_count", "cached_votes_total",
    "tags", "annotations", "photos_json", "identifications_json",
]

INSERT_SQL = (
    "INSERT OR REPLACE INTO observations ({}) VALUES ({})"
).format(
    ", ".join(OBS_COLS),
    ", ".join("?" for _ in OBS_COLS),
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Import iNaturalist observations to SQLite")
    parser.add_argument("--user-login", help=f"iNaturalist username (default: {USER_LOGIN})")
    parser.add_argument("--id-above", type=int, help="Only fetch observations with id > this value (incremental sync)")
    parser.add_argument("--no-prompt", action="store_true", help="Don't prompt before importing")
    args = parser.parse_args()

    user = args.user_login or USER_LOGIN
    id_above = args.id_above or 0

    print(f"iNaturalist → SQLite Importer")
    print(f"  User:       {user}")
    print(f"  DB path:    {os.path.abspath(DB_PATH)}")
    print(f"  API base:   {BASE_URL}")
    print(f"  Incremental: {'yes, starting from id=' + str(id_above) if id_above else 'no (full fetch)'}")
    print()

    # quick count check
    try:
        count = api_get("/observations", {"user_login": user, "per_page": 1})
        total = count.get("total_results", 0)
        print(f"  Total observations for {user}: {total}")
        print()
    except Exception as e:
        print(f"  WARNING: Could not check total count: {e}", flush=True)

    if not args.no_prompt:
        inp = input("  Proceed with import? [Y/n]: ").strip().lower()
        if inp and inp not in ("y", "yes", ""):
            print("Aborted.")
            sys.exit(0)

    print()
    print("Fetching observations...")
    obs = fetch_all_observations(id_above if id_above > 0 else None)

    if not obs:
        print("No new observations to import.")
        sys.exit(0)

    print(f"\nFetched {len(obs)} observations in total.")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    inserted = 0
    skipped = 0

    for o in obs:
        oid = o.get("id")
        if not oid:
            skipped += 1
            continue
        try:
            conn.execute(INSERT_SQL, flatten_obs(o))
            inserted += 1
        except Exception as e:
            print(f"  Error on obs {oid}: {e}")
            skipped += 1

    # metadata
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", ("source", "inaturalist_api"))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", ("imported_at", now))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", ("user_login", user))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", ("record_count", str(inserted)))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", ("max_id", str(max(o.get("id") for o in obs))))
    conn.commit()

    # stats
    species_count = conn.execute(
        "SELECT COUNT(DISTINCT taxon_name) FROM observations WHERE taxon_name IS NOT NULL"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(observed_on), MAX(observed_on) FROM observations"
    ).fetchone()
    total_db = conn.execute(
        "SELECT COUNT(*) FROM observations"
    ).fetchone()[0]

    conn.close()

    print(f"\n✓ Imported: {inserted} observations")
    print(f"  Skipped:  {skipped}")
    print(f"  DB total: {total_db}")
    print(f"  Species:  {species_count}")
    print(f"  Date range: {date_range[0]} to {date_range[1]}")
    print(f"  DB path:  {os.path.abspath(DB_PATH)}")
    print(f"\nIncremental hint: next run with --id-above {max(o.get('id') for o in obs)}")


if __name__ == "__main__":
    main()
