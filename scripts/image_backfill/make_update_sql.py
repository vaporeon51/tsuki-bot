#!/usr/bin/env python3
"""Emit a SQL file that updates role_info.image_url from a CSV.

Reads a role_info CSV (with image_url already populated by earlier passes)
and writes a single `UPDATE role_info ... FROM (VALUES ...)` statement
covering every row whose image_url is non-empty. Runs atomically: if any
role_id is missing on the DB side, nothing changes for that row and nothing
breaks.

Usage:
    python3 scripts/image_backfill/make_update_sql.py [INPUT_CSV] [OUTPUT_SQL]

Defaults:
    INPUT_CSV  = scripts/image_backfill/role_info_wikidata.csv
    OUTPUT_SQL = scripts/image_backfill/image_url_updates.sql
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path


def sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def main() -> int:
    default_in = Path(__file__).parent / "role_info_wikidata.csv"
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_in
    out_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(__file__).parent / "image_url_updates.sql"
    )

    with in_path.open() as f:
        rows = list(csv.DictReader(f))

    pairs: list[tuple[str, str]] = []
    for row in rows:
        role_id = (row.get("role_id") or "").strip()
        image_url = (row.get("image_url") or "").strip()
        if role_id and image_url:
            pairs.append((role_id, image_url))

    if not pairs:
        print(f"[!] No rows with image_url found in {in_path}", file=sys.stderr)
        return 1

    values_lines = ",\n    ".join(
        f"({sql_quote(role_id)}, {sql_quote(url)})" for role_id, url in pairs
    )
    sql = (
        f"-- Backfill role_info.image_url for {len(pairs)} idols.\n"
        f"-- Generated from {in_path.name}.\n"
        f"UPDATE role_info AS r\n"
        f"SET image_url = v.image_url\n"
        f"FROM (VALUES\n    {values_lines}\n) AS v(role_id, image_url)\n"
        f"WHERE r.role_id = v.role_id;\n"
    )

    out_path.write_text(sql)
    print(f"Wrote {len(pairs)} updates to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
