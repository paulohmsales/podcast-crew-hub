import os
import tempfile

# Point the app at a throwaway database before it is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Member
from app.web import COOKIE


@pytest.fixture(autouse=True)
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        yield session


def _member(db, name, admin=False):
    member = Member(name=name, token=f"tok-{name}", is_admin=admin)
    db.add(member)
    db.commit()
    return member


def _client(member):
    client = TestClient(app)
    client.cookies.set(COOKIE, member.token)
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
