"""Test log/stato poll IMAP condiviso."""
from ui.common import gmail_imap_poll_log as poll_log
from ui.common.gmail_imap_poll_log import (
    get_poll_log_lines,
    record_imap_poll_result,
)


def _reset_poll_log_buffer() -> None:
    poll_log._log_lines.clear()


def test_record_imap_poll_result_appends_log(tmp_path, monkeypatch):
    _reset_poll_log_buffer()
    monkeypatch.setattr(
        "ui.common.gmail_imap_poll_log._project_root",
        lambda: tmp_path,
    )
    record_imap_poll_result(
        {
            "status": "OK",
            "emails_processed": 3,
            "orders_saved": 1,
            "confirmations_sent": 1,
            "last_email_subject": "Re: Ordine test",
        },
        source="auto",
    )
    lines = get_poll_log_lines(max_lines=5)
    assert len(lines) == 1
    assert "AUTO" in lines[0]
    assert "3 mail" in lines[0]
    assert (tmp_path / "logs" / "gmail_orders_status.json").exists()


def test_record_imap_poll_error_line(tmp_path, monkeypatch):
    _reset_poll_log_buffer()
    monkeypatch.setattr(
        "ui.common.gmail_imap_poll_log._project_root",
        lambda: tmp_path,
    )
    record_imap_poll_result(
        {"status": "ERROR", "error_message": "login failed"},
        source="manual",
    )
    lines = get_poll_log_lines(max_lines=5)
    assert len(lines) == 1
    assert "MAN" in lines[0]
    assert "ERRORE" in lines[0]
