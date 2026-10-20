from datetime import date, datetime

from app import schedule
from app.models import Member, Poll, PollSlot, Recording, Theme, ThemeVote


def test_requires_login():
    from fastapi.testclient import TestClient

    from app.main import app

    res = TestClient(app).get("/", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/entrar"


def test_theme_create_vote_comment_status(client, ana_client, db):
    res = client.post("/temas", data={"title": "Jogos de blefe", "description": "Coup, Skull", "links": "https://x.y\n"})
    theme_id = int(res.url.path.rsplit("/", 1)[1])
    # creator's vote is automatic; Ana adds hers, then takes it back
    ana_client.post(f"/temas/{theme_id}/voto")
    assert db.query(ThemeVote).filter_by(theme_id=theme_id).count() == 2
    ana_client.post(f"/temas/{theme_id}/voto")
    assert db.query(ThemeVote).filter_by(theme_id=theme_id).count() == 1

    ana_client.post(f"/temas/{theme_id}/comentarios", data={"body": "Adiciono Love Letter"})
    page = client.get(f"/temas/{theme_id}").text
    assert "Adiciono Love Letter" in page and "Coup, Skull" in page

    client.post(f"/temas/{theme_id}/status", data={"status": "pauta"})
    db.expire_all()
    assert db.get(Theme, theme_id).status == "pauta"
    assert "Jogos de blefe" in client.get("/temas").text
    assert "Jogos de blefe" not in client.get("/temas?status=publicado").text


def test_only_creator_or_admin_deletes_theme(client, ana_client, db):
    res = ana_client.post("/temas", data={"title": "Euros"})
    theme_id = int(res.url.path.rsplit("/", 1)[1])
    from tests.conftest import _client, _member

    bia = _client(_member(db, "Bia"))
    assert bia.post(f"/temas/{theme_id}/excluir").status_code == 403
    client.post(f"/temas/{theme_id}/excluir")  # admin
    db.expire_all()
    assert db.get(Theme, theme_id) is None


def _make_poll(client, **extra):
    data = {"start_date": "2026-11-02", "end_date": "2026-11-04", "day_start": "19:00", "day_end": "22:00", "slot_minutes": "30"}
    data.update(extra)
    res = client.post("/agenda", data=data)
    assert res.status_code == 200, res.text
    return int(res.url.path.rsplit("/", 1)[1])


def test_poll_availability_and_best_window(client, ana_client, db, paulo, ana):
    poll_id = _make_poll(client)
    # both free Tue 19:00-21:00; Paulo also Mon
    client.post(f"/agenda/{poll_id}/disponibilidade", json={"slots": [
        "2026-11-02T19:00", "2026-11-02T19:30",
        "2026-11-03T19:00", "2026-11-03T19:30", "2026-11-03T20:00", "2026-11-03T20:30",
    ]})
    res = ana_client.post(f"/agenda/{poll_id}/disponibilidade", json={"slots": [
        "2026-11-03T19:00", "2026-11-03T19:30", "2026-11-03T20:00", "2026-11-03T20:30",
        "2026-11-09T19:00",  # outside the poll: ignored
    ]})
    assert res.json() == {"ok": True, "saved": 4}

    poll = db.get(Poll, poll_id)
    windows = schedule.best_windows(poll, [paulo, ana])
    assert windows[0].start == datetime(2026, 11, 3, 19, 0)
    assert windows[0].end == datetime(2026, 11, 3, 21, 0)
    assert [m.name for m in windows[0].members] == ["Ana", "Paulo"]
    assert "ter 03/11, 19:00–21:00" in client.get(f"/agenda/{poll_id}").text

    # re-saving replaces the old answer
    ana_client.post(f"/agenda/{poll_id}/disponibilidade", json={"slots": []})
    db.expire_all()
    assert db.query(PollSlot).filter_by(poll_id=poll_id, member_id=ana.id).count() == 0
    assert "falta você" not in ana_client.get("/agenda").text  # answered "none" still counts


def test_book_recording_schedules_theme_and_ics(client, db):
    res = client.post("/temas", data={"title": "Party games"})
    theme_id = int(res.url.path.rsplit("/", 1)[1])
    poll_id = _make_poll(client, theme_id=str(theme_id))
    client.post(f"/agenda/{poll_id}/marcar", data={"starts_at": "2026-11-03T19:00", "duration_minutes": "90"})
    db.expire_all()
    poll = db.get(Poll, poll_id)
    assert poll.closed
    assert db.get(Theme, theme_id).status == "agendado"
    rec = db.query(Recording).one()
    ics = client.get(f"/agenda/gravacoes/{rec.id}.ics")
    assert "DTSTART;TZID=America/Sao_Paulo:20261103T190000" in ics.text
    assert "Party games" in ics.text
    # closed polls refuse new availability
    assert client.post(f"/agenda/{poll_id}/disponibilidade", json={"slots": []}).status_code == 409

    client.post(f"/agenda/gravacoes/{rec.id}/gravado")
    db.expire_all()
    assert db.get(Theme, theme_id).status == "gravado"


def test_poll_until_midnight(client, db):
    poll_id = _make_poll(client, day_start="22:00", day_end="00:00")
    poll = db.get(Poll, poll_id)
    assert poll.day_end == 24 * 60
    assert schedule.poll_times(poll) == [1320, 1350, 1380, 1410]


def test_best_windows_prefers_more_people_then_longer():
    a, b, c = (Member(id=i, name=n) for i, n in [(1, "A"), (2, "B"), (3, "C")])
    poll = Poll(start_date=date(2026, 11, 2), end_date=date(2026, 11, 2), day_start=18 * 60, day_end=23 * 60, slot_minutes=30)
    free = {
        1: ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00", "21:30"],
        2: ["20:00", "20:30", "21:00"],
        3: ["20:00", "20:30", "21:00", "21:30", "22:00"],
    }
    poll.availability = [
        PollSlot(member_id=m, slot=datetime.fromisoformat(f"2026-11-02T{t}")) for m, ts in free.items() for t in ts
    ]
    windows = schedule.best_windows(poll, [a, b, c])
    assert (windows[0].label, len(windows[0].members)) == ("seg 02/11, 20:00–21:30", 3)
    # next best: A and C for longer
    assert (windows[1].label, len(windows[1].members)) == ("seg 02/11, 20:00–22:00", 2)
