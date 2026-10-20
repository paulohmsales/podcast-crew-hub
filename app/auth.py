"""Passwords (stdlib scrypt), login sessions, reset links and a login throttle."""

import hashlib
import hmac
import secrets
import string
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import LoginSession, Member, PasswordReset

SESSION_DAYS = 180
RESET_HOURS = 2
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


def generate_password() -> str:
    # Readable: no 0/O/1/l/I, grouped for typing on a phone.
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    raw = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres."
    return None


def normalize_username(value: str) -> str:
    return value.strip().lower()


def username_problem(value: str) -> str | None:
    if not 3 <= len(value) <= 40 or not all(c.isalnum() or c in "._-" for c in value):
        return "Usuário: 3 a 40 letras, números, ponto, hífen ou _."
    return None


def find_member(db: Session, login: str) -> Member | None:
    login = login.strip().lower()
    if not login:
        return None
    return db.scalar(select(Member).where(or_(Member.username == login, Member.email == login)))


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


def create_reset(db: Session, member: Member) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordReset(
            token_hash=_sha(token), member_id=member.id, expires_at=datetime.now() + timedelta(hours=RESET_HOURS)
        )
    )
    db.commit()
    return token


def valid_reset(db: Session, token: str) -> PasswordReset | None:
    reset = db.get(PasswordReset, _sha(token))
    if not reset or reset.used or reset.expires_at < datetime.now():
        return None
    return reset


def taken_by_other(db: Session, member_id: int | None, name: str, username: str, email: str) -> str | None:
    """Message if another member already uses this name, username or email."""
    others = select(Member).where(Member.id != member_id) if member_id else select(Member)
    if db.scalar(others.where(Member.name == name)):
        return "Já existe alguém com esse nome."
    if db.scalar(others.where(Member.username == username)):
        return "Esse usuário já está em uso."
    if email and db.scalar(others.where(Member.email == email)):
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
