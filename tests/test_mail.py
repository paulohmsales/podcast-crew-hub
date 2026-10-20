import smtplib

import pytest

from app import mail
from tests.conftest import REAL_SEND


class FakeSMTP:
    instances = []

    def __init__(self, host, port, **kw):
        self.host, self.port, self.sent, self.logged = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        if password != "abcdefghijklmnop":
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        self.logged = user

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setattr(mail, "send", REAL_SEND)
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_USER", "podcast@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.delenv("MAIL_FROM", raising=False)
    return FakeSMTP


def test_sends_over_ssl_with_spaces_stripped(smtp):
    mail.send("ana@ex.com", "Oi", "corpo")
    s = smtp.instances[0]
    assert (s.host, s.port, s.logged) == ("smtp.gmail.com", 465, "podcast@gmail.com")
    msg = s.sent[0]
    assert msg["To"] == "ana@ex.com" and "podcast@gmail.com" in msg["From"] and "corpo" in msg.get_content()


def test_starttls_port(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "587")
    mail.send("ana@ex.com", "Oi", "corpo")
    assert smtp.instances[0].tls


def test_bad_password_is_mail_error(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "wrong")
    with pytest.raises(mail.MailError, match="senha de app"):
        mail.send("ana@ex.com", "Oi", "corpo")


def test_not_configured(smtp, monkeypatch):
    monkeypatch.delenv("SMTP_USER")
    with pytest.raises(mail.MailError, match="não configurado"):
        mail.send("ana@ex.com", "Oi", "corpo")
