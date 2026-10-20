"""Passwords (stdlib scrypt), login sessions and a login throttle."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import LoginSession, Member

SESSION_DAYS = 180
MIN_PASSWORD = 8

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(check.hex(), digest)


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres."
    return None


def normalize_email(value: str) -> str:
    return value.strip().lower()


def email_problem(email: str) -> str | None:
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email:
        return "Email inválido."
    return None


def find_member(db: Session, email: str) -> Member | None:
    email = normalize_email(email)
    return db.scalar(select(Member).where(Member.email == email)) if email else None


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, member: Member) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=_sha(token), member_id=member.id, expires_at=datetime.now() + timedelta(days=SESSION_DAYS)
        )
    )
    db.commit()
    return token


def session_member(db: Session, token: str | None) -> Member | None:
    if not token:
        return None
    sess = db.get(LoginSession, _sha(token))
    if not sess or sess.expires_at < datetime.now():
        return None
    return sess.member


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == _sha(token)))
        db.commit()


def end_all_sessions(db: Session, member: Member) -> None:
    db.execute(delete(LoginSession).where(LoginSession.member_id == member.id))


def set_password(db: Session, member: Member, password: str) -> None:
    """Sets the password and logs the member out everywhere. Caller commits."""
    member.password_hash = hash_password(password)
    end_all_sessions(db, member)


def clear_password(db: Session, member: Member) -> None:
    """Back to first access: the next login with their email sets the password. Caller commits."""
    member.password_hash = None
    end_all_sessions(db, member)


def taken_by_other(db: Session, member_id: int | None, name: str, email: str) -> str | None:
    """Message if another member already uses this name or email."""
    others = select(Member).where(Member.id != member_id) if member_id else select(Member)
    if db.scalar(others.where(Member.name == name)):
        return "Já existe alguém com esse nome."
    if db.scalar(others.where(Member.email == email)):
        return "Esse email já está em uso."
    return None


class Throttle:
    """At most `limit` failed logins per key in `window` seconds (in memory)."""

    def __init__(self, limit: int = 8, window: int = 15 * 60):
        self.limit, self.window = limit, window
        self.fails: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str) -> deque[float]:
        q = self.fails[key]
        while q and q[0] < time.monotonic() - self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._trim(key)) >= self.limit

    def fail(self, key: str) -> None:
        self._trim(key).append(time.monotonic())

    def clear(self, key: str) -> None:
        self.fails.pop(key, None)


login_throttle = Throttle()
