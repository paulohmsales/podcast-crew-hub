# Então Ganhei

App do grupo do podcast: **temas** (sugerir, votar, comentar, acompanhar status)
e **agenda** (rodadas de disponibilidade estilo when2meet, melhores horários,
gravação marcada com convite .ics e atalhos de WhatsApp).

FastAPI + Jinja, SQLite, sem build de frontend.

## Rodar local

    uv sync
    uv run alembic upgrade head
    uv run python -m app.cli add-member "Paulo" --admin   # imprime o link de login
    uv run uvicorn app.main:app --reload

Testes: `uv run pytest`.

## Login

Sem senha: cada pessoa tem um link pessoal (`/entrar/<token>`) que grava um
cookie. Admins adicionam gente e mandam o link pelo WhatsApp na página **Grupo**;
"novo link" invalida o anterior.

## Produção (VPS)

https://podcast.example.com — serviço Swarm `entaoganhei_web` atrás
do Traefik; banco SQLite no volume `entaoganhei_data`.

    deploy/deploy.sh          # rsync → build no VPS → stack deploy (migrações rodam no start)

Primeira vez, no VPS: `/opt/entaoganhei/src/deploy/install-backup.sh` (backup diário
em `/opt/entaoganhei/backups`, 30 dias). Criar o primeiro admin:

    ssh jobz-vps 'docker exec $(docker ps -q -f name=entaoganhei_web) python -m app.cli add-member "Paulo" --admin'

## Próximos passos

- Jogos via LudoAPI (Ludopedia): app cadastrado em ludopedia.com.br/aplicativos,
  `access_token` do dono do app no servidor; `/jogos?search=`, `/jogos/{id}`.
- Estatísticas: lista de episódios pelo RSS/Spotify; números de plays via CSV
  exportado do Spotify for Creators.
