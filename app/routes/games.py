"""Jogos: search Ludopedia and see which games the podcast already covered."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ludopedia
from app.db import get_db
from app.models import Game, Member, Theme, theme_games
from app.web import current_member, render

router = APIRouter(prefix="/jogos")


@router.get("")
def games(
    request: Request, q: str = "", page: int = 1, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    results, total, error = [], 0, None
    if q.strip():
        try:
            results, total = ludopedia.search(q, page=max(1, page))
        except ludopedia.LudopediaError as e:
            error = str(e)
    covered = db.scalars(select(Game).where(Game.id.in_(select(theme_games.c.game_id))).order_by(Game.name)).all()
    covered_ids = {g.id for g in covered}
    return render(
        request,
        "games.html",
        me,
        q=q,
        page=page,
        results=results,
        total=total,
        error=error,
        covered=covered,
        covered_ids=covered_ids,
        ready=ludopedia.configured(),
    )


@router.get("/{game_id}")
def game_page(game_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    try:
        game = ludopedia.get_game(db, game_id)
    except ludopedia.LudopediaError as e:
        raise HTTPException(502, str(e))
    episodes = sorted(game.episodes, key=lambda t: (t.published_on is None, t.published_on), reverse=False)
    open_episodes = db.scalars(
        select(Theme).where(Theme.status.in_(["ideia", "pauta", "agendado"])).order_by(Theme.title)
    ).all()
    return render(
        request,
        "game.html",
        me,
        game=game,
        episodes=episodes,
        open_episodes=[t for t in open_episodes if game not in t.games],
    )


@router.post("/{game_id}/episodio")
def add_to_episode(
    game_id: int, theme_id: int = Form(...), _me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    theme = db.get(Theme, theme_id)
    if not theme:
        raise HTTPException(404, "Episódio não encontrado.")
    try:
        game = ludopedia.get_game(db, game_id)
    except ludopedia.LudopediaError as e:
        raise HTTPException(502, str(e))
    if game not in theme.games:
        theme.games.append(game)
        db.commit()
    return RedirectResponse(f"/jogos/{game_id}", status_code=303)
