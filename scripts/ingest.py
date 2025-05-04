import asyncio
import argparse
from datetime import datetime, timedelta
from transcript_engine.core.config import Settings
from transcript_engine.ingest.ingest import ingest_transcripts

def main():
    parser = argparse.ArgumentParser(description="Ingest transcripts from the Limitless API.")
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format. If not provided, fetches all available.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format. If not provided, uses current date.",
    )
    parser.add_argument(
        "--timezone",
        type=str,
        default="UTC",
        help="IANA timezone specifier. Defaults to UTC.",
    )
    args = parser.parse_args()

    settings = Settings()
    asyncio.run(
        ingest_transcripts(
            settings=settings,
            start_date=args.start_date,
            end_date=args.end_date,
            timezone=args.timezone,
        )
    )

if __name__ == "__main__":
    main() 