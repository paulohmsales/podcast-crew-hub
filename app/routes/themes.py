"""Episodes (stored as themes): the board, the list, and each episode's page."""

from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import feed, history, ludopedia
from app.db import get_db
from app.models import (
    THEME_STATUSES,
    Member,
    Poll,
    Recording,
    ScriptRevision,
    Segment,
    Theme,
    ThemeComment,
    ThemeEvent,
    ThemeVote,
)
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


def _last_recordings(db: Session) -> dict[int, datetime]:
    now = datetime.now()
    rows = db.execute(
        select(Recording.theme_id, func.max(Recording.starts_at))
        .where(Recording.theme_id.is_not(None), Recording.starts_at < now)
        .group_by(Recording.theme_id)
    ).all()
    return dict(rows)


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
    recorded = _last_recordings(db)
    far = datetime.max

    def newest_first(when: date | datetime | None, t: Theme) -> tuple:
        return (-(when.toordinal() if when else 0), -(t.number or 0), -t.updated_at.timestamp())

    # Votes rank the ideas, and the agenda keeps that order; after that, dates do.
    for col, items in by_status.items():
        if col in ("ideia", "pauta", "descartado"):
            items.sort(key=lambda t: (-votes.get(t.id, 0), -t.created_at.timestamp()))
        elif col == "agendado":
            items.sort(key=lambda t: upcoming.get(t.id, far))
        elif col == "gravado":
            items.sort(key=lambda t: newest_first(recorded.get(t.id), t))
        else:
            items.sort(key=lambda t: newest_first(t.published_on, t))
    return render(
        request, "board.html", me,
        columns=columns, by_status=by_status, upcoming=upcoming, recorded=recorded, descartados=descartados, **common,
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
        episodes = feed.load(url)
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
    db.add(ThemeVote(theme_id=theme.id, member_id=me.id))  # suggesting counts as a vote
    history.log(db, theme, me, "criado", "sugeriu o episódio")
    db.commit()
    return RedirectResponse(f"/episodios/{theme.id}", status_code=303)


TABS = {"resumo": "Resumo", "roteiro": "Roteiro", "jogos": "Jogos", "conversa": "Conversa", "historico": "Histórico"}


def _ep_url(theme_id: int, tab: str = "resumo", **params) -> str:
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items() if v)
    base = f"/episodios/{theme_id}" + ("" if tab == "resumo" else f"?aba={tab}")
    return base + (("&" if "?" in base else "?") + query if query else "")


@router.get("/{theme_id}")
def show_theme(
    theme_id: int,
    request: Request,
    aba: str = "resumo",
    jogo: str = "",
    erro: str = "",
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    tab = aba if aba in TABS else "resumo"
    voters = sorted((v.member for v in theme.votes), key=lambda m: m.name)
    ctx = dict(
        theme=theme,
        tab=tab,
        tabs=TABS,
        voters=voters,
        voted=any(v.id == me.id for v in voters),
        recordings=db.scalars(
            select(Recording).where(Recording.theme_id == theme.id).order_by(Recording.starts_at)
        ).all(),
        polls=db.scalars(select(Poll).where(Poll.theme_id == theme.id).order_by(Poll.closed, Poll.start_date.desc())).all(),
        member_count=db.scalar(select(func.count(Member.id))),
        error=erro,
    )
    if tab == "jogos":
        ctx.update(_game_search(theme, jogo), ludopedia_ready=ludopedia.configured())
    elif tab == "historico":
        ctx["events"] = db.scalars(
            select(ThemeEvent).where(ThemeEvent.theme_id == theme.id).order_by(ThemeEvent.created_at.desc())
        ).all()
    elif tab == "roteiro":
        ctx["revisions"] = db.scalars(
            select(ScriptRevision).where(ScriptRevision.theme_id == theme.id).order_by(ScriptRevision.created_at.desc()).limit(30)
        ).all()
    return render(request, "theme.html", me, **ctx)


@router.get("/{theme_id}/editar")
def edit_page(theme_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    return render(
        request,
        "episode_edit.html",
        me,
        theme=theme,
        members=db.scalars(select(Member).order_by(Member.name)).all(),
        all_segments=db.scalars(select(Segment).order_by(Segment.archived, Segment.position, Segment.name)).all(),
        can_delete=me.is_admin or theme.created_by_id == me.id,
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
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    try:
        new_date = date.fromisoformat(published_on) if published_on else None
    except ValueError:
        raise HTTPException(400, "Data inválida.")
    before = _snapshot(theme)
    if title.strip():
        theme.title = title.strip()[:200]
    theme.description = description.strip()
    theme.links = links.strip()
    theme.number = int(number) if number.strip().isdigit() else None
    theme.episode_url = episode_url.strip()[:500]
    theme.published_on = new_date
    theme.segments = db.scalars(select(Segment).where(Segment.id.in_(segment_ids))).all() if segment_ids else []
    theme.participants = db.scalars(select(Member).where(Member.id.in_(member_ids))).all() if member_ids else []
    changed = [label for label, value in _snapshot(theme).items() if before[label] != value]
    if changed:
        history.log(db, theme, me, "edicao", "editou " + _join(changed))
    db.commit()
    return RedirectResponse(f"/episodios/{theme_id}", status_code=303)


def _snapshot(theme: Theme) -> dict:
    return {
        "o título": theme.title,
        "a pauta": theme.description,
        "os links": theme.links,
        "o número": theme.number,
        "o link do episódio": theme.episode_url,
        "a data de publicação": theme.published_on,
        "os quadros": sorted(s.id for s in theme.segments),
        "os participantes": sorted(m.id for m in theme.participants),
    }


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


# --- script -------------------------------------------------------------------


def _script_state(theme: Theme, me: Member) -> dict:
    return {
        "version": theme.script_version,
        "text": theme.script,
        "updated_by": theme.script_updated_by.name if theme.script_updated_by else None,
        "updated_at": theme.script_updated_at.strftime("%d/%m %H:%M") if theme.script_updated_at else None,
        "editing": history.touch_editing(theme.id, me.name),
    }


@router.get("/{theme_id}/roteiro.json")
def script_state(theme_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    return _script_state(_theme_or_404(db, theme_id), me)


@router.post("/{theme_id}/roteiro")
def save_script(
    theme_id: int,
    base_version: int = Body(...),
    base_text: str = Body(...),
    text: str = Body(...),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    try:
        history.save_script(db, theme, me, base_version, base_text, text)
    except history.ScriptConflict:
        return JSONResponse({"conflict": True, **_script_state(theme, me)}, status_code=409)
    return _script_state(theme, me)


@router.get("/{theme_id}/roteiro.txt")
def script_download(theme_id: int, _me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    name = f"roteiro-{theme.number or theme.id}.txt"
    return PlainTextResponse(theme.script, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/{theme_id}/roteiro/versoes/{revision_id}/restaurar")
def restore_script(theme_id: int, revision_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    revision = db.get(ScriptRevision, revision_id)
    if not revision or revision.theme_id != theme_id:
        raise HTTPException(404)
    history.save_script(db, theme, me, theme.script_version, theme.script, revision.text)
    history.log(db, theme, me, "roteiro", f"restaurou a versão do roteiro de {revision.created_at:%d/%m %H:%M}")
    db.commit()
    return RedirectResponse(_ep_url(theme_id, "roteiro"), status_code=303)


# --- games --------------------------------------------------------------------


def _game_search(theme: Theme, jogo: str) -> dict:
    ctx = dict(theme=theme, jogo=jogo, game_results=[], attached={g.id for g in theme.games}, search_error="")
    if jogo.strip():
        try:
            ctx["game_results"], _ = ludopedia.search(jogo)
        except ludopedia.LudopediaError as e:
            ctx["search_error"] = str(e)
    return ctx


def _from_script(request: Request) -> bool:
    # games.js adds and removes without reloading, so the search box keeps its text and focus
    return request.headers.get("x-requested-with") == "fetch"


def _episode_games(request: Request, theme: Theme, me: Member):
    res = render(request, "_episode_games.html", me, theme=theme)
    res.headers["X-Games-Count"] = str(len(theme.games))
    return res


@router.get("/{theme_id}/jogos/busca")
def search_games(
    theme_id: int, request: Request, jogo: str = "", me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    """The search results alone, fetched as the member types."""
    return render(request, "_game_results.html", me, **_game_search(_theme_or_404(db, theme_id), jogo))


@router.post("/{theme_id}/jogos")
def add_game(
    theme_id: int,
    request: Request,
    game_id: int = Form(...),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = _theme_or_404(db, theme_id)
    try:
        game = ludopedia.get_game(db, game_id)
    except ludopedia.LudopediaError as e:
        if _from_script(request):
            return PlainTextResponse(str(e), status_code=502)
        return RedirectResponse(_ep_url(theme_id, "jogos", erro=str(e)), status_code=303)
    if game not in theme.games:
        theme.games.append(game)
        history.log(db, theme, me, "jogo", f"adicionou o jogo {game.name}")
        db.commit()
    if _from_script(request):
        return _episode_games(request, theme, me)
    return RedirectResponse(_ep_url(theme_id, "jogos"), status_code=303)


@router.post("/{theme_id}/jogos/{game_id}/remover")
def remove_game(
    theme_id: int, game_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    theme = _theme_or_404(db, theme_id)
    removed = [g for g in theme.games if g.id == game_id]
    if removed:
        theme.games = [g for g in theme.games if g.id != game_id]
        history.log(db, theme, me, "jogo", f"tirou o jogo {removed[0].name}")
        db.commit()
    if _from_script(request):
        return _episode_games(request, theme, me)
    return RedirectResponse(_ep_url(theme_id, "jogos"), status_code=303)


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
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    if status not in THEME_STATUSES:
        raise HTTPException(400, "Status inválido.")
    theme = _theme_or_404(db, theme_id)
    history.set_status(db, theme, status, me)
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
    theme = _theme_or_404(db, theme_id)
    if body.strip():
        db.add(ThemeComment(theme_id=theme_id, member_id=me.id, body=body.strip()))
        history.log(db, theme, me, "comentario", "comentou na conversa")
        db.commit()
    return RedirectResponse(_ep_url(theme_id, "conversa"), status_code=303)


@router.post("/{theme_id}/comentarios/{comment_id}/excluir")
def delete_comment(
    theme_id: int, comment_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    comment = db.get(ThemeComment, comment_id)
    if comment and comment.theme_id == theme_id and (comment.member_id == me.id or me.is_admin):
        db.delete(comment)
        db.commit()
    return RedirectResponse(_ep_url(theme_id, "conversa"), status_code=303)


@router.post("/{theme_id}/excluir")
def delete_theme(theme_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    if not (me.is_admin or theme.created_by_id == me.id):
        raise HTTPException(403, "Só quem sugeriu o episódio ou um admin pode excluir.")
    db.delete(theme)
    db.commit()
    return RedirectResponse("/episodios", status_code=303)
