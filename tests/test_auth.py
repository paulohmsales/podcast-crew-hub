import re

from fastapi.testclient import TestClient

from app import auth, mail
from app.main import app
from app.models import LoginSession, Member
from tests.conftest import PASSWORD


def _login(login, password):
    c = TestClient(app)
    res = c.post("/entrar", data={"login": login, "password": password}, follow_redirects=False)
    return c, res


def test_login_with_username_or_email(paulo):
    c, res = _login("Paulo", PASSWORD)  # case-insensitive username
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert "Oi, Paulo" in c.get("/").text
    c2, res = _login("paulo@ex.com", PASSWORD)
    assert res.status_code == 303


def test_wrong_password_and_throttle(paulo):
    _, res = _login("paulo", "errada")
    assert res.status_code == 200 and "incorretos" in res.text
    for _ in range(10):
        _login("paulo", "errada")
    _, res = _login("paulo", PASSWORD)
    assert "Muitas tentativas" in res.text


def test_logout_kills_session(client, db):
    assert client.get("/", follow_redirects=False).status_code == 200
    client.post("/sair")
    assert db.query(LoginSession).count() == 0
    assert client.get("/", follow_redirects=False).headers["location"] == "/entrar"


def test_admin_adds_member_and_password_is_emailed(client, ana_client, db, outbox):
    assert ana_client.post("/membros", data={"name": "Caio", "username": "caio", "email": "c@ex.com"}).status_code == 403
    res = client.post("/membros", data={"name": "Caio", "username": "Caio", "email": "C@ex.com"})
    assert "Acesso enviado para c@ex.com" in res.text
    to, subject, text = outbox[-1]
    assert to == "c@ex.com"
    password = re.search(r"Senha:\s+(\S+)", text).group(1)
    assert "Usuário:  caio" in text
    _, res = _login("caio", password)
    assert res.status_code == 303
    # duplicates are refused
    res = client.post("/membros", data={"name": "Outro", "username": "caio", "email": "x@ex.com"})
    assert "já está em uso" in res.text


def test_failed_email_shows_password_to_admin(client, monkeypatch, outbox):
    def boom(*_):
        raise mail.MailError("domínio não verificado")

    monkeypatch.setattr(mail, "send", boom)
    res = client.post("/membros", data={"name": "Dani", "username": "dani", "email": "d@ex.com"})
    assert "O email não foi enviado" in res.text and "domínio não verificado" in res.text
    password = re.search(r"Senha: <code>([^<]+)</code>", res.text).group(1)
    _, res = _login("dani", password)
    assert res.status_code == 303


def test_resend_access_replaces_password(client, ana, outbox, db):
    client.post(f"/membros/{ana.id}/reenviar")
    _, res = _login("ana", PASSWORD)
    assert res.status_code == 200  # old password no longer works
    new = re.search(r"Senha:\s+(\S+)", outbox[-1][2]).group(1)
    assert _login("ana", new)[1].status_code == 303


def test_forgot_and_reset_password(ana, outbox):
    c = TestClient(app)
    res = c.post("/esqueci", data={"login": "ana@ex.com"})
    assert "Se esse usuário" in res.text
    link = re.search(r"(/redefinir/\S+)", outbox[-1][2]).group(1)
    assert "ana" in c.get(link).text
    res = c.post(link, data={"password": "nova-senha-1", "confirm": "outra"})
    assert "não batem" in res.text
    res = c.post(link, data={"password": "nova-senha-1", "confirm": "nova-senha-1"}, follow_redirects=False)
    assert res.status_code == 303
    assert "expirou ou já foi usado" in c.get(link).text  # single use
    assert _login("ana", "nova-senha-1")[1].status_code == 303
    # unknown accounts get the same answer and no email
    n = len(outbox)
    assert "Se esse usuário" in c.post("/esqueci", data={"login": "ninguem"}).text
    assert len(outbox) == n


def test_change_password_and_profile(ana_client, db, ana):
    res = ana_client.post("/conta/senha", data={"current": "errada", "password": "abcdefgh", "confirm": "abcdefgh"})
    assert "incorreta" in res.text
    res = ana_client.post("/conta/senha", data={"current": PASSWORD, "password": "abcdefgh", "confirm": "abcdefgh"})
    assert "Senha trocada" in res.text
    assert ana_client.get("/", follow_redirects=False).status_code == 200  # still logged in here
    assert _login("ana", "abcdefgh")[1].status_code == 303
    res = ana_client.post("/conta", data={"name": "Ana Lu", "username": "analu", "email": "ANA@ex.com", "phone": ""})
    assert "Dados salvos" in res.text
    db.expire_all()
    assert db.get(Member, ana.id).username == "analu"


def test_password_hash_roundtrip():
    h = auth.hash_password("x" * 10)
    assert auth.verify_password("x" * 10, h) and not auth.verify_password("y" * 10, h)
    assert not auth.verify_password("x", None)
