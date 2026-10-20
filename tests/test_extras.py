from datetime import date

import pytest

from app import branding, feed, ludopedia
from app.models import Game, Theme

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel><title>Ent\xc3\xa3o Ganhei</title>
<item><title>Ent\xc3\xa3o Ganhei!: Ep.2 - Party games</title><guid>ep-2</guid><pubDate>Tue, 07 Oct 2025 12:00:00 GMT</pubDate>
  <link>https://creators.spotify.com/pod/show/eg/episodes/2</link><itunes:episode>2</itunes:episode>
  <description><![CDATA[<p>Falamos de <b>Codenames</b></p><p>e Dixit</p>]]></description></item>
<item><title>Ep.1 - Estreia</title><guid>ep-1</guid><pubDate>Tue, 30 Sep 2025 12:00:00 GMT</pubDate>
  <enclosure url="https://cdn.example/1.mp3" type="audio/mpeg"/></item>
</channel></rss>"""


def test_feed_parse_and_import_dedupes(paulo, db):
    eps = feed.parse(FEED)
    assert [e.title for e in eps] == ["Party games", "Estreia"]
    assert eps[1].number == 1  # from the title when there's no itunes:episode
    assert eps[0].published_on == date(2025, 10, 7) and eps[0].number == 2
    assert eps[0].description == "Falamos de Codenames\ne Dixit"
    assert eps[1].url == "https://cdn.example/1.mp3"
    assert feed.import_episodes(db, eps, paulo) == (2, 0)
    assert feed.import_episodes(db, eps, paulo) == (0, 2)  # running again is safe
    t = db.query(Theme).filter_by(number=2).one()
    assert t.status == "publicado" and t.episode_url.endswith("/episodes/2")
    with pytest.raises(feed.FeedError):
        feed.parse(b"<html>not a feed")


def test_import_page_admin_only(client, ana_client, monkeypatch):
    monkeypatch.setattr(feed, "fetch", lambda url: FEED)
    assert ana_client.get("/episodios/importar").status_code == 403
    res = client.post("/episodios/importar", data={"url": "https://x/rss"})
    assert "Criados: <strong>2</strong>" in res.text
    assert "Estreia" in client.get("/episodios").text


def test_new_idea_has_its_own_page(client):
    assert 'action="/episodios"' in client.get("/episodios/nova").text
    board = client.get("/episodios").text
    assert "Nova ideia de episódio" not in board and 'href="/episodios/nova"' in board
    assert "Nova ideia de episódio" not in client.get("/episodios?ver=lista").text


DETAIL = {
    "id_jogo": 404, "nm_jogo": "Terra Mystica", "thumb": "https://img/404_t.jpg",
    "link": "https:ludopedia.com.br/jogo/terra-mystica", "ano_publicacao": 2012,
    "qt_jogadores_min": 2, "qt_jogadores_max": 5, "vl_tempo_jogo": 100, "idade_minima": 12,
    "mecanicas": [{"id_mecanica": 1, "nm_mecanica": "Controle de Área"}],
    "categorias": [{"id_categoria": 2, "nm_categoria": "Fantasia"}],
}


@pytest.fixture
def fake_ludopedia(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path == "/mecanicas":
            return {"mecanicas": [{"id_mecanica": 7, "nm_mecanica": "Alocação de Trabalhadores"},
                                  {"id_mecanica": 8, "nm_mecanica": "Velha_deleted"}]}
        if path == "/jogos":
            return {"jogos": [{"id_jogo": 404, "nm_jogo": "Terra Mystica", "nm_original": "Terra Mystica",
                               "thumb": "https://img/404_t.jpg", "link": "jogo/terra-mystica"}],
                    "total": 1}
        return DETAIL

    monkeypatch.setenv("LUDOPEDIA_TOKEN", "tok")
    monkeypatch.setattr(ludopedia, "_get", fake_get)
    ludopedia._search_cache.clear()
    ludopedia._mechanics_cache.clear()
    return calls


def test_add_game_to_episode(client, db, fake_ludopedia):
    res = client.post("/episodios", data={"title": "Euros"})
    t = int(res.url.path.rsplit("/", 1)[1])
    page = client.get(f"/episodios/{t}?jogo=terra").text
    assert "Terra Mystica" in page and 'name="game_id" value="404"' in page
    client.post(f"/episodios/{t}/jogos", data={"game_id": "404"})
    db.expire_all()
    game = db.get(Game, 404)
    assert game.players == "2–5" and game.mechanic_list == ["Controle de Área"]
    assert game.link == "https://ludopedia.com.br/jogo/terra-mystica"  # API's missing slashes fixed
    assert [g.id for g in db.get(Theme, t).games] == [404]
    assert "já falamos" in client.get("/jogos?q=terra").text
    assert "Euros" in client.get("/jogos/404").text
    n = len(fake_ludopedia)
    client.get("/jogos?q=terra")
    assert len(fake_ludopedia) == n  # search cached
    client.post(f"/episodios/{t}/jogos/404/remover")
    db.expire_all()
    assert db.get(Theme, t).games == []


def test_ludopedia_not_configured(client):
    assert "Ludopedia ainda não conectada" in client.get("/jogos").text
    assert "LUDOPEDIA_TOKEN" in client.get("/jogos?q=azul").text


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def test_logo_upload_and_reset(client, ana_client):
    assert client.get("/logo", follow_redirects=False).headers["location"] == "/static/icon.svg"
    res = ana_client.post("/aparencia/logo", files={"file": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")})
    assert "PNG, JPG, WEBP ou GIF" in res.text
    ana_client.post("/aparencia/logo", files={"file": ("logo.png", PNG, "image/png")})
    res = client.get("/logo")
    assert res.headers["content-type"] == "image/png" and res.content == PNG
    assert "/logo?v=" in client.get("/").text
    client.post("/aparencia/logo/padrao")
    assert branding.current() is None


def test_search_by_mechanic(client, fake_ludopedia):
    page = client.get("/jogos").text
    assert "Alocação de Trabalhadores" in page and "Velha_deleted" not in page
    page = client.get("/jogos?mecanica=7").text
    assert "Terra Mystica" in page and 'href="/jogos/404"' in page
    assert ("/jogos", {"page": 1, "rows": 20, "id_mecanica": 7}) in fake_ludopedia
    results, _ = ludopedia.search("terra")
    assert results[0]["link"] == "https://ludopedia.com.br/jogo/terra-mystica"


def test_tidy_title():
    assert feed.tidy_title("Então Ganhei!: Ep.42 - Turno Duplo Especial - Doff 2026 ") == ("Turno Duplo Especial - Doff 2026", 42)
    assert feed.tidy_title("Episódio 7: Wargames") == ("Wargames", 7)
    assert feed.tidy_title("Especial de Natal") == ("Especial de Natal", None)


def test_spotify_import(monkeypatch, paulo, db):
    import io, json as _json
    pages = {
        "https://api.spotify.com/v1/shows/6qpGRBoKE0KOMPsnUcDGYR/episodes?market=BR&limit=50": {
            "items": [{"id": "a" * 22, "name": "Então Ganhei!: Ep.42 - Turno Duplo", "release_date": "2026-07-29",
                       "release_date_precision": "day", "external_urls": {"spotify": "https://open.spotify.com/episode/x"},
                       "description": "desc"}],
            "next": "https://api.spotify.com/v1/page2"},
        "https://api.spotify.com/v1/page2": {"items": [{"id": "b" * 22, "name": "Ep.41 - Outro", "release_date": "2026-07",
                             "release_date_precision": "month", "external_urls": {}}], "next": None},
    }

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        if "accounts.spotify.com" in req.full_url:
            return Resp(b'{"access_token": "t"}')
        return Resp(_json.dumps(pages[req.full_url]).encode())

    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.setattr(feed.urllib.request, "urlopen", fake_urlopen)
    eps = feed.load("https://open.spotify.com/show/6qpGRBoKE0KOMPsnUcDGYR?si=abc")
    assert [(e.number, e.title, e.published_on) for e in eps] == [(42, "Turno Duplo", date(2026, 7, 29)), (41, "Outro", None)]
    assert feed.import_episodes(db, eps, paulo) == (2, 0)


def test_spotify_needs_credentials(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with pytest.raises(feed.FeedError, match="SPOTIFY_CLIENT_ID"):
        feed.load("https://open.spotify.com/show/6qpGRBoKE0KOMPsnUcDGYR")
