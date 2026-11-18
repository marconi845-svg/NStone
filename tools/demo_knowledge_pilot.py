"""Demo end-to-end: indicizza knowledge demo e interroga con Ollama."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUESTIONS = [
    ("Qual è l'assorbimento d'acqua del Carrara CD?", "scheda_carrara"),
    ("Entro quanti giorni posso fare un reso di merce integra?", "policy"),
    ("Quale tensione filo impostare all'avvio del multifilo?", "multifilo"),
]


def main() -> int:
    from modules.knowledge_db import init_knowledge_tables
    from modules.knowledge_ingest import reindex_all, stats_summary
    from modules.knowledge_retriever import format_context_block, format_sources_summary, retrieve
    from llm.llm_service import LLMService

    print("=== Retrieval Fabric — demo knowledge ===\n")

    init_knowledge_tables()
    n = reindex_all()
    stats = stats_summary()
    print(f"Indicizzati {n} file · {stats['documents']} doc · {stats['chunks']} chunk\n")

    llm = LLMService()
    if not llm.is_configured():
        print(f"(!) Ollama non disponibile: {llm.configuration_error_message()}")
        print("  (Retrieval funziona lo stesso — mostro solo i chunk recuperati)\n")
        ollama_ok = False
    else:
        ollama_ok = True
        print("[OK] Ollama raggiungibile\n")

    for question, tag in QUESTIONS:
        print("-" * 60)
        print(f"Q [{tag}]: {question}")
        hits = retrieve(question, limit=3)
        if not hits:
            print("  [X] Nessun chunk trovato\n")
            continue

        print(f"  Fonti: {format_sources_summary(hits)}")
        context = format_context_block(hits)
        prompt = f"{context}\n\n[USER QUESTION]\n{question}"

        if ollama_ok:
            answer = llm.send_message(prompt, request_kind="operational")
            preview = answer.replace("\n", " ")[:280]
            print(f"  Risposta Ollama: {preview}{'...' if len(answer) > 280 else ''}")
        else:
            print(f"  Chunk top: {hits[0]['file_name']} § {hits[0].get('section_title', '—')}")
            print(f"  Estratto: {hits[0]['content'][:200]}...")
        print()

    print("=== Demo completata ===")
    print("Apri NStone -> Retrieval Fabric -> Library / Ask per provare in UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
