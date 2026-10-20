from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import history, schedule
from app.db import get_db
from app.models import Member, Poll, PollResponse, PollSlot, Recording, Theme
from app.web import BASE_URL, current_member, render

router = APIRouter(prefix="/agenda")


def _poll_or_404(db: Session, poll_id: int) -> Poll:
    poll = db.get(Poll, poll_id)
    if not poll:
        raise HTTPException(404, "Agenda não encontrada.")
    return poll


def _schedulable_themes(db: Session) -> list[Theme]:
    return db.scalars(
        select(Theme).where(Theme.status.in_(["ideia", "pauta", "agendado"])).order_by(Theme.title)
    ).all()


def _booked(db: Session, theme: Theme | None, me: Member, starts_at: datetime) -> None:
    if not theme:
        return
    history.log(db, theme, me, "gravacao", f"marcou a gravação para {schedule.fmt_slot(starts_at)}")
    if theme.status in ("ideia", "pauta"):
        history.set_status(db, theme, "agendado", me)


@router.get("")
def agenda(request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    today = datetime.combine(date.today(), datetime.min.time())
    upcoming = db.scalars(select(Recording).where(Recording.starts_at >= today).order_by(Recording.starts_at)).all()
    past = db.scalars(
        select(Recording).where(Recording.starts_at < today).order_by(Recording.starts_at.desc()).limit(10)
    ).all()
    open_polls = db.scalars(select(Poll).where(Poll.closed.is_(False)).order_by(Poll.start_date)).all()
    closed_polls = db.scalars(select(Poll).where(Poll.closed.is_(True)).order_by(Poll.start_date.desc()).limit(10)).all()
    answered = set(db.scalars(select(PollResponse.poll_id).where(PollResponse.member_id == me.id)).all())
    return render(
        request,
        "agenda.html",
        me,
        upcoming=upcoming,
        past=past,
        open_polls=open_polls,
        closed_polls=closed_polls,
        answered=answered,
        themes=_schedulable_themes(db),
    )


@router.get("/nova")
def new_poll_form(
    request: Request, tema: int | None = None, me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    start = date.today() + timedelta(days=1)
    return render(
        request,
        "poll_new.html",
        me,
        themes=_schedulable_themes(db),
        theme_id=tema,
        start=start,
        end=start + timedelta(days=6),
    )


@router.post("")
def create_poll(
    title: str = Form(""),
    theme_id: str = Form(""),
    start_date: date = Form(...),
    end_date: date = Form(...),
    day_start: str = Form("19:00"),
    day_end: str = Form("23:00"),
    slot_minutes: int = Form(30),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    try:
        start_min = schedule.parse_hhmm(day_start)
        end_min = schedule.parse_hhmm(day_end) if day_end.strip() else 24 * 60
    except ValueError:
        raise HTTPException(400, "Horário inválido, use HH:MM.")
    if end_min == 0:
        end_min = 24 * 60  # "até 00:00" means until midnight
    if end_min <= start_min:
        raise HTTPException(400, "O horário final precisa ser depois do inicial.")
    if end_date < start_date:
        raise HTTPException(400, "A data final precisa ser depois da inicial.")
    if (end_date - start_date).days + 1 > schedule.MAX_DAYS:
        raise HTTPException(400, f"No máximo {schedule.MAX_DAYS} dias por agenda.")
    if slot_minutes not in (15, 30, 60):
        raise HTTPException(400, "Intervalo inválido.")
    theme = db.get(Theme, int(theme_id)) if theme_id.isdigit() else None
    if not title.strip():
        title = f"Gravação: {theme.title}" if theme else f"Semana de {schedule.fmt_day(start_date)}"
    poll = Poll(
        title=title.strip()[:200],
        theme_id=theme.id if theme else None,
        start_date=start_date,
        end_date=end_date,
        day_start=start_min,
        day_end=end_min,
        slot_minutes=slot_minutes,
        created_by_id=me.id,
    )
    db.add(poll)
    db.commit()
    return RedirectResponse(f"/agenda/{poll.id}", status_code=303)


@router.get("/{poll_id}")
def show_poll(poll_id: int, request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    poll = _poll_or_404(db, poll_id)
    members = db.scalars(select(Member).order_by(Member.name)).all()
    free = schedule.free_by_slot(poll)
    names = {m.id: m.name for m in members}
    responded = {r.member_id for r in poll.responses}
    pending = [m for m in members if m.id not in responded]
    url = f"{BASE_URL}/agenda/{poll.id}"
    recordings = db.scalars(select(Recording).where(Recording.poll_id == poll.id).order_by(Recording.starts_at)).all()
    cells = {
        slot.isoformat(timespec="minutes"): sorted(names[i] for i in ids if i in names)
        for slot, ids in free.items()
    }
    return render(
        request,
        "poll.html",
        me,
        poll=poll,
        days=schedule.poll_days(poll),
        times=schedule.poll_times(poll),
        slot_at=schedule.slot_at,
        mine=sorted(s.isoformat(timespec="minutes") for s, ids in free.items() if me.id in ids),
        cells=cells,
        members=members,
        responded=responded,
        pending=pending,
        windows=schedule.best_windows(poll, members),
        recordings=recordings,
        invite_text=f"📅 {poll.title}\nMarquem quando vocês podem gravar: {url}",
        reminder_text=(
            f"👀 Ainda faltam marcar a disponibilidade em \"{poll.title}\": "
            + ", ".join(m.name for m in pending)
            + f"\n{url}"
        ),
        themes=_schedulable_themes(db),
    )


@router.post("/{poll_id}/disponibilidade")
def save_availability(
    poll_id: int,
    slots: list[str] = Body(..., embed=True),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    poll = _poll_or_404(db, poll_id)
    if poll.closed:
        raise HTTPException(409, "Essa agenda já foi fechada.")
    valid = set(schedule.all_slots(poll))
    chosen: set[datetime] = set()
    for raw in slots:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            raise HTTPException(400, f"Horário inválido: {raw}")
        if dt in valid:
            chosen.add(dt)
    db.execute(delete(PollSlot).where(PollSlot.poll_id == poll_id, PollSlot.member_id == me.id))
    db.add_all(PollSlot(poll_id=poll_id, member_id=me.id, slot=dt) for dt in chosen)
    response = db.get(PollResponse, (poll_id, me.id))
    if response:
        response.updated_at = datetime.now()
    else:
        db.add(PollResponse(poll_id=poll_id, member_id=me.id))
    db.commit()
    return {"ok": True, "saved": len(chosen)}


@router.post("/{poll_id}/marcar")
def book_recording(
    poll_id: int,
    starts_at: datetime = Form(...),
    duration_minutes: int = Form(90),
    theme_id: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    poll = _poll_or_404(db, poll_id)
    theme = db.get(Theme, int(theme_id)) if theme_id.isdigit() else poll.theme
    duration = max(15, min(duration_minutes, 600))
    db.add(
        Recording(
            starts_at=starts_at,
            duration_minutes=duration,
            theme_id=theme.id if theme else None,
            poll_id=poll.id,
        )
    )
    if theme and not theme.participants:
        # Start the episode's lineup with whoever is free for the whole recording.
        free = schedule.free_throughout(poll, starts_at, duration)
        theme.participants = db.scalars(select(Member).where(Member.id.in_(free))).all() if free else []
    poll.closed = True
    _booked(db, theme, me, starts_at)
    db.commit()
    return RedirectResponse(f"/agenda/{poll_id}", status_code=303)


@router.post("/{poll_id}/reabrir")
def reopen_poll(poll_id: int, _me: Member = Depends(current_member), db: Session = Depends(get_db)):
    _poll_or_404(db, poll_id).closed = False
    db.commit()
    return RedirectResponse(f"/agenda/{poll_id}", status_code=303)


@router.post("/{poll_id}/fechar")
def close_poll(poll_id: int, _me: Member = Depends(current_member), db: Session = Depends(get_db)):
    _poll_or_404(db, poll_id).closed = True
    db.commit()
    return RedirectResponse(f"/agenda/{poll_id}", status_code=303)


@router.post("/{poll_id}/excluir")
def delete_poll(poll_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    poll = _poll_or_404(db, poll_id)
    if not (me.is_admin or poll.created_by_id == me.id):
        raise HTTPException(403, "Só quem criou a agenda ou um admin pode excluir.")
    db.delete(poll)
    db.commit()
    return RedirectResponse("/agenda", status_code=303)


# --- recordings -------------------------------------------------------------


@router.post("/gravacoes")
def create_recording(
    starts_at: datetime = Form(...),
    duration_minutes: int = Form(90),
    theme_id: str = Form(""),
    notes: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    theme = db.get(Theme, int(theme_id)) if theme_id.isdigit() else None
    db.add(
        Recording(
            starts_at=starts_at,
            duration_minutes=max(15, min(duration_minutes, 600)),
            theme_id=theme.id if theme else None,
            notes=notes.strip(),
        )
    )
    _booked(db, theme, me, starts_at)
    db.commit()
    return RedirectResponse("/agenda", status_code=303)


@router.get("/gravacoes/{recording_id}.ics")
def recording_ics(recording_id: int, db: Session = Depends(get_db)):
    # No login: calendar apps fetch this link directly. Ids reveal only a date and theme.
    recording = db.get(Recording, recording_id)
    if not recording:
        raise HTTPException(404)
    body = schedule.ics_for(recording, f"{BASE_URL}/agenda")
    return Response(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="gravacao-{recording_id}.ics"'},
    )


@router.post("/gravacoes/{recording_id}/gravado")
def mark_recorded(recording_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording and recording.theme and recording.theme.status in ("ideia", "pauta", "agendado"):
        history.set_status(db, recording.theme, "gravado", me)
        db.commit()
    return RedirectResponse("/agenda", status_code=303)


@router.post("/gravacoes/{recording_id}/excluir")
def delete_recording(recording_id: int, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    recording = db.get(Recording, recording_id)
    if recording:
        theme = recording.theme
        if theme:
            history.log(db, theme, me, "gravacao", f"desmarcou a gravação de {schedule.fmt_slot(recording.starts_at)}")
            if theme.status == "agendado":
                history.set_status(db, theme, "pauta", me)
        db.delete(recording)
        db.commit()
    return RedirectResponse("/agenda", status_code=303)
