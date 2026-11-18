"""Tests for AI compliance service and registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.ai_compliance_service import compute_posture, render_worker_notice
from modules.compliance_registry_db import (
    ensure_compliance_tables,
    insert_worker_acknowledgment,
    load_compliance_profile,
    publish_worker_notice,
    save_compliance_profile,
)


@pytest.fixture
def compliance_db(tmp_path: Path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(
        "modules.compliance_registry_db.DEFAULT_DB_PATH",
        db,
    )
    monkeypatch.setattr(
        "modules.ai_compliance_service.DEFAULT_DB_PATH",
        db,
    )
    ensure_compliance_tables(db_path=db)
    return db


def test_render_worker_notice_it(compliance_db: Path):
    save_compliance_profile(
        {
            "employer_name": "Marmi Verona Srl",
            "workplace_site": "Verona",
            "processing_purposes": "Preventivi e ordini",
        },
        db_path=compliance_db,
    )
    text = render_worker_notice(language="it")
    assert "Marmi Verona Srl" in text
    assert "L. 132/2025" in text


def test_posture_after_publish(compliance_db: Path):
    save_compliance_profile(
        {
            "employer_name": "Acme Stone",
            "dpo_email": "dpo@example.com",
            "processing_purposes": "Orders",
        },
        db_path=compliance_db,
    )
    publish_worker_notice(version="1.0", db_path=compliance_db)
    posture = compute_posture()
    assert posture["auto_checks"]["worker_notice_published"]["ok"] is True
    assert posture["auto_checks"]["profile_complete"]["ok"] is True


def test_worker_acknowledgment(compliance_db: Path):
    ack_id = insert_worker_acknowledgment(
        "Mario Rossi",
        "1.0",
        worker_role="operator",
        db_path=compliance_db,
    )
    assert ack_id >= 1
    profile = load_compliance_profile(db_path=compliance_db)
    assert profile["employer_name"] == ""


def test_export_compliance_pdf(compliance_db: Path, tmp_path: Path):
    save_compliance_profile(
        {
            "employer_name": "Marmi Test Srl",
            "dpo_email": "dpo@test.it",
            "processing_purposes": "Ordini e preventivi",
            "workplace_site": "Verona",
        },
        db_path=compliance_db,
    )
    publish_worker_notice(version="1.0", db_path=compliance_db)
    try:
        pdf_path = __import__(
            "modules.compliance_pdf_export",
            fromlist=["export_compliance_pdf_for_consultant"],
        ).export_compliance_pdf_for_consultant(tmp_path)
    except ImportError:
        pytest.skip("fpdf2 not installed")
    assert pdf_path.exists()
    assert pdf_path.suffix.lower() == ".pdf"
    assert pdf_path.stat().st_size > 500
