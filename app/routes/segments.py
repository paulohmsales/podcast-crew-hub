"""Quadros: the podcast's recurring segments, attached to episodes."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Member, Segment, theme_segments
from app.web import current_member, render

router = APIRouter(prefix="/quadros")


def _ordered(db: Session) -> list[Segment]:
    return db.scalars(select(Segment).order_by(Segment.archived, Segment.position, Segment.name)).all()


def _segment_or_404(db: Session, segment_id: int) -> Segment:
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(404, "Quadro não encontrado.")
    return segment


@router.get("")
def list_segments(request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    counts = dict(
        db.execute(select(theme_segments.c.segment_id, func.count()).group_by(theme_segments.c.segment_id)).all()
    )
    return render(request, "segments.html", me, segments=_ordered(db), counts=counts)


@router.post("")
def create_segment(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    _me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    name = name.strip()[:80]
    if not name:
        raise HTTPException(400, "O quadro precisa de um nome.")
    if db.scalar(select(Segment).where(func.lower(Segment.name) == name.lower())):
        raise HTTPException(400, "Já existe um quadro com esse nome.")
    last = db.scalar(select(func.max(Segment.position))) or 0
    db.add(Segment(name=name, description=description.strip(), position=last + 1))
    db.commit()
    return RedirectResponse("/quadros", status_code=303)


@router.post("/{segment_id}/editar")
def edit_segment(
    segment_id: int,
    name: str = Form(...),
    description: str = Form(""),
    _me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    segment = _segment_or_404(db, segment_id)
    name = name.strip()[:80]
    clash = db.scalar(select(Segment).where(func.lower(Segment.name) == name.lower(), Segment.id != segment_id))
    if not name or clash:
        raise HTTPException(400, "Nome vazio ou já usado por outro quadro.")
    segment.name, segment.description = name, description.strip()
    db.commit()
    return RedirectResponse("/quadros", status_code=303)


@router.post("/{segment_id}/arquivar")
def toggle_archived(segment_id: int, _me: Member = Depends(current_member), db: Session = Depends(get_db)):
    segment = _segment_or_404(db, segment_id)
    segment.archived = not segment.archived
    db.commit()
    return RedirectResponse("/quadros", status_code=303)


@router.post("/{segment_id}/mover")
def move_segment(
    segment_id: int, direcao: str = Form(...), _me: Member = Depends(current_member), db: Session = Depends(get_db)
):
    active = [s for s in _ordered(db) if not s.archived]
    ids = [s.id for s in active]
    if segment_id in ids:
        i = ids.index(segment_id)
        j = i - 1 if direcao == "cima" else i + 1
        if 0 <= j < len(active):
            active[i], active[j] = active[j], active[i]
        for pos, s in enumerate(active, start=1):
            s.position = pos
        db.commit()
    return RedirectResponse("/quadros", status_code=303)
