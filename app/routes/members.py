from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Member
from app.web import admin_member, current_member, new_token, render

router = APIRouter(prefix="/membros")


@router.get("")
def list_members(request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    members = db.scalars(select(Member).order_by(Member.name)).all()
    return render(request, "members.html", me, members=members)


@router.post("")
def add_member(
    name: str = Form(...),
    phone: str = Form(""),
    is_admin: bool = Form(False),
    _admin: Member = Depends(admin_member),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "Nome obrigatório.")
    if db.scalar(select(Member).where(Member.name == name)):
        raise HTTPException(400, "Já existe alguém com esse nome.")
    db.add(Member(name=name[:80], phone=phone.strip() or None, is_admin=is_admin, token=new_token()))
    db.commit()
    return RedirectResponse("/membros", status_code=303)


@router.post("/{member_id}/editar")
def edit_member(
    member_id: int,
    name: str = Form(...),
    phone: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    if not (me.is_admin or me.id == member_id):
        raise HTTPException(403)
    member = db.get(Member, member_id) or _404()
    if name.strip():
        member.name = name.strip()[:80]
    member.phone = phone.strip() or None
    db.commit()
    return RedirectResponse("/membros", status_code=303)


@router.post("/{member_id}/novo-link")
def regenerate_link(member_id: int, _admin: Member = Depends(admin_member), db: Session = Depends(get_db)):
    member = db.get(Member, member_id) or _404()
    member.token = new_token()
    db.commit()
    return RedirectResponse(f"/membros#m{member_id}", status_code=303)


def _404():
    raise HTTPException(404, "Membro não encontrado.")
