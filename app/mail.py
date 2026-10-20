"""Outgoing email through Resend's HTTP API (stdlib only)."""

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
FROM = os.environ.get("MAIL_FROM", "Então Ganhei <onboarding@resend.dev>")


class MailError(Exception):
    pass


def send(to: str, subject: str, text: str) -> None:
    """Raises MailError when the mail can't be handed to Resend."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise MailError("RESEND_API_KEY não configurada no servidor.")
    body = json.dumps({"from": FROM, "to": [to], "subject": subject, "text": text}).encode()
    req = urllib.request.Request(
        RESEND_API_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "entaoganhei"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        log.warning("resend %s for %s: %s", e.code, to, detail)
        raise MailError(f"Resend recusou o envio ({e.code}): {detail}") from e
    except OSError as e:
        raise MailError(f"Falha ao falar com o Resend: {e}") from e


def welcome_text(name: str, username: str, password: str, url: str) -> str:
    return f"""Oi, {name}!

Você tem acesso ao app do Então Ganhei: temas, votação e agenda das gravações.

Endereço: {url}/entrar
Usuário:  {username}
Senha:    {password}

Depois de entrar, troque a senha em "Minha conta".
"""


def reset_text(name: str, url: str) -> str:
    return f"""Oi, {name}!

Alguém pediu para redefinir a sua senha do app do Então Ganhei.
Para criar uma senha nova, abra o link abaixo (vale por 2 horas):

{url}

Se não foi você, é só ignorar este email.
"""
