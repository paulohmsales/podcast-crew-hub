from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Member, Poll, PollResponse, Recording, Theme, ThemeVote
from app.routes import account, agenda, appearance, games, members, segments, stats, themes
from app.web import LoginRequired, current_member, render

app = FastAPI(title="Então Ganhei", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(account.router)
app.include_router(themes.router)
app.include_router(themes.legacy)
app.include_router(segments.router)
app.include_router(games.router)
app.include_router(appearance.router)
app.include_router(agenda.router)
app.include_router(members.router)
app.include_router(stats.router)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, _exc: LoginRequired):
    return RedirectResponse("/entrar", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/bem-vindo/foto")
def welcome_photo(request: Request, me: Member = Depends(current_member)):
    return render(request, "welcome_photo.html", me)


@app.get("/bem-vindo")
def tutorial():
    # The guide is a popup now (the ? on every page); it opens by itself on the home page.
    return RedirectResponse("/?sem_foto=1", status_code=303)


@app.post("/guia")
def guide_setting(mostrar: int = Form(1), me: Member = Depends(current_member), db: Session = Depends(get_db)):
    """The guide's "não mostrar ao entrar" box: mostrar=0 stops it opening by itself."""
    me.tutorial_seen_at = None if mostrar else (me.tutorial_seen_at or datetime.now())
    db.commit()
    return {"ok": True, "mostrar": bool(mostrar)}


@app.get("/")
def home(
    request: Request, sem_foto: bool = False, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    if not me.tutorial_seen_at and not me.photo and not sem_foto:
        # First access: a photo first (so everyone can tell who's who); the guide then opens here.
        return RedirectResponse("/bem-vindo/foto", status_code=303)
    now = datetime.now()
    upcoming = db.scalars(
        select(Recording).where(Recording.starts_at >= now.replace(hour=0, minute=0)).order_by(Recording.starts_at).limit(3)
    ).all()
    open_polls = db.scalars(select(Poll).where(Poll.closed.is_(False)).order_by(Poll.start_date)).all()
    answered = set(
        db.scalars(select(PollResponse.poll_id).where(PollResponse.member_id == me.id)).all()
    )
    votes = func.count(ThemeVote.member_id)
    top_themes = db.execute(
        select(Theme, votes)
        .outerjoin(ThemeVote)
        .where(Theme.status.in_(["ideia", "pauta"]))
        .group_by(Theme.id)
        .order_by(votes.desc(), Theme.created_at.desc())
        .limit(5)
    ).all()
    my_votes = set(db.scalars(select(ThemeVote.theme_id).where(ThemeVote.member_id == me.id)).all())
    member_count = db.scalar(select(func.count(Member.id)))
    return render(
        request,
        "home.html",
        me,
        upcoming=upcoming,
        open_polls=open_polls,
        answered=answered,
        top_themes=top_themes,
        my_votes=my_votes,
        member_count=member_count,
    )
