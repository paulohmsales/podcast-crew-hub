from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import auth
from app.db import get_db
from app.models import Member
from app.web import COOKIE, current_member, render, set_session_cookie

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/entrar")
def login_page(request: Request):
    return render(request, "login.html", None)


@router.post("/entrar")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    key = f"{auth.normalize_email(email)}|{_client_ip(request)}"

    def fail(error: str):
        return render(request, "login.html", None, email=email, error=error)

    if auth.login_throttle.blocked(key):
        return fail("Muitas tentativas. Espere 15 minutos.")
    member = auth.find_member(db, email)
    if not member:
        auth.login_throttle.fail(key)
        return fail("Esse email não está no grupo. Fale com quem administra o app.")
    if member.password_hash is None:
        # First access: the password typed now becomes theirs.
        if problem := auth.password_problem(password):
            return fail(f"Primeiro acesso: crie sua senha. {problem}")
        auth.set_password(db, member, password)
        db.commit()
    elif not auth.verify_password(password, member.password_hash):
        auth.login_throttle.fail(key)
        return fail("Senha incorreta. Se esqueceu, peça para um admin liberar um novo acesso.")
    auth.login_throttle.clear(key)
    resp = RedirectResponse("/", status_code=303)
    set_session_cookie(resp, auth.start_session(db, member))
    return resp


@router.post("/sair")
def logout(request: Request, db: Session = Depends(get_db)):
    auth.end_session(db, request.cookies.get(COOKIE))
    resp = RedirectResponse("/entrar", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


@router.get("/conta")
def account_page(request: Request, me: Member = Depends(current_member)):
    return render(request, "account.html", me)


@router.post("/conta")
def update_account(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    name, email = name.strip(), auth.normalize_email(email)
    error = ("Nome obrigatório." if not name else None) or auth.email_problem(email)
    error = error or auth.taken_by_other(db, me.id, name, email)
    if error:
        return render(request, "account.html", me, error=error)
    me.name, me.email, me.phone = name[:80], email, phone.strip() or None
    db.commit()
    return render(request, "account.html", me, notice="Dados salvos.")


@router.post("/conta/senha")
def change_password(
    request: Request,
    current: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(current, me.password_hash):
        return render(request, "account.html", me, pw_error="Senha atual incorreta.")
    error = auth.password_problem(password) or (None if password == confirm else "As senhas não batem.")
    if error:
        return render(request, "account.html", me, pw_error=error)
    auth.set_password(db, me, password)  # logs out other devices too
    db.commit()
    resp = render(request, "account.html", me, notice="Senha trocada. Os outros aparelhos foram desconectados.")
    set_session_cookie(resp, auth.start_session(db, me))
    return resp
