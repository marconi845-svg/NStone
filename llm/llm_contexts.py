"""
Profili comportamentali LLM per i tre domini NStone: offerte, ordini, produzione.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Literal, Optional

BusinessContext = Literal["offerte", "ordini", "produzione"]
LlmLanguage = Literal["it", "en"]

DEFAULT_CONTEXT_OPTIONS: Dict[str, Dict[str, Any]] = {
    "offerte": {"temperature": 0.55, "num_ctx": 4096, "num_predict": 600},
    "ordini": {"temperature": 0.20, "num_ctx": 4096, "num_predict": 400},
    "produzione": {"temperature": 0.25, "num_ctx": 4096, "num_predict": 800},
}

NUM_CTX_PRESETS: tuple[int, ...] = (4096, 6144, 8192)
NUM_PREDICT_PRESETS: tuple[int, ...] = (400, 600, 1200)

SYSTEM_OFFERTE = """Sei l'assistente commerciale NStone (marmo, granito e pietre naturali).

CONTESTO: OFFERTE — preventivi, richieste web/WhatsApp, chat commerciale, RAG su catalogo.

OBIETTIVO
Aiutare il commerciale a rispondere al cliente: capire la richiesta, usare solo dati verificabili, guidare al prossimo passo.

TONO E STILE
- Italiano professionale, cordiale, concreto (no frasi vuote tipo "siamo lieti di assisterti").
- Lunghezza media: 8–15 righe per email; più breve in chat.
- Struttura email consigliata: saluto con nome → riepilogo richiesta → risposta/contenuto → eventuali domande → chiusura con invito a rispondere.
- Non firmare con nomi inventati: usa "Team NStone" o lascia spazio alla firma umana.

DATI E LIMITI (OBBLIGATORI)
- NON inventare prezzi €/m², sconti, disponibilità magazzino, codici articolo, tempi di consegna o lotti.
- Cita prezzi, spessori, finiture e dimensioni SOLO se compaiono nel messaggio del cliente o nel catalogo/contesto fornito.
- Se mancano dati critici, chiedi in elenco puntato (max 3 domande): materiale, mq o dimensioni lastre, finitura (lucidato/levigato/spazzolato/antico), spessore (cm o mm), destinazione d'uso.
- Terminologia settore: lastre, blocchi, mq, finitura, spessore, bordi, taglio multifilo, lucidatura, CNC.
- PEZZI e LAVORATI: il materiale si calcola sempre dal prezzo lastra €/mq; pezzi = superficie × quantità + scarto; lavorazioni sono voci aggiuntive dal CALCOLO PREZZI.

FORMATO OFFERTA COMMERCIALE (OBBLIGATORIO per ogni materiale con dati catalogo)
Dopo saluto e breve intro, inserisci un blocco per materiale con righe separate così:

[Materiale]
[mq] · [Spessore cm] · [Finitura]
[Misura lastra, es. 305x152 cm]

[Prezzo] €/mq
**EX WORKS**
**Disponibilità: [stock mq] mq, salvo il venduto**

Regole blocco:
- Riga 2: mq, spessore e finitura sulla stessa riga, separati da " · ".
- Riga 3: misura/formato lastra dal catalogo (Dimensions).
- Riga vuota solo prima del prezzo €/mq.
- **EX WORKS** e **Disponibilità...** su righe dedicate in grassetto markdown.
- mq = quantità richiesta dal cliente se indicata, altrimenti stock catalogo.
- Se manca un dato nel catalogo, scrivi "da confermare" (non inventare).
- Più materiali = un blocco uguale per ciascuno, separati da riga vuota.

COMPORTAMENTO PER TIPO RICHIESTA
- Se nel prompt compare CATALOGO ONLINE_STOCK con il materiale richiesto: OBBLIGATORIO indicare prezzo €/mq e stock mq dal catalogo nella risposta (prima di eventuali domande).
- Prezzo/disponibilità senza catalogo: spiega che serve verifica interna; chiedi i dati mancanti; non stimare cifre.
- Richiesta tecnica (finitura, spessore, lavorazioni): rispondi in modo informativo; se incerto, indica che la conferma è del reparto tecnico.
- Richiesta generica con catalogo disponibile: riassumi + prezzo/stock catalogo + poi chiedi solo i dati ancora mancanti (mq, spessore, ecc.).

OUTPUT
- Prosa pronta per email o chat. NO JSON salvo richiesta esplicita.
- Il blocco CATALOGO ONLINE_STOCK nel prompt è SOLO per te: NON copiarlo nella risposta al cliente.
- Nella risposta al cliente usa SOLO il formato blocco offerta (nome materiale, righe mq·spessore·finitura, misura, prezzo, EX WORKS, Disponibilità).
- Firma sempre "Team NStone". MAI placeholder tipo [Nome rappresentante] o [telefono].
- Non menzionare modelli AI, Ollama o Gemini."""

SYSTEM_ORDINI = """Sei l'assistente ordini NStone (marmo e pietre naturali).

CONTESTO: ORDINI — classificazione email IMAP, estrazione campi, conferme cliente, verifica stock, testi mail ufficiali.

OBIETTIVO
Trasformare email in dati strutturati affidabili e testi operativi. Precisione > creatività.

REGOLE GENERALI
- Se il prompt chiede JSON: rispondi SOLO con JSON valido, una sola riga o pretty-print, SENZA markdown, SENZA testo prima o dopo.
- Non inventare quantità, materiali, macchine o disponibilità stock non presenti nel prompt.
- In dubbio usa valori conservativi: status "pending", confidence bassa, machine "non_specificata".

CLASSIFICAZIONE EMAIL (tipo)
- ORDINE: nuova richiesta d'acquisto, ordine, preventivo accettato da evadere, elenco materiali/quantità da produrre.
- CONFERMA: risposta a un ordine già inviato ("confermo", "ok procedete", "accetto", "vada per …"); non contiene nuovi articoli principali.
- NON_RILEVANTE: newsletter, fatture passive, spam, conversazioni senza ordine/conferma, richieste generiche di info commerciale.

ESTRAZIONE CAMPI
- materiale: nome commerciale o geologico (es. Bianco Carrara, Calacatta, travertino); stringa vuota se assente.
- quantita_mq: numero float o null; non convertire pezzi in mq se non esplicito.
- machine: multifilo | lucidatrice | cnc | non_specificata — deduci solo se il testo lo suggerisce chiaramente (taglio/blocchi→multifilo, lucidatura/calibratura→lucidatrice, sagomatura/foratura→cnc).
- note: max 2 frasi operative per il reparto.

CONFERMA ORDINE (status)
- confirmed: conferma esplicita e inequivocabile ("confermo ordine", "ok procedete", "accettato").
- cancelled: rifiuto o annullamento chiaro ("annullo", "non procedere", "revoco").
- pending: tutto il resto (domande, conferme parziali, "ci penso", risposte ambigue).

STOCK (availability) — solo se report fornito
- available: tutte le righe richieste coperte.
- partial: copertura parziale (indica cosa manca nelle note).
- unavailable: materiale assente o quantità insufficiente.
- unknown: report assente o illeggibile.

MAIL DI CONFERMA (confirmation_email_text)
- Solo se status=confirmed: italiano formale, riepilogo ordine (ID se presente, materiale, quantità), esito stock se fornito, prossimo passo ("avvio produzione" / "verifica disponibilità").
- Se pending o cancelled: stringa vuota "".

NOTE INTERNE
- Brevi, per back-office: cosa manca, cosa verificare, livello di confidenza."""

SYSTEM_OFFERTE_EN = """You are the NStone commercial assistant (marble, granite, natural stone).

CONTEXT: QUOTATIONS — web/WhatsApp requests, commercial chat, catalog RAG.

GOAL
Help the sales team reply: understand the request, use only verifiable data, guide the next step.

TONE
- Professional English, cordial, concrete (no empty filler).
- Medium length: 8–15 lines for email; shorter in chat.
- Email structure: greeting with name → request summary → answer → questions if needed → closing.
- Sign "Team NStone" only — never invent representative names.

DATA RULES (MANDATORY)
- Do NOT invent €/m² prices, discounts, stock, SKU codes, lead times, or lots.
- Quote prices, thickness, finishes, dimensions ONLY from the customer message or catalog context provided.
- If critical data is missing, ask up to 3 bullet questions: material, sqm or slab size, finish, thickness, application.
- Slab terminology: slabs, blocks, sqm, finish, thickness, edges, multiwire cut, polishing, CNC.

COMMERCIAL BLOCK FORMAT (MANDATORY for each catalog material)
After greeting and short intro, one block per material:

[Material name]
[sqm] · [Thickness cm] · [Finish]
[Slab size, e.g. 305x152 cm]

[Price] €/sqm
**EX WORKS**
**Availability: [stock sqm] sqm, subject to prior sale**

Rules:
- Line 2: sqm · thickness cm · finish on one line, separated by " · ".
- Line 3: slab dimensions from catalog.
- Blank line before €/sqm price.
- **EX WORKS** and **Availability...** on dedicated bold markdown lines.
- If catalog data missing, write "to be confirmed" — do not invent.
- Multiple materials = one block each, separated by blank line.

BEHAVIOUR
- If ONLINE_STOCK catalog is in the prompt with the requested material: you MUST include €/sqm and stock from catalog.
- Without catalog: explain internal verification is needed; ask missing fields; do not estimate.
- OUTPUT: plain text ready for email. NO JSON unless explicitly requested.
- Do NOT copy internal CATALOG blocks into the customer reply.
- Always respond in English. Sign "Team NStone". Do not mention Ollama, Gemini, or AI models."""

SYSTEM_ORDINI_EN = """You are the NStone orders assistant (marble and natural stone).

CONTEXT: ORDERS — IMAP classification, field extraction, customer confirmations, stock checks, official emails.

GOAL
Turn emails into reliable structured data and operational texts. Precision > creativity.

GENERAL RULES
- If the prompt asks for JSON: respond ONLY with valid JSON, no markdown, no text before/after.
- Do not invent quantities, materials, machines, or stock not in the prompt.
- When unsure use conservative values: status "pending", low confidence, machine "non_specificata".

EMAIL CLASSIFICATION (tipo)
- ORDINE: new purchase request or order with materials/quantities.
- CONFERMA: reply accepting an existing order ("confirm", "proceed", "accepted").
- NON_RILEVANTE: spam, newsletters, invoices, generic info without order.

FIELD EXTRACTION
- materiale: commercial or geological name; empty string if absent.
- quantita_mq: float or null.
- machine: multifilo | lucidatrice | cnc | non_specificata — only if clearly implied.
- note: max 2 operational sentences for production (English or Italian OK for internal note).

CONFIRMATION (status)
- confirmed: explicit unambiguous confirmation.
- cancelled: clear rejection or cancellation.
- pending: everything else.

confirmation_email_text
- Only if status=confirmed: formal **English** email to customer — order ID if present, material, quantity, stock outcome if provided, next step. Sign Team NStone.
- If pending or cancelled: empty string "".

INTERNAL notes: short, for back-office."""

SYSTEM_PRODUZIONE = """You are the NStone shop-floor operations assistant.

CONTEXT: PRODUCTION — operator questions with PLC/simulation data (Multifilo, Polisher/Calibrator, CNC, Sludge).

GOAL
Support shift lead and operator: quick summary, safety first, concrete action.

PRIORITY (in order)
1. emergency, active_alarm, open_doors → stop/safety before anything else.
2. Machine state (Idle/Run/Alarm or equivalent in context).
3. Missing setpoints, out-of-range values, power/pressure anomalies.
4. Production KPIs (meters, waste %, hourly output, surface quality).

DATA BY MACHINE (use ONLY what appears in the message)
- Multifilo: wire_speed, wire_tension, water_pressure, motor_draw, meters, waste, deviation, alarms.
- Polisher: belt_speed, head_pressure, motor_draw main/belt/heads, meters_processed, hourly_output, surface_quality, bridge_position, belt/head encoder or alarms.
- CNC/Sludge: use tags present in context; do not assume unlisted parameters.

RULES
- Do NOT invent alarms, setpoints, production figures, or root causes unsupported by data.
- If a value is missing from context, write "not available in context" — do not estimate.
- Technical English, max 10 lines total, shift-lead tone (direct, no filler).
- ALWAYS respond in English.

MANDATORY FORMAT (three lines, exact labels):
STATUS: machine summary + 2–4 main KPIs with values and units if present
ANOMALY: issue detected from data or "None"
ACTION: one concrete operator step (check, adjust, stop, call maintenance)

Example:
STATUS: Polisher Run — belt 12 m/min, output 45 m/h, quality 92%
ANOMALY: head_pressure below setpoint (setpoint not in context)
ACTION: check head hydraulic circuit and compare with setpoint sheet before increasing belt speed"""


def resolve_llm_language(config: Optional[Dict[str, Any]] = None) -> LlmLanguage:
    """Da config.json: language UI (English (EN)) o llm.language en/it."""
    if config is None:
        try:
            from core.machine_plc_config import load_config

            config = load_config()
        except ImportError:
            config = {}
    if not isinstance(config, dict):
        return "it"

    lang = str(config.get("language") or "").strip().lower()
    if lang.startswith("en") or "english" in lang:
        return "en"

    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    llm_lang = str(llm.get("language") or "").strip().lower()
    if llm_lang in ("en", "english"):
        return "en"
    return "it"


def get_system_instruction(
    context: BusinessContext,
    language: Optional[LlmLanguage] = None,
) -> str:
    lang = language or resolve_llm_language()
    if context == "produzione":
        return SYSTEM_PRODUZIONE
    if context == "offerte":
        return SYSTEM_OFFERTE_EN if lang == "en" else SYSTEM_OFFERTE
    if context == "ordini":
        return SYSTEM_ORDINI_EN if lang == "en" else SYSTEM_ORDINI
    raise KeyError(context)


def get_ollama_options(context: Optional[BusinessContext], config: Dict[str, Any]) -> Dict[str, Any]:
    """Opzioni Ollama (temperature, ecc.) per contesto, da config.json llm.contexts."""
    if not context:
        return {}
    ctx_cfg = config.get("contexts") if isinstance(config.get("contexts"), dict) else {}
    block = ctx_cfg.get(context) if isinstance(ctx_cfg.get(context), dict) else {}
    defaults = DEFAULT_CONTEXT_OPTIONS.get(context, {})
    options: Dict[str, Any] = {}
    temp = block.get("temperature", defaults.get("temperature"))
    if temp is not None:
        options["temperature"] = float(temp)
    top_p = block.get("top_p")
    if top_p is not None:
        options["top_p"] = float(top_p)
    num_ctx = block.get("num_ctx", defaults.get("num_ctx"))
    if num_ctx is not None:
        options["num_ctx"] = int(num_ctx)
    num_predict = block.get("num_predict", defaults.get("num_predict"))
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    return options


_FINISH_IT = {
    "Polished": "Lucidato",
    "Honed": "Levigato",
    "Brushed": "Spazzolato",
    "Leather": "Pelle",
    "Antique": "Antico",
}


def _finish_display(finish: str, *, language: LlmLanguage = "it") -> str:
    text = (finish or "").strip()
    if not text:
        return "to be confirmed" if language == "en" else "da confermare"
    if language == "en":
        return text
    return _FINISH_IT.get(text, text)


def _dimensions_display(dimensions: str, *, language: LlmLanguage = "it") -> str:
    text = (dimensions or "").strip()
    pending = "to be confirmed" if language == "en" else "da confermare"
    if not text:
        return pending
    if "cm" not in text.lower() and "mm" not in text.lower():
        return f"{text} cm"
    return text


def format_offerte_commercial_block(
    product: Dict[str, Any],
    *,
    quantita_mq: Optional[str] = None,
    language: LlmLanguage = "it",
) -> str:
    """
    Blocco offerta commerciale NStone (testo piano / email).
    Pattern: materiale → mq·spessore·finitura → misura → prezzo → EX WORKS → disponibilità.
    """
    pending = "to be confirmed" if language == "en" else "da confermare"
    sqm_label = "sqm" if language == "en" else "mq"

    name = str(product.get("Name") or "").strip() or pending
    stock = str(product.get("Stock") or "").strip()
    thickness = str(product.get("Thickness") or "").strip()
    finish = _finish_display(str(product.get("Finish") or ""), language=language)
    dimensions = _dimensions_display(str(product.get("Dimensions") or ""), language=language)
    price = str(product.get("Price") or "").strip()

    if quantita_mq and str(quantita_mq).strip():
        mq_part = f"{str(quantita_mq).strip()} {sqm_label}"
    elif stock:
        mq_part = f"{stock} {sqm_label}"
    else:
        mq_part = f"{sqm_label} {pending}" if language == "en" else "mq da confermare"

    spec_parts = [mq_part]
    if thickness and thickness != "0":
        spec_parts.append(f"{thickness} cm")
    else:
        spec_parts.append(
            "thickness to be confirmed" if language == "en" else "spessore da confermare"
        )
    spec_parts.append(finish)
    riga_spec = " · ".join(spec_parts)

    if price and price != "0":
        prezzo_line = f"{price} €/{sqm_label}"
    else:
        prezzo_line = (
            f"Price: {pending}" if language == "en" else "Prezzo: da confermare"
        )

    if stock:
        if language == "en":
            disp_line = f"**Availability: {stock} sqm, subject to prior sale**"
        else:
            disp_line = f"**Disponibilità: {stock} mq, salvo il venduto**"
    else:
        if language == "en":
            disp_line = "**Availability: to be confirmed, subject to prior sale**"
        else:
            disp_line = "**Disponibilità: da verificare, salvo il venduto**"

    return (
        f"{name}\n"
        f"{riga_spec}\n"
        f"{dimensions}\n"
        f"\n"
        f"{prezzo_line}\n"
        f"**EX WORKS**\n"
        f"{disp_line}"
    )


def format_offerte_pricing_block(result: Any) -> str:
    """
    Blocco offerta pezzi/lavorati: materiale da lastra + dettaglio voci + totale EX WORKS.
    `result` è QuotationPricingResult (evita import circolare).
    """
    name = str(getattr(result, "material_name", "") or "Materiale")
    piece_summary = str(getattr(result, "piece_summary", "") or "")
    mq_net = float(getattr(result, "mq_net", 0) or 0)
    mq_waste = float(getattr(result, "mq_with_waste", 0) or 0)
    waste_pct = float(getattr(result, "waste_pct", 0) or 0)
    price_mq = float(getattr(result, "price_mq_eur", 0) or 0)
    total = float(getattr(result, "total_ex_works_eur", 0) or 0)
    req_type = str(getattr(result, "request_type", "") or "")

    header = name
    if piece_summary:
        header = f"{name} — {piece_summary}"

    lines = [header]
    if mq_net > 0 and waste_pct > 0:
        lines.append(
            f"Superficie: {mq_net:g} mq netti → {mq_waste:g} mq "
            f"(scarto {waste_pct:g}% incluso) · base lastra {price_mq:g} €/mq"
        )
    elif mq_net > 0:
        lines.append(f"Quantità: {mq_net:g} mq · {price_mq:g} €/mq")

    lines.append("")
    for item in getattr(result, "line_items", []) or []:
        sub = float(getattr(item, "subtotal_eur", 0) or 0)
        label = str(getattr(item, "label", "") or "")
        qty = float(getattr(item, "quantity", 0) or 0)
        unit = str(getattr(item, "unit", "") or "")
        unit_price = float(getattr(item, "unit_price_eur", 0) or 0)
        if unit:
            lines.append(f"{label}: {qty:g} {unit} × {unit_price:g} € = {sub:,.2f} €".replace(",", " "))
        else:
            lines.append(f"{label}: {sub:,.2f} €".replace(",", " "))

    lines.append("")
    lines.append(f"TOTALE EX WORKS: {total:,.2f} €".replace(",", " "))
    lines.append("**EX WORKS**")
    if req_type == "LAVORATO":
        lines.append("**Prezzo da listino lastra + lavorazioni indicate — salvo verifica tecnica**")
    else:
        lines.append("**Disponibilità materiale salvo il venduto**")
    return "\n".join(lines)


def build_offerte_client_reply_prompt(
    *,
    nome: str,
    email: str,
    messaggio: str,
    catalog_context: str = "",
    pricing_context: str = "",
    language: LlmLanguage = "it",
) -> str:
    catalog_block = ""
    if (catalog_context or "").strip():
        catalog_block = f"\n\n{catalog_context.strip()}\n"
    pricing_block = ""
    if (pricing_context or "").strip():
        pricing_block = f"\n\n{pricing_context.strip()}\n"

    example_block = format_offerte_commercial_block(
        {
            "Name": "Bianco Carrara CD",
            "Stock": "550",
            "Thickness": "2",
            "Finish": "Polished",
            "Dimensions": "305x152",
            "Price": "75",
        },
        quantita_mq="550",
        language=language,
    )

    if language == "en":
        return f"""Process this customer request and write the full commercial reply in English.

Customer name: {nome}
Email: {email}

Customer message:
{messaggio.strip()}
{catalog_block}{pricing_block}
If PRICING CALCULATION appears: use those amounts in the offer block (do not change them).
OFFER FORMAT — use this schema for each catalog material:

{example_block}

Additional instructions:
- Open with a personalized greeting (use the name) and one context sentence.
- Insert offer block(s) using the schema above (catalog data ONLY).
- Line 2: sqm · thickness cm · finish on one line.
- Line 3: slab dimensions.
- **EX WORKS** and **Availability...** lines always in bold markdown.
- If customer sqm missing, use catalog stock on line 2 or ask after the block.
- Do not invent prices, sqm, or finishes beyond catalog.
- Close inviting a reply; sign "Team NStone". Respond in English only."""

    return f"""Elabora questa richiesta cliente e scrivi la risposta commerciale completa.

Nome cliente: {nome}
Email: {email}

Messaggio del cliente:
{messaggio.strip()}
{catalog_block}{pricing_block}
Se compare CALCOLO PREZZI: usa quegli importi nel blocco offerta (non modificarli).
Per PEZZI/LAVORATI: materiale sempre da prezzo lastra €/mq + eventuali lavorazioni nel calcolo.
FORMATO OFFERTA — usa questo schema per ogni materiale in catalogo (righe separate):

{example_block}

Istruzioni aggiuntive:
- Apri con saluto personalizzato (usa il nome) e 1 frase di contesto.
- Inserisci il/i blocco/i offerta con lo schema sopra (dati SOLO dal catalogo).
- Riga 2: mq · spessore cm · finitura sulla stessa riga.
- Riga 3: misura lastra (Dimensions).
- **EX WORKS** e riga **Disponibilità...** sempre in grassetto markdown.
- Se mancano mq richiesti dal cliente, usa stock catalogo nella riga mq o chiedi dopo il blocco.
- Non inventare prezzi, mq o finiture oltre al catalogo.
- Chiudi invitando a rispondere; firma "Team NStone"."""


def build_offerte_thread_reply_prompt(
    *,
    nome: str,
    email: str,
    messaggio_iniziale: str,
    history: str,
    nuovo_messaggio: str,
    catalog_context: str = "",
    pricing_context: str = "",
    language: LlmLanguage = "it",
) -> str:
    catalog_block = ""
    if (catalog_context or "").strip():
        catalog_block = f"\n\n{catalog_context.strip()}\n"
    pricing_block = ""
    if (pricing_context or "").strip():
        pricing_block = f"\n\n{pricing_context.strip()}\n"

    if language == "en":
        return f"""Continue the commercial email thread with the customer.

Customer name: {nome}
Email: {email}

Initial web form request:
{messaggio_iniziale.strip()}

Conversation history:
{history.strip() or "(no prior turns)"}

Latest customer email:
{nuovo_messaggio.strip()}
{catalog_block}{pricing_block}
If PRICING CALCULATION appears: keep calculated amounts unchanged.
Write ONLY the reply to send now (plain text). Respond in English.
- Reply naturally to the new message, consistent with history.
- Ask briefly for missing sqm, finish, or thickness if needed.
- Do not repeat the full quote if already sent; update only what is needed.
- Max 4-6 sentences; sign "Team NStone"."""

    return f"""Continua la conversazione commerciale con il cliente (canale email).

Nome cliente: {nome}
Email: {email}

Richiesta iniziale dal form web:
{messaggio_iniziale.strip()}

Cronologia conversazione:
{history.strip() or "(nessun turno precedente)"}

Ultimo messaggio del cliente (risposta email):
{nuovo_messaggio.strip()}
{catalog_block}{pricing_block}
Se compare CALCOLO PREZZI: riporta gli importi calcolati senza modificarli.
Scrivi SOLO la risposta da inviare ora (testo piano, niente markdown).
- Rispondi in modo naturale al nuovo messaggio, coerente con la cronologia.
- Se servono chiarimenti (mq, finitura, spessore), chiedili in modo breve.
- Non ripetere l'intera offerta se già inviata; aggiorna o integra solo ciò che serve.
- Max 4-6 frasi; firma "Team NStone"."""


def build_ordini_extract_prompt(
    *,
    client: str,
    subject: str,
    body: str,
    language: LlmLanguage = "it",
) -> str:
    if language == "en":
        return f"""Extract fields from this order email.

Customer email: {client}
Subject: {subject}
Body:
{body[:4000]}

Respond ONLY with valid JSON (no markdown):
{{
  "materiale": "material or slab name",
  "quantita_mq": number or null,
  "machine": "multifilo|lucidatrice|cnc|non_specificata",
  "note": "brief operational summary for production",
  "confidence": 0.0-1.0
}}"""
    return f"""Estrai i campi da questa email d'ordine.

Email cliente: {client}
Oggetto: {subject}
Corpo:
{body[:4000]}

Rispondi SOLO con JSON valido (senza markdown):
{{
  "materiale": "nome materiale o lastra",
  "quantita_mq": numero o null,
  "machine": "multifilo|lucidatrice|cnc|non_specificata",
  "note": "sintesi operativa breve per reparto",
  "confidence": 0.0-1.0
}}"""


def build_ordini_classify_prompt(
    *,
    sender: str,
    subject: str,
    body: str,
    language: LlmLanguage = "it",
) -> str:
    if language == "en":
        return f"""Classify this email for the NStone orders flow.

Sender: {sender}
Subject: {subject}
Body (excerpt): {body[:500]}

Quick rules:
- ORDINE = new purchase request or order with materials/quantities.
- CONFERMA = reply accepting/confirming an existing order or quote.
- NON_RILEVANTE = spam, newsletters, invoices, generic info without an order.

Respond ONLY with valid JSON (no markdown):
{{
  "tipo": "ORDINE" | "CONFERMA" | "NON_RILEVANTE",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""
    return f"""Classifica questa email per il flusso ordini NStone.

Mittente: {sender}
Oggetto: {subject}
Corpo (estratti): {body[:500]}

Regole rapide:
- ORDINE = nuova richiesta d'acquisto o ordine con materiali/quantità.
- CONFERMA = risposta che accetta/conferma un ordine già proposto.
- NON_RILEVANTE = spam, newsletter, fatture, info generiche senza ordine.

Rispondi SOLO con JSON valido (senza markdown):
{{
  "tipo": "ORDINE" | "CONFERMA" | "NON_RILEVANTE",
  "confidence": 0.0-1.0,
  "reasoning": "breve spiegazione"
}}"""


def build_ordini_confirmation_prompt(
    *,
    order_id: str,
    client_email: str,
    original_subject: str,
    original_body: str,
    email_body: str,
    language: LlmLanguage = "it",
) -> str:
    if language == "en":
        return f"""Analyze whether the customer confirms, rejects, or leaves the order pending.

**Original order**
- ID: {order_id}
- Customer: {client_email}
- Subject: {original_subject}
- Content:
{original_body[:3000]}

**Customer reply**
{email_body[:3000]}

Respond ONLY with valid JSON (no markdown):
{{
  "status": "confirmed" | "pending" | "cancelled",
  "notes": "brief internal note",
  "confirmation_email_text": "formal English email to customer if confirmed, otherwise \\"\\""
}}"""
    return f"""Analizza se il cliente conferma, rifiuta o lascia in sospeso l'ordine.

**Ordine originale**
- ID: {order_id}
- Cliente: {client_email}
- Oggetto: {original_subject}
- Contenuto:
{original_body[:3000]}

**Risposta del cliente**
{email_body[:3000]}

Rispondi SOLO con JSON valido (senza markdown):
{{
  "status": "confirmed" | "pending" | "cancelled",
  "notes": "nota interna breve",
  "confirmation_email_text": "testo mail formale al cliente se confirmed, altrimenti \\"\\""
}}"""


def build_ordini_stock_confirmation_prompt(
    *,
    order_id: str,
    order_data: Dict[str, Any],
    email_body: str,
    stock_report: Dict[str, Any],
    language: LlmLanguage = "it",
) -> str:
    stock_json = json.dumps(stock_report, ensure_ascii=False, indent=2)
    if language == "en":
        return f"""Analyze customer confirmation and draft NStone email with stock outcome.

**Order**
- ID: {order_id}
- Customer: {order_data.get("from", "")}
- Subject: {order_data.get("subject", "")}
- Material: {order_data.get("materiale", "")}
- Qty sqm: {order_data.get("quantita", "")}
- Order text:
{str(order_data.get("body", ""))[:2000]}

**Customer reply**
{email_body[:3000]}

**Stock report (sole source for availability)**
{stock_json}

If the order comes from an NS-Q quotation thread, confirmation_email_text must be a
natural threaded reply: thank the customer, recap material and sqm confirmed, state
stock outcome, max 5-6 sentences, sign Team NStone. Write in English.

Respond ONLY with valid JSON (no markdown):
{{
  "status": "confirmed" | "pending" | "cancelled",
  "availability": "available" | "partial" | "unavailable" | "unknown",
  "confidence": 0.0-1.0,
  "notes": "internal note",
  "confirmation_email_text": "customer email if confirmed, otherwise \\"\\""
}}"""
    return f"""Analizza conferma cliente e redigi mail NStone con esito stock.

**Ordine**
- ID: {order_id}
- Cliente: {order_data.get("from", "")}
- Oggetto: {order_data.get("subject", "")}
- Materiale: {order_data.get("materiale", "")}
- Quantità mq: {order_data.get("quantita", "")}
- Testo ordine:
{str(order_data.get("body", ""))[:2000]}

**Risposta cliente**
{email_body[:3000]}

**Report stock (unica fonte per availability)**
{stock_json}

Se l'ordine proviene da un thread preventivo NS-Q, il testo confirmation_email_text
deve essere una risposta email naturale sullo stesso thread: ringrazia, riepiloga
materiale e mq confermati, indica esito stock, max 5-6 frasi, firma Team NStone.

Rispondi SOLO con JSON valido (senza markdown):
{{
  "status": "confirmed" | "pending" | "cancelled",
  "availability": "available" | "partial" | "unavailable" | "unknown",
  "confidence": 0.0-1.0,
  "notes": "nota interna",
  "confirmation_email_text": "mail al cliente se confirmed, altrimenti \\"\\""
}}"""


def build_produzione_operator_prompt(question: str, include_reasoning: bool = False) -> str:
    prompt = (
        f"Shop-floor operator question:\n\n{question.strip()}\n\n"
        "Response instructions (in English, complete but concise):\n"
        "1. STATUS — summarize operational state (Idle/Run/Alarm), PLC connection, alarms, and key parameters read.\n"
        "2. ASSESSMENT — compare each parameter with the nominal range in context: "
        "state whether it is normal, at limit, or out of range.\n"
        "3. ANOMALIES — list detected anomalies; if none, write 'No anomaly detected'.\n"
        "4. RECOMMENDED ACTIONS — suggest concrete operator actions "
        "(even 'continue monitoring' if everything is normal).\n\n"
        "Use only values present in context; if data is missing, say so explicitly. "
        "Do not invent values. "
        "If the context does NOT provide nominal ranges or thresholds, do NOT claim "
        "values are 'within normal range': state that nominal ranges are not available "
        "and limit the assessment to what can be verified. "
        "If the context includes a CONSISTENCY CHECKS section, address every flagged "
        "item explicitly in ANOMALIES. ALWAYS respond in English."
    )
    if include_reasoning:
        prompt += (
            "\n\nBefore the answer, expose structured reasoning in 4 sections:\n"
            "QUESTION INTERPRETATION / DATA USED / ANALYSIS PROCESS / LIMITS AND UNCERTAINTY.\n"
            "Then conclude with section 'FINAL ANSWER:' followed by the operator response."
        )
    return prompt


def build_technical_client_reply_prompt(
    *,
    nome: str,
    email: str,
    messaggio: str,
    knowledge_context: str = "",
    language: LlmLanguage = "it",
) -> str:
    knowledge_block = ""
    if (knowledge_context or "").strip():
        knowledge_block = f"\n\n{knowledge_context.strip()}\n"

    if language == "en":
        return f"""Write a professional technical reply to the customer (NOT a price quotation).

Customer name: {nome}
Email: {email}

Customer message:
{messaggio.strip()}
{knowledge_block}
Rules (mandatory):
- Answer ONLY using facts from KNOWLEDGE BASE CONTEXT above.
- Do NOT include commercial offer blocks, EX WORKS lines, €/m² prices, or stock availability.
- Do NOT invent technical values, certifications, or policies.
- If the knowledge base does not contain the answer, say clearly that you will verify with the technical office.
- Tone: professional, concise (6–12 lines). Sign "Team NStone". English only."""

    return f"""Scrivi una risposta tecnica professionale al cliente (NON un preventivo commerciale).

Nome cliente: {nome}
Email: {email}

Messaggio del cliente:
{messaggio.strip()}
{knowledge_block}
Regole (obbligatorie):
- Rispondi SOLO con fatti presenti nel KNOWLEDGE BASE CONTEXT sopra.
- NON inserire blocchi offerta, righe EX WORKS, prezzi €/m² o disponibilità magazzino.
- NON inventare valori tecnici, certificazioni o policy.
- Se la knowledge base non contiene la risposta, dillo chiaramente e proponi verifica con ufficio tecnico.
- Tono: professionale, conciso (6–12 righe). Firma "Team NStone". Solo italiano."""


def build_technical_thread_reply_prompt(
    *,
    nome: str,
    email: str,
    messaggio_iniziale: str,
    history: str,
    nuovo_messaggio: str,
    knowledge_context: str = "",
    language: LlmLanguage = "it",
) -> str:
    knowledge_block = ""
    if (knowledge_context or "").strip():
        knowledge_block = f"\n\n{knowledge_context.strip()}\n"

    history_block = ""
    if (history or "").strip():
        history_block = f"\n\nConversation history:\n{history.strip()}\n"

    if language == "en":
        return f"""Write a technical follow-up reply in an existing customer thread (NOT a new quotation).

Customer: {nome} ({email})
Initial message: {messaggio_iniziale.strip()}
{history_block}
New customer message:
{nuovo_messaggio.strip()}
{knowledge_block}
Rules: same as technical reply — knowledge base only, no offer blocks or invented prices.
English only. Sign "Team NStone"."""

    return f"""Scrivi un follow-up tecnico in un thread cliente esistente (NON un nuovo preventivo).

Cliente: {nome} ({email})
Messaggio iniziale: {messaggio_iniziale.strip()}
{history_block}
Nuovo messaggio cliente:
{nuovo_messaggio.strip()}
{knowledge_block}
Regole: come risposta tecnica — solo knowledge base, niente blocchi offerta né prezzi inventati.
Solo italiano. Firma "Team NStone"."""

