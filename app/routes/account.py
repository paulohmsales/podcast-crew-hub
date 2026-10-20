from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, mail
from app.db import get_db
from app.models import Member
from app.web import BASE_URL, COOKIE, current_member, render, set_session_cookie

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/entrar")
def login_page(request: Request):
    return render(request, "login.html", None)


@router.post("/entrar")
def login(request: Request, login: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    key = f"{login.strip().lower()}|{_client_ip(request)}"
    if auth.login_throttle.blocked(key):
        return render(request, "login.html", None, login=login, error="Muitas tentativas. Espere 15 minutos.")
    member = auth.find_member(db, login)
    if not member or not auth.verify_password(password, member.password_hash):
        auth.login_throttle.fail(key)
        return render(request, "login.html", None, login=login, error="Usuário ou senha incorretos.")
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


@router.get("/esqueci")
def forgot_page(request: Request):
    return render(request, "forgot.html", None)


@router.post("/esqueci")
def forgot(request: Request, login: str = Form(...), db: Session = Depends(get_db)):
    key = f"reset|{_client_ip(request)}"
    if auth.login_throttle.blocked(key):
        return render(request, "forgot.html", None, error="Muitas tentativas. Espere 15 minutos.")
    auth.login_throttle.fail(key)  # every request counts, so this can't be used to spam inboxes
    member = auth.find_member(db, login)
    if member and member.email:
        token = auth.create_reset(db, member)
        try:
            mail.send(member.email, "Redefinir senha · Então Ganhei", mail.reset_text(member.name, f"{BASE_URL}/redefinir/{token}"))
        except mail.MailError:
            pass  # same answer either way: don't reveal who has an account
    return render(request, "forgot.html", None, sent=True)


@router.get("/redefinir/{token}")
def reset_page(token: str, request: Request, db: Session = Depends(get_db)):
    reset = auth.valid_reset(db, token)
    return render(request, "reset.html", None, token=token, invalid=reset is None, who=reset and reset.member)


@router.post("/redefinir/{token}")
def reset(
    token: str,
    request: Request,
    password: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    reset = auth.valid_reset(db, token)
    if not reset:
        return render(request, "reset.html", None, token=token, invalid=True)
    error = auth.password_problem(password) or (None if password == confirm else "As senhas não batem.")
    if error:
        return render(request, "reset.html", None, token=token, who=reset.member, error=error)
    auth.set_password(db, reset.member, password)
    reset.used = True
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    set_session_cookie(resp, auth.start_session(db, reset.member))
    return resp


@router.get("/conta")
def account_page(request: Request, me: Member = Depends(current_member)):
    return render(request, "account.html", me)


@router.post("/conta")
def update_account(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    me: Member = Depends(current_member),
    db: Session = Depends(get_db),
):
    username = auth.normalize_username(username)
    email = email.strip().lower()
    error = auth.username_problem(username)
    if not error and not name.strip():
        error = "Nome obrigatório."
    if not error and email and "@" not in email:
        error = "Email inválido."
    if not error:
        error = auth.taken_by_other(db, me.id, name.strip(), username, email)
    if error:
        return render(request, "account.html", me, error=error)
    me.name, me.username, me.email, me.phone = name.strip()[:80], username, email or None, phone.strip() or None
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

