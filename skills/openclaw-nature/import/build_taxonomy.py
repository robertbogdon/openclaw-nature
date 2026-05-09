#!/usr/bin/env python3
"""
OpenClaw Nature — Taxonomy Builder

Creates a canonical species/taxonomy table from eBird and iNaturalist data,
cross-referencing by scientific name.

Output:
  - Adds `species`, `ebird_species_map`, `inat_species_map` tables
    to the openclaw-nature.db database
  - Prints a report of matched/unmatched species

Algorithm:
  1. Read all unique species from eBird DB (common_name + scientific_name)
  2. Read all unique species from iNat DB (species_guess + taxon_name)
  3. Cross-reference by case-insensitive scientific name exact match
  4. Canonical display name: eBird common name preferred if available,
     otherwise iNat preferred common name, otherwise species_guess
  5. Report unmatched entries for manual review

Usage:
    python3 import/build_taxonomy.py
    python3 import/build_taxonomy.py --ebird-db ../ebird/ebird.db
    python3 import/build_taxonomy.py --session-db import/openclaw-nature.db

Stdlib only — no external dependencies.
"""

import sqlite3
import sys
import os

# ── Paths (auto-discover siblings) ────────────────────────────────────

IMPORT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(IMPORT_DIR)

DEFAULT_EBIRD_DB = os.path.join(
    SKILL_DIR, "..", "ebird", "ebird.db"  # sibling ebird skill
)
DEFAULT_INAT_DB = os.path.join(
    SKILL_DIR, "..", "inaturalist", "import", "inat.db"  # sibling inat skill
)
DEFAULT_SESSION_DB = os.path.join(IMPORT_DIR, "openclaw-nature.db")

# Known fallback paths for when the script is run from a skill directory
# that might not have siblings at the expected relative path:
FALLBACK_EBIRD_DB = os.path.expanduser(
    "~/.openclaw/workspace/zookeeper/modules/ebird/ebird.db"
)
FALLBACK_INAT_DB = os.path.expanduser(
    "~/.openclaw/workspace/skills/inaturalist/import/inat.db"
)


# ── Schema ────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS species (
    id              INTEGER PRIMARY KEY,
    canonical       TEXT NOT NULL UNIQUE,
    scientific      TEXT,
    taxon_group     TEXT,
    category        TEXT DEFAULT 'species'
);

CREATE TABLE IF NOT EXISTS ebird_species_map (
    species_id      INTEGER REFERENCES species(id),
    taxon_code      TEXT,
    display_name    TEXT,
    scientific      TEXT,
    UNIQUE(species_id, taxon_code)
);

CREATE TABLE IF NOT EXISTS inat_species_map (
    species_id      INTEGER REFERENCES species(id),
    taxon_id        INTEGER,
    display_name    TEXT,
    scientific      TEXT,
    rank            TEXT DEFAULT 'species',
    UNIQUE(species_id, taxon_id)
);
"""


# ── Helpers ────────────────────────────────────────────────────────────

TAXON_GROUP_MAP = {
    "Animalia": "animal",
    "Aves": "bird",
    "Mammalia": "mammal",
    "Amphibia": "amphibian",
    "Reptilia": "reptile",
    "Actinopterygii": "fish",
    "Insecta": "insect",
    "Arachnida": "arachnid",
    "Mollusca": "mollusc",
    "Fungi": "fungus",
    "Plantae": "plant",
    "Chromista": "chromist",
    "Protozoa": "protozoan",
    "Unknown": "unknown",
}


def _taxon_group(iconic_name):
    """Map iNat iconic taxon name to a simple group string."""
    if not iconic_name:
        return "unknown"
    return TAXON_GROUP_MAP.get(iconic_name, iconic_name.lower())


def _normalize_scientific(name):
    """Case-insensitive comparison key for scientific names."""
    if not name:
        return ""
    return name.strip().lower()


def _resolve_db_path(path, fallback=None):
    """Resolve a DB path, checking absolute path then fallback."""
    abspath = os.path.abspath(path)
    if os.path.exists(abspath):
        return abspath
    if fallback and os.path.exists(fallback):
        print(f"  (fallback: using {fallback})", file=sys.stderr)
        return fallback
    return abspath


# ── Main ────────────────────────────────────────────────────────────────


class SpeciesEntry:
    """One canonical species entry with source-specific details."""

    def __init__(self, canonical, scientific="", taxon_group="unknown"):
        self.canonical = canonical
        self.scientific = scientific
        self.taxon_group = taxon_group
        self.ebird_codes = []       # [(code, display_name, scientific)]
        self.inat_ids = []          # [(taxon_id, display_name, scientific, rank)]
        self.source = ""            # "ebird", "inat", or "both"


def collect_ebird_species(ebird_db_path):
    """Read all unique species from the eBird database.

    Returns dict: normalized_scientific -> SpeciesEntry
    """
    conn = sqlite3.connect(ebird_db_path)
    rows = conn.execute(
        "SELECT DISTINCT common_name, scientific_name "
        "FROM observations ORDER BY common_name"
    ).fetchall()
    conn.close()

    species = {}
    for common_name, scientific_name in rows:
        key = _normalize_scientific(scientific_name)
        if key not in species:
            canonical = common_name or scientific_name or "Unknown"
            entry = SpeciesEntry(canonical, scientific_name or "", "bird")
            # Use the common_name as a pseudo-code for mapping
            entry.source = "ebird"
            species[key] = entry
        # Add eBird mapping (code is first letter of each word, lower)
        # eBird doesn't have a per-dataset code, so we use common_name
        common = common_name or ""
        sci = scientific_name or ""
        species[key].ebird_codes.append((common, common, sci))

    return species


def collect_inat_species(inat_db_path):
    """Read all unique species from the iNat database.

    Returns tuple: (species dict, list of (sciname, conflict_info) for review)
    """
    conn = sqlite3.connect(inat_db_path)
    rows = conn.execute(
        "SELECT DISTINCT species_guess, taxon_name, taxon_id, "
        "taxon_rank, taxon_preferred_common_name, taxon_iconic_taxon_name "
        "FROM observations "
        "WHERE species_guess IS NOT NULL "
        "ORDER BY species_guess"
    ).fetchall()
    conn.close()

    species = {}
    conflicts = []

    for species_guess, taxon_name, taxon_id, taxon_rank, pref_common, iconic in rows:
        key = _normalize_scientific(taxon_name)
        display_name = pref_common or species_guess or taxon_name or "Unknown"
        group = _taxon_group(iconic)

        if key not in species:
            entry = SpeciesEntry(display_name, taxon_name or "", group)
            entry.source = "inat"
            species[key] = entry
        else:
            # Check for conflicts
            existing = species[key]
            existing.source = "both"
            # If display names differ, flag for review
            if display_name != existing.canonical:
                conflicts.append(
                    (taxon_name, existing.canonical, display_name)
                )

        species[key].inat_ids.append(
            (taxon_id, display_name, taxon_name or "", taxon_rank or "species")
        )

    return species, conflicts


def merge_species(ebird_species, inat_species, conflicts):
    """Merge eBird and iNat species into a canonical list.

    Prioritizes:
      - eBird common name as canonical (more standardized for birds)
      - iNat display name for non-bird taxa
    """
    all_keys = set(ebird_species.keys()) | set(inat_species.keys())
    merged = []
    unmatched_ebird = []
    unmatched_inat = []

    for key in sorted(all_keys):
        eb_entry = ebird_species.get(key)
        inat_entry = inat_species.get(key)

        if eb_entry and inat_entry:
            # Both sources agree on this species
            entry = SpeciesEntry(
                canonical=eb_entry.canonical,  # eBird names are more standardized
                scientific=key,
                taxon_group=eb_entry.taxon_group or inat_entry.taxon_group,
            )
            entry.source = "both"
            entry.ebird_codes = eb_entry.ebird_codes
            entry.inat_ids = inat_entry.inat_ids
            merged.append(entry)

        elif eb_entry:
            # Only in eBird
            entry = SpeciesEntry(
                canonical=eb_entry.canonical,
                scientific=key,
                taxon_group=eb_entry.taxon_group,
            )
            entry.source = "ebird"
            entry.ebird_codes = eb_entry.ebird_codes
            merged.append(entry)
            unmatched_ebird.append(entry)

        elif inat_entry:
            # Only in iNat
            entry = SpeciesEntry(
                canonical=inat_entry.canonical,
                scientific=key,
                taxon_group=inat_entry.taxon_group,
            )
            entry.source = "inat"
            entry.inat_ids = inat_entry.inat_ids
            merged.append(entry)
            unmatched_inat.append(entry)

    return merged, unmatched_ebird, unmatched_inat


def write_species_db(session_db_path, merged_species, conflicts):
    """Write the species + mapping tables to the session DB."""
    conn = sqlite3.connect(session_db_path)

    # Create tables
    conn.executescript(SCHEMA_SQL)

    # Clear existing data (rebuild mode)
    conn.execute("DELETE FROM ebird_species_map")
    conn.execute("DELETE FROM inat_species_map")
    conn.execute("DELETE FROM species")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('species', 'ebird_species_map', 'inat_species_map')")

    for entry in merged_species:
        conn.execute(
            "INSERT INTO species (canonical, scientific, taxon_group, category) "
            "VALUES (?, ?, ?, 'species')",
            (entry.canonical, entry.scientific, entry.taxon_group),
        )
        species_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for code, display, sci in entry.ebird_codes:
            conn.execute(
                "INSERT INTO ebird_species_map (species_id, taxon_code, display_name, scientific) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(species_id, taxon_code) DO NOTHING",
                (species_id, code, display, sci or entry.scientific),
            )

        for tid, display, sci, rank in entry.inat_ids:
            conn.execute(
                "INSERT INTO inat_species_map (species_id, taxon_id, display_name, scientific, rank) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(species_id, taxon_id) DO NOTHING",
                (species_id, tid, display, sci or entry.scientific, rank),
            )

    conn.commit()
    conn.close()


def print_report(
    merged_species,
    unmatched_ebird,
    unmatched_inat,
    conflicts,
    show_matched=False,
):
    """Print a formatted taxonomy report."""
    total = len(merged_species)
    matched = total - len(unmatched_ebird) - len(unmatched_inat)
    # Count "both" source entries properly
    both = sum(1 for s in merged_species if s.source == "both")

    print(f"\n  ── Taxonomy Report ──")
    print(f"  Canonical species:  {total}")
    print(f"  In both sources:    {both}")
    print(f"  eBird only:         {len(unmatched_ebird)}")
    print(f"  iNat only:          {len(unmatched_inat)}")
    print(f"  Name conflicts:     {len(conflicts)}")
    print()

    if show_matched and both > 0:
        print("  ── Matched (in both sources) ──")
        for entry in merged_species:
            if entry.source == "both":
                ebird_name = (
                    entry.ebird_codes[0][1] if entry.ebird_codes else ""
                )
                print(
                    f"    {entry.canonical:35s}  {entry.scientific:35s}"
                    f"  [{entry.taxon_group}]"
                )
        print()

    if unmatched_ebird:
        print("  ── eBird-only species ──")
        for entry in unmatched_ebird:
            print(f"    {entry.canonical:35s}  {entry.scientific or ''}")
        print()

    if unmatched_inat:
        print("  ── iNat-only species ──")
        for entry in unmatched_inat:
            print(f"    {entry.canonical:35s}  {entry.scientific or ''}")
        print()

    if conflicts:
        print("  ── Name conflicts (same scientific, diff display) ──")
        for sci, ebird_name, inat_name in conflicts:
            print(f"    {sci:35s}  eBird: {ebird_name:30s}  iNat: {inat_name}")
        print()


# ── Entry point ────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build canonical taxonomy from eBird + iNat"
    )
    parser.add_argument(
        "--ebird-db",
        default=None,
        help=f"Path to eBird database (default: auto-discover)",
    )
    parser.add_argument(
        "--inat-db",
        default=None,
        help=f"Path to iNaturalist database (default: auto-discover)",
    )
    parser.add_argument(
        "--session-db",
        default=None,
        help=f"Path to session database (default: {DEFAULT_SESSION_DB})",
    )
    parser.add_argument(
        "--show-matched",
        action="store_true",
        help="Show matched species in report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report without writing to DB",
    )

    args = parser.parse_args()

    ebird_db_path = _resolve_db_path(
        args.ebird_db or DEFAULT_EBIRD_DB, FALLBACK_EBIRD_DB
    )
    inat_db_path = _resolve_db_path(
        args.inat_db or DEFAULT_INAT_DB, FALLBACK_INAT_DB
    )
    session_db_path = args.session_db or DEFAULT_SESSION_DB

    print(
        f"OpenClaw Nature — Taxonomy Builder\n"
        f"====================================\n"
        f"  eBird DB:  {ebird_db_path}\n"
        f"  iNat DB:   {inat_db_path}\n"
        f"  Output DB: {session_db_path}\n"
    )

    # Verify source DBs exist
    for label, path in [
        ("eBird", ebird_db_path),
        ("iNat", inat_db_path),
    ]:
        if not os.path.exists(path):
            print(f"  ERROR: {label} database not found: {path}")
            sys.exit(1)

    print("  Reading eBird species...")
    ebird_species = collect_ebird_species(ebird_db_path)
    print(f"    Found {len(ebird_species)} unique species")

    print("  Reading iNaturalist species...")
    inat_species, conflicts = collect_inat_species(inat_db_path)
    print(f"    Found {len(inat_species)} unique species")

    print("  Merging...")
    merged, unmatched_eb, unmatched_inat = merge_species(
        ebird_species, inat_species, conflicts
    )
    print(f"    {len(merged)} canonical species")

    print_report(
        merged, unmatched_eb, unmatched_inat, conflicts,
        show_matched=args.show_matched,
    )

    if args.dry_run:
        print("  Dry run — no data written.\n")
        return

    print("  Writing to database...")
    write_species_db(session_db_path, merged, conflicts)
    print(f"    Done. Tables: species, ebird_species_map, inat_species_map\n")


if __name__ == "__main__":
    main()
