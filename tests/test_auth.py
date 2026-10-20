from fastapi.testclient import TestClient

from app import auth
from app.main import app
from app.models import LoginSession, Member
from tests.conftest import PASSWORD


def _login(email, password):
    c = TestClient(app)
    res = c.post("/entrar", data={"email": email, "password": password}, follow_redirects=False)
    return c, res


def test_login_with_email(paulo):
    c, res = _login(" Paulo@EX.com ", PASSWORD)  # case and spaces don't matter
    assert res.status_code == 303 and res.headers["location"] == "/"
    assert "Oi, Paulo" in c.get("/").text


def test_wrong_password_unknown_email_and_throttle(paulo):
    assert "Senha incorreta" in _login("paulo@ex.com", "errada")[1].text
    assert "não está no grupo" in _login("x@ex.com", "qualquer-coisa")[1].text
    for _ in range(10):
        _login("paulo@ex.com", "errada")
    assert "Muitas tentativas" in _login("paulo@ex.com", PASSWORD)[1].text


def test_first_access_sets_password(client, db):
    client.post("/membros", data={"name": "Caio", "email": "Caio@ex.com"})
    caio = db.query(Member).filter_by(email="caio@ex.com").one()
    assert caio.password_hash is None
    assert "ainda não entrou" in client.get("/membros").text
    # too short: refused, still no password
    assert "Primeiro acesso" in _login("caio@ex.com", "curta")[1].text
    c, res = _login("caio@ex.com", "minha-senha")
    assert res.status_code == 303 and "Oi, Caio" in c.get("/").text
    # from now on only that password works
    assert "Senha incorreta" in _login("caio@ex.com", "outra-senha")[1].text
    assert _login("caio@ex.com", "minha-senha")[1].status_code == 303


def test_admin_reopens_first_access(client, ana_client, ana, db):
    assert ana_client.post(f"/membros/{ana.id}/liberar").status_code == 403
    client.post(f"/membros/{ana.id}/liberar")
    assert ana_client.get("/", follow_redirects=False).status_code == 303  # logged out
    assert _login("ana@ex.com", "nova-senha-ana")[1].status_code == 303
    assert "Senha incorreta" in _login("ana@ex.com", PASSWORD)[1].text


def test_add_member_validation(client, ana_client):
    assert ana_client.post("/membros", data={"name": "X", "email": "x@ex.com"}).status_code == 403
    assert "Email inválido" in client.post("/membros", data={"name": "X", "email": "nope"}).text
    assert "já está em uso" in client.post("/membros", data={"name": "X", "email": "ANA@ex.com"}).text


def test_logout_kills_session(client, db):
    assert client.get("/", follow_redirects=False).status_code == 200
    client.post("/sair")
    assert db.query(LoginSession).count() == 0
    assert client.get("/", follow_redirects=False).headers["location"] == "/entrar"


def test_change_password_and_profile(ana_client, db, ana):
    res = ana_client.post("/conta/senha", data={"current": "errada", "password": "abcdefgh", "confirm": "abcdefgh"})
    assert "incorreta" in res.text
    res = ana_client.post("/conta/senha", data={"current": PASSWORD, "password": "abcdefgh", "confirm": "abcdefgh"})
    assert "Senha trocada" in res.text
    assert ana_client.get("/", follow_redirects=False).status_code == 200  # still logged in here
    assert _login("ana@ex.com", "abcdefgh")[1].status_code == 303
    res = ana_client.post("/conta", data={"name": "Ana Lu", "email": "ANALU@ex.com", "phone": ""})
    assert "Dados salvos" in res.text
    db.expire_all()
    assert db.get(Member, ana.id).email == "analu@ex.com"


def test_password_hash_roundtrip():
    h = auth.hash_password("x" * 10)
    assert auth.verify_password("x" * 10, h) and not auth.verify_password("y" * 10, h)
    assert not auth.verify_password("x", None)
