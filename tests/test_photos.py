import io
from datetime import datetime

from PIL import Image

from app import photos
from app.models import Member, Theme
from tests.conftest import _client


def _jpeg(w=800, h=600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


def test_initials():
    assert photos.initials("Paulo Sales") == "PS"
    assert photos.initials("ana") == "A"
    assert photos.initials("João da Silva") == "JS"
    assert photos.initials("  ") == "?"


def test_card_shows_initials_then_photo(client, paulo, db):
    paulo.name = "Paulo Sales"
    t = Theme(title="Party games", created_by_id=paulo.id, participants=[paulo])
    db.add(t)
    db.commit()
    board = client.get("/episodios").text
    assert ">PS</span>" in board

    res = client.post("/conta/foto", files={"file": ("me.jpg", _jpeg(), "image/jpeg")})
    assert "Foto atualizada" in res.text
    db.refresh(paulo)
    assert paulo.photo and paulo.photo.endswith(".webp")
    with Image.open(photos.PHOTO_DIR / paulo.photo) as img:
        assert img.size == (photos.SIZE, photos.SIZE)
    assert f'src="/fotos/{paulo.photo}"' in client.get("/episodios").text
    assert client.get(f"/fotos/{paulo.photo}").headers["content-type"] == "image/webp"

    old = paulo.photo
    client.post("/conta/foto", files={"file": ("me.jpg", _jpeg(300, 900), "image/jpeg")})
    db.refresh(paulo)
    assert paulo.photo != old and not (photos.PHOTO_DIR / old).exists()

    client.post("/conta/foto/remover")
    db.refresh(paulo)
    assert paulo.photo is None and ">PS</span>" in client.get("/episodios").text


def test_rejects_non_images_and_bad_paths(client, paulo, db):
    res = client.post("/conta/foto", files={"file": ("x.jpg", b"<svg onload=alert(1)>", "image/jpeg")})
    assert "Não consegui ler" in res.text
    db.refresh(paulo)
    assert paulo.photo is None
    assert client.get("/fotos/..%2Fentao.db").status_code == 404
    assert client.get("/fotos/1-abc.webp").status_code == 404


def test_first_access_asks_for_photo_then_guide(db):
    novo = Member(name="Bia Costa", email="bia@ex.com", password_hash="x")
    db.add(novo)
    db.commit()
    c = _client(novo)
    res = c.get("/", follow_redirects=False)
    assert res.headers["location"] == "/bem-vindo/foto"
    page = c.get("/bem-vindo/foto").text
    assert "foto sua" in page and ">BC</span>" in page and 'href="/bem-vindo"' in page  # can skip
    res = c.post("/conta/foto", data={"next": "/bem-vindo"}, files={"file": ("b.jpg", _jpeg(), "image/jpeg")},
                 follow_redirects=False)
    assert res.headers["location"] == "/bem-vindo"
    db.refresh(novo)
    assert novo.photo
    page = c.get("/", follow_redirects=False)
    assert page.status_code == 200 and "data-auto" in page.text  # with a photo: home, guide opens


def test_home_nudges_members_without_photo(client):
    assert "Adicionar foto" in client.get("/").text
