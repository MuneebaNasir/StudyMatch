import argparse
import asyncio
import logging

from .db.session import init_db
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

    args = parser.parse_args()

    if args.command == "init-db":
        asyncio.run(init_db())
    elif args.command == "ingest":
        result = asyncio.run(run_ingestion(limit_ids=args.ids))
        print(f"Ingested {result['succeeded']}/{result['total']} programs. Failed IDs: {result['failed_ids']}")


if __name__ == "__main__":
    main()
