#!/usr/bin/env python3
"""Populate role_info.image_url from Wikidata (property P18).

Reads a role_info CSV, queries Wikidata once per unique group_name for the
group's members + their canonical image, then matches each CSV row back by
(group_name, member_name) and fills image_url where empty.

Usage:
    python3 scripts/image_backfill/wikidata.py [INPUT_CSV] [OUTPUT_CSV]

Defaults:
    INPUT_CSV  = scripts/image_backfill/role_info.csv
    OUTPUT_CSV = scripts/image_backfill/role_info_wikidata.csv

The script never overwrites an existing non-empty image_url; it only fills
blanks. Rows without a member_name (group-level entries) are skipped.
"""
from __future__ import annotations

import csv
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = "tsuki-bot-image-backfill/0.1 (https://github.com/vaporeon51/tsuki-bot)"

# Match the group by its English label OR any English alt-label, then collect
# every entity that's linked to it via "member of" (P463) or "part of" (P361).
# For each member we fetch the image (P18), stage name (P742), and all alt
# labels via the label service — any of those strings can be the romanized
# name we have in the CSV.
QUERY_TEMPLATE = """
SELECT DISTINCT ?member ?memberLabel ?memberAltLabel ?stageName ?image WHERE {
  ?group rdfs:label|skos:altLabel %(group_literal)s .
  { ?member wdt:P463 ?group } UNION { ?member wdt:P361 ?group }
  OPTIONAL { ?member wdt:P18 ?image }
  OPTIONAL { ?member wdt:P742 ?stageName }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
"""


def norm(s: str | None) -> str:
    """Lowercase and strip non-alphanumeric for forgiving name comparison."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def sparql_literal(s: str) -> str:
    """Quote a Python string as a SPARQL "..."@en literal."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"@en'


def query_group(group_name: str) -> list[dict]:
    query = QUERY_TEMPLATE % {"group_literal": sparql_literal(group_name)}
    resp = requests.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def candidate_names(binding: dict) -> list[str]:
    names = []
    for field in ("memberLabel", "stageName"):
        val = binding.get(field, {}).get("value")
        if val:
            names.append(val)
    alt = binding.get("memberAltLabel", {}).get("value")
    if alt:
        names.extend(n.strip() for n in alt.split(",") if n.strip())
    return names


def main() -> int:
    default_in = Path(__file__).parent / "role_info.csv"
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_in
    out_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else in_path.with_name(in_path.stem + "_wikidata.csv")
    )

    with in_path.open() as f:
        rows = list(csv.DictReader(f))

    if "image_url" not in rows[0]:
        print(f"[!] {in_path} has no image_url column", file=sys.stderr)
        return 1

    groups = sorted({r["group_name"] for r in rows if r.get("group_name")})
    print(f"Querying Wikidata for {len(groups)} unique group names...\n")

    # (norm_group, norm_member) -> image_url
    image_lookup: dict[tuple[str, str], str] = {}
    per_group_hits: dict[str, int] = defaultdict(int)

    for group_name in groups:
        ng = norm(group_name)
        try:
            bindings = query_group(group_name)
        except Exception as e:
            print(f"  [!] {group_name!r}: SPARQL query failed: {e}")
            continue

        members_seen: set[str] = set()
        for b in bindings:
            members_seen.add(b["member"]["value"])
            image_url = b.get("image", {}).get("value")
            if not image_url:
                continue
            for name in candidate_names(b):
                image_lookup[(ng, norm(name))] = image_url
            per_group_hits[group_name] += 1

        print(
            f"  {group_name}: {len(members_seen)} member records, "
            f"{per_group_hits[group_name]} with images"
        )
        time.sleep(0.3)  # be polite to the Wikidata endpoint

    # Match back to CSV rows, only filling blanks.
    individual_rows = 0
    filled = 0
    already_filled = 0
    unmatched: list[tuple[str, str]] = []
    for row in rows:
        if not row.get("member_name"):
            continue
        individual_rows += 1
        if row.get("image_url"):
            already_filled += 1
            continue
        key = (norm(row["group_name"]), norm(row["member_name"]))
        url = image_lookup.get(key)
        if url:
            row["image_url"] = url
            filled += 1
        else:
            unmatched.append((row["member_name"], row["group_name"]))

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"\nSummary: {filled} new images filled, {already_filled} already had one, "
        f"{len(unmatched)} still missing (of {individual_rows} individual rows)."
    )
    if unmatched:
        preview = unmatched[:20]
        print(f"\nFirst {len(preview)} unmatched:")
        for member, group in preview:
            print(f"  - {member} [{group}]")
        if len(unmatched) > len(preview):
            print(f"  ... and {len(unmatched) - len(preview)} more")

    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
