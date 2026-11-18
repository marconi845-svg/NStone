from modules.quotation_inbound_pipeline import is_inbound_quotation_request


def test_keywords_match_new_request():
    assert is_inbound_quotation_request(
        "Richiesta lastre Carrara",
        "Buongiorno, vorrei 100 mq spessore 2 cm",
    )
    assert is_inbound_quotation_request(
        "Preventivo marmo",
        "Salve, quanto costa?",
    )


def test_replies_skipped():
    assert not is_inbound_quotation_request(
        "Re: Preventivo marmo",
        "Ecco chiarimenti",
    )


def test_pure_order_not_quotation():
    assert not is_inbound_quotation_request(
        "Ordine lastre",
        "Vi confermo ordine 50 mq granito",
    )


def test_confirmation_blocked():
    assert not is_inbound_quotation_request(
        "Conferma",
        "Confermo l'ordine come da preventivo inviato",
    )
