# Então Ganhei

App do grupo do podcast: **temas** (sugerir, votar, comentar, acompanhar status)
e **agenda** (rodadas de disponibilidade estilo when2meet, melhores horários,
gravação marcada com convite .ics e atalhos de WhatsApp).

FastAPI + Jinja, SQLite, sem build de frontend.

## Rodar local

    uv sync
    uv run alembic upgrade head
    uv run python -m app.cli add-member "Paulo" --username paulo --admin   # imprime a senha
    uv run uvicorn app.main:app --reload

Testes: `uv run pytest`.

## Login

Usuário (ou email) e senha. Na página **Grupo**, um admin adiciona a pessoa
(nome, usuário, email); o app gera uma senha e manda usuário + senha por email
(SMTP de uma conta Gmail). Se o email falhar, a senha aparece na tela uma vez para passar por
outro canal. "Reenviar acesso" gera uma senha nova. Cada um troca a senha e o
email em **Minha conta**, e "Esqueci minha senha" manda um link (2 h, uso único).

Email: `SMTP_USER` (o Gmail) e `SMTP_PASSWORD` (senha de app do Gmail, exige
verificação em duas etapas) em `/opt/entaoganhei/.env` no VPS; opcionais
`SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM`. Depois de editar: `docker service update
--force entaoganhei_web`.

## Produção (VPS)

https://podcast.example.com — serviço Swarm `entaoganhei_web` atrás
do Traefik; banco SQLite no volume `entaoganhei_data`.

    deploy/deploy.sh          # rsync → build no VPS → stack deploy (migrações rodam no start)

Primeira vez, no VPS: `/opt/entaoganhei/src/deploy/install-backup.sh` (backup diário
em `/opt/entaoganhei/backups`, 30 dias). Criar o primeiro admin:

    ssh jobz-vps 'docker exec $(docker ps -q -f name=entaoganhei_web) python -m app.cli reset-password paulo'

## Próximos passos

- Jogos via LudoAPI (Ludopedia): app cadastrado em ludopedia.com.br/aplicativos,
  `access_token` do dono do app no servidor; `/jogos?search=`, `/jogos/{id}`.
- Estatísticas: lista de episódios pelo RSS/Spotify; números de plays via CSV
  exportado do Spotify for Creators.
