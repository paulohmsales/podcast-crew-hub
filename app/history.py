"""Episode history ("Histórico") and the shared script ("Roteiro")."""

import time
from datetime import date, datetime, timedelta

from diff_match_patch import diff_match_patch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import THEME_STATUSES, Member, ScriptRevision, Theme, ThemeEvent

SCRIPT_EVENT_GAP = timedelta(minutes=30)  # one "editou o roteiro" per person per half hour
REVISION_GAP = timedelta(minutes=10)  # keep a copy at most this often per person
EDITING_SECONDS = 20  # "editando agora" if they saved or synced this recently


def log(db: Session, theme: Theme, member: Member | None, kind: str, text: str) -> None:
    """Adds a history line; the caller commits."""
    db.add(ThemeEvent(theme_id=theme.id, member_id=member.id if member else None, kind=kind, text=text))


def set_status(db: Session, theme: Theme, status: str, by: Member | None) -> None:
    """Moves the episode and logs it; the caller commits."""
    if status == theme.status:
        return
    log(db, theme, by, "status", f"moveu de {THEME_STATUSES[theme.status]} para {THEME_STATUSES[status]}")
    theme.status = status
    if status == "publicado" and not theme.published_on:
        theme.published_on = date.today()


class ScriptConflict(Exception):
    pass


def save_script(db: Session, theme: Theme, member: Member, base_version: int, base_text: str, text: str) -> None:
    """Saves an edit made on top of `base_text` (version `base_version`).

    If someone saved in between, the edit is turned into a patch and applied
    to the newer text, so both people's changes survive. Commits.
    """
    if base_version != theme.script_version:
        dmp = diff_match_patch()
        patches = dmp.patch_make(base_text, text)
        merged, applied = dmp.patch_apply(patches, theme.script)
        if not all(applied):
            raise ScriptConflict()
        text = merged
    if text == theme.script:
        return
    now = datetime.now()
    theme.script = text
    theme.script_version += 1
    theme.script_updated_at = now
    theme.script_updated_by_id = member.id

    last_rev = db.scalar(
        select(ScriptRevision)
        .where(ScriptRevision.theme_id == theme.id, ScriptRevision.member_id == member.id)
        .order_by(ScriptRevision.created_at.desc())
    )
    if last_rev and now - last_rev.created_at < REVISION_GAP:
        last_rev.text, last_rev.created_at = text, now  # same editing session: update the copy
    else:
        db.add(ScriptRevision(theme_id=theme.id, member_id=member.id, text=text, created_at=now))

    last_event = db.scalar(
        select(ThemeEvent)
        .where(ThemeEvent.theme_id == theme.id, ThemeEvent.member_id == member.id, ThemeEvent.kind == "roteiro")
        .order_by(ThemeEvent.created_at.desc())
    )
    if not last_event or now - last_event.created_at > SCRIPT_EVENT_GAP:
        log(db, theme, member, "roteiro", "editou o roteiro")
    db.commit()


# Who has the script open: {theme_id: {member name: last seen}}, in memory.
_editing: dict[int, dict[str, float]] = {}


def touch_editing(theme_id: int, name: str) -> list[str]:
    """Marks `name` as on the script page and returns the others there."""
    now = time.monotonic()
    people = _editing.setdefault(theme_id, {})
    people[name] = now
    return sorted(n for n, seen in people.items() if n != name and now - seen < EDITING_SECONDS)
