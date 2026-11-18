"""Test priorità classificazione ORDINE vs CONFERMA."""
from modules.email_classifier import classify_email_with_rules


def test_confermo_wins_when_subject_is_ordine():
    tipo, conf = classify_email_with_rules(
        "Ordine",
        "Confermo l ordine per 100 mq Botticino lastre lucide.",
        "cliente@example.com",
    )
    assert tipo == "CONFERMA"
    assert conf >= 0.55


def test_new_order_without_confirm_keywords():
    tipo, _ = classify_email_with_rules(
        "Richiesta ordine marmo",
        "Vorrei 50 mq di Carrara spessore 2cm",
        "cliente@example.com",
    )
    assert tipo == "ORDINE"


def test_confermarvi_in_body():
    tipo, _ = classify_email_with_rules(
        "Ordine",
        "La presente per confermarvi il seguente ordine Botticino 100 mq",
        "cliente@example.com",
    )
    assert tipo == "CONFERMA"
