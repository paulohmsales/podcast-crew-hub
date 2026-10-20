"""Shared web plumbing: templates, the logged-in member, WhatsApp links."""

import os
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import auth, branding, schedule
from app.db import get_db
from app.models import THEME_STATUSES, Member

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
COOKIE = "eg_session"
COOKIE_SECURE = BASE_URL.startswith("https://")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    STATUSES=THEME_STATUSES,
    fmt_day=schedule.fmt_day,
    fmt_slot=schedule.fmt_slot,
    fmt_minutes=schedule.fmt_minutes,
    BASE_URL=BASE_URL,
)


def whatsapp_url(text: str, phone: str | None = None) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return f"https://wa.me/{digits}?text={quote(text)}"


templates.env.globals.update(whatsapp_url=whatsapp_url, logo_url=branding.logo_url)


class LoginRequired(Exception):
    pass


def current_member(request: Request, db: Session = Depends(get_db)) -> Member:
    member = auth.session_member(db, request.cookies.get(COOKIE))
    if not member:
        raise LoginRequired()
    return member


def admin_member(member: Member = Depends(current_member)) -> Member:
    if not member.is_admin:
        raise HTTPException(403, "Só admins podem fazer isso.")
    return member


def set_session_cookie(resp, token: str) -> None:
    resp.set_cookie(
        COOKIE, token, max_age=auth.SESSION_DAYS * 24 * 3600, httponly=True, secure=COOKIE_SECURE, samesite="lax"
    )


def render(request: Request, name: str, member: Member | None, **ctx):
    return templates.TemplateResponse(request, name, {"me": member, **ctx})
