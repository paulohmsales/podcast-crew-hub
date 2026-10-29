# podcast-crew-hub

A small web app a podcast crew uses to run their show, from the first episode idea
to the published episode. It was built for **Então Ganhei**, a Brazilian board-game
podcast with seven hosts who used to coordinate everything over WhatsApp. It runs in
production for them, so the UI is in Portuguese.

**What it does**

- **Episode pipeline:** a kanban board (Idea → On the agenda → Scheduled → Recorded →
  Published) with drag and drop that works with a mouse and on touch screens. Members
  vote on ideas, the cards show the segment colors, host photos and a listen link,
  and each column scrolls on its own.
- **Episode page:** a summary, a shared script that saves on its own (server-side
  diff-match-patch merge, version history and restore, a "someone is editing"
  indicator), the games covered, comments and a change history.
- **Scheduling:** when2meet-style availability polls, the best time slots, an .ics
  invite and WhatsApp share links.
- **Games:** search the Ludopedia catalog by name or mechanic and see which
  episodes covered each game.
- **Numbers:** a BI page with releases per month, episodes per segment, who
  recorded most, the most-discussed games and the episode funnel, filterable by year.
- **Onboarding:** a photo step and a help popup that opens on each new visit until a
  member turns it off; it's always one click away afterwards.

**Stack:** FastAPI, Jinja templates, SQLAlchemy and Alembic on SQLite, with plain JS
and CSS (no frontend build). It's deployed as a Docker Swarm service behind Traefik
on a single VPS, with daily backups. Tests use pytest.

---

# Então Ganhei

App do grupo do podcast: **episódios** num painel kanban (Ideia → Na pauta →
Agendado → Gravado → Publicado; votos, comentários, quadros, participantes,
link e data de publicação), **quadros** (os segmentos fixos do podcast) e **agenda** (rodadas de disponibilidade estilo when2meet, melhores horários,
gravação marcada com convite .ics e atalhos de WhatsApp).

FastAPI + Jinja, SQLite, sem build de frontend.

## Rodar local

    uv sync
    uv run alembic upgrade head
    uv run python -m app.cli add-member "Paulo" paulo@exemplo.com --admin
    uv run uvicorn app.main:app --reload

Testes: `uv run pytest`.

## Login

Email e senha. Na página **Grupo**, um admin adiciona a pessoa (nome e email).
No primeiro acesso ela entra com o email e a senha que digitar vira a dela
(mínimo 8 caracteres). Esqueceu a senha: um admin clica em "liberar novo
acesso" e o próximo login com o email define a senha de novo. Nada é enviado
por email.

## Produção (VPS)

Serviço Swarm `entaoganhei_web` atrás
do Traefik; banco SQLite no volume `entaoganhei_data`.

    deploy/deploy.sh          # rsync → build no VPS → stack deploy (migrações rodam no start)

Primeira vez, no VPS: `/opt/entaoganhei/src/deploy/install-backup.sh` (backup diário
em `/opt/entaoganhei/backups`, 30 dias). Liberar o primeiro acesso de um admin pela linha de comando:

    ssh jobz-vps 'docker exec $(docker ps -q -f name=entaoganhei_web) python -m app.cli first-access Paulo --email paulo@exemplo.com'

## Próximos passos

- Jogos via LudoAPI (Ludopedia): app cadastrado em ludopedia.com.br/aplicativos,
  `access_token` do dono do app no servidor; `/jogos?search=`, `/jogos/{id}`.
- Estatísticas: lista de episódios pelo RSS/Spotify; números de plays via CSV
  exportado do Spotify for Creators.
