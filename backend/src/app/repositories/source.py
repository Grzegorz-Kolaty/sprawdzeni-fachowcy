from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import Source


def get_source_by_url(
    db: Session,
    url: str,
) -> Source | None:
    statement = select(Source).where(Source.url == url)

    return db.scalar(statement)


def get_or_create_source(
    db: Session,
    *,
    url: str,
    source_type: str,
    title: str | None,
) -> Source:
    source = get_source_by_url(
        db,
        url,
    )

    if source is not None:
        source.fetched_at = datetime.now(UTC)
        source.source_type = source_type

        if title is not None:
            source.title = title

        return source

    source = Source(
        url=url,
        source_type=source_type,
        title=title,
    )

    db.add(source)

    return source


def get_source(
    db: Session,
    source_id: int,
) -> Source | None:
    return db.get(
        Source,
        source_id,
    )
