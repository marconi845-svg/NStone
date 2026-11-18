# NStone Marmo — modello dominio Plant

Due fasi: **oggi** identità dominio via Ollama Modelfile; **dopo** LoRA Unsloth sullo stesso tag.

## Fase 0 — Subito (senza GPU training)

1. Base già presente: `ollama pull qwen2.5:14b-instruct-q4_0`
2. Dalla cartella repo:
   ```bat
   models\nstone-marmo\BUILD.bat
   ```
3. In `config.json`:
   ```json
   "llm": {
     "provider": "ollama",
     "ollama": {
       "model": "nstone-marmo:latest"
     }
   }
   ```
4. Riavvia NStone / salva Impostazioni.

**Cosa fa:** system prompt Plant baked nel modello (terminologia, divieto prezzi inventati, formati offerte/produzione). L'app continua a inviare i prompt per-contesto da `llm_contexts.py` — si sommano al comportamento base.

**Test rapido:**
```bat
ollama run nstone-marmo "Cliente chiede 50 mq travertino senza listino: cosa rispondi?"
```

## Fase 1 — Fine-tuning Unsloth (quando avete GPU + tempo)

**Hardware consigliato:** NVIDIA RTX 3060 12GB+ (training); inferenza resta su Ollama come oggi.

**Dataset:**
- Partire da `dataset_seed.jsonl` (6 esempi seed)
- Aggiungere 50–300 coppie reali **anonimizzate**: mail ordini, preventivi OK, risposte produzione, JSON ordini
- Formato chat JSONL (campo `messages`) — compatibile Unsloth / HuggingFace

**Workflow tipico:**
1. Installare Unsloth in venv separato (non dentro PyQt):
   ```bash
   pip install unsloth
   ```
2. Fine-tune LoRA su `Qwen/Qwen2.5-14B-Instruct` con `dataset_seed.jsonl` + vostri dati
3. Export **GGUF** q4_0
4. Modelfile aggiornato:
   ```
   FROM ./nstone-marmo-q4_0.gguf
   # + stesso SYSTEM di models/nstone-marmo/Modelfile
   ```
5. `ollama create nstone-marmo-ft -f Modelfile`
6. `config.json` → `"model": "nstone-marmo-ft:latest"`

**Non integrare Unsloth nella GUI NStone** finché non c'è un cliente pagante per custom model — training resta in questa cartella.

## Cosa aggiungere al dataset (priorità)

| Tipo | Esempi target |
|------|----------------|
| Offerte con catalogo | Blocco EX WORKS corretto |
| Offerte senza prezzo | Domande, no € inventati |
| Ordini | JSON estrazione campi |
| Produzione EN | STATUS / ANOMALY / ACTION |
| Sicurezza | Emergency → stop, no ottimizzazione |

## Roadmap prodotto

- **Pilota OEM:** `nstone-marmo:latest` (fase 0) sufficiente
- **Post-pilota:** fase 1 con mail cliente anonimizzate del sito pilota
- **GUI:** solo selettore modello in Impostazioni (già supportato via `config.json`)
