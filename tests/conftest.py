import os
import tempfile

# Point the app at a throwaway database before it is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Member
from app.web import COOKIE

PASSWORD = "senha-forte-123"


@pytest.fixture(autouse=True)
def _reset_throttle():
    auth.login_throttle.fails.clear()


@pytest.fixture(autouse=True)
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        yield session


def _member(db, name, admin=False):
    member = Member(
        name=name, email=f"{name.lower()}@ex.com",
        password_hash=auth.hash_password(PASSWORD), is_admin=admin,
    )
    db.add(member)
    db.commit()
    return member


def _client(member):
    client = TestClient(app)
    with SessionLocal() as db:
        client.cookies.set(COOKIE, auth.start_session(db, db.get(Member, member.id)))
    return client


@pytest.fixture
def paulo(db):
    return _member(db, "Paulo", admin=True)


@pytest.fixture
def ana(db):
    return _member(db, "Ana")


@pytest.fixture
def client(paulo):
    return _client(paulo)


@pytest.fixture
def ana_client(ana):
    return _client(ana)
