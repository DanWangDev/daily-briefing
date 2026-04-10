"""Shared RSS parsing utilities for Google News and Financial RSS collectors."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def parse_rss_items(xml_bytes: bytes) -> list[dict]:
    """Parse RSS 2.0 XML into a list of article dicts.

    Returns list of::

        {"title": str, "link": str, "pub_date": datetime,
         "source": str, "description": str}
    """
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        logger.warning("Failed to parse RSS XML")
        return items

    for item_el in root.iter("item"):
        title = _text(item_el, "title")
        link = _text(item_el, "link")
        if not title or not link:
            continue

        source_el = item_el.find("source")
        source = source_el.text if source_el is not None and source_el.text else ""

        items.append({
            "title": title,
            "link": link,
            "pub_date": parse_rss_date(_text(item_el, "pubDate")),
            "source": source,
            "description": _text(item_el, "description"),
        })

    return items


def parse_rss_date(date_str: str) -> datetime:
    """Parse an RSS date string (RFC 2822 or ISO 8601) into a UTC datetime."""
    if not date_str:
        return datetime.now(timezone.utc)

    # Try RFC 2822 first (standard RSS format)
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    # Try ISO 8601
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt
    except (ValueError, TypeError):
        pass

    return datetime.now(timezone.utc)


def _text(el: ET.Element, tag: str) -> str:
    """Extract text from a child element, returning empty string if missing."""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""
