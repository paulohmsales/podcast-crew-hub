from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Member, Poll, PollResponse, Recording, Theme, ThemeVote
from app.routes import account, agenda, appearance, games, members, segments, themes
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


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, _exc: LoginRequired):
    return RedirectResponse("/entrar", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/bem-vindo")
def tutorial(request: Request, me: Member = Depends(current_member)):
    return render(request, "tutorial.html", me)


@app.post("/bem-vindo/concluir")
def tutorial_done(me: Member = Depends(current_member), db: Session = Depends(get_db)):
    if not me.tutorial_seen_at:
        me.tutorial_seen_at = datetime.now()
        db.commit()
    return RedirectResponse("/episodios", status_code=303)


@app.get("/")
def home(request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    if not me.tutorial_seen_at:
        return RedirectResponse("/bem-vindo", status_code=303)
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
