"""Test keyword bilingue pipeline Quotations / Orders."""

from modules.pipeline_keywords import (
    confirmation_rule_fallback_match,
    is_confirmation_hint,
    json_fallback_confirmation_status,
    offer_term_requires_stone_context,
    text_contains_any,
)
from modules.quotation_inbound_pipeline import is_inbound_quotation_request
from modules.quotation_order_confirmation_pipeline import is_order_confirmation_intent


def test_inbound_quotation_en():
    assert is_inbound_quotation_request(
        "Quote request — Bianco Carrara",
        "We need 50 sqm polished marble slabs for a project.",
    )


def test_inbound_quotation_it_still_works():
    assert is_inbound_quotation_request(
        "Richiesta preventivo",
        "Servono 40 mq di Carrara lucido",
    )


def test_inbound_not_confirmation_en():
    assert not is_inbound_quotation_request(
        "Re: Quote",
        "I confirm the order for 50 sqm",
    )


def test_order_confirmation_en():
    ok, score = is_order_confirmation_intent(
        "Re: NStone quotation",
        "I confirm the order for 45 sqm. Please proceed.",
    )
    assert ok and score >= 0.65


def test_order_confirmation_it_still_works():
    ok, score = is_order_confirmation_intent(
        "Re: Preventivo",
        "Confermo l'ordine per 45 mq",
    )
    assert ok and score >= 0.65


def test_confirmation_hint_bilingual():
    assert is_confirmation_hint("Order update", "I accept the quote")
    assert is_confirmation_hint("Ordine", "confermo")


def test_offer_requires_stone_context():
    assert offer_term_requires_stone_context("special offer for you")
    assert not offer_term_requires_stone_context("quote for calacatta marble 50 sqm")


def test_confirmation_rule_fallback_en():
    assert confirmation_rule_fallback_match("i accept the order for carrara")


def test_json_fallback_en():
    assert json_fallback_confirmation_status("customer says confirm order") == "confirmed"


def test_quotation_keywords_tuple_has_both():
    from modules.pipeline_keywords import QUOTATION_INBOUND_KEYWORDS

    assert text_contains_any("preventivo", QUOTATION_INBOUND_KEYWORDS)
    assert text_contains_any("quotation", QUOTATION_INBOUND_KEYWORDS)
