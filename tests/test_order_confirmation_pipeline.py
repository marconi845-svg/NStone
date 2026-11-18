"""Test gate autonomia pipeline conferma ordine classica."""
from unittest.mock import patch

import pytest

from modules.order_confirmation_pipeline import process_client_confirmation_email


@pytest.fixture
def sample_email():
    return {
        "from": "Mario <mario@example.com>",
        "subject": "Re: Ordine Carrara",
        "body": "Confermo l'ordine come da preventivo.",
        "timestamp": "2026-06-03T12:00:00",
    }


@pytest.fixture
def sample_order():
    return {
        "order_id": "20260603_mario",
        "client_email": "mario@example.com",
        "client": "mario",
        "product": "Ordine Carrara",
        "materiale": "Carrara",
        "quantita": 20.0,
        "email_subject": "Ordine Carrara",
        "email_body": "Richiesta 20 mq",
    }


@patch("modules.orders_database.update_order_confirmation_result")
@patch("modules.orders_database.save_email_log")
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.orders_database.find_order_for_confirmation")
@patch("modules.quotation_auto_pipeline.office_may_auto_email", return_value=False)
def test_l1_saves_draft_without_send(
    _mock_auto,
    mock_find,
    mock_stock,
    mock_log,
    mock_update,
    sample_email,
    sample_order,
):
    mock_find.return_value = sample_order
    mock_stock.return_value = {"availability": "available", "message": "ok"}

    with patch(
        "modules.gemini_module.analyze_confirmation_with_stock",
        return_value={
            "status": "confirmed",
            "availability": "available",
            "confidence": 0.9,
            "notes": "Ok",
            "confirmation_email_text": "Grazie, ordine confermato.",
        },
    ), patch(
        "modules.order_confirmation_pdf.generate_order_confirmation_pdf",
        return_value=None,
    ):
        ok = process_client_confirmation_email(sample_email)

    assert ok is True
    mock_update.assert_called_once()
    kwargs = mock_update.call_args.kwargs
    assert kwargs["status"] == "PENDING_APPROVAL"
    assert kwargs["confirmation_email"]["draft"] is True
    assert kwargs["confirmation_email"]["sent"] is False


@patch("modules.orders_database.update_order_confirmation_result")
@patch("modules.orders_database.save_email_log")
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.orders_database.find_order_for_confirmation")
@patch("modules.quotation_auto_pipeline.office_may_auto_email", return_value=True)
@patch("modules.email_service.send_order_confirmation_email")
def test_l2_sends_when_auto_email_on(
    mock_send,
    _mock_auto,
    mock_find,
    mock_stock,
    mock_log,
    mock_update,
    sample_email,
    sample_order,
):
    mock_find.return_value = sample_order
    mock_stock.return_value = {"availability": "available"}
    mock_send.return_value = {
        "sent": True,
        "timestamp": "2026-06-03T12:01:00",
        "subject": "Conferma",
        "body": "test",
        "to": "mario@example.com",
    }

    with patch(
        "modules.gemini_module.analyze_confirmation_with_stock",
        return_value={
            "status": "confirmed",
            "availability": "available",
            "confidence": 0.9,
            "notes": "Ok",
            "confirmation_email_text": "Grazie, ordine confermato.",
        },
    ), patch(
        "modules.order_stock_check.apply_stock_deduction_for_order",
        return_value={"applied": False},
    ), patch(
        "modules.order_confirmation_pdf.generate_order_confirmation_pdf",
        return_value=None,
    ):
        ok = process_client_confirmation_email(sample_email)

    assert ok is True
    mock_send.assert_called_once()
    assert mock_update.call_args.kwargs["status"] == "CONFIRMED"


@patch("modules.orders_database.update_order_confirmation_result")
@patch("modules.orders_database.save_email_log")
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.orders_database.find_order_for_confirmation")
@patch("modules.quotation_auto_pipeline.office_may_auto_email", return_value=False)
@patch("modules.email_service.send_order_confirmation_email")
def test_force_send_bypasses_l1_gate(
    mock_send,
    _mock_auto,
    mock_find,
    mock_stock,
    mock_log,
    mock_update,
    sample_email,
    sample_order,
):
    mock_find.return_value = sample_order
    mock_stock.return_value = {"availability": "available"}
    mock_send.return_value = {
        "sent": True,
        "timestamp": "2026-06-03T12:01:00",
        "subject": "Conferma",
        "body": "test",
        "to": "mario@example.com",
    }

    with patch(
        "modules.gemini_module.analyze_confirmation_with_stock",
        return_value={
            "status": "confirmed",
            "availability": "available",
            "confidence": 0.9,
            "notes": "Ok",
            "confirmation_email_text": "Grazie, ordine confermato.",
        },
    ), patch(
        "modules.order_stock_check.apply_stock_deduction_for_order",
        return_value={"applied": False},
    ), patch(
        "modules.order_confirmation_pdf.generate_order_confirmation_pdf",
        return_value=None,
    ):
        ok = process_client_confirmation_email(sample_email, force_send=True)

    assert ok is True
    mock_send.assert_called_once()


@patch("modules.orders_database.update_order_confirmation_result")
@patch("modules.orders_database.save_email_log")
@patch("modules.order_stock_check.check_material_availability")
@patch("modules.orders_database.find_order_for_confirmation")
@patch("modules.quotation_auto_pipeline.office_may_auto_email", return_value=True)
@patch("modules.email_service.send_order_confirmation_email")
def test_poll_fast_path_without_llm(
    mock_send,
    _mock_auto,
    mock_find,
    mock_stock,
    mock_log,
    mock_update,
    sample_email,
    sample_order,
):
    mock_find.return_value = sample_order
    mock_stock.return_value = {"availability": "available"}
    mock_send.return_value = {
        "sent": True,
        "timestamp": "2026-06-03T12:01:00",
        "subject": "Conferma",
        "body": "test",
        "to": "mario@example.com",
    }

    with patch(
        "modules.gemini_module.analyze_confirmation_with_stock",
    ) as mock_llm, patch(
        "modules.order_stock_check.apply_stock_deduction_for_order",
        return_value={"applied": False},
    ), patch(
        "modules.order_confirmation_pdf.generate_order_confirmation_pdf",
        return_value=None,
    ):
        ok = process_client_confirmation_email(sample_email, use_llm=False)

    assert ok is True
    mock_llm.assert_not_called()
    mock_send.assert_called_once()
