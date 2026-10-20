from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_db
from app.models import Member
from app.web import admin_member, current_member, render

router = APIRouter(prefix="/membros")


def _page(request: Request, me: Member, db: Session, **ctx):
    members = db.scalars(select(Member).order_by(Member.name)).all()
    return render(request, "members.html", me, members=members, **ctx)


@router.get("")
def list_members(request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    return _page(request, me, db)


@router.post("")
def add_member(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    is_admin: bool = Form(False),
    me: Member = Depends(admin_member),
    db: Session = Depends(get_db),
):
    name, email = name.strip(), auth.normalize_email(email)
    error = ("Nome obrigatório." if not name else None) or auth.email_problem(email)
    error = error or auth.taken_by_other(db, None, name, email)
    if error:
        return _page(request, me, db, error=error, form={"name": name, "email": email, "phone": phone})
    db.add(Member(name=name[:80], email=email, phone=phone.strip() or None, is_admin=is_admin))
    db.commit()
    return _page(request, me, db, notice=f"{name} adicionado. No primeiro acesso, ele entra com {email} e cria a senha.")


@router.post("/{member_id}/editar")
def edit_member(
    member_id: int,
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    is_admin: bool = Form(False),
    me: Member = Depends(admin_member),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id) or _404()
    name, email = name.strip(), auth.normalize_email(email)
    error = ("Nome obrigatório." if not name else None) or auth.email_problem(email)
    error = error or auth.taken_by_other(db, member.id, name, email)
    if error:
        return _page(request, me, db, error=error)
    member.name, member.email, member.phone = name[:80], email, phone.strip() or None
    if member.id != me.id:  # can't remove your own admin by accident
        member.is_admin = is_admin
    db.commit()
    return _page(request, me, db, notice=f"{member.name} atualizado.")


@router.post("/{member_id}/liberar")
def reopen_first_access(member_id: int, request: Request, me: Member = Depends(admin_member), db: Session = Depends(get_db)):
    member = db.get(Member, member_id) or _404()
    auth.clear_password(db, member)
    db.commit()
    return _page(request, me, db, notice=f"Pronto: {member.name} cria uma senha nova no próximo acesso com {member.email}.")


def _404():
    raise HTTPException(404, "Membro não encontrado.")
