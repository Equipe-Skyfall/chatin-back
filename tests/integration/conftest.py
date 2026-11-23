"""Integration tests run against a real (throwaway) Postgres schema - JSONB,
gen_random_uuid() and CHECK constraints used by the models aren't available on
sqlite, so these are skipped unless TEST_DATABASE_URL points at a real Postgres
instance (e.g. a local Supabase/Postgres container or a disposable schema).
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import *  # noqa: F401,F403 - registers every model on Base.metadata

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def engine():
    # A `pytestmark` in a conftest does not reach the test modules, so the skip
    # lives here: every integration test goes through this fixture.
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set - integration tests need a real Postgres schema")
    eng = create_engine(TEST_DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
