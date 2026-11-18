"""Tests for app_user session management."""
from pathlib import Path

import pytest

from modules import app_users_db as users


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    users.ensure_app_user_table(db_path=db)
    return db


def test_seed_default_administrator(temp_db: Path):
    rows = users.load_app_users(db_path=temp_db)
    assert len(rows) >= 1
    assert rows[0]["role"] == users.ROLE_ADMINISTRATOR


def test_insert_and_set_current(temp_db: Path):
    result = users.insert_app_user(
        "marco",
        "Marco Rossi",
        role=users.ROLE_OPERATOR,
        db_path=temp_db,
    )
    assert result["ok"]
    set_result = users.set_current_user(result["id"], db_path=temp_db)
    assert set_result["ok"]
    current = users.get_current_user(db_path=temp_db)
    assert current["username"] == "marco"
    assert "Marco Rossi" in users.current_user_banner_text(db_path=temp_db)


def test_cannot_delete_last_user(temp_db: Path):
    rows = users.load_app_users(db_path=temp_db)
    assert len(rows) == 1
    result = users.delete_app_user(rows[0]["id"], db_path=temp_db)
    assert not result["ok"]
