"""Test criteri IMAP mirati (no poll UNSEEN globale)."""
from modules.orders_imap_service import (
    build_imap_search_criteria,
    build_imap_search_criteria_list,
    format_imap_filter_summary,
    get_orders_imap_settings,
    get_orders_table_max_rows,
    is_commercial_spam_email,
    pick_newest_unseen_uid,
)


def test_default_poll_and_table_limits():
    settings = get_orders_imap_settings()
    assert settings.get("imap_max_per_poll") == 5
    assert settings.get("imap_max_llm_per_poll") == 1
    assert get_orders_table_max_rows() == 5


def test_pick_newest_unseen_uid():
    # newest first: 5 unseen, 4 seen, 3 unseen
    target = pick_newest_unseen_uid(
        [b"5", b"4", b"3"],
        {b"3", b"5", b"7"},
    )
    assert target == b"5"


def test_never_bare_unseen():
    crit = build_imap_search_criteria()
    assert crit != "UNSEEN"
    assert "preventivo" in crit.lower() or "richiesta" in crit.lower()
    assert "confermo" in crit.lower() or "conferma" in crit.lower()
    assert 'TEXT "confermo"' in crit or 'TEXT "conferma"' in crit


def test_filter_summary_mentions_orders():
    summary = format_imap_filter_summary()
    assert "ordine" in summary.lower()
    assert "conferma" in summary.lower()
    assert "preventivo" in summary.lower()


def test_criteria_list_unseen_first_by_default():
    crits = build_imap_search_criteria_list()
    assert crits
    assert crits[0].startswith("(UNSEEN")
    joined = " ".join(crits)
    assert 'SUBJECT "ordine"' in joined or 'TEXT "ordine"' in joined


def test_criteria_list_no_global_unseen():
    for crit in build_imap_search_criteria_list():
        assert crit.strip() != "UNSEEN"


def test_indeed_is_spam():
    assert is_commercial_spam_email({
        "from": "Indeed <noreply@indeed.com>",
        "subject": "Nuova offerta di lavoro per te",
        "body": "Candidati ora",
    })


def test_real_preventivo_not_spam():
    assert not is_commercial_spam_email({
        "from": "cliente@azienda.it",
        "subject": "richiesta preventivo marmo",
        "body": "Vorrei un preventivo per lastre",
    })
