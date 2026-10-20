from app.models import ScriptRevision, Theme


def _new(client, title="Episódio"):
    res = client.post("/episodios", data={"title": title})
    return int(res.url.path.rsplit("/", 1)[1])


def _save(c, t, base_version, base_text, text):
    return c.post(f"/episodios/{t}/roteiro", json={"base_version": base_version, "base_text": base_text, "text": text})


def test_tabs_render(client):
    t = _new(client)
    for tab in ("", "?aba=roteiro", "?aba=jogos", "?aba=conversa", "?aba=historico", "?aba=xyz"):
        assert client.get(f"/episodios/{t}{tab}").status_code == 200
    page = client.get(f"/episodios/{t}").text
    assert "▲ 1 voto" in page and "Querem gravar" not in page


def test_script_saves_and_merges_concurrent_edits(client, ana_client, db):
    t = _new(client)
    first = "Abertura\n\nBloco 1: notícias\n\nEncerramento\n"
    res = _save(client, t, 0, "", first).json()
    assert res["version"] == 1 and res["text"] == first

    # Both start from version 1; Paulo edits the top, Ana the bottom.
    paulo = first.replace("Abertura", "Abertura com vinheta")
    ana = first.replace("Encerramento", "Encerramento e recados")
    assert _save(client, t, 1, first, paulo).json()["version"] == 2
    merged = _save(ana_client, t, 1, first, ana).json()
    assert merged["version"] == 3
    assert "Abertura com vinheta" in merged["text"] and "Encerramento e recados" in merged["text"]

    db.expire_all()
    theme = db.get(Theme, t)
    assert theme.script == merged["text"] and theme.script_updated_by.name == "Ana"
    # Ana sees Paulo editing (he saved seconds ago)
    assert "Paulo" in ana_client.get(f"/episodios/{t}/roteiro.json").json()["editing"]
    assert client.get(f"/episodios/{t}/roteiro.txt").text == merged["text"]


def test_script_revisions_and_restore(client, db):
    t = _new(client)
    _save(client, t, 0, "", "versão um")
    rev = db.query(ScriptRevision).filter_by(theme_id=t).one()
    _save(client, t, 1, "versão um", "versão um, editada")  # same session: updates the same copy
    db.expire_all()
    assert db.query(ScriptRevision).filter_by(theme_id=t).count() == 1
    rev.text = "versão antiga"
    db.commit()
    client.post(f"/episodios/{t}/roteiro/versoes/{rev.id}/restaurar")
    db.expire_all()
    assert db.get(Theme, t).script == "versão antiga"


def test_history_logs_changes(client, ana_client, db, paulo, ana):
    t = _new(client, "Blefe")
    client.post(f"/episodios/{t}/status", data={"status": "pauta"})
    ana_client.post(f"/episodios/{t}/editar", data={"title": "Blefe", "number": "7", "member_ids": [str(paulo.id)]})
    ana_client.post(f"/episodios/{t}/comentarios", data={"body": "boa"})
    _save(client, t, 0, "", "roteiro")
    _save(client, t, 1, "roteiro", "roteiro 2")  # within 30 min: no second history line
    page = client.get(f"/episodios/{t}?aba=historico").text
    for line in ("sugeriu o episódio", "moveu de Ideia para Na pauta", "editou o número e os participantes",
                 "comentou na conversa", "editou o roteiro"):
        assert line in page, line
    assert page.count("editou o roteiro") == 1


def test_edit_page(client):
    t = _new(client, "Original")
    assert 'action="/episodios/%d/editar"' % t in client.get(f"/episodios/{t}/editar").text
    client.post(f"/episodios/{t}/editar", data={"title": "Novo título"})
    assert "Novo título" in client.get(f"/episodios/{t}").text
