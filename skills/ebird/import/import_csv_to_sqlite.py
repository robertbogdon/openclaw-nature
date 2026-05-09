#!/usr/bin/env python3
"""Import MyEBirdData.csv into a SQLite database."""

import csv
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "ebird.db")
CSV_PATH = os.path.join(
    os.path.dirname(__file__),  # try modules/ebird/ first
    "..", "..", "legacy", "ebird", "MyEBirdData.csv"
)
# Also try absolute fallback
FALLBACK_CSV = "/home/openclaw/.openclaw/workspace/zookeeper/legacy/ebird/MyEBirdData.csv"


def resolve_csv():
    for p in [CSV_PATH, FALLBACK_CSV]:
        absp = os.path.abspath(p)
        if os.path.exists(absp):
            return absp
    raise FileNotFoundError(
        f"Could not find MyEBirdData.csv. Tried:\n"
        f"  {os.path.abspath(CSV_PATH)}\n"
        f"  {FALLBACK_CSV}"
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    submission_id    TEXT PRIMARY KEY,
    common_name      TEXT NOT NULL,
    scientific_name  TEXT NOT NULL,
    taxonomic_order  INTEGER,
    count_or_x       TEXT,
    state_province   TEXT,
    county           TEXT,
    location_id      TEXT,
    location_name    TEXT,
    latitude         REAL,
    longitude        REAL,
    obs_date         TEXT,
    obs_time         TEXT,
    protocol         TEXT,
    duration_min     INTEGER,
    all_obs_reported INTEGER,
    distance_km      REAL,
    area_ha          REAL,
    num_observers    INTEGER,
    breeding_code    TEXT,
    observation_details TEXT,
    checklist_comments  TEXT,
    ml_catalog_numbers  TEXT
);

CREATE INDEX IF NOT EXISTS idx_obs_date ON observations(obs_date);
CREATE INDEX IF NOT EXISTS idx_sci_name ON observations(scientific_name);
CREATE INDEX IF NOT EXISTS idx_common   ON observations(common_name);
CREATE INDEX IF NOT EXISTS idx_location  ON observations(location_id);
CREATE INDEX IF NOT EXISTS idx_submission ON observations(submission_id);

-- Track import metadata
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def safe(v):
    """Return stripped string or None."""
    if v is None:
        return None
    s = v.strip()
    return s if s else None


def parse_int(v):
    v = safe(v)
    if v is None or v == "X":
        return None
    try:
        return int(v)
    except ValueError:
        return None


def parse_float(v):
    v = safe(v)
    if v is None or v == "X":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def main():
    csv_path = resolve_csv()
    print(f"Reading: {csv_path}")

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"CSV rows: {len(rows)}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)

    inserted = 0
    skipped = 0

    for row in rows:
        sid = row.get("Submission ID", "").strip()
        if not sid:
            skipped += 1
            continue

        try:
            conn.execute(
                """INSERT OR REPLACE INTO observations VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )""",
                (
                    sid,
                    safe(row.get("Common Name")),
                    safe(row.get("Scientific Name")),
                    parse_int(row.get("Taxonomic Order")),
                    safe(row.get("Count")),
                    safe(row.get("State/Province")),
                    safe(row.get("County")),
                    safe(row.get("Location ID")),
                    safe(row.get("Location")),
                    parse_float(row.get("Latitude")),
                    parse_float(row.get("Longitude")),
                    safe(row.get("Date")),
                    safe(row.get("Time")),
                    safe(row.get("Protocol")),
                    parse_int(row.get("Duration (Min)")),
                    parse_int(row.get("All Obs Reported")),
                    parse_float(row.get("Distance Traveled (km)")),
                    parse_float(row.get("Area Covered (ha)")),
                    parse_int(row.get("Number of Observers")),
                    safe(row.get("Breeding Code")),
                    safe(row.get("Observation Details")),
                    safe(row.get("Checklist Comments")),
                    safe(row.get("ML Catalog Numbers")),
                ),
            )
            inserted += 1
        except Exception as e:
            print(f"  Error on row {sid}: {e}")
            skipped += 1

    # metadata
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("source_file", os.path.basename(csv_path)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("imported_at", __import__("datetime").datetime.utcnow().isoformat()),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("record_count", str(inserted)),
    )
    conn.commit()

    # quick stats
    species_count = conn.execute(
        "SELECT COUNT(DISTINCT scientific_name) FROM observations"
    ).fetchone()[0]
    date_range = conn.execute(
        "SELECT MIN(obs_date), MAX(obs_date) FROM observations"
    ).fetchone()
    checklist_count = conn.execute(
        "SELECT COUNT(DISTINCT submission_id) FROM observations"
    ).fetchone()[0]

    conn.close()

    print(f"\nImported: {inserted} observations")
    print(f"Skipped:  {skipped}")
    print(f"DB path:  {os.path.abspath(DB_PATH)}")
    print(f"Species:  {species_count}")
    print(f"Date range: {date_range[0]} to {date_range[1]}")
    print(f"Checklists: {checklist_count}")


if __name__ == "__main__":
    main()
