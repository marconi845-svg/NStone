"""Tests for section_password access control DB."""
import sqlite3
from pathlib import Path

import pytest

from modules import access_control_db as acdb


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    acdb.ensure_section_password_table(db_path=db)
    return db


def test_ensure_creates_default_rows(temp_db: Path):
    rows = acdb.load_section_password_records(db_path=temp_db)
    keys = {r["section_key"] for r in rows}
    assert acdb.SECTION_AGENTS_COMMAND_CENTER in keys
    assert acdb.SECTION_ADVANCED_DATASET_OPTIONS in keys
    assert acdb.SECTION_ADMINISTRATOR_BYPASS in keys


def test_section_pin_flow(temp_db: Path):
    rows = acdb.load_section_password_records(db_path=temp_db)
    agents = next(r for r in rows if r["section_key"] == acdb.SECTION_AGENTS_COMMAND_CENTER)
    assert not acdb.section_requires_pin(acdb.SECTION_AGENTS_COMMAND_CENTER, db_path=temp_db)

    result = acdb.update_section_access(
        agents["id"],
        protection_enabled=True,
        new_password="secret123",
        db_path=temp_db,
    )
    assert result["ok"]
    assert acdb.section_requires_pin(acdb.SECTION_AGENTS_COMMAND_CENTER, db_path=temp_db)
    assert acdb.verify_section_pin(acdb.SECTION_AGENTS_COMMAND_CENTER, "secret123", db_path=temp_db)
    assert not acdb.verify_section_pin(acdb.SECTION_AGENTS_COMMAND_CENTER, "wrong", db_path=temp_db)


def test_admin_bypass_skips_pin(temp_db: Path):
    rows = acdb.load_section_password_records(db_path=temp_db)
    agents = next(r for r in rows if r["section_key"] == acdb.SECTION_AGENTS_COMMAND_CENTER)
    bypass = next(r for r in rows if r["section_key"] == acdb.SECTION_ADMINISTRATOR_BYPASS)

    acdb.update_section_access(
        agents["id"],
        protection_enabled=True,
        new_password="secret123",
        db_path=temp_db,
    )
    assert acdb.section_requires_pin(acdb.SECTION_AGENTS_COMMAND_CENTER, db_path=temp_db)

    acdb.update_section_access(
        bypass["id"],
        protection_enabled=True,
        db_path=temp_db,
    )
    assert not acdb.section_requires_pin(acdb.SECTION_AGENTS_COMMAND_CENTER, db_path=temp_db)


def test_enable_without_password_fails(temp_db: Path):
    rows = acdb.load_section_password_records(db_path=temp_db)
    agents = next(r for r in rows if r["section_key"] == acdb.SECTION_AGENTS_COMMAND_CENTER)
    result = acdb.update_section_access(
        agents["id"],
        protection_enabled=True,
        new_password="",
        db_path=temp_db,
    )
    assert not result["ok"]
