#!/usr/bin/env python3
"""
OpenClaw Nature — Session Builder

Groups eBird and iNaturalist observations into unified "sessions"
(outings at the same place and time).

ALGORITHM (Two-phase):

Phase 1 — Cluster iNaturalist observations by proximity in space & time:
   - iNaturalist timestamps are accurate (ISO 8601 with UTC offset)
   - Group them by the standard session rule:
     * Sort by UTC timestamp
     * Same session if within DISTANCE_KM of the LAST observation
       AND within TIME_MINUTES of the PREVIOUS observation's time
     * Otherwise start a new session
   - Each iNat session gets a start time (first obs), end time (last obs),
     centroid location, and explicit UTC boundaries

Phase 2 — Overlay eBird onto iNat sessions:
   - eBird CSV only has dates (times defaulted to noon) — not reliable
   - For each eBird checklist, find ALL iNat sessions on the same date
     within DISTANCE_KM of the checklist location
   - If EXACTLY ONE session matches: merge eBird species into that
     session. eBird observations are ASSIGNED the session's END TIME
     (they happened during the outing, even if recorded separately).
   - If MULTIPLE sessions match (ambiguous): create an eBird-only
     session — we can't know which outing the checklist belongs to.
   - If NO sessions match: create an eBird-only session.
   - Original eBird data is NEVER modified — the overlay is stored
     in openclaw-nature.db with an is_overlay flag on each observation

Usage:
    python3 import/build_sessions.py
    python3 import/build_sessions.py --start-date 2026-05-04 --end-date 2026-05-08
    python3 import/build_sessions.py --dist 1.0 --time 120

Stdlib only — no external dependencies.
"""

import argparse
import csv
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, date, time, timedelta, timezone

# ── Defaults ───────────────────────────────────────────────────────────

DEFAULT_EBIRD_DB = os.path.join(
    os.path.dirname(__file__), "..", "ebird", "import", "ebird.db"
)
DEFAULT_INAT_DB = os.path.join(
    os.path.dirname(__file__), "..", "inaturalist", "import", "inat.db"
)
DEFAULT_SESSION_DB = os.path.join(os.path.dirname(__file__), "openclaw-nature.db")

FALLBACK_EBIRD_DB = "/home/openclaw/.openclaw/workspace/zookeeper/modules/ebird/ebird.db"
FALLBACK_INAT_DB = "/home/openclaw/.openclaw/workspace/skills/inaturalist/import/inat.db"
DEFAULT_TAXONOMY_DB = os.path.join(os.path.dirname(__file__), "openclaw-nature.db")

DISTANCE_THRESHOLD_KM = 1.0
TIME_THRESHOLD_MINUTES = 120
OUTPUT_TIMEZONE = "America/Los_Angeles"

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


def _parse_offset(offset_str):
    """Parse a timezone offset string like '-07:00' or '+00:00' or 'Z'."""
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
    """Parse iNaturalist ISO 8601 timestamp to naive UTC datetime.

    Handles formats like:
      2026-05-06T07:36:18-07:00
      2026-05-06T14:36:18Z
      2026-05-06T14:36:18+00:00

    Uses regex to find the timezone offset so that dashes in the
    date portion (e.g., 2026-05-06) are NOT confused with negative
    UTC offsets (e.g., -07:00).
    """
    if not ts_str:
        return None
    ts_str = ts_str.strip()

    # Normalize Z suffix
    normalized = ts_str
    if normalized.endswith("Z") or normalized.endswith("z"):
        normalized = normalized[:-1] + "+00:00"

    # Match timezone offset at the end of the string:
    # [+-]HH:MM (e.g., -07:00, +00:00, +05:30)
    match = re.search(r"([+-])(\d{2}):(\d{2})$", normalized)
    if match:
        offset_str = match.group(0)
        dt_str = normalized[: match.start()]
    else:
        dt_str = normalized
        offset_str = "+00:00"

    try:
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        return None

    offset = _parse_offset(offset_str)
    utc_dt = dt.replace(tzinfo=timezone.utc) - offset
    return utc_dt.replace(tzinfo=None)


def _local_tz_offset(dt, tz_name="America/Los_Angeles"):
    """Estimate UTC offset for America/Los_Angeles on a given date."""
    if tz_name != "America/Los_Angeles":
        return -8
    year = dt.year
    mar_1 = date(year, 3, 1)
    first_sun_mar = mar_1 + timedelta(days=(6 - mar_1.weekday()))
    dst_start = first_sun_mar + timedelta(days=7)
    dst_start_dt = datetime.combine(dst_start, time(2, 0))
    nov_1 = date(year, 11, 1)
    dst_end = nov_1 + timedelta(days=(6 - nov_1.weekday()))
    dst_end_dt = datetime.combine(dst_end, time(2, 0))
    if dst_start_dt <= dt < dst_end_dt:
        return -7
    else:
        return -8


def utc_to_local(utc_dt, local_tz_name="America/Los_Angeles"):
    """Convert naive UTC datetime to local time, return (iso_string, offset_hours)."""
    offset_h = _local_tz_offset(utc_dt, local_tz_name)
    local_dt = utc_dt + timedelta(hours=offset_h)
    return local_dt.isoformat(), offset_h


def utc_to_local_str(utc_dt, local_tz_name="America/Los_Angeles"):
    s, _ = utc_to_local(utc_dt, local_tz_name)
    return s


# ── Database readers ───────────────────────────────────────────────────


def _resolve_db_path(path, fallback=None):
    abspath = os.path.abspath(path)
    if os.path.exists(abspath):
        return abspath
    if fallback and os.path.exists(fallback):
        print(f"  (fallback: using {fallback})", file=sys.stderr)
        return fallback
    return abspath


def read_inat_observations(db_path, start_date=None, end_date=None):
    """Fetch iNaturalist observations with full detail."""
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
            return []

        query = """
            SELECT id, observed_on, time_observed_at, latitude, longitude,
                   species_guess, taxon_name, place_guess,
                   tags, annotations, photos_json, sounds_json,
                   identifications_json
            FROM observations
            WHERE latitude IS NOT NULL
        """
        params = []
        if start_date:
            query += " AND observed_on >= ?"
            params.append(start_date)
        if end_date:
            query += " AND observed_on <= ?"
            params.append(end_date)
        query += " ORDER BY observed_on, time_observed_at"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        result = []
        for r in rows:
            # Skip observations with no date at all
            if r["observed_on"] is None:
                continue
            utc_dt = parse_inat_timestamp(r["time_observed_at"])
            if utc_dt is None:
                # Fallback: use noon on observed_on
                try:
                    d = datetime.fromisoformat(r["observed_on"])
                except (ValueError, TypeError):
                    continue
                utc_dt = d.replace(hour=12, minute=0, second=0)
            species = r["species_guess"] or r["taxon_name"] or "Unknown"
            result.append({
                "obs_id": f"inat:{r['id']}",
                "source": "inaturalist",
                "utc_dt": utc_dt,
                "lat": r["latitude"],
                "lng": r["longitude"],
                "species": species,
                "place_guess": r["place_guess"] or "",
                "observed_on": r["observed_on"],
                "tags": r["tags"],
                "annotations": r["annotations"],
                "photos_json": r["photos_json"],
                "sounds_json": r["sounds_json"],
                "identifications_json": r["identifications_json"],
            })
        return result
    except Exception as e:
        print(f"  Error reading iNat DB: {e}", file=sys.stderr)
        return []


def read_ebird_checklists(db_path, start_date=None, end_date=None):
    """Fetch eBird checklists grouped by submission_id.

    Returns a dict: {submission_id: {'date': str, 'lat': float, 'lng': float,
                                      'location_name': str, 'species': [str]}}
    """
    if not os.path.exists(db_path):
        print(f"  eBird DB not found: {db_path}", file=sys.stderr)
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='observations'"
        ).fetchall()
        if not tables:
            conn.close()
            return []

        query = """
            SELECT submission_id, obs_date, latitude, longitude, location_name,
                   common_name, scientific_name
            FROM observations
            WHERE latitude IS NOT NULL
        """
        params = []
        if start_date:
            query += " AND obs_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND obs_date <= ?"
            params.append(end_date)
        query += " ORDER BY submission_id"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        checklists = {}
        for r in rows:
            sid = r["submission_id"]
            if sid not in checklists:
                checklists[sid] = {
                    "submission_id": sid,
                    "obs_date": r["obs_date"],
                    "lat": r["latitude"],
                    "lng": r["longitude"],
                    "location_name": r["location_name"] or "",
                    "species": [],
                }
            species = r["common_name"] or r["scientific_name"] or "Unknown"
            checklists[sid]["species"].append(species)

        return list(checklists.values())
    except Exception as e:
        print(f"  Error reading eBird DB: {e}", file=sys.stderr)
        return []


# ── Taxonomy Lookup ────────────────────────────────────────────────────


def load_species_lookup(db_path):
    """Load canonical species taxonomy into lookup dicts.

    Returns dict: {"ebird": {display_name: species_id},
                   "inat":  {display_name: species_id}}
    """
    if not os.path.exists(db_path):
        return {"ebird": {}, "inat": {}}

    conn = sqlite3.connect(db_path)

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('species', 'ebird_species_map', 'inat_species_map')"
    )]
    if len(tables) < 3:
        conn.close()
        return {"ebird": {}, "inat": {}}

    lookup = {"ebird": {}, "inat": {}}

    for row in conn.execute(
        "SELECT m.display_name, m.species_id "
        "FROM ebird_species_map m "
        "JOIN species s ON s.id = m.species_id"
    ):
        lookup["ebird"][row[0]] = row[1]

    for row in conn.execute(
        "SELECT m.display_name, m.species_id "
        "FROM inat_species_map m "
        "JOIN species s ON s.id = m.species_id"
    ):
        lookup["inat"][row[0]] = row[1]

    conn.close()
    return lookup


def resolve_species_id(species_lookup, species_name, source):
    """Resolve a species name to a canonical species_id."""
    key_map = species_lookup.get(source, {})
    sid = key_map.get(species_name)
    if sid is not None:
        return sid
    other = "ebird" if source == "inat" else "inat"
    return species_lookup.get(other, {}).get(species_name)


# ── Session Data Structure ─────────────────────────────────────────────


class Session:
    """A unified outing session, populated in two phases."""

    def __init__(self, session_num):
        self.session_num = session_num
        # iNat observations (source = "inaturalist")
        self.inat_obs = []
        # eBird species (source = "ebird")
        self.ebird_species = []  # list of {"species": str, "checklist_id": str}
        # Temporal bounds (set by iNat phase)
        self.start_utc = None
        self.end_utc = None
        # Spatial info
        self.all_lats = []
        self.all_lngs = []
        self.place_guesses = set()

    @property
    def num_obs(self):
        return len(self.inat_obs) + len(self.ebird_species)

    @property
    def ebird_count(self):
        return len(self.ebird_species)

    @property
    def inat_count(self):
        return len(self.inat_obs)

    @property
    def centroid_lat(self):
        if not self.all_lats:
            return 0.0
        return sum(self.all_lats) / len(self.all_lats)

    @property
    def centroid_lng(self):
        if not self.all_lngs:
            return 0.0
        return sum(self.all_lngs) / len(self.all_lngs)

    @property
    def location_summary(self):
        parts = sorted(self.place_guesses)
        return "; ".join(parts) if parts else "Unknown"

    @property
    def species_set(self):
        s = {o["species"] for o in self.inat_obs}
        s.update(e["species"] for e in self.ebird_species)
        return s

    @property
    def duration(self):
        if self.start_utc and self.end_utc:
            return self.end_utc - self.start_utc
        return timedelta(0)

    def add_inat_obs(self, obs):
        """Add an iNaturalist observation."""
        self.inat_obs.append(obs)
        self.all_lats.append(obs["lat"])
        self.all_lngs.append(obs["lng"])
        if obs.get("place_guess"):
            self.place_guesses.add(obs["place_guess"])

        if self.start_utc is None or obs["utc_dt"] < self.start_utc:
            self.start_utc = obs["utc_dt"]
        if self.end_utc is None or obs["utc_dt"] > self.end_utc:
            self.end_utc = obs["utc_dt"]

    def merge_ebird_checklist(self, checklist):
        """Overlay an eBird checklist onto this session.

        eBird species get the session's END TIME as their timestamp (overlay).
        The centroid is updated to include the eBird location.
        """
        self.all_lats.append(checklist["lat"])
        self.all_lngs.append(checklist["lng"])
        if checklist.get("location_name"):
            self.place_guesses.add(checklist["location_name"])

        for sp in checklist["species"]:
            self.ebird_species.append({
                "species": sp,
                "checklist_id": checklist["submission_id"],
                "assigned_dt": self.end_utc,  # overlay time = session end
                "lat": checklist["lat"],
                "lng": checklist["lng"],
            })

    def to_dict(self):
        """Return a dict suitable for CSV or DB insertion."""
        d = self.duration
        total_secs = int(d.total_seconds())
        dur_str = f"{total_secs // 3600:02d}:{(total_secs % 3600) // 60:02d}:{total_secs % 60:02d}"
        return {
            "session_num": self.session_num,
            "start_utc": self.start_utc.isoformat() if self.start_utc else "",
            "end_utc": self.end_utc.isoformat() if self.end_utc else "",
            "start_local": utc_to_local_str(self.start_utc) if self.start_utc else "",
            "end_local": utc_to_local_str(self.end_utc) if self.end_utc else "",
            "duration": dur_str,
            "location": self.location_summary,
            "centroid_lat": round(self.centroid_lat, 6),
            "centroid_lng": round(self.centroid_lng, 6),
            "num_obs": self.num_obs,
            "ebird_count": self.ebird_count,
            "inat_count": self.inat_count,
            "species_count": len(self.species_set),
            "species_list": ", ".join(sorted(self.species_set)),
        }


# ── Phase 1: Cluster iNaturalist observations ─────────────────────────


def cluster_inat_obs(obs_list, dist_km=1.0, time_min=120):
    """Group iNat observations into sessions by spatial-temporal proximity.

    Standard session algorithm:
    - Sort by UTC timestamp
    - Same session if within dist_km of the LAST observation
      AND within time_min of the PREVIOUS observation's time
    - Otherwise start a new session
    """
    sorted_obs = sorted(obs_list, key=lambda o: o["utc_dt"])
    sessions = []
    current = None

    for obs in sorted_obs:
        if current is None:
            current = Session(len(sessions) + 1)
            current.add_inat_obs(obs)
            sessions.append(current)
            continue

        # Check distance from LAST observation
        last_obs = current.inat_obs[-1]
        d = haversine_km(last_obs["lat"], last_obs["lng"], obs["lat"], obs["lng"])

        # Check time from PREVIOUS observation
        t = (obs["utc_dt"] - last_obs["utc_dt"]).total_seconds() / 60.0

        if d <= dist_km and abs(t) <= time_min:
            current.add_inat_obs(obs)
        else:
            current = Session(len(sessions) + 1)
            current.add_inat_obs(obs)
            sessions.append(current)

    return sessions


# ── Phase 2: Overlay eBird onto sessions ──────────────────────────────


def overlay_ebird(sessions, ebird_checklists, dist_km=1.0):
    """Overlay eBird checklists onto existing sessions.

    For each eBird checklist:
    1. Find all sessions on the same date that have observations within dist_km
    2. If exactly ONE session matches, merge eBird species into that session
    3. If ZERO sessions match (no iNat nearby), create a new eBird-only session
    4. If MULTIPLE sessions match (ambiguous), create a new eBird-only session
       — we can't know which outing the birds belong to

    Returns: (updated_sessions, unmatched_checklists)
    """
    unmatched = []

    # Build a spatial index per date: for each iNat session, list its
    # observation coordinates so we can check distance
    inat_session_map = {}  # date_str -> [(session, lat, lng), ...]
    for sess in sessions:
        d = sess.start_utc.strftime("%Y-%m-%d") if sess.start_utc else ""
        if d not in inat_session_map:
            inat_session_map[d] = []
        for obs in sess.inat_obs:
            inat_session_map[d].append((sess, obs["lat"], obs["lng"]))

    next_num = len(sessions) + 1

    for cl in ebird_checklists:
        cl_date = cl["obs_date"]

        # Find ALL sessions within range
        candidates = inat_session_map.get(cl_date, [])
        matching_sessions = set()
        for sess, slat, slng in candidates:
            d = haversine_km(cl["lat"], cl["lng"], slat, slng)
            if d <= dist_km:
                matching_sessions.add(sess)

        if len(matching_sessions) == 1:
            # Unambiguous match — merge into this session
            matched_session = list(matching_sessions)[0]
            matched_session.merge_ebird_checklist(cl)
        else:
            # Ambiguous (2+ matches) or no iNat nearby
            cl["_num_matching_sessions"] = len(matching_sessions)
            unmatched.append(cl)

    # Group unmatched checklists by date + location grid cell (~1.1km
    # resolution) so checklists at the same park become one eBird-only
    # session instead of many singleton sessions.
    LOC_GROUP_DEG = 0.01
    groups = defaultdict(list)
    for cl in unmatched:
        glat = round(cl["lat"] / LOC_GROUP_DEG) * LOC_GROUP_DEG
        glng = round(cl["lng"] / LOC_GROUP_DEG) * LOC_GROUP_DEG
        groups[(cl["obs_date"], glat, glng)].append(cl)

    for (gdate, _, _), checklists in groups.items():
        sess = _make_ebird_session_from_checklists(checklists, next_num)
        next_num += 1
        sessions.append(sess)

    return sessions, unmatched


def _make_ebird_session_from_checklists(checklists, session_num):
    """Create a new session from one or more eBird checklists with no
    iNat partner.

    All checklists share the same date and approximate location, so they
    form a single session. Uses noon local as the default timestamp.
    """
    sess = Session(session_num)

    # Collect all location info
    all_lats = []
    all_lngs = []
    for cl in checklists:
        all_lats.append(cl["lat"])
        all_lngs.append(cl["lng"])
        if cl.get("location_name"):
            sess.place_guesses.add(cl["location_name"])

    # Centroid
    sess.all_lats = all_lats
    sess.all_lngs = all_lngs

    # Default timestamp: noon local
    parts = checklists[0]["obs_date"].split("-")
    d = date(int(parts[0]), int(parts[1]), int(parts[2]))
    noon_utc = datetime.combine(d, time(12, 0))
    offset = _local_tz_offset(noon_utc)
    default_ts = noon_utc - timedelta(hours=offset)

    for cl in checklists:
        for sp in cl["species"]:
            sess.ebird_species.append({
                "species": sp,
                "checklist_id": cl["submission_id"],
                "assigned_dt": default_ts,
                "lat": cl["lat"],
                "lng": cl["lng"],
            })

    sess.start_utc = default_ts
    sess.end_utc = default_ts
    return sess


# ── Output ─────────────────────────────────────────────────────────────


def print_session_report(sessions, local_tz_name=OUTPUT_TIMEZONE, csv_output=None):
    """Print a formatted session report and optionally write CSV."""
    total_obs = sum(s.num_obs for s in sessions)
    total_eb = sum(s.ebird_count for s in sessions)
    total_inat = sum(s.inat_count for s in sessions)

    print(f"\n  {'─' * 200}")
    print(f"  Session  Start (local)          End (local)            Duration   Location{' ':<50} Lat       Lng       Obs   eB   iNat  Species ")
    print(f"  {'─' * 200}")

    for sess in sessions:
        d = sess.to_dict()
        loc = d["location"]
        if len(loc) > 52:
            loc = loc[:49] + "..."
        dur_s = d["duration"]
        print(
            f"  #{d['session_num']:<5} {d['start_local']:<23} {d['end_local']:<23} {dur_s:<10} {loc:<52} "
            f"{d['centroid_lat']:.4f}   {d['centroid_lng']:.4f}  "
            f"{d['num_obs']:<4} {d['ebird_count']:<3} {d['inat_count']:<4} {d['species_count']:<6}"
        )
    print(f"  {'─' * 200}")
    print(
        f"  Total{' ':<99}"
        f"{total_obs:<5} {total_eb:<4} {total_inat:<4}"
    )

    # Detailed per-session
    for sess in sessions:
        d = sess.to_dict()
        print(f"\n  Session #{d['session_num']} ({d['start_local']}) — {d['location']}")
        print(f"    Duration: {d['duration']}  |  {d['num_obs']} obs ({d['ebird_count']} eBird, {d['inat_count']} iNat)  |  {d['species_count']} species")
        # Show iNat first
        if sess.inat_obs:
            inat_species = sorted(set(o["species"] for o in sess.inat_obs))
            print(f"    iNat species ({len(inat_species)}): {', '.join(inat_species[:20])}{'…' if len(inat_species) > 20 else ''}")
        # Then eBird overlay
        if sess.ebird_species:
            eb_species = sorted(set(e["species"] for e in sess.ebird_species))
            print(f"    eBird overlay ({len(eb_species)}): {', '.join(eb_species[:20])}{'…' if len(eb_species) > 20 else ''}")

    # Summary
    merged = [s for s in sessions if s.ebird_count > 0 and s.inat_count > 0]
    print(f"\n  ── Summary ──")
    print(f"  Total sessions: {len(sessions)}")
    print(f"  iNat-only sessions: {sum(1 for s in sessions if s.inat_count > 0 and s.ebird_count == 0)}")
    print(f"  eBird-only sessions: {sum(1 for s in sessions if s.ebird_count > 0 and s.inat_count == 0)}")
    print(f"  Merged sessions (both sources): {len(merged)}")
    print(f"  Total observations: {total_obs} ({total_eb} eBird, {total_inat} iNat)")

    if merged:
        print(f"\n  ── Merged Session Details ──")
        for sess in merged:
            d = sess.to_dict()
            print(f"  #{d['session_num']}: {d['location']}")
            print(f"     {d['inat_count']} iNat observations ({d['start_local']} → {d['end_local']})")
            print(f"     + {d['ebird_count']} eBird species overlaid at end time")

    # CSV output
    if csv_output:
        fieldnames = [
            "session_num", "start_utc", "end_utc", "start_local", "end_local",
            "duration",
            "location", "centroid_lat", "centroid_lng",
            "num_obs", "ebird_count", "inat_count", "species_count", "species_list",
        ]
        with open(csv_output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for sess in sessions:
                writer.writerow(sess.to_dict())
        print(f"\n  CSV written to: {os.path.abspath(csv_output)}")


# ── SQLite Schema ─────────────────────────────────────────────────────


SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_num  INTEGER NOT NULL,
    start_utc    TEXT,
    end_utc      TEXT,
    start_local  TEXT,
    end_local    TEXT,
    duration     TEXT,
    location     TEXT,
    centroid_lat REAL,
    centroid_lng REAL,
    num_obs      INTEGER,
    ebird_count  INTEGER,
    inat_count   INTEGER,
    species_count INTEGER,
    species_list TEXT,
    merged       INTEGER DEFAULT 0,
    user_label   TEXT,            -- custom user name for this session
    user_notes   TEXT,            -- custom notes for this session
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_num ON sessions(session_num);

CREATE TABLE IF NOT EXISTS session_observations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER REFERENCES sessions(id),
    source        TEXT NOT NULL,   -- 'inaturalist' or 'ebird'
    obs_id        TEXT,            -- inat:<id> or ebird:<submission_id>
    species       TEXT,
    species_id    INTEGER,
    lat           REAL,
    lng           REAL,
    utc_timestamp TEXT,
    local_timestamp TEXT,
    is_overlay    INTEGER DEFAULT 0,  -- 1 = eBird time was assigned by overlay
    details_json  TEXT,
    user_label    TEXT,            -- custom user name for this observation
    user_notes    TEXT,            -- custom notes for this observation
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    UNIQUE(source, obs_id)
);

CREATE INDEX IF NOT EXISTS idx_so_session  ON session_observations(session_id);
CREATE INDEX IF NOT EXISTS idx_so_source   ON session_observations(source);
CREATE INDEX IF NOT EXISTS idx_so_species  ON session_observations(species_id);

-- User metadata tables (never dropped by the builder)
CREATE TABLE IF NOT EXISTS session_metadata (
    session_num   INTEGER PRIMARY KEY,
    user_label    TEXT,            -- custom name for the session
    user_notes    TEXT             -- custom notes
);

CREATE TABLE IF NOT EXISTS species_metadata (
    species_id    INTEGER PRIMARY KEY REFERENCES species(id),
    user_label    TEXT,            -- custom name for this species
    user_notes    TEXT             -- custom notes
);
"""


def write_session_db(db_path, sessions, species_lookup=None, append=False):
    """Write sessions to SQLite.

    Uses upsert-on-rebuild: auto-generated rows are replaced by session_num
    (for sessions) or (source, obs_id) (for observations), but user metadata
    columns (user_label, user_notes) are NEVER touched by the builder.

    Args:
        db_path: Path to output database
        sessions: List of Session objects
        species_lookup: Dict of {"ebird": {name: id}, "inat": {name: id}}
            from load_species_lookup(). If None, species_id will be NULL.
        append: If True, preserve existing rows and add new ones alongside.
    """
    if species_lookup is None:
        species_lookup = {"ebird": {}, "inat": {}}
    mode = "append" if append else "overwrite"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    # Always ensure schema tables exist (IF NOT EXISTS — never drops)
    conn.executescript(SESSION_SCHEMA)

    # Migrate: add user_label/user_notes columns if they don't exist yet
    # (older DBs may have been created without these)
    migrations = [
        ("sessions", "user_label", "ALTER TABLE sessions ADD COLUMN user_label TEXT"),
        ("sessions", "user_notes", "ALTER TABLE sessions ADD COLUMN user_notes TEXT"),
        ("session_observations", "user_label",
         "ALTER TABLE session_observations ADD COLUMN user_label TEXT"),
        ("session_observations", "user_notes",
         "ALTER TABLE session_observations ADD COLUMN user_notes TEXT"),
    ]
    existing_cols = {}
    for t in ["sessions", "session_observations"]:
        existing_cols[t] = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
    for table, col, sql in migrations:
        if col not in existing_cols.get(table, set()):
            conn.execute(sql)

    # Get existing user_label/user_notes from sessions before upsert
    existing_labels = {}
    for row in conn.execute(
        "SELECT session_num, user_label, user_notes FROM sessions "
        "WHERE user_label IS NOT NULL OR user_notes IS NOT NULL"
    ):
        existing_labels[row[0]] = {"user_label": row[1], "user_notes": row[2]}

    # Get existing observation user metadata before upsert
    obs_metadata = {}
    for row in conn.execute(
        "SELECT source, obs_id, user_label, user_notes "
        "FROM session_observations "
        "WHERE (user_label IS NOT NULL OR user_notes IS NOT NULL)"
    ):
        key = (row[0], row[1])
        obs_metadata[key] = {"user_label": row[2], "user_notes": row[3]}

    if not append:
        # Remove auto-generated rows only — metadata tables untouched
        conn.execute("DELETE FROM session_observations")
        conn.execute("DELETE FROM sessions")

    for sess in sessions:
        d = sess.to_dict()
        is_merged = 1 if sess.ebird_count > 0 and sess.inat_count > 0 else 0

        # Restore any user-set label/notes
        user_label = None
        user_notes = None
        meta = existing_labels.get(d["session_num"])
        if meta:
            user_label = meta["user_label"]
            user_notes = meta["user_notes"]

        conn.execute(
            """INSERT INTO sessions
               (session_num, start_utc, end_utc, start_local, end_local,
                duration, location, centroid_lat, centroid_lng,
                num_obs, ebird_count, inat_count, species_count,
                species_list, merged, user_label, user_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_num) DO UPDATE SET
                start_utc=excluded.start_utc,
                end_utc=excluded.end_utc,
                start_local=excluded.start_local,
                end_local=excluded.end_local,
                duration=excluded.duration,
                location=excluded.location,
                centroid_lat=excluded.centroid_lat,
                centroid_lng=excluded.centroid_lng,
                num_obs=excluded.num_obs,
                ebird_count=excluded.ebird_count,
                inat_count=excluded.inat_count,
                species_count=excluded.species_count,
                species_list=excluded.species_list,
                merged=excluded.merged,
                user_label=COALESCE(sessions.user_label, excluded.user_label),
                user_notes=COALESCE(sessions.user_notes, excluded.user_notes)""",
            (
                d["session_num"], d["start_utc"], d["end_utc"],
                d["start_local"], d["end_local"],
                d["duration"], d["location"],
                d["centroid_lat"], d["centroid_lng"],
                d["num_obs"], d["ebird_count"], d["inat_count"],
                d["species_count"], d["species_list"], is_merged,
                user_label, user_notes,
            ),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE session_num = ?",
            (d["session_num"],),
        ).fetchone()[0]

        # Write iNat observations
        for obs in sess.inat_obs:
            local_ts = utc_to_local_str(obs["utc_dt"])
            details = json.dumps(
                {k: obs[k] for k in ["tags", "annotations", "photos_json",
                                     "sounds_json", "identifications_json", "place_guess"]
                 if k in obs}
            )
            sid = resolve_species_id(
                species_lookup, obs["species"], "inat"
            )
            # Restore observation user metadata
            obs_key = (obs["source"], obs["obs_id"])
            obs_m = obs_metadata.get(obs_key, {})
            conn.execute(
                """INSERT INTO session_observations
                   (session_id, source, obs_id, species, species_id, lat, lng,
                    utc_timestamp, local_timestamp, is_overlay, details_json,
                    user_label, user_notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, obs_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    species=excluded.species,
                    species_id=excluded.species_id,
                    lat=excluded.lat,
                    lng=excluded.lng,
                    utc_timestamp=excluded.utc_timestamp,
                    local_timestamp=excluded.local_timestamp,
                    is_overlay=excluded.is_overlay,
                    details_json=excluded.details_json,
                    user_label=COALESCE(session_observations.user_label, excluded.user_label),
                    user_notes=COALESCE(session_observations.user_notes, excluded.user_notes)""",
                (session_id, obs["source"], obs["obs_id"], obs["species"],
                 sid, obs["lat"], obs["lng"],
                 obs["utc_dt"].isoformat(), local_ts, 0, details,
                 obs_m.get("user_label"), obs_m.get("user_notes")),
            )

        # Write eBird overlay observations
        for e in sess.ebird_species:
            local_ts = utc_to_local_str(e["assigned_dt"]) if e["assigned_dt"] else ""
            sid = resolve_species_id(
                species_lookup, e["species"], "ebird"
            )
            obs_key = ("ebird", e["checklist_id"])
            obs_m = obs_metadata.get(obs_key, {})
            conn.execute(
                """INSERT INTO session_observations
                   (session_id, source, obs_id, species, species_id, lat, lng,
                    utc_timestamp, local_timestamp, is_overlay, details_json,
                    user_label, user_notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, obs_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    species=excluded.species,
                    species_id=excluded.species_id,
                    lat=excluded.lat,
                    lng=excluded.lng,
                    utc_timestamp=excluded.utc_timestamp,
                    local_timestamp=excluded.local_timestamp,
                    is_overlay=excluded.is_overlay,
                    details_json=excluded.details_json,
                    user_label=COALESCE(session_observations.user_label, excluded.user_label),
                    user_notes=COALESCE(session_observations.user_notes, excluded.user_notes)""",
                (session_id, "ebird", e["checklist_id"], e["species"],
                 sid, e["lat"], e["lng"],
                 e["assigned_dt"].isoformat() if e["assigned_dt"] else "",
                 local_ts, 1, "{}",
                 obs_m.get("user_label"), obs_m.get("user_notes")),
            )

    conn.commit()
    size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    print(f"\n  Session DB written to: {os.path.abspath(db_path)} ({size / 1024:.0f} KB)")
    print(f"  Mode: {mode}")
    conn.close()


# ── Main ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Build nature observation sessions from eBird + iNaturalist data"
    )
    parser.add_argument("--ebird-db", default=DEFAULT_EBIRD_DB)
    parser.add_argument("--inat-db", default=DEFAULT_INAT_DB)
    parser.add_argument("--session-db", default=None)
    parser.add_argument(
        "--taxonomy-db", default=None,
        help="Path to species taxonomy DB (default: session DB)"
    )
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--dist", type=float, default=DISTANCE_THRESHOLD_KM)
    parser.add_argument("--time", type=int, default=TIME_THRESHOLD_MINUTES)
    parser.add_argument("--tz", default=OUTPUT_TIMEZONE)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()

    ebird_db = _resolve_db_path(args.ebird_db, FALLBACK_EBIRD_DB)
    inat_db = _resolve_db_path(args.inat_db, FALLBACK_INAT_DB)
    session_db = args.session_db if args.session_db else DEFAULT_SESSION_DB

    # Load taxonomy for species resolution
    taxonomy_db = args.taxonomy_db if args.taxonomy_db else session_db
    species_lookup = load_species_lookup(taxonomy_db)
    has_taxonomy = bool(species_lookup["ebird"]) or bool(species_lookup["inat"])
    print(f"  Taxonomy DB:    {taxonomy_db}")
    if has_taxonomy:
        print(f"    {len(species_lookup['ebird'])} eBird + "
              f"{len(species_lookup['inat'])} iNat species resolution entries")
    else:
        print("    (no taxonomy tables — species stored as text only)")

    print("OpenClaw Nature — Session Builder (Overlay Mode)")
    print("=" * 50)
    print(f"  eBird DB:       {ebird_db}")
    print(f"  iNat DB:        {inat_db}")
    print(f"  Date range:     {args.start_date or 'all'} to {args.end_date or 'all'}")
    print(f"  Distance thresh: {args.dist} km")
    print(f"  Time thresh:    {args.time} min")
    print(f"  Display TZ:     {args.tz}")
    print(f"\n  Two-phase algorithm:")
    print(f"    1. Cluster iNaturalist observations by proximity (space + time)")
    print(f"    2. Overlay eBird checklists onto same-date iNat clusters")
    print(f"       eBird observations assigned the session's END TIME")
    print()

    # Phase 1: Read data
    print("  Reading iNaturalist observations...")
    inat_obs = read_inat_observations(inat_db, args.start_date, args.end_date)
    print(f"    Found {len(inat_obs)} iNaturalist observations")

    print("  Reading eBird checklists...")
    ebird_cls = read_ebird_checklists(ebird_db, args.start_date, args.end_date)
    print(f"    Found {len(ebird_cls)} eBird checklists")

    if not inat_obs:
        print("\n  No iNaturalist observations to cluster. Exiting.")
        return

    # Phase 1: Cluster iNat
    print(f"\n  Phase 1: Clustering {len(inat_obs)} iNaturalist observations...")
    sessions = cluster_inat_obs(inat_obs, dist_km=args.dist, time_min=args.time)
    print(f"    Created {len(sessions)} iNat session(s)")

    # Phase 2: Overlay eBird
    print(f"\n  Phase 2: Overlaying {len(ebird_cls)} eBird checklists onto sessions...")
    sessions, unmatched = overlay_ebird(sessions, ebird_cls, dist_km=args.dist)
    print(f"    Matched: {len(ebird_cls) - len(unmatched)} checklists")
    print(f"    Unmatched (eBird-only sessions): {len(unmatched)} checklists")

    # Report
    print_session_report(sessions, local_tz_name=args.tz, csv_output=args.csv)

    # Write DB
    if not args.no_db and session_db:
        write_session_db(session_db, sessions, species_lookup=species_lookup, append=False)


if __name__ == "__main__":
    main()
