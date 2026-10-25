"""Brownfield enhancement: owner-scoped daily click aggregation."""
from collections import Counter
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from shortener.models import Click

def daily_report(session: Session, code: str) -> dict[str, object]:
    timestamps = session.scalars(select(Click.timestamp).where(Click.code == code)).all()
    counts = Counter(datetime.fromtimestamp(t, UTC).date().isoformat() for t in timestamps)
    return {"code": code, "total": len(timestamps), "daily": dict(sorted(counts.items()))}
