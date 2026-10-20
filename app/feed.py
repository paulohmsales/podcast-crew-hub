"""Import published episodes from the podcast's RSS feed or its Spotify show.

Spotify needs a developer app (https://developer.spotify.com/dashboard) whose
client id/secret go in SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET; the show's
episodes are public, so the client-credentials flow is enough.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
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


EPISODE_PREFIX = re.compile(r"^(?:Ent[aã]o Ganhei!?\s*[:\-–|]\s*)?(?:Ep(?:is[oó]dio)?\.?\s*#?(\d+)\s*[:\-–|]?\s*)?", re.I)


def tidy_title(title: str) -> tuple[str, int | None]:
    """"Então Ganhei!: Ep.42 - Turno Duplo" → ("Turno Duplo", 42)."""
    title = _clean_title(title)
    m = EPISODE_PREFIX.match(title)
    rest = title[m.end():].strip() if m else title
    number = int(m.group(1)) if m and m.group(1) else None
    return (rest or title), number


def parse(xml: bytes) -> list[FeedEpisode]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise FeedError("Isso não parece um feed RSS válido.") from e
    episodes = []
    for item in root.iter("item"):
        title, title_number = tidy_title(_text(item, "title"))
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
                number=int(number) if number.isdigit() else title_number,
                description=_plain(_text(item, "description"))[:4000],
            )
        )
    if not episodes and root.find(".//channel") is None:
        raise FeedError("Isso não parece um feed RSS de podcast.")
    return episodes


SHOW_URL = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?show/([A-Za-z0-9]{22})")


def spotify_show_id(url: str) -> str | None:
    m = SHOW_URL.search(url)
    return m.group(1) if m else None


def _spotify_token() -> str:
    cid, secret = os.environ.get("SPOTIFY_CLIENT_ID", ""), os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not cid or not secret:
        raise FeedError("Importar do Spotify precisa de SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no servidor.")
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise FeedError(f"O Spotify recusou as credenciais ({e.code}).") from e
    except (OSError, ValueError, KeyError) as e:
        raise FeedError(f"Não consegui falar com o Spotify: {e}") from e


def fetch_spotify(show_id: str) -> list[FeedEpisode]:
    token = _spotify_token()
    url = f"https://api.spotify.com/v1/shows/{show_id}/episodes?market=BR&limit=50"
    episodes = []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                page = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise FeedError(f"O Spotify respondeu com erro {e.code} ao listar os episódios.") from e
        except (OSError, ValueError) as e:
            raise FeedError(f"Não consegui falar com o Spotify: {e}") from e
        for item in page.get("items") or []:
            if not item:
                continue
            title, number = tidy_title(item.get("name") or "")
            released = item.get("release_date") or ""
            precise = item.get("release_date_precision") == "day"
            episodes.append(
                FeedEpisode(
                    guid=f"spotify:episode:{item['id']}",
                    title=title,
                    published_on=date.fromisoformat(released) if precise else None,
                    url=(item.get("external_urls") or {}).get("spotify", ""),
                    number=number,
                    description=(item.get("description") or "")[:4000],
                )
            )
        url = page.get("next")
    return episodes


def load(source: str) -> list[FeedEpisode]:
    """Episodes from a Spotify show link or an RSS feed URL."""
    source = source.strip()
    if show_id := spotify_show_id(source):
        return fetch_spotify(show_id)
    return parse(fetch(source))


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
