from datetime import date

from app.models import Member, Poll, Segment, Theme


def _new(client, title):
    res = client.post("/episodios", data={"title": title})
    return int(res.url.path.rsplit("/", 1)[1])


def test_board_columns_and_drag_status(client, db):
    a = _new(client, "Jogos de blefe")
    b = _new(client, "Euros")
    client.post(f"/episodios/{b}/status", data={"status": "gravado"})
    page = client.get("/episodios").text
    for label in ("Ideia", "Na pauta", "Agendado", "Gravado", "Publicado"):
        assert label in page
    assert "Jogos de blefe" in page and "Euros" in page

    # drag and drop sends Accept: application/json and gets JSON back
    res = client.post(f"/episodios/{a}/status", data={"status": "publicado"}, headers={"Accept": "application/json"})
    assert res.json() == {"ok": True, "status": "publicado"}
    db.expire_all()
    assert db.get(Theme, a).published_on == date.today()  # publishing stamps the air date

    client.post(f"/episodios/{b}/status", data={"status": "descartado"})
    assert "Euros" not in client.get("/episodios").text
    assert "Euros" in client.get("/episodios?descartados=1").text


def test_edit_episode_segments_participants_link(client, db, paulo, ana):
    client.post("/quadros", data={"name": "Jogo da Semana"})
    client.post("/quadros", data={"name": "Notícias"})
    seg = db.query(Segment).filter_by(name="Jogo da Semana").one()
    t = _new(client, "Especial Azul")
    client.post(f"/episodios/{t}/editar", data={
        "title": "Especial Azul", "number": "42", "episode_url": "https://open.spotify.com/episode/abc",
        "published_on": "2026-10-01", "segment_ids": [str(seg.id)], "member_ids": [str(paulo.id), str(ana.id)],
    })
    db.expire_all()
    theme = db.get(Theme, t)
    assert theme.number == 42 and theme.published_on == date(2026, 10, 1)
    assert [s.name for s in theme.segments] == ["Jogo da Semana"]
    assert [m.name for m in theme.participants] == ["Ana", "Paulo"]

    board = client.get("/episodios").text
    assert "#42" in board and "Jogo da Semana" in board and "Ana, Paulo" in board and "open.spotify.com/episode/abc" in board
    # filter by segment
    other = _new(client, "Sem quadro")
    assert "Sem quadro" not in client.get(f"/episodios?quadro={seg.id}").text
    assert "Especial Azul" in client.get(f"/episodios?quadro={seg.id}").text
    # clearing the checkboxes removes them
    client.post(f"/episodios/{t}/editar", data={"title": "Especial Azul"})
    db.expire_all()
    assert db.get(Theme, t).participants == [] and db.get(Theme, t).segments == []


def test_segments_order_archive_and_unique(client, db):
    for name in ("A", "B", "C"):
        client.post("/quadros", data={"name": name})
    c = db.query(Segment).filter_by(name="C").one()
    client.post(f"/quadros/{c.id}/mover", data={"direcao": "cima"})
    db.expire_all()
    order = [s.name for s in db.query(Segment).order_by(Segment.position)]
    assert order == ["A", "C", "B"]
    assert client.post("/quadros", data={"name": "a"}).status_code == 400
    client.post(f"/quadros/{c.id}/arquivar")
    db.expire_all()
    assert db.get(Segment, c.id).archived
    assert "Arquivados" in client.get("/quadros").text


def test_booking_from_poll_fills_lineup(client, ana_client, db, paulo, ana):
    t = _new(client, "Party games")
    res = client.post("/agenda", data={"theme_id": str(t), "start_date": "2026-11-02", "end_date": "2026-11-02",
                                       "day_start": "19:00", "day_end": "22:00", "slot_minutes": "30"})
    poll_id = int(res.url.path.rsplit("/", 1)[1])
    client.post(f"/agenda/{poll_id}/disponibilidade", json={"slots": ["2026-11-02T19:00", "2026-11-02T19:30", "2026-11-02T20:00"]})
    ana_client.post(f"/agenda/{poll_id}/disponibilidade", json={"slots": ["2026-11-02T19:00"]})
    client.post(f"/agenda/{poll_id}/marcar", data={"starts_at": "2026-11-02T19:00", "duration_minutes": "90"})
    db.expire_all()
    assert [m.name for m in db.get(Theme, t).participants] == ["Paulo"]  # Ana only had 30 min


def test_old_theme_urls_redirect(client):
    res = client.get("/temas/5", follow_redirects=False)
    assert res.status_code == 301 and res.headers["location"] == "/episodios/5"
    assert client.get("/temas", follow_redirects=False).headers["location"] == "/episodios"
