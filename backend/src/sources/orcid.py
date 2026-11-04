"""Recent works of a followed author via the public ORCID API (no key needed)."""
from __future__ import annotations

from datetime import datetime

import httpx

ORCID_WORKS_URL = "https://pub.orcid.org/v3.0/{orcid}/works"


def _work_date(summary: dict) -> tuple[datetime | None, bool]:
    """Returns (date, precise). ORCID often has only a year; such works get Dec 31 of
    that year so a year-only 2026 work still counts as recent in November 2026."""
    pd = summary.get("publication-date") or {}
    try:
        year = int((pd.get("year") or {}).get("value"))
    except (TypeError, ValueError):
        return None, False
    month = (pd.get("month") or {}).get("value")
    day = (pd.get("day") or {}).get("value")
    if not month:
        return datetime(year, 12, 31), False
    try:
        return datetime(year, int(month), int(day or 1)), bool(day)
    except ValueError:
        return datetime(year, 12, 31), False


async def orcid_recent_dois(orcid: str, since: datetime) -> list[str]:
    """DOIs of works dated on/after `since` (works without a date are included)."""
    dois: list[str] = []
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(ORCID_WORKS_URL.format(orcid=orcid), headers={"Accept": "application/json"}, timeout=20.0)
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception as e:
        print(f"ORCID fetch failed for {orcid}: {e}")
        return []

    since_naive = since.replace(tzinfo=None)
    for group in data.get("group", []):
        for summary in group.get("work-summary", []):
            date, _precise = _work_date(summary)
            if date is not None and date < since_naive:
                continue
            for ext in (summary.get("external-ids") or {}).get("external-id", []):
                if (ext.get("external-id-type") or "").lower() == "doi" and ext.get("external-id-value"):
                    dois.append(ext["external-id-value"].strip().lower())
                    break
    return list(dict.fromkeys(dois))
