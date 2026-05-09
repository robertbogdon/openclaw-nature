#!/usr/bin/env python3
"""
OpenClaw Nature — Session Builder

Groups eBird and iNaturalist observations into unified "sessions"
(outings at the same place and time).

Algorithm:
1. Collect all observations from both sources within a date range
2. Normalize timestamps to UTC datetime objects
3. Sort by UTC timestamp
4. Iterate through sorted observations, applying proximity grouping:
   - Same session if within DISTANCE_THRESHOLD (default 1 km) of last obs
     AND within TIME_THRESHOLD (default 120 min) of previous obs time
   - Otherwise, start a new session
5. Print a session report and optionally write to sessions.db

Usage:
    python3 import/build_sessions.py
    python3 import/build_sessions.py --start-date 2026-05-04 --end-date 2026-05-08
    python3 import/build_sessions.py --dist 2.0 --time 180 --tz America/New_York
    python3 import/build_sessions.py --ebird-db ../ebird/import/ebird.db
    python3 import/build_sessions.py --no-output   # only print report, don't write DB

Stdlib only — no external dependencies.
"""

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, date, time, timedelta, timezone

# ── Defaults ───────────────────────────────────────────────────────────

DEFAULT_EBIRD_DB = os.path.join(
    os.path.dirname(__file__), "..", "ebird", "import", "ebird.db"
)
DEFAULT_INAT_DB = os.path.join(
    os.path.dirname(__file__), "..", "inaturalist", "import", "inat.db"
)
DEFAULT_SESSION_DB = os.path.join(os.path.dirname(__file__), "sessions.db")

FALLBACK_EBIRD_DB = "/home/openclaw/.openclaw/workspace/zookeeper/modules/ebird/ebird.db"
FALLBACK_INAT_DB = "/home/openclaw/.openclaw/workspace/skills/inaturalist/import/inat.db"

DISTANCE_THRESHOLD_KM = 1.0
TIME_THRESHOLD_MINUTES = 120
OUTPUT_TIMEZONE = "America/Los_Angeles"  # for display

# ── Haversine ──────────────────────────────────────────────────────────


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lng points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ── Timezone helpers ───────────────────────────────────────────────────

# Simple UTC offset parsing for ISO 8601 strings with explicit offsets
# We don't use pytz/zoneinfo - just parse offsets manually for the Pacific TZ


def _parse_offset(offset_str):
    """Parse a timezone offset string like '-07:00' or '+00:00' or 'Z'
    into a timedelta."""
    if offset_str == "Z" or offset_str == "z":
        return timedelta(0)
    sign = 1
    s = offset_str
    if s.startswith("+"):
        sign = 1
        s = s[1:]
    elif s.startswith("-"):
        sign = -1
        s = s[1:]
    parts = s.split(":")
    hours = int(parts[0]) if parts else 0
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return sign * timedelta(hours=hours, minutes=minutes)


def parse_inat_timestamp(ts_str):
    """Parse iNaturalist ISO 8601 timestamp with offset to UTC datetime.

    Handles formats:
        '2025-06-15T14:30:00-07:00'
        '2025-06-15T14:30:00Z'
        '2025-06-15T14:30:00+00:00'
    """
    if not ts_str:
        return None
    # Normalize 'Z' suffix
    ts_str = ts_str.strip()
    if ts_str.endswith("Z") or ts_str.endswith("z"):
        ts_str = ts_str[:-1] + "+00:00"

    # Split date/time part from offset
    if "+" in ts_str[10:]:
        dt_str, offset_str = ts_str.rsplit("+", 1)
        offset_str = "+" + offset_str
    elif "-" in ts_str[10:]:
        # Find the rightmost '-' after the time part that is the offset
        # e.g. "2025-06-15T14:30:00-07:00" - the T splits date from time
        # Find the '-' or '+' that starts the timezone offset
        # ISO 8601: after time part, the offset starts with + or -
        # Walk backwards from the end to find the offset separator
        parts = ts_str.rsplit("-", 2)
        if len(parts) == 3:
            dt_str = parts[0]
            offset_str = "-" + parts[1] + "-" + parts[2]
        else:
            # No timezone info — treat as UTC
            dt_str = ts_str
            offset_str = "+00:00"
    else:
        dt_str = ts_str
        offset_str = "+00:00"

    try:
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        return None

    offset = _parse_offset(offset_str)
    # Make offset-aware and convert to UTC
    dt_with_offset = dt.replace(tzinfo=timezone.utc) - offset
    # Return naive UTC
    return dt_with_offset.replace(tzinfo=None)


def parse_ebird_timestamp(obs_date, obs_time, local_tz_name="America/Los_Angeles"):
    """Parse eBird date+time into a UTC datetime.

    eBird times are LOCAL time (usually Pacific for this data).
    If no time is given, we use noon on that date as a default.

    Args:
        obs_date: 'YYYY-MM-DD' string
        obs_time: 'HH:MM AM/PM' or 'HH:MM:SS' or 'HH:MM' or None/empty
        local_tz_name: IANA timezone name for the local time
    """
    if not obs_date:
        return None

    # Parse date
    parts = obs_date.strip().split("-")
    if len(parts) != 3:
        return None
    d = date(int(parts[0]), int(parts[1]), int(parts[2]))

    # Parse time (if available)
    t = None
    if obs_time and obs_time.strip():
        t_str = obs_time.strip().upper()
        try:
            if "AM" in t_str or "PM" in t_str:
                t = datetime.strptime(t_str, "%I:%M %p").time()
            elif t_str.count(":") == 2:
                t = datetime.strptime(t_str, "%H:%M:%S").time()
            elif t_str.count(":") == 1:
                t = datetime.strptime(t_str, "%H:%M").time()
        except ValueError:
            pass

    if t is None:
        t = time(12, 0)  # default to noon if no time

    local_dt = datetime.combine(d, t)

    # Convert local time to UTC using the configured timezone offset.
    # For America/Los_Angeles, approximate offset:
    #   PDT = UTC-7 (March~November), PST = UTC-8 (November~March)
    # Use a rough heuristic based on date
    offset_hours = _local_tz_offset(local_dt, local_tz_name)
    utc_dt = local_dt - timedelta(hours=offset_hours)
    return utc_dt


def _local_tz_offset(dt, tz_name="America/Los_Angeles"):
    """Estimate UTC offset for America/Los_Angeles based on date.

    Second Sunday of March at 2AM -> PDT (UTC-7)
    First Sunday of November at 2AM -> PST (UTC-8)
    """
    if tz_name != "America/Los_Angeles":
        # For other timezones, warn and default to -8
        return -8

    year = dt.year
    # DST starts second Sunday of March at 2AM
    mar_1 = date(year, 3, 1)
    # First Sunday
    first_sun_mar = mar_1 + timedelta(days=(6 - mar_1.weekday()))
    dst_start = first_sun_mar + timedelta(days=7)  # second Sunday
    dst_start_dt = datetime.combine(dst_start, time(2, 0))

    # DST ends first Sunday of November at 2AM
    nov_1 = date(year, 11, 1)
    dst_end = nov_1 + timedelta(days=(6 - nov_1.weekday()))
    dst_end_dt = datetime.combine(dst_end, time(2, 0))

    if dst_start_dt <= dt < dst_end_dt:
        return -7  # PDT
    else:
        return -8  # PST


def utc_to_local(utc_dt, local_tz_name="America/Los_Angeles"):
    """Convert a naive UTC datetime to local time string (Pacific).

    Returns (local_dt_string, offset_hours).
    """
    offset_h = _local_tz_offset(utc_dt, local_tz_name)
    local_dt = utc_dt + timedelta(hours=offset_h)
    return local_dt.isoformat(), offset_h


# ── Observation types ──────────────────────────────────────────────────


class Observation:
    """A single observation record from eBird or iNaturalist."""

    def __init__(self, source, obs_id, utc_dt, lat, lng, species, location_name):
        self.source = source  # 'ebird' or 'inaturalist'
        self.obs_id = str(obs_id)
        self.utc_dt = utc_dt  # naive datetime in UTC
        self.lat = lat
        self.lng = lng
        self.species = species or "Unknown"
        self.location_name = location_name or ""

    def __repr__(self):
        return (
            f"<{self.source}:{self.obs_id} "
            f"{self.utc_dt.isoformat()}Z "
            f"{self.species} @ ({self.lat}, {self.lng})>"
        )


# ── Database readers ───────────────────────────────────────────────────


def _resolve_db_path(path, fallback=None):
    """Resolve a DB path, trying the given path first, then fallback."""
    abspath = os.path.abspath(path)
    if os.path.exists(abspath):
        return abspath
    if fallback and os.path.exists(fallback):
        print(f"  (fallback: using {fallback})", file=sys.stderr)
        return fallback
    return abspath


def read_ebird_observations(db_path, start_date=None, end_date=None):
    """Fetch eBird observations from SQLite DB.

    Returns list of Observation objects.
    Returns empty list if DB doesn't exist or has no table.
    """
    if not os.path.exists(db_path):
        print(f"  eBird DB not found: {db_path}", file=sys.stderr)
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Verify schema
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='observations'"
        ).fetchall()
        if not tables:
            conn.close()
            print(f"  eBird DB has no 'observations' table: {db_path}", file=sys.stderr)
            return []

        query = """
            SELECT submission_id, common_name, scientific_name,
                   obs_date, obs_time, latitude, longitude, location_name
            FROM observations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
        params = []
        if start_date:
            query += " AND obs_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND obs_date <= ?"
            params.append(end_date)
        query += " ORDER BY obs_date, obs_time"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        # Observations are per-species-per-checklist (multiple rows per
        # checklist). We group them: each unique submission_id + date becomes
        # one observation entry (since all rows in a checklist share lat/lng).
        checklists = {}  # key: (submission_id, date) -> first row data
        for r in rows:
            key = (r["submission_id"], r["obs_date"])
            if key not in checklists:
                checklists[key] = r

        obs_list = []
        for key, r in checklists.items():
            utc_dt = parse_ebird_timestamp(r["obs_date"], r["obs_time"])
            if utc_dt is None:
                continue
            species = r["common_name"] or r["scientific_name"] or "Unknown"
            loc = r["location_name"] or ""
            obs_list.append(
                Observation(
                    source="ebird",
                    obs_id=key[0],
                    utc_dt=utc_dt,
                    lat=r["latitude"],
                    lng=r["longitude"],
                    species=species,
                    location_name=loc,
                )
            )

        return obs_list

    except Exception as e:
        print(f"  Error reading eBird DB: {e}", file=sys.stderr)
        return []


def read_inaturalist_observations(db_path, start_date=None, end_date=None):
    """Fetch iNaturalist observations from SQLite DB.

    Returns list of Observation objects.
    Returns empty list if DB doesn't exist or has no table.
    """
    if not os.path.exists(db_path):
        print(f"  iNat DB not found: {db_path}", file=sys.stderr)
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='observations'"
        ).fetchall()
        if not tables:
            conn.close()
            print(f"  iNat DB has no 'observations' table: {db_path}", file=sys.stderr)
            return []

        query = """
            SELECT id, time_observed_at, observed_on,
                   taxon_name, latitude, longitude, place_guess
            FROM observations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
        params = []
        if start_date:
            query += " AND observed_on >= ?"
            params.append(start_date)
        if end_date:
            query += " AND observed_on <= ?"
            params.append(end_date)
        query += " ORDER BY time_observed_at, observed_on"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        obs_list = []
        for r in rows:
            utc_dt = parse_inat_timestamp(r["time_observed_at"])
            if utc_dt is None:
                # If no time, use noon UTC on observed_on date
                if r["observed_on"]:
                    parts = r["observed_on"].strip().split("-")
                    if len(parts) == 3:
                        utc_dt = datetime(
                            int(parts[0]), int(parts[1]), int(parts[2]), 12, 0
                        )
            if utc_dt is None:
                continue

            species = r["taxon_name"] or "Unknown"
            loc = r["place_guess"] or ""
            obs_list.append(
                Observation(
                    source="inaturalist",
                    obs_id=r["id"],
                    utc_dt=utc_dt,
                    lat=r["latitude"],
                    lng=r["longitude"],
                    species=species,
                    location_name=loc,
                )
            )

        return obs_list

    except Exception as e:
        print(f"  Error reading iNat DB: {e}", file=sys.stderr)
        return []


# ── Session building ───────────────────────────────────────────────────


class Session:
    """A group of observations at the same place and time."""

    def __init__(self, first_obs):
        self.observations = [first_obs]
        self.start_utc = first_obs.utc_dt
        self.end_utc = first_obs.utc_dt
        self.lats = [first_obs.lat]
        self.lngs = [first_obs.lng]
        self.locations = set()
        if first_obs.location_name:
            self.locations.add(first_obs.location_name)

    def try_add(self, obs, dist_km, time_threshold_min, time_threshold_prev_min):
        """Check if obs can be added to this session.

        Args:
            obs: The observation to try adding
            dist_km: Distance threshold in km
            time_threshold_min: Time threshold from previous obs in minutes
            time_threshold_prev_min: Time threshold from the *previous* obs (same as time_threshold_min)

        Returns:
            True if added, False if should start new session
        """
        last_obs = self.observations[-1]

        # Check distance from LAST observation's location
        d = haversine_km(last_obs.lat, last_obs.lng, obs.lat, obs.lng)

        # Check time from PREVIOUS observation's time
        td = (obs.utc_dt - last_obs.utc_dt).total_seconds() / 60.0  # minutes

        if d <= dist_km and td <= time_threshold_min:
            self.observations.append(obs)
            self.end_utc = obs.utc_dt
            self.lats.append(obs.lat)
            self.lngs.append(obs.lng)
            if obs.location_name:
                self.locations.add(obs.location_name)
            return True

        return False

    @property
    def centroid_lat(self):
        return sum(self.lats) / len(self.lats) if self.lats else 0.0

    @property
    def centroid_lng(self):
        return sum(self.lngs) / len(self.lngs) if self.lngs else 0.0

    @property
    def duration(self):
        return self.end_utc - self.start_utc

    @property
    def num_obs(self):
        return len(self.observations)

    @property
    def ebird_count(self):
        return sum(1 for o in self.observations if o.source == "ebird")

    @property
    def inat_count(self):
        return sum(1 for o in self.observations if o.source == "inaturalist")

    @property
    def species_set(self):
        return set(o.species for o in self.observations)

    @property
    def location_summary(self):
        if self.locations:
            return "; ".join(sorted(self.locations)[:3])
        return f"({self.centroid_lat:.4f}, {self.centroid_lng:.4f})"


def build_sessions(observations, dist_km=1.0, time_min=120):
    """Group observations into sessions.

    Args:
        observations: List of Observation objects (sorted by UTC time)
        dist_km: Distance threshold in km
        time_min: Time threshold in minutes

    Returns:
        List of Session objects
    """
    if not observations:
        return []

    # Sort by UTC time
    sorted_obs = sorted(observations, key=lambda o: o.utc_dt)

    sessions = []
    current_session = Session(sorted_obs[0])

    for obs in sorted_obs[1:]:
        if not current_session.try_add(obs, dist_km, time_min, time_min):
            # Start new session
            sessions.append(current_session)
            current_session = Session(obs)

    # Don't forget the last session
    sessions.append(current_session)

    return sessions


# ── Session DB Writer ──────────────────────────────────────────────────


SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_num     INTEGER NOT NULL,
    start_utc       TEXT NOT NULL,
    end_utc         TEXT NOT NULL,
    duration_seconds REAL,
    centroid_lat    REAL,
    centroid_lng    REAL,
    location_summary TEXT,
    num_obs         INTEGER NOT NULL,
    ebird_count     INTEGER DEFAULT 0,
    inat_count      INTEGER DEFAULT 0,
    species_count   INTEGER DEFAULT 0,
    species_list    TEXT
);

CREATE TABLE IF NOT EXISTS session_observations (
    session_id  INTEGER NOT NULL,
    source      TEXT NOT NULL,
    obs_id      TEXT NOT NULL,
    species     TEXT,
    lat         REAL,
    lng         REAL,
    utc_time    TEXT,
    location_name TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_utc);
CREATE INDEX IF NOT EXISTS idx_sessions_obs ON session_observations(session_id);
"""


def write_session_db(db_path, sessions, append=False):
    """Write sessions to SQLite database.

    Args:
        db_path: Path to sessions.db
        sessions: List of Session objects
        append: If True, don't clear existing data
    """
    mode = "append" if append else "overwrite"
    print(f"\n  Writing sessions to: {os.path.abspath(db_path)} ({mode})")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    # Ensure both sessions + metadata tables exist
    conn.executescript(SESSION_SCHEMA)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    if not append:
        conn.execute("DELETE FROM session_observations")
        conn.execute("DELETE FROM sessions")

    for sess in sessions:
        dur = sess.duration.total_seconds()
        species_list = ", ".join(sorted(sess.species_set))
        conn.execute(
            """INSERT INTO sessions
               (session_num, start_utc, end_utc, duration_seconds,
                centroid_lat, centroid_lng, location_summary,
                num_obs, ebird_count, inat_count, species_count, species_list)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sessions.index(sess) + 1,
                sess.start_utc.isoformat(),
                sess.end_utc.isoformat(),
                dur,
                sess.centroid_lat,
                sess.centroid_lng,
                sess.location_summary,
                sess.num_obs,
                sess.ebird_count,
                sess.inat_count,
                len(sess.species_set),
                species_list,
            ),
        )
        session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for obs in sess.observations:
            conn.execute(
                """INSERT INTO session_observations
                   (session_id, source, obs_id, species, lat, lng, utc_time, location_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    obs.source,
                    obs.obs_id,
                    obs.species,
                    obs.lat,
                    obs.lng,
                    obs.utc_dt.isoformat(),
                    obs.location_name,
                ),
            )

    # Metadata
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("built_at", datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("num_sessions", str(len(sessions))),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("dist_km", str(dist_km)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata VALUES (?, ?)",
        ("time_min", str(time_min)),
    )

    conn.commit()
    conn.close()


# ── Report printing ────────────────────────────────────────────────────


def print_session_report(sessions, local_tz_name="America/Los_Angeles", csv_output=None):
    """Print a formatted session report.

    Args:
        sessions: List of Session objects
        local_tz_name: IANA timezone name for display
        csv_output: If set, a file path to write CSV output
    """
    if not sessions:
        print("\n  No sessions found.")
        return

    total_obs = sum(s.num_obs for s in sessions)
    total_ebird = sum(s.ebird_count for s in sessions)
    total_inat = sum(s.inat_count for s in sessions)

    print(f"\n  ── OpenClaw Nature Session Report ──")
    print(f"  Sessions:     {len(sessions)}")
    print(f"  Observations: {total_obs} ({total_ebird} eBird, {total_inat} iNaturalist)")
    print(
        f"  Date range:   {sessions[0].start_utc.isoformat()}Z to {sessions[-1].end_utc.isoformat()}Z"
    )
    print(f"  Distance threshold: {dist_km} km")
    print(f"  Time threshold:     {time_min} minutes")
    print(f"  Display timezone:   {local_tz_name}")
    print()

    # Column widths
    cols = ["Session", "Start (local)", "End (local)", "Duration",
            "Location", "Lat", "Lng", "Obs", "eB", "iNat", "Species"]
    header = "  {:<8} {:<22} {:<22} {:<10} {:<38} {:<9} {:<9} {:<5} {:<4} {:<5} {:<8}".format(*cols)
    sep = "  " + "-" * len(header)

    print(sep)
    print(header)
    print(sep)

    for i, sess in enumerate(sessions):
        start_local, _ = utc_to_local(sess.start_utc, local_tz_name)
        end_local, _ = utc_to_local(sess.end_utc, local_tz_name)
        dur_str = str(sess.duration).split(".")[0]  # trim microseconds

        loc = sess.location_summary
        if len(loc) > 38:
            loc = loc[:35] + "..."

        print(
            "  {:<8} {:<22} {:<22} {:<10} {:<38} {:<9.4f} {:<9.4f} {:<5} {:<4} {:<5} {:<8}".format(
                f"#{i+1}",
                start_local,
                end_local,
                dur_str,
                loc,
                sess.centroid_lat,
                sess.centroid_lng,
                sess.num_obs,
                sess.ebird_count,
                sess.inat_count,
                len(sess.species_set),
            )
        )

    print(sep)
    print(f"  Total{'':<8} {'':<22} {'':<22} {'':<10} {'':<38} {'':<9} {'':<9} {total_obs:<5} {total_ebird:<4} {total_inat:<5}")
    print()

    # Print details for each session
    print("  ── Session Details ──")
    for i, sess in enumerate(sessions):
        start_local, _ = utc_to_local(sess.start_utc, local_tz_name)
        print(f"\n  Session #{i+1} ({start_local}) — {sess.location_summary}")
        print(f"    Duration: {sess.duration}")
        print(f"    Species ({len(sess.species_set)}): {', '.join(sorted(sess.species_set))}")
        print(f"    Observations: {sess.num_obs} ({sess.ebird_count} eBird, {sess.inat_count} iNat)")
        # Show first few observations
        for obs in sess.observations[:5]:
            print(
                f"      [{obs.source}] {obs.species} @ ({obs.lat:.4f}, {obs.lng:.4f})"
            )
        if len(sess.observations) > 5:
            print(f"      ... and {len(sess.observations) - 5} more")

    # CSV output
    if csv_output:
        _write_csv(csv_output, sessions, local_tz_name)


def _write_csv(path, sessions, local_tz_name):
    """Write session report to CSV file."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "session_num",
                "start_local",
                "end_local",
                "duration",
                "location",
                "centroid_lat",
                "centroid_lng",
                "num_obs",
                "ebird_count",
                "inat_count",
                "species_count",
                "species_list",
            ]
        )
        for i, sess in enumerate(sessions):
            start_local, _ = utc_to_local(sess.start_utc, local_tz_name)
            end_local, _ = utc_to_local(sess.end_utc, local_tz_name)
            dur_str = str(sess.duration).split(".")[0]
            writer.writerow(
                [
                    i + 1,
                    start_local,
                    end_local,
                    dur_str,
                    sess.location_summary,
                    f"{sess.centroid_lat:.6f}",
                    f"{sess.centroid_lng:.6f}",
                    sess.num_obs,
                    sess.ebird_count,
                    sess.inat_count,
                    len(sess.species_set),
                    ", ".join(sorted(sess.species_set)),
                ]
            )
    print(f"\n  CSV written to: {os.path.abspath(path)}")


# ── Main ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Build nature observation sessions from eBird + iNaturalist data"
    )
    parser.add_argument(
        "--ebird-db",
        default=DEFAULT_EBIRD_DB,
        help=f"Path to eBird SQLite DB (default: relative to script)",
    )
    parser.add_argument(
        "--inat-db",
        default=DEFAULT_INAT_DB,
        help=f"Path to iNaturalist SQLite DB (default: relative to script)",
    )
    parser.add_argument(
        "--session-db",
        default=None,
        help="Path to output sessions.db (default: no DB written unless specified)",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date (YYYY-MM-DD). Default: all data",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date (YYYY-MM-DD). Default: all data",
    )
    parser.add_argument(
        "--dist",
        type=float,
        default=DISTANCE_THRESHOLD_KM,
        help=f"Distance threshold in km (default: {DISTANCE_THRESHOLD_KM})",
    )
    parser.add_argument(
        "--time",
        type=int,
        default=TIME_THRESHOLD_MINUTES,
        help=f"Time threshold in minutes (default: {TIME_THRESHOLD_MINUTES})",
    )
    parser.add_argument(
        "--tz",
        default=OUTPUT_TIMEZONE,
        help=f"Display timezone (default: {OUTPUT_TIMEZONE})",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Write session report to CSV file",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip writing to sessions.db even if --session-db is set",
    )
    args = parser.parse_args()

    global dist_km, time_min
    dist_km = args.dist
    time_min = args.time

    # Resolve DB paths
    ebird_db = _resolve_db_path(args.ebird_db, FALLBACK_EBIRD_DB)
    inat_db = _resolve_db_path(args.inat_db, FALLBACK_INAT_DB)

    session_db = args.session_db
    if session_db is None and not args.no_db:
        session_db = DEFAULT_SESSION_DB

    print("OpenClaw Nature — Session Builder")
    print("=" * 50)
    print(f"  eBird DB:       {ebird_db}")
    print(f"  iNat DB:        {inat_db}")
    print(f"  Date range:     {args.start_date or 'all'} to {args.end_date or 'all'}")
    print(f"  Distance thresh: {dist_km} km")
    print(f"  Time thresh:    {time_min} min")
    print(f"  Display TZ:     {args.tz}")
    print()

    # Read observations
    print("  Reading eBird observations...")
    ebird_obs = read_ebird_observations(ebird_db, args.start_date, args.end_date)
    print(f"    Found {len(ebird_obs)} eBird checklists")

    print("  Reading iNaturalist observations...")
    inat_obs = read_inaturalist_observations(inat_db, args.start_date, args.end_date)
    print(f"    Found {len(inat_obs)} iNaturalist observations")

    all_obs = ebird_obs + inat_obs
    print(f"\n  Total: {len(all_obs)} observations from both sources")

    if not all_obs:
        print("\n  No observations to process. Exiting.")
        return

    # Build sessions
    print("  Building sessions...")
    sessions = build_sessions(all_obs, dist_km=dist_km, time_min=time_min)

    # Print report
    print_session_report(sessions, local_tz_name=args.tz, csv_output=args.csv)

    # Write session DB
    if session_db and not args.no_db:
        write_session_db(session_db, sessions, append=False)


if __name__ == "__main__":
    dist_km = DISTANCE_THRESHOLD_KM
    time_min = TIME_THRESHOLD_MINUTES
    main()
