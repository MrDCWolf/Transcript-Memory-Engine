async def ingest_transcripts(
    settings: Settings,
    start_date: str | None = None,
    end_date: str | None = None,
    timezone: str = "UTC",
) -> None:
    """Ingest transcripts from the Limitless API into the database.

    Args:
        settings: Application settings.
        start_date: Start date in YYYY-MM-DD format. If None, fetches all available.
        end_date: End date in YYYY-MM-DD format. If None, uses current date.
        timezone: IANA timezone specifier. Defaults to UTC.
    """
    logger.info("Starting transcript ingestion...")
    if not settings.limitless_api_key:
        logger.error("Limitless API key is missing in configuration.")
        raise ValueError("Limitless API key not configured.")

    try:
        # Fetch transcripts from the API
        transcripts = await fetch_transcripts(
            api_key=settings.limitless_api_key,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )

        if not transcripts:
            logger.warning("No transcripts found to ingest.")
            return

        logger.info(f"Fetched {len(transcripts)} transcripts from the API.")

        # Insert transcripts into the database
        with get_db() as conn:
            cursor = conn.cursor()
            for transcript in transcripts:
                cursor.execute(
                    """
                    INSERT INTO transcripts (title, content, start_time, end_time)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        transcript.title,
                        transcript.content,
                        transcript.start_time,
                        transcript.end_time,
                    ),
                )
            conn.commit()

        logger.info(f"Successfully ingested {len(transcripts)} transcripts into the database.")

    except Exception as e:
        logger.error(f"Error during transcript ingestion: {e}", exc_info=True)
        raise 