"""Episodes (stored as themes): the board, the list, and each episode's page."""

from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import feed, ludopedia
from app.db import get_db
from app.models import THEME_STATUSES, Game, Member, Recording, Segment, Theme, ThemeComment, ThemeVote
from app.web import admin_member, current_member, render

router = APIRouter(prefix="/episodios")
legacy = APIRouter()

SORTS = {"votos": "Mais votados", "recentes": "Mais recentes"}
BOARD_COLUMNS = ["ideia", "pauta", "agendado", "gravado", "publicado"]


@legacy.get("/temas")
@legacy.get("/temas/{rest:path}")
def old_urls(rest: str = ""):
    return RedirectResponse(f"/episodios/{rest}".rstrip("/"), status_code=301)


def _theme_or_404(db: Session, theme_id: int) -> Theme:
    theme = db.get(Theme, theme_id)
    if not theme:
        raise HTTPException(404, "Episódio não encontrado.")
    return theme


def _back(request: Request, fallback: str) -> RedirectResponse:
    # Return to the page the form was on (board, list or detail); only same-site paths.
    ref = request.headers.get("referer", "")
    path = ref.split(request.url.netloc, 1)[-1] if request.url.netloc in ref else ""
    return RedirectResponse(path if path.startswith("/") else fallback, status_code=303)


def _vote_counts(db: Session) -> dict[int, int]:
    return dict(db.execute(select(ThemeVote.theme_id, func.count()).group_by(ThemeVote.theme_id)).all())


def _next_recordings(db: Session) -> dict[int, datetime]:
    today = datetime.combine(date.today(), datetime.min.time())
    rows = db.execute(
        select(Recording.theme_id, func.min(Recording.starts_at))
        .where(Recording.theme_id.is_not(None), Recording.starts_at >= today)
        .group_by(Recording.theme_id)
    ).all()
    return dict(rows)


def set_status(theme: Theme, status: str) -> None:
    theme.status = status
    if status == "publicado" and not theme.published_on:
        theme.published_on = date.today()


@router.get("")
def episodes(
    request: Request,
    ver: str = "quadro",
    status: str = "abertos",
    ordem: str = "votos",
    q: str = "",
    quadro: int | None = None,
    descartados: bool = False,
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    segments = db.scalars(select(Segment).where(Segment.archived.is_(False)).order_by(Segment.position, Segment.name)).all()
    votes = _vote_counts(db)
    my_votes = set(db.scalars(select(ThemeVote.theme_id).where(ThemeVote.member_id == me.id)).all())
    stmt = select(Theme)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(Theme.title.ilike(like) | Theme.description.ilike(like))
    if quadro:
        stmt = stmt.where(Theme.segments.any(Segment.id == quadro))
    common = dict(segments=segments, vote_counts=votes, my_votes=my_votes, q=q, quadro=quadro, ver=ver)

    if ver == "lista":
        if status == "abertos":
            stmt = stmt.where(Theme.status.in_(["ideia", "pauta"]))
        elif status in THEME_STATUSES:
            stmt = stmt.where(Theme.status == status)
        themes = db.scalars(stmt).all()
        if ordem == "recentes":
            themes = sorted(themes, key=lambda t: t.created_at, reverse=True)
        else:
            themes = sorted(themes, key=lambda t: (-votes.get(t.id, 0), -t.created_at.timestamp()))
        counts = dict(db.execute(select(Theme.status, func.count()).group_by(Theme.status)).all())
        comment_counts = dict(
            db.execute(select(ThemeComment.theme_id, func.count()).group_by(ThemeComment.theme_id)).all()
        )
        return render(
            request, "themes.html", me,
            themes=themes, status=status, ordem=ordem, counts=counts, comment_counts=comment_counts, sorts=SORTS,
            **common,
        )

    columns = BOARD_COLUMNS + (["descartado"] if descartados else [])
    upcoming = _next_recordings(db)
    by_status: dict[str, list[Theme]] = {c: [] for c in columns}
    for theme in db.scalars(stmt.where(Theme.status.in_(columns))).all():
        by_status[theme.status].append(theme)
    far = datetime.max
    for col, items in by_status.items():
        if col in ("ideia", "pauta"):
            items.sort(key=lambda t: (-votes.get(t.id, 0), -t.created_at.timestamp()))
        elif col == "agendado":
            items.sort(key=lambda t: upcoming.get(t.id, far))
        else:  # newest first
            items.sort(key=lambda t: (t.published_on or date.min, t.number or 0, t.updated_at), reverse=True)
    return render(
        request, "board.html", me,
        columns=columns, by_status=by_status, upcoming=upcoming, descartados=descartados, **common,
    )


@router.get("/nova")
def new_theme_page(request: Request, me: Member = Depends(current_member)):
    return render(request, "episode_new.html", me)


@router.get("/importar")
def import_page(request: Request, me: Member = Depends(admin_member)):
    return render(request, "import.html", me)


@router.post("/importar")
def import_feed(
    request: Request, url: str = Form(...), me: Member = Depends(admin_member), db: Session = Depends(get_db)
):
    try:
        episodes = feed.parse(feed.fetch(url.strip()))
    except feed.FeedError as e:
        return render(request, "import.html", me, url=url, error=str(e))
    created, skipped = feed.import_episodes(db, episodes, me)
    return render(request, "import.html", me, url=url, created=created, skipped=skipped, found=len(episodes))


@router.post("")
def create_theme(
    title: str = Form(...),
    description: str = Form(""),
    links: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    title = title.strip()
    if not title:
        raise HTTPException(400, "O episódio precisa de um título.")
    theme = Theme(title=title[:200], description=description.strip(), links=links.strip(), created_by_id=me.id)
    db.add(theme)
    db.flush()
    db.add(ThemeVote(theme_id=theme.id, member_id=me.id))  # suggesting counts as wanting it
    db.commit()
    return RedirectResponse(f"/episodios/{theme.id}", status_code=303)


@router.get("/{theme_id}")
def show_theme(
    theme_id: int,
    request: Request,
    jogo: str = "",
    erro: str = "",
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    game_results, game_error = [], erro
    if jogo.strip():
        try:
            game_results, _ = ludopedia.search(jogo)
        except ludopedia.LudopediaError as e:
            game_error = str(e)
    voters = sorted((v.member for v in theme.votes), key=lambda m: m.name)
    recordings = db.scalars(select(Recording).where(Recording.theme_id == theme.id).order_by(Recording.starts_at)).all()
    return render(
        request,
        "theme.html",
        me,
        theme=theme,
        voters=voters,
        voted=any(v.id == me.id for v in voters),
        can_delete=me.is_admin or theme.created_by_id == me.id,
        recordings=recordings,
        members=db.scalars(select(Member).order_by(Member.name)).all(),
        all_segments=db.scalars(select(Segment).order_by(Segment.archived, Segment.position, Segment.name)).all(),
        jogo=jogo,
        game_results=game_results,
        game_error=game_error,
        attached={g.id for g in theme.games},
        ludopedia_ready=ludopedia.configured(),
    )


@router.post("/{theme_id}/editar")
def edit_theme(
    theme_id: int,
    title: str = Form(...),
    description: str = Form(""),
    links: str = Form(""),
    number: str = Form(""),
    episode_url: str = Form(""),
    published_on: str = Form(""),
    segment_ids: list[int] = Form([]),
    member_ids: list[int] = Form([]),
    _me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    if title.strip():
        theme.title = title.strip()[:200]
    theme.description = description.strip()
    theme.links = links.strip()
    theme.number = int(number) if number.strip().isdigit() else None
    theme.episode_url = episode_url.strip()[:500]
    try:
        theme.published_on = date.fromisoformat(published_on) if published_on else None
    except ValueError:
        raise HTTPException(400, "Data inválida.")
    theme.segments = db.scalars(select(Segment).where(Segment.id.in_(segment_ids))).all() if segment_ids else []
    theme.participants = db.scalars(select(Member).where(Member.id.in_(member_ids))).all() if member_ids else []
    db.commit()
    return RedirectResponse(f"/episodios/{theme_id}", status_code=303)


@router.post("/{theme_id}/jogos")
def add_game(
    theme_id: int, game_id: int = Form(...), _me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    theme = _theme_or_404(db, theme_id)
    try:
        game = ludopedia.get_game(db, game_id)
    except ludopedia.LudopediaError as e:
        return RedirectResponse(f"/episodios/{theme_id}?erro={quote(str(e))}#jogos", status_code=303)
    if game not in theme.games:
        theme.games.append(game)
        db.commit()
    return RedirectResponse(f"/episodios/{theme_id}#jogos", status_code=303)


@router.post("/{theme_id}/jogos/{game_id}/remover")
def remove_game(theme_id: int, game_id: int, _me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    theme.games = [g for g in theme.games if g.id != game_id]
    db.commit()
    return RedirectResponse(f"/episodios/{theme_id}#jogos", status_code=303)


@router.post("/{theme_id}/voto")
def toggle_vote(theme_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    _theme_or_404(db, theme_id)
    vote = db.get(ThemeVote, (theme_id, me.id))
    if vote:
        db.delete(vote)
    else:
        db.add(ThemeVote(theme_id=theme_id, member_id=me.id))
    db.commit()
    return _back(request, f"/episodios/{theme_id}")


@router.post("/{theme_id}/status")
def change_status(
    theme_id: int,
    request: Request,
    status: str = Form(...),
    _me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    if status not in THEME_STATUSES:
        raise HTTPException(400, "Status inválido.")
    theme = _theme_or_404(db, theme_id)
    set_status(theme, status)
    db.commit()
    if "application/json" in request.headers.get("accept", ""):  # board drag and drop
        return JSONResponse({"ok": True, "status": status})
    return _back(request, f"/episodios/{theme_id}")


@router.post("/{theme_id}/comentarios")
def add_comment(
    theme_id: int,
    body: str = Form(...),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    _theme_or_404(db, theme_id)
    if body.strip():
        db.add(ThemeComment(theme_id=theme_id, member_id=me.id, body=body.strip()))
        db.commit()
    return RedirectResponse(f"/episodios/{theme_id}#comentarios", status_code=303)


@router.post("/{theme_id}/comentarios/{comment_id}/excluir")
def delete_comment(
    theme_id: int, comment_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    comment = db.get(ThemeComment, comment_id)
    if comment and comment.theme_id == theme_id and (comment.member_id == me.id or me.is_admin):
        db.delete(comment)
        db.commit()
    return RedirectResponse(f"/episodios/{theme_id}#comentarios", status_code=303)


@router.post("/{theme_id}/excluir")
def delete_theme(theme_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    if not (me.is_admin or theme.created_by_id == me.id):
        raise HTTPException(403, "Só quem sugeriu o episódio ou um admin pode excluir.")
    db.delete(theme)
    db.commit()
    return RedirectResponse("/episodios", status_code=303)
