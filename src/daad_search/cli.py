import argparse
import asyncio
import logging

from .db.session import init_db
from .extraction.pipeline import run_extraction
from .ingestion.pipeline import run_ingestion


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="daad-search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create Postgres tables")

    ingest_parser = subparsers.add_parser("ingest", help="Run the full ingestion pipeline")
    ingest_parser.add_argument(
        "--ids", type=int, nargs="*", default=None,
        help="Only ingest these DAAD program IDs (for testing)",
    )
    ingest_parser.add_argument(
        "--refresh", action="store_true",
        help="Ignore cached DAAD responses and re-fetch everything for this run",
    )

    extract_parser = subparsers.add_parser(
        "extract", help="Extract structured eligibility criteria for programs missing it"
    )
    extract_parser.add_argument(
        "--ids", type=int, nargs="*", default=None,
        help="Only extract these DAAD program IDs (for testing)",
    )
    extract_parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most this many programs this run (e.g. to respect a daily quota)",
    )

    args = parser.parse_args()

    if args.command == "init-db":
        asyncio.run(init_db())
    elif args.command == "ingest":
        result = asyncio.run(run_ingestion(limit_ids=args.ids, refresh=args.refresh))
        print(
            f"Ingested {result['succeeded']}/{result['total']} programs. "
            f"Failed IDs: {result['failed_ids']}"
        )
        print(
            f"Embedded {result['embedded']}/{result['succeeded']} programs. "
            f"Embedding failures: {len(result['embedding_failed_ids'])} "
            f"{result['embedding_failed_ids']}"
        )
        if result["reconciled_ids"]:
            print(
                f"Reconciled away {len(result['reconciled_ids'])} programs "
                f"no longer listed by DAAD: {result['reconciled_ids']}"
            )
    elif args.command == "extract":
        result = asyncio.run(run_extraction(limit_ids=args.ids, limit=args.limit))
        print(
            f"Extracted eligibility for {result['succeeded']}/{result['total_candidates']} "
            f"candidate programs. Failed IDs: {result['failed_ids']}"
        )
        if result["stopped_early"]:
            print(
                "Stopped early after repeated consecutive failures (likely quota exhausted). "
                "Re-run `extract` later to resume."
            )


if __name__ == "__main__":
    main()
