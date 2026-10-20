from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, mail
from app.db import get_db
from app.models import Member
from app.web import BASE_URL, admin_member, current_member, render

router = APIRouter(prefix="/membros")


def _page(request: Request, me: Member, db: Session, **ctx):
    members = db.scalars(select(Member).order_by(Member.name)).all()
    return render(request, "members.html", me, members=members, **ctx)


def _send_access(db: Session, member: Member) -> dict:
    """New random password, emailed. Returns page context: a notice, or the
    password itself when the email can't go out so the admin can pass it on."""
    password = auth.generate_password()
    auth.set_password(db, member, password)
    db.commit()
    if not member.email:
        return {"credentials": (member, password, "Essa pessoa não tem email cadastrado.")}
    try:
        mail.send(member.email, "Seu acesso ao app do Então Ganhei", mail.welcome_text(member.name, member.username, password, BASE_URL))
    except mail.MailError as e:
        return {"credentials": (member, password, str(e))}
    return {"notice": f"Acesso enviado para {member.email}."}


@router.get("")
def list_members(request: Request, me: Member = Depends(current_member), db: Session = Depends(get_db)):
    return _page(request, me, db)


@router.post("")
def add_member(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    is_admin: bool = Form(False),
    me: Member = Depends(admin_member),
    db: Session = Depends(get_db),
):
    name, username, email = name.strip(), auth.normalize_username(username), email.strip().lower()
    error = auth.username_problem(username)
    if not error and (not name or "@" not in email):
        error = "Nome e email válidos são obrigatórios."
    error = error or auth.taken_by_other(db, None, name, username, email)
    if error:
        return _page(request, me, db, error=error, form={"name": name, "username": username, "email": email, "phone": phone})
    member = Member(name=name[:80], username=username, email=email, phone=phone.strip() or None, is_admin=is_admin)
    db.add(member)
    db.flush()
    return _page(request, me, db, **_send_access(db, member))


@router.post("/{member_id}/editar")
def edit_member(
    member_id: int,
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    is_admin: bool = Form(False),
    me: Member = Depends(admin_member),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id) or _404()
    name, username, email = name.strip(), auth.normalize_username(username), email.strip().lower()
    error = auth.username_problem(username) or auth.taken_by_other(db, member.id, name, username, email)
    if not error and (not name or (email and "@" not in email)):
        error = "Nome obrigatório e email válido."
    if error:
        return _page(request, me, db, error=error)
    member.name, member.username, member.email, member.phone = name[:80], username, email or None, phone.strip() or None
    if member.id != me.id:  # can't remove your own admin by accident
        member.is_admin = is_admin
    db.commit()
    return _page(request, me, db, notice=f"{member.name} atualizado.")


@router.post("/{member_id}/reenviar")
def resend_access(member_id: int, request: Request, me: Member = Depends(admin_member), db: Session = Depends(get_db)):
    member = db.get(Member, member_id) or _404()
    return _page(request, me, db, **_send_access(db, member))


def _404():
    raise HTTPException(404, "Membro não encontrado.")
