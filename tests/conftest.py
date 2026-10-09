from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zerqon.config import Settings
from zerqon.db.connection import Database
from zerqon.web.app import create_app, init_database


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", allow_localhost=True)  # type: ignore[call-arg]


@pytest.fixture
def db(settings: Settings) -> Database:
    return init_database(settings)


@pytest.fixture
def conn(db: Database) -> Iterator[sqlite3.Connection]:
    connection = db.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8765") as test_client:
        yield test_client
