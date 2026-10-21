"""One-off: snapshot programs' structured eligibility into the eval dataset.

    python -m evals.snapshot_programs 3624 3686 ...

Reads (SELECT only) through Neon's HTTPS SQL endpoint rather than asyncpg,
since outbound 5432 is blocked on some networks. This is public catalog data,
so the snapshot is committed -- it keeps eval runs independent of Postgres.
"""
import json
import sys
from urllib.parse import urlparse

import httpx

from daad_search.config import settings

from .datasets import DATASETS_DIR


def fetch_snapshots(program_ids: list[int]) -> list[dict]:
    conn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    resp = httpx.post(
        f"https://{urlparse(conn).hostname}/sql",
        headers={"Neon-Connection-String": conn},
        json={
            "query": "SELECT p.id AS program_id, p.course_name, e.structured_eligibility "
                     "FROM programs p JOIN eligibility e ON e.program_id = p.id "
                     "WHERE p.id = ANY($1) ORDER BY p.id",
            "params": [program_ids],
        },
        timeout=60,
    )
    resp.raise_for_status()
    rows = resp.json()["rows"]
    missing = set(program_ids) - {r["program_id"] for r in rows}
    if missing:
        raise SystemExit(f"No eligibility data for program(s): {sorted(missing)}")
    return rows


def main(argv: list[str]) -> None:
    rows = fetch_snapshots([int(a) for a in argv])
    out = DATASETS_DIR / "program_snapshots.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} snapshots to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
