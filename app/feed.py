"""Import published episodes from the podcast's RSS feed."""

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from html import unescape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Member, Theme

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
MAX_BYTES = 20 * 1024 * 1024


class FeedError(Exception):
    pass


@dataclass
class FeedEpisode:
    guid: str
    title: str
    published_on: date | None
    url: str
    number: int | None
    description: str


def fetch(url: str) -> bytes:
    if not url.startswith(("http://", "https://")):
        raise FeedError("Use o endereço completo do feed (https://…).")
    req = urllib.request.Request(url, headers={"User-Agent": "entaoganhei"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(MAX_BYTES + 1)
    except OSError as e:
        raise FeedError(f"Não consegui baixar o feed: {e}") from e
    if len(body) > MAX_BYTES:
        raise FeedError("Feed grande demais.")
    return body


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def _plain(html: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", html, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clean_title(title: str) -> str:
    # Spotify for Creators titles often carry zero-width joiners and no-break spaces.
    title = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", title)
    return re.sub(r"\s+", " ", title.replace("\xa0", " ")).strip()


def parse(xml: bytes) -> list[FeedEpisode]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise FeedError("Isso não parece um feed RSS válido.") from e
    episodes = []
    for item in root.iter("item"):
        title = _clean_title(_text(item, "title"))
        if not title:
            continue
        published = None
        if raw := _text(item, "pubDate"):
            try:
                published = parsedate_to_datetime(raw).date()
            except (TypeError, ValueError):
                pass
        number = _text(item, f"{ITUNES}episode")
        enclosure = item.find("enclosure")
        url = _text(item, "link") or (enclosure.get("url", "") if enclosure is not None else "")
        episodes.append(
            FeedEpisode(
                guid=_text(item, "guid") or url or title,
                title=title,
                published_on=published,
                url=url,
                number=int(number) if number.isdigit() else None,
                description=_plain(_text(item, "description"))[:4000],
            )
        )
    if not episodes and root.find(".//channel") is None:
        raise FeedError("Isso não parece um feed RSS de podcast.")
    return episodes


def import_episodes(db: Session, episodes: list[FeedEpisode], by: Member) -> tuple[int, int]:
    """Creates a published episode per feed item not seen before (matched by
    guid, or by title for episodes added by hand). Returns (created, skipped)."""
    known_guids = set(db.scalars(select(Theme.feed_guid).where(Theme.feed_guid.is_not(None))).all())
    known_titles = {t.strip().lower() for t in db.scalars(select(Theme.title)).all()}
    created = skipped = 0
    for ep in episodes:
        if ep.guid in known_guids or ep.title.strip().lower() in known_titles:
            skipped += 1
            continue
        db.add(
            Theme(
                title=ep.title[:200],
                description=ep.description,
                status="publicado",
                number=ep.number,
                episode_url=ep.url[:500],
                published_on=ep.published_on,
                feed_guid=ep.guid[:300],
                created_by_id=by.id,
            )
        )
        known_guids.add(ep.guid)
        known_titles.add(ep.title.strip().lower())
        created += 1
    db.commit()
    return created, skipped
