from llm.rag_engine import RAGEngine


def test_split_structured_answer():
    text = (
        "1. INTERPRETAZIONE\nDomanda su avanzamento.\n"
        "4. RISPOSTA FINALE\nIl filo è al 45%."
    )
    answer, reasoning = RAGEngine._split_structured_answer(text)
    assert "45%" in answer
    assert "INTERPRETAZIONE" in reasoning
    assert "45%" not in reasoning
