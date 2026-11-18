from llm.llm_contexts import (
    build_offerte_client_reply_prompt,
    build_ordini_confirmation_prompt,
    build_ordini_stock_confirmation_prompt,
    build_produzione_operator_prompt,
    format_offerte_commercial_block,
    get_ollama_options,
    get_system_instruction,
    resolve_llm_language,
)


def test_systems_defined():
    for ctx in ("offerte", "ordini", "produzione"):
        text = get_system_instruction(ctx)
        assert "NStone" in text
        assert len(text) > 200
    en_offerte = get_system_instruction("offerte", language="en")
    assert "English" in en_offerte or "english" in en_offerte.lower()


def test_resolve_llm_language():
    assert resolve_llm_language({"language": "English (EN)"}) == "en"
    assert resolve_llm_language({"language": "Italiano (IT)"}) == "it"


def test_offerte_prompt():
    p = build_offerte_client_reply_prompt(
        nome="Mario", email="a@b.it", messaggio="Prezzo Carrara 2cm lucidato"
    )
    assert "Mario" in p
    assert "Carrara" in p
    assert "EX WORKS" in p
    assert "salvo il venduto" in p


def test_offerte_commercial_block_format():
    block = format_offerte_commercial_block(
        {
            "Name": "Bianco Carrara CD",
            "Stock": "550",
            "Thickness": "2",
            "Finish": "Polished",
            "Dimensions": "305x152",
            "Price": "75",
        }
    )
    lines = block.splitlines()
    assert lines[0] == "Bianco Carrara CD"
    assert lines[1] == "550 mq · 2 cm · Lucidato"
    assert lines[2] == "305x152 cm"
    assert "75 €/mq" in block
    assert "**EX WORKS**" in block
    assert "**Disponibilità: 550 mq, salvo il venduto**" in block


def test_ordini_confirmation_prompt():
    p = build_ordini_confirmation_prompt(
        order_id="ORD-1",
        client_email="c@x.it",
        original_subject="Ordine marmo",
        original_body="100 mq",
        email_body="Confermo",
    )
    assert "ORD-1" in p
    assert "confirmed" in p


def test_offerte_commercial_block_format_en():
    block = format_offerte_commercial_block(
        {
            "Name": "Bianco Carrara CD",
            "Stock": "550",
            "Thickness": "2",
            "Finish": "Polished",
            "Dimensions": "305x152",
            "Price": "75",
        },
        language="en",
    )
    assert "Availability: 550 sqm" in block
    assert "Polished" in block


def test_produzione_format_hint():
    p = build_produzione_operator_prompt("Belt status?")
    assert "STATUS" in p
    assert "English" in p


def test_produzione_prompt_reasoning():
    p = build_produzione_operator_prompt("Belt status?", include_reasoning=True)
    assert "FINAL ANSWER" in p


def test_context_temperature():
    cfg = {"contexts": {"ordini": {"temperature": 0.1}}}
    opts = get_ollama_options("ordini", cfg)
    assert opts["temperature"] == 0.1


def test_context_num_ctx_and_predict():
    cfg = {"contexts": {"offerte": {"num_ctx": 4096, "num_predict": 600}}}
    opts = get_ollama_options("offerte", cfg)
    assert opts["num_ctx"] == 4096
    assert opts["num_predict"] == 600


def test_context_defaults_include_num_predict():
    opts = get_ollama_options("offerte", {})
    assert opts["num_ctx"] == 4096
    assert opts["num_predict"] == 600


def test_stock_prompt_includes_report():
    p = build_ordini_stock_confirmation_prompt(
        order_id="X",
        order_data={"from": "a@b.it", "subject": "s", "body": "b"},
        email_body="ok",
        stock_report={"availability": "partial"},
    )
    assert "partial" in p
