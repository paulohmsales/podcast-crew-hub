"""Outgoing email through SMTP (stdlib only), e.g. a Gmail account with an app password.

Env: SMTP_USER and SMTP_PASSWORD (required), SMTP_HOST (default smtp.gmail.com),
SMTP_PORT (default 465, implicit TLS; 587 uses STARTTLS), MAIL_FROM (display
name + address; defaults to "Então Ganhei <SMTP_USER>").
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger(__name__)


class MailError(Exception):
    pass


def send(to: str, subject: str, text: str) -> None:
    """Raises MailError when the mail can't be handed to the SMTP server."""
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")  # Gmail shows app passwords in groups of 4
    if not user or not password:
        raise MailError("Email não configurado no servidor (SMTP_USER/SMTP_PASSWORD).")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))

    msg = EmailMessage()
    msg["From"] = os.environ.get("MAIL_FROM") or formataddr(("Então Ganhei", user))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)

    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.starttls(context=context)
                smtp.login(user, password)
                smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        log.warning("smtp auth failed for %s: %s", user, e)
        raise MailError("O servidor de email recusou o login (confira a senha de app do Gmail).") from e
    except (smtplib.SMTPException, OSError) as e:
        log.warning("smtp send to %s failed: %s", to, e)
        raise MailError(f"Falha ao enviar email: {e}") from e


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
