"""Test pipeline presa ordine ex novo."""
from unittest.mock import patch

import pytest

from modules.order_intake_pipeline import process_new_order_intake


@pytest.fixture
def sample_email():
    return {
        "from": "Mario <mario@example.com>",
        "subject": "Ordine Carrara",
        "body": "Vorrei 30 mq lastre Carrara 2 cm",
        "timestamp": "2026-06-09T12:00:00",
    }


@pytest.fixture
def sample_order():
    return {
        "order_id": "20260609_mario",
        "client_email": "mario@example.com",
        "client": "mario",
        "product": "Ordine Carrara",
        "email_subject": "Ordine Carrara",
        "email_body": "Vorrei 30 mq lastre Carrara 2 cm",
        "status": "NEW",
    }


@patch("modules.order_confirmation_pipeline.dispatch_order_acknowledgment", return_value=True)
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.orders_database.get_order_by_order_id")
def test_intake_rule_based_without_llm(
    mock_get,
    mock_stock,
    mock_dispatch,
    sample_email,
    sample_order,
):
    mock_get.return_value = sample_order
    mock_stock.return_value = {"availability": "available", "message": "ok"}

    ok = process_new_order_intake("20260609_mario", sample_email, use_llm=False)

    assert ok is True
    mock_dispatch.assert_called_once()
    analysis = mock_dispatch.call_args.args[1]
    assert analysis["status"] == "confirmed"
    assert "ricevuto il Suo ordine" in analysis["confirmation_email_text"]


@patch("modules.order_confirmation_pipeline.dispatch_order_acknowledgment", return_value=True)
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.orders_database.update_order_ai_fields")
@patch("modules.orders_database.get_order_by_order_id")
@patch("modules.order_ai_analysis.analyze_order_email_with_ai")
@patch("modules.gemini_module.analyze_confirmation_with_stock")
def test_intake_with_llm_extract_and_text(
    mock_confirm_llm,
    mock_extract,
    mock_get,
    _mock_update,
    mock_stock,
    mock_dispatch,
    sample_email,
    sample_order,
):
    mock_get.return_value = sample_order
    mock_stock.return_value = {"availability": "partial", "message": "parziale"}
    mock_extract.return_value = {
        "materiale": "Carrara",
        "quantita_mq": 30.0,
        "machine": "Multifilo",
        "note": "2 cm",
        "confidence": 0.9,
    }
    mock_confirm_llm.return_value = {
        "status": "pending",
        "availability": "partial",
        "confidence": 0.88,
        "notes": "LLM ok",
        "confirmation_email_text": "Grazie, ordine in lavorazione.",
    }

    ok = process_new_order_intake("20260609_mario", sample_email, use_llm=True)

    assert ok is True
    mock_extract.assert_called_once()
    mock_confirm_llm.assert_called_once()
    analysis = mock_dispatch.call_args.args[1]
    assert analysis["status"] == "confirmed"
