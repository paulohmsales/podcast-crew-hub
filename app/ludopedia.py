"""Ludopedia's LudoAPI (https://ludopedia.com.br/api/documentacao.html).

Auth is the access_token Ludopedia generates for the app's owner when the app
is registered at https://ludopedia.com.br/aplicativos; it goes in
LUDOPEDIA_TOKEN. Game data is public, so the owner's token is enough.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Game

API = "https://ludopedia.com.br/api/v1"
SEARCH_TTL = 600  # seconds
DETAIL_MAX_AGE_DAYS = 30

MECHANICS_TTL = 24 * 3600

_search_cache: dict[tuple[str, int, int | None], tuple[float, dict]] = {}
_mechanics_cache: list = []  # [expires_at, [(id, name), ...]]


class LudopediaError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("LUDOPEDIA_TOKEN"))


def _get(path: str, params: dict | None = None) -> dict:
    token = os.environ.get("LUDOPEDIA_TOKEN", "")
    if not token:
        raise LudopediaError("A integração com a Ludopedia ainda não foi configurada (LUDOPEDIA_TOKEN).")
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "entaoganhei"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise LudopediaError("A Ludopedia recusou o token (LUDOPEDIA_TOKEN inválido ou expirado).") from e
        if e.code == 404:
            raise LudopediaError("Jogo não encontrado na Ludopedia.") from e
        raise LudopediaError(f"A Ludopedia respondeu com erro {e.code}.") from e
    except (OSError, ValueError) as e:
        raise LudopediaError(f"Não consegui falar com a Ludopedia: {e}") from e


def search(query: str, page: int = 1, rows: int = 20, mechanic: int | None = None) -> tuple[list[dict], int]:
    """Games whose name matches and/or that use a mechanic, most popular first.
    Returns (results, total); each result has id, name, original_name, thumb, link."""
    query = query.strip()
    if not query and not mechanic:
        return [], 0
    key = (query.lower(), page, mechanic)
    hit = _search_cache.get(key)
    if hit and hit[0] > time.monotonic():
        data = hit[1]
    else:
        params = {"page": page, "rows": rows}
        if query:
            params["search"] = query
        if mechanic:
            params["id_mecanica"] = mechanic  # in the API docs' text, not its parameter list
        data = _get("/jogos", params)
        _search_cache[key] = (time.monotonic() + SEARCH_TTL, data)
    results = [
        {
            "id": j["id_jogo"],
            "name": j.get("nm_jogo") or "",
            "original_name": j.get("nm_original") or "",
            "thumb": j.get("thumb") or "",
            "link": _fix_link(j.get("link") or ""),
        }
        for j in data.get("jogos") or []
    ]
    return results, int(data.get("total") or len(results))


def mechanics() -> list[tuple[int, str]]:
    """All of Ludopedia's mechanics as (id, name), alphabetical. Cached for a day."""
    if _mechanics_cache and _mechanics_cache[0] > time.monotonic():
        return _mechanics_cache[1]
    items = [
        (m["id_mecanica"], m["nm_mecanica"])
        for m in _get("/mecanicas").get("mecanicas") or []
        if not m.get("nm_mecanica", "").endswith("_deleted")
    ]
    _mechanics_cache[:] = [time.monotonic() + MECHANICS_TTL, items]
    return items


def _fix_link(link: str) -> str:
    # The API returns "jogo/azul" in searches and sometimes "https:ludopedia.com.br/..." in details.
    if not link or link.startswith("https://"):
        return link
    if link.startswith("https:"):
        return "https://" + link[len("https:"):].lstrip("/")
    return "https://ludopedia.com.br/" + link.lstrip("/")


def _names(items, key: str) -> str:
    return "|".join(i.get(key, "") for i in items or [] if i.get(key))


def apply_details(game: Game, data: dict) -> None:
    game.name = data.get("nm_jogo") or game.name
    game.original_name = data.get("nm_original") or game.original_name or ""
    game.thumb = data.get("thumb") or game.thumb or ""
    game.link = _fix_link(data.get("link") or game.link or "")
    game.year = data.get("ano_publicacao") or None
    game.players_min = data.get("qt_jogadores_min") or None
    game.players_max = data.get("qt_jogadores_max") or None
    game.minutes = data.get("vl_tempo_jogo") or None
    game.min_age = data.get("idade_minima") or None
    game.mechanics = _names(data.get("mecanicas"), "nm_mecanica")
    game.categories = _names(data.get("categorias"), "nm_categoria")
    game.fetched_at = datetime.now()


def get_game(db: Session, game_id: int, refresh: bool = False) -> Game:
    """The cached game, loading or refreshing details from Ludopedia when needed.
    Falls back to stale cached data if Ludopedia is unreachable."""
    game = db.get(Game, game_id)
    stale = not game or not game.fetched_at or (datetime.now() - game.fetched_at).days >= DETAIL_MAX_AGE_DAYS
    if refresh or stale:
        try:
            data = _get(f"/jogos/{game_id}")
        except LudopediaError:
            if game:
                return game
            raise
        if not game:
            game = Game(id=game_id, name=data.get("nm_jogo") or f"Jogo {game_id}")
            db.add(game)
        apply_details(game, data)
        db.commit()
    return game
