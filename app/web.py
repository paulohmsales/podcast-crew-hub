"""Shared web plumbing: templates, the logged-in member, WhatsApp links."""

import os
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schedule
from app.db import get_db
from app.models import THEME_STATUSES, Member

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
COOKIE = "eg_member"
COOKIE_SECURE = BASE_URL.startswith("https://")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    STATUSES=THEME_STATUSES,
    fmt_day=schedule.fmt_day,
    fmt_slot=schedule.fmt_slot,
    fmt_minutes=schedule.fmt_minutes,
    BASE_URL=BASE_URL,
)


def new_token() -> str:
    return secrets.token_urlsafe(24)


def login_url(member: Member) -> str:
    return f"{BASE_URL}/entrar/{member.token}"


def whatsapp_url(text: str, phone: str | None = None) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}"


templates.env.globals.update(whatsapp_url=whatsapp_url, login_url=login_url)


class LoginRequired(Exception):
    pass


def current_member(request: Request, db: Session = Depends(get_db)) -> Member:
    token = request.cookies.get(COOKIE)
    member = token and db.scalar(select(Member).where(Member.token == token))
    if not member:
        raise LoginRequired()
    return member


def admin_member(member: Member = Depends(current_member)) -> Member:
    if not member.is_admin:
        raise HTTPException(403, "Só admins podem fazer isso.")
    return member


def render(request: Request, name: str, member: Member | None, **ctx):
    return templates.TemplateResponse(request, name, {"me": member, **ctx})
