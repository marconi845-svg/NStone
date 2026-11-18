"""
RAG Engine - Retrieval Augmented Generation per Nstone LLM
Backend per recupero contesto dal database e generazione risposte con Gemini
"""
import os
import sys
import re
import time
import hashlib
from pathlib import Path
import sqlite3
from typing import List, Dict, Optional, Tuple
from llm.gemini_service import GeminiService
from llm.gemini_model_registry import get_model, initialize_registry


class RAGEngine:
    """
    Motore RAG per recupero contesto dal database e generazione risposte
    con profilo comportamentale Gemini integrato
    """
    
    # Gemini Personality Profile - Profilo comportamentale permanente
    GEMINI_PERSONALITY_PROFILE = """
Sei Nstone Neural Engine, il primo motore neurale per la gestione di pietre naturali.

**Profilo Comportamentale:**
- Stile: Tecnico e professionale
- Tono: Competente, preciso, orientato alle soluzioni
- Conoscenza: Esperto del motore neurale Nstone LLM, database SQLite, gestione inventario pietre naturali
- Regole di risposta:
  * Fornisci risposte accurate basate sul contesto recuperato dal database
  * Se il contesto non è disponibile, indica chiaramente i limiti
  * Usa terminologia tecnica appropriata quando necessario
  * Mantieni un tono professionale ma accessibile
  * Priorità: precisione, modularità, sicurezza
  * Nessun contenuto superfluo, nessuna fantasia non richiesta
- Priorità:
  1. Accuratezza dei dati dal database
  2. Chiarezza nella spiegazione
  3. Utilità pratica per l'utente
  4. Coerenza con il sistema Nstone LLM

**Contesto Permanente:**
- Sistema: Nstone LLM v0.0.12
- Database: SQLite (data/nstonellm.db)
- Tabelle principali: online_stock, quotations, orders, production, collection, administration
- Modalità: Sola lettura, nessuna modifica ai dati

Quando rispondi, integra sempre il contesto recuperato dal database nella tua risposta.
Risposte coerenti con l'identità NStone, orientate alla soluzione pratica.
"""

    OPERATIONAL_SYSTEM = (
        "Sei l'assistente operativo NStone in reparto macchine. "
        "Rispondi in italiano, massimo 10 righe, tono tecnico. "
        "Usa solo i dati nel messaggio; non inventare valori PLC assenti."
    )
    
    def __init__(self, api_key: Optional[str] = None, db_path: Optional[Path] = None):
        """
        Inizializza il RAG Engine
        
        Args:
            api_key: Chiave API Gemini (opzionale)
            db_path: Percorso database SQLite (opzionale)
        """
        # Inizializza Gemini Service
        self.gemini_service = GeminiService(api_key=api_key)
        
        # Percorso database
        if db_path is None:
            self.db_path = Path(__file__).resolve().parents[1] / "data" / "nstonellm.db"
        else:
            self.db_path = Path(db_path)
        
        # Cache per informazioni database
        self._db_locked = False
        self._table_schemas = {}
        
        # Storage per reasoning dell'ultima risposta
        self._last_reasoning = ""
        self._last_question = ""
        self._last_context = ""
        self._last_answer = ""

        # Cache breve retrieve/search (stessa domanda ripetuta)
        self._search_cache: Dict[str, Tuple[float, Dict]] = {}
        self._search_cache_ttl_sec = 45.0
        self._search_cache_max_entries = 32
        
        # Inizializza tabella rag_memory se non esiste
        self._init_rag_memory_table()
    
    def _init_rag_memory_table(self):
        """
        Inizializza la tabella rag_memory se non esiste.
        Scrittura controllata solo da parte del RAG Engine.
        """
        if not self.db_path.exists():
            return
        
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=2.0)
            cursor = conn.cursor()
            
            # Crea tabella rag_memory se non esiste
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rag_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    question TEXT NOT NULL,
                    context TEXT,
                    answer TEXT NOT NULL,
                    reasoning TEXT,
                    tags TEXT
                )
            """)
            
            conn.commit()
            conn.close()
        except sqlite3.OperationalError:
            # Database locked, ignora
            pass
        except Exception:
            # Altri errori silenziosi
            pass
    
    def save_interaction(self, question: str, context: str, answer: str, reasoning: str = "", tags: str = ""):
        """
        Salva un'interazione nella memoria evolutiva.
        Scrittura controllata, connessione dedicata, sempre chiusa.
        
        Args:
            question: Domanda dell'utente
            context: Contesto recuperato
            answer: Risposta generata
            reasoning: Reasoning (opzionale)
            tags: Tag per categorizzazione (opzionale)
        """
        if self.is_database_locked():
            return  # Non salvare se DB locked
        
        if not self.db_path.exists():
            return
        
        try:
            from datetime import datetime
            timestamp = datetime.now().isoformat()
            
            conn = sqlite3.connect(str(self.db_path), timeout=2.0)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO rag_memory (timestamp, question, context, answer, reasoning, tags)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (timestamp, question, context, answer, reasoning, tags))
            
            conn.commit()
            conn.close()
        except sqlite3.OperationalError:
            # Database locked, ignora
            pass
        except Exception:
            # Altri errori silenziosi
            pass
    
    def is_database_locked(self) -> bool:
        """
        Verifica se il database è locked da un altro programma.
        Restituisce True se locked, False se disponibile.
        """
        if not self.db_path.exists():
            return False
        
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=1.0)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            self._db_locked = False
            return False
        except sqlite3.OperationalError:
            self._db_locked = True
            return True
        except Exception:
            self._db_locked = False
            return False
    
    def _extract_keywords(self, question: str) -> List[str]:
        """
        Estrae keyword dalla domanda rimuovendo stopwords italiane.
        Normalizza, rimuove articoli, preposizioni, parole corte.
        
        Args:
            question: Domanda dell'utente
        
        Returns:
            Lista di keyword uniche (minimo 3 caratteri)
        """
        # Stopwords italiane comuni
        stopwords = {
            'il', 'la', 'lo', 'gli', 'le', 'i', 'un', 'una', 'uno', 'dei', 'degli', 'delle',
            'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 'dal', 'dalla', 'dallo',
            'del', 'della', 'dello', 'dei', 'degli', 'delle', 'al', 'alla', 'allo', 'ai', 'agli',
            'che', 'chi', 'cosa', 'come', 'dove', 'quando', 'perché', 'quale', 'quali',
            'è', 'sono', 'ha', 'hanno', 'era', 'erano', 'sarà', 'saranno',
            'e', 'o', 'ma', 'se', 'non', 'più', 'molto', 'tanto', 'poco',
            'questo', 'questa', 'questi', 'queste', 'quello', 'quella', 'quelli', 'quelle'
        }
        
        # Normalizza: minuscolo, trim
        normalized = question.lower().strip()
        
        # Rimuovi punteggiatura comune
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        
        # Dividi in parole
        words = normalized.split()
        
        # Filtra: rimuovi stopwords e parole < 3 caratteri
        keywords = [w for w in words if len(w) >= 3 and w not in stopwords]
        
        # Rimuovi duplicati mantenendo ordine
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        # Se non rimane nulla, usa la domanda intera come fallback
        if not unique_keywords:
            # Usa parole >= 3 caratteri anche se sono stopwords
            fallback = [w for w in words if len(w) >= 3]
            return fallback[:5]  # Limita a 5 parole principali
        
        return unique_keywords
    
    def _calculate_relevance_score(self, text: str, keywords: List[str]) -> int:
        """
        Calcola punteggio di rilevanza per un testo basato sulle keyword.
        
        Args:
            text: Testo da analizzare
            keywords: Lista di keyword
        
        Returns:
            Punteggio (1 punto per ogni keyword trovata)
        """
        if not text:
            return 0
        
        text_lower = text.lower()
        score = 0
        
        for keyword in keywords:
            if keyword.lower() in text_lower:
                score += 1
        
        return score
    
    def _should_activate_ocular_mode(self, question: str) -> bool:
        """
        Determina se attivare la Modalità Oculare basandosi sulla domanda.
        
        Args:
            question: Domanda dell'utente
        
        Returns:
            True se la Modalità Oculare deve essere attivata
        """
        question_lower = question.lower()
        
        # Parole chiave che attivano Modalità Oculare
        ocular_keywords = [
            "oculare", "analizza bene", "guarda tutto", "precisione", "attenzione",
            "analizza", "verifica", "controlla", "ispeziona", "esamina",
            "dettaglio", "dettagli", "accurato", "accurata", "preciso", "precisa"
        ]
        
        # Controlla se contiene parole chiave
        for keyword in ocular_keywords:
            if keyword in question_lower:
                return True
        
        # Controlla se la domanda è critica (ordini, produzione, prezzi, disponibilità)
        critical_keywords = [
            "ordine", "ordini", "produzione", "prezzo", "prezzi", "costo", "costos",
            "disponibilità", "disponibile", "stock", "inventario", "magazzino",
            "consegna", "spedizione", "fattura", "fatture", "pagamento", "pagamenti"
        ]
        
        for keyword in critical_keywords:
            if keyword in question_lower:
                return True
        
        return False
    
    @staticmethod
    def _split_structured_answer(answer: str) -> Tuple[str, str]:
        """
        Se la risposta contiene Reasoning Strutturato (4 sezioni), separa
        RISPOSTA FINALE dal resto per evitare una seconda chiamata LLM.
        """
        if not answer or "RISPOSTA FINALE" not in answer.upper():
            return answer, ""

        upper = answer.upper()
        marker = "RISPOSTA FINALE"
        idx = upper.find(marker)
        reasoning_part = answer[:idx].strip()
        final_part = answer[idx + len(marker) :].strip()
        if final_part.startswith(":"):
            final_part = final_part[1:].strip()
        if not final_part:
            return answer, ""
        return final_part, reasoning_part

    def _should_activate_structured_reasoning(self, question: str, include_reasoning: bool = False) -> bool:
        """
        Determina se attivare il Reasoning Strutturato (Livello 2) basandosi sulla domanda.
        
        Args:
            question: Domanda dell'utente
            include_reasoning: Se True, l'utente ha richiesto esplicitamente il reasoning
        
        Returns:
            True se il Reasoning Strutturato deve essere attivato
        """
        # Se l'utente ha richiesto esplicitamente reasoning
        if include_reasoning:
            return True
        
        question_lower = question.lower()
        
        # Parole chiave che attivano Reasoning Strutturato
        reasoning_keywords = [
            "spiega", "spiegami", "spiegare", "mostra il ragionamento", "mostra ragionamento",
            "come ci arrivi", "come arrivi", "ragionamento", "reasoning",
            "analisi", "analizza", "dimostra", "motiva", "giustifica",
            "perché", "perche", "come funziona", "come hai fatto"
        ]
        
        # Controlla se contiene parole chiave
        for keyword in reasoning_keywords:
            if keyword in question_lower:
                return True
        
        # Controlla se la domanda è critica (ordini, produzione, disponibilità, prezzi)
        critical_keywords = [
            "ordine", "ordini", "produzione", "disponibilità", "disponibile",
            "prezzo", "prezzi", "costo", "costos", "stock", "inventario"
        ]
        
        for keyword in critical_keywords:
            if keyword in question_lower:
                return True
        
        return False
    
    def search_database(self, question: str, max_results: int = 10) -> Dict:
        """
        Cerca nel database informazioni rilevanti per la domanda.
        Potenziato con estrazione keyword e punteggi di rilevanza.
        Include anche ricerca nella memoria evolutiva rag_memory.
        SOLA LETTURA - Nessuna query pericolosa - Nessuna modifica ai dati.
        
        Args:
            question: Domanda dell'utente
            max_results: Numero massimo di risultati per tabella
        
        Returns:
            Dizionario con:
            - "db_results": Lista di dict {table, columns, records_with_scores}
            - "memory_results": Lista di dict {id, timestamp, question, answer, reasoning, tags, score, matched_keywords}
        """
        result = {
            "db_results": [],
            "memory_results": []
        }
        
        question_norm = (question or "").strip().lower()
        if question_norm:
            cache_key = hashlib.sha1(question_norm.encode("utf-8")).hexdigest()
            cached = self._search_cache.get(cache_key)
            if cached and (time.time() - cached[0]) < self._search_cache_ttl_sec:
                return cached[1]
        
        # Verifica lock
        if self.is_database_locked():
            return result
        
        if not self.db_path.exists():
            return result
        
        # Estrai keyword dalla domanda (max 3 per ridurre query LIKE)
        keywords = self._extract_keywords(question)[:3]
        
        # Se non ci sono keyword, usa la domanda intera come fallback
        if not keywords:
            keywords = [question[:20]]  # Primi 20 caratteri come fallback
        
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=2.0)
            try:
                conn.execute("PRAGMA busy_timeout=2000")
                conn.execute("PRAGMA query_only=ON")
            except sqlite3.Error:
                pass
            cursor = conn.cursor()
            
            # Tabelle rilevanti per il RAG
            relevant_tables = ['online_stock', 'quotations', 'orders', 'production', 'collection', 'administration']
            
            # Cerca in ogni tabella rilevante
            for table_name in relevant_tables:
                try:
                    # Verifica che la tabella esista
                    cursor.execute("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name=?
                    """, (table_name,))
                    if not cursor.fetchone():
                        continue
                    
                    # Ottieni schema colonne
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns_info = cursor.fetchall()
                    column_names = [col[1] for col in columns_info]
                    
                    if not column_names:
                        continue
                    
                    # Identifica colonne testuali principali
                    text_columns = []
                    for col_name in column_names:
                        # Colonne testuali comuni
                        if any(keyword in col_name.lower() for keyword in ['name', 'type', 'color', 'origin', 'cliente', 'materiale', 'client', 'product', 'status', 'transporter', 'destination']):
                            text_columns.append(col_name)
                    
                    # Se non ci sono colonne testuali identificate, usa tutte le colonne
                    if not text_columns:
                        text_columns = column_names[:5]  # Limita a prime 5 colonne
                    
                    # Esegui ricerca per ogni keyword
                    all_matched_records = []
                    record_scores = {}  # {(record_tuple): score}
                    
                    for keyword in keywords:
                        search_conditions = []
                        search_params = []
                        
                        for col_name in text_columns:
                            try:
                                search_conditions.append(f"{col_name} LIKE ?")
                                search_params.append(f"%{keyword}%")
                            except:
                                pass
                        
                        if search_conditions:
                            where_clause = " OR ".join(search_conditions)
                            search_query = f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT ?"
                            search_params.append(max_results * 2)  # Prendi più record per poi filtrare
                            
                            cursor.execute(search_query, search_params)
                            records = cursor.fetchall()
                            
                            # Calcola punteggio per ogni record
                            for record in records:
                                # Costruisci testo combinato del record
                                record_text = " ".join([str(val) if val is not None else "" for val in record])
                                
                                # Calcola punteggio
                                score = self._calculate_relevance_score(record_text, keywords)
                                
                                if score > 0:
                                    # Usa tuple come chiave (immutabile)
                                    record_key = tuple(record)
                                    if record_key not in record_scores:
                                        record_scores[record_key] = score
                                        all_matched_records.append((record, score))
                                    else:
                                        # Aggiorna punteggio se più alto
                                        if score > record_scores[record_key]:
                                            record_scores[record_key] = score
                                            # Aggiorna nella lista
                                            for i, (r, s) in enumerate(all_matched_records):
                                                if r == record:
                                                    all_matched_records[i] = (record, score)
                                                    break
                    
                    # Ordina per punteggio decrescente e limita
                    all_matched_records.sort(key=lambda x: x[1], reverse=True)
                    top_records = all_matched_records[:max_results]
                    
                    if top_records:
                        result["db_results"].append({
                            "table": table_name,
                            "columns": column_names,
                            "records_with_scores": top_records  # Lista di (record, score)
                        })
                            
                except Exception:
                    # Ignora errori su singole tabelle
                    continue
            
            # Ricerca potenziata in rag_memory
            try:
                # Verifica che la tabella esista
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='rag_memory'
                """)
                if cursor.fetchone():
                    # Cerca per ogni keyword
                    memory_candidates = []
                    
                    for keyword in keywords:
                        cursor.execute("""
                            SELECT id, timestamp, question, context, answer, reasoning, tags
                            FROM rag_memory
                            WHERE question LIKE ? OR answer LIKE ? OR context LIKE ?
                        """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))
                        
                        for row in cursor.fetchall():
                            # Calcola punteggio
                            mem_id, mem_timestamp, mem_question, mem_context, mem_answer, mem_reasoning, mem_tags = row
                            
                            # Combina tutti i testi per calcolo punteggio
                            combined_text = f"{mem_question or ''} {mem_answer or ''} {mem_context or ''}"
                            score = self._calculate_relevance_score(combined_text, keywords)
                            
                            if score > 0:
                                # Trova keyword matchate
                                matched_keywords = [kw for kw in keywords if kw.lower() in combined_text.lower()]
                                
                                memory_candidates.append({
                                    "id": mem_id,
                                    "timestamp": mem_timestamp,
                                    "question": mem_question,
                                    "context": mem_context,
                                    "answer": mem_answer,
                                    "reasoning": mem_reasoning,
                                    "tags": mem_tags,
                                    "score": score,
                                    "matched_keywords": matched_keywords
                                })
                    
                    # Rimuovi duplicati (stesso ID) mantenendo quello con punteggio più alto
                    unique_memory = {}
                    for mem in memory_candidates:
                        mem_id = mem["id"]
                        if mem_id not in unique_memory or mem["score"] > unique_memory[mem_id]["score"]:
                            unique_memory[mem_id] = mem
                    
                    # Ordina per punteggio decrescente, poi timestamp decrescente
                    memory_sorted = sorted(
                        unique_memory.values(),
                        key=lambda x: (x["score"], x["timestamp"]),
                        reverse=True
                    )
                    
                    # Limita a top 5-10
                    result["memory_results"] = memory_sorted[:10]
                    
            except Exception:
                # Ignora errori sulla memoria
                pass
            
            conn.close()
            
        except sqlite3.OperationalError:
            self._db_locked = True
        except Exception:
            # Altri errori silenziosi
            pass

        if question_norm:
            if len(self._search_cache) >= self._search_cache_max_entries:
                oldest = min(self._search_cache.items(), key=lambda item: item[1][0])[0]
                self._search_cache.pop(oldest, None)
            self._search_cache[cache_key] = (time.time(), result)
        
        return result
    
    def build_context(self, data: Dict) -> str:
        """
        Trasforma i dati del database in testo leggibile e formattato.
        Include anche memoria storica rilevante con punteggi di rilevanza.
        
        Args:
            data: Dizionario restituito da search_database() con nuova struttura
        
        Returns:
            Stringa formattata con contesto leggibile (DB + memoria) con rilevanza
        """
        context_parts = []
        
        # Parte 1: Contesto dalle tabelle principali
        if data.get("db_results"):
            context_parts.append("[CONTESTO DALLE TABELLE PRINCIPALI]")
            context_parts.append("")
            
            for db_result in data["db_results"]:
                table_name = db_result["table"]
                columns = db_result["columns"]
                records_with_scores = db_result["records_with_scores"]
                
                if not records_with_scores:
                    continue
                
                # Calcola punteggio medio per determinare rilevanza
                scores = [score for _, score in records_with_scores]
                avg_score = sum(scores) / len(scores) if scores else 0
                
                # Determina rilevanza
                if avg_score >= 3:
                    relevance = "alta"
                elif avg_score >= 1.5:
                    relevance = "media"
                else:
                    relevance = "bassa"
                
                # Seleziona colonne significative (prime 5-6 colonne principali)
                significant_columns = columns[:6]
                
                context_parts.append(f"[Tabella: {table_name}] (Rilevanza: {relevance})")
                context_parts.append(f"Colonne chiave: {', '.join(significant_columns)}")
                context_parts.append(f"Record trovati: {len(records_with_scores)}")
                context_parts.append("")
                
                # Formatta record (solo top records)
                for record, score in records_with_scores[:5]:  # Limita a top 5 per tabella
                    record_parts = []
                    for i, value in enumerate(record):
                        if i < len(significant_columns):
                            col_name = significant_columns[i]
                            # Formatta valore
                            if value is None:
                                val_str = "NULL"
                            else:
                                val_str = str(value)
                            # Tronca valori molto lunghi
                            if len(val_str) > 50:
                                val_str = val_str[:50] + "..."
                            record_parts.append(f"{col_name}={val_str}")
                    
                    if record_parts:
                        context_parts.append(f"  - {' | '.join(record_parts)}")
                
                context_parts.append("")  # Linea vuota tra tabelle
        
        # Parte 2: Memoria storica rilevante (basata su punteggi)
        if data.get("memory_results"):
            context_parts.append("[MEMORIA STORICA RILEVANTE]")
            context_parts.append("")
            
            # Prendi solo top 3-5 interazioni migliori
            top_memory = data["memory_results"][:5]
            
            for mem in top_memory:
                mem_id = mem["id"]
                mem_timestamp = mem["timestamp"]
                mem_question = mem["question"] or ""
                mem_answer = mem["answer"] or ""
                mem_tags = mem["tags"] or ""
                mem_score = mem["score"]
                matched_keywords = mem.get("matched_keywords", [])
                
                # Determina rilevanza basata su punteggio
                if mem_score >= 3:
                    relevance = "alta"
                elif mem_score >= 1.5:
                    relevance = "media"
                else:
                    relevance = "bassa"
                
                # Formatta timestamp
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(mem_timestamp)
                    timestamp_formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    timestamp_formatted = mem_timestamp
                
                context_parts.append(f"--- Interazione #{mem_id} ({timestamp_formatted}, Rilevanza: {relevance}) ---")
                context_parts.append(f"Domanda precedente: {mem_question[:200]}")
                
                # Estratto risposta (primi 300 caratteri)
                answer_extract = mem_answer[:300] + "..." if len(mem_answer) > 300 else mem_answer
                context_parts.append(f"Risposta data: {answer_extract}")
                
                # Motivo rilevanza
                if matched_keywords:
                    keywords_str = ", ".join(matched_keywords[:5])  # Limita a 5 keyword
                    context_parts.append(f"Motivo rilevanza: match su parole chiave: {keywords_str}")
                
                if mem_tags:
                    context_parts.append(f"Tag: {mem_tags}")
                
                context_parts.append("")
        
        # Fallback elegante
        if not context_parts:
            context_parts.append("[CONTESTO DAL DATABASE]")
            context_parts.append("Nessun dato rilevante trovato nel database né nella memoria storica per questa domanda.")
        
        return "\n".join(context_parts).strip()
    
    def retrieve_context(self, question: str, max_results: int = 10) -> str:
        """
        Recupera contesto rilevante dal database basato sulla domanda.
        Include anche memoria evolutiva rilevante con punteggi di rilevanza.
        Usa search_database() e build_context() internamente.
        
        Args:
            question: Domanda dell'utente
            max_results: Numero massimo di risultati da recuperare per tabella
        
        Returns:
            Stringa con contesto recuperato (DB + memoria), o messaggio di errore se DB locked
        """
        # Verifica lock
        if self.is_database_locked():
            return "⚠️ Database aperto in un altro programma. Recupero contesto disabilitato."
        
        if not self.db_path.exists():
            return "⚠️ Database non trovato."
        
        # Cerca nel database (include anche memoria) - usa nuova struttura con punteggi
        search_data = self.search_database(question, max_results)
        
        # Costruisci contesto formattato (include memoria se presente) con rilevanza
        context = self.build_context(search_data)
        
        return context
    
    def generate_answer(
        self,
        question: str,
        include_reasoning: bool = False,
        operational: bool = False,
    ) -> Dict[str, str]:
        """
        Genera una risposta usando RAG: recupera contesto e genera risposta con Gemini.
        Include memoria evolutiva e salva automaticamente l'interazione.
        
        Args:
            question: Domanda dell'utente
            include_reasoning: Se True, include il reasoning nella risposta
            operational: Modalità veloce per domande macchina (no scan DB, modello fast)
        
        Returns:
            Dizionario con:
            - "context": Contesto recuperato dal database + memoria
            - "answer": Risposta generata da Gemini
            - "reasoning": Reasoning (se include_reasoning=True)
        """
        q_upper = question.upper()
        has_machine_ctx = (
            "[CONTESTO MACCHINA" in q_upper
            or "[CONTESTO IMPIANTO" in q_upper
            or "[CNC MACHINE" in q_upper
        )
        if operational or has_machine_ctx:
            return self._generate_operational_answer(question, include_reasoning)

        # Step 1: Recupera contesto dal database (include memoria)
        context = self.retrieve_context(question)
        
        # Salva per reasoning futuro
        self._last_question = question
        self._last_context = context
        self._last_reasoning = ""
        
        # Step 1.5: Determina se attivare Modalità Oculare e Reasoning Strutturato
        ocular_mode_active = self._should_activate_ocular_mode(question)
        structured_reasoning_active = self._should_activate_structured_reasoning(question, include_reasoning)
        
        # Step 2: Prepara prompt arricchito con memoria storica e rilevanza
        # Il contesto già include sezioni separate [CONTESTO DALLE TABELLE PRINCIPALI] e [MEMORIA STORICA RILEVANTE]
        
        # Costruisci prompt completo e strutturato
        prompt_parts = [
            "[SYSTEM — PERSONALITY PROFILE]",
            self.GEMINI_PERSONALITY_PROFILE,
            "",
            "[DOMANDA UTENTE]",
            question,
            ""
        ]
        
        # Aggiungi contesto se disponibile e valido
        if context and not context.startswith("⚠️"):
            # Il contesto già contiene le sezioni strutturate
            prompt_parts.extend([
                context,
                ""
            ])
        elif context.startswith("⚠️"):
            # Database locked o errore
            prompt_parts.extend([
                "[CONTESTO DAL DATABASE]",
                context,
                ""
            ])
        else:
            # Nessun contesto
            prompt_parts.extend([
                "[CONTESTO DAL DATABASE]",
                "Nessun dato rilevante trovato nel database né nella memoria storica per questa domanda.",
                ""
            ])
        
        # Aggiungi Modalità Oculare se attivata
        if ocular_mode_active:
            prompt_parts.extend([
                "[MODALITÀ OCULARE — ATTENZIONE AUMENTATA]",
                "",
                "Il motore neurale deve attivare la Modalità Oculare per questa domanda.",
                "",
                "Comportamento richiesto:",
                "- Analizza ogni parola della domanda con massima precisione.",
                "- Identifica tutte le entità rilevanti (prodotti, clienti, ordini, date, quantità).",
                "- Confronta la domanda con la memoria evolutiva e segnala eventuali somiglianze.",
                "- Evita interpretazioni ambigue: se un termine può significare più cose, scegli quella più coerente con il contesto storico.",
                "- Mantieni coerenza con risposte precedenti sullo stesso tema.",
                "- Se mancano dati, dichiara esplicitamente cosa manca.",
                "- Se ci sono rischi di fraintendimento, esplicitali.",
                "- Rispondi con struttura chiara, sezioni ordinate e logica trasparente.",
                "",
                "Se l'utente richiede attenzione aumentata o usa termini come 'oculare', attiva automaticamente la Modalità Oculare.",
                ""
            ])
        
        # Aggiungi Reasoning Strutturato (Livello 2) se attivato
        if structured_reasoning_active:
            prompt_parts.extend([
                "[REASONING STRUTTURATO — LIVELLO 2]",
                "",
                "Quando l'utente richiede reasoning o analisi dettagliata, struttura il ragionamento in quattro sezioni:",
                "",
                "1. INTERPRETAZIONE DELLA DOMANDA",
                "   - Spiega cosa sta chiedendo l'utente.",
                "   - Identifica eventuali ambiguità.",
                "   - Specifica quali elementi della domanda sono critici.",
                "",
                "2. DATI RILEVANTI TROVATI",
                "   - Elenca i dati estratti dal database.",
                "   - Elenca i dati estratti dalla memoria evolutiva.",
                "   - Indica perché questi dati sono rilevanti.",
                "   - Non inventare nulla: usa solo ciò che è nel contesto.",
                "",
                "3. DECISIONE LOGICA",
                "   - Spiega come colleghi i dati alla domanda.",
                "   - Mostra il ragionamento passo-passo.",
                "   - Evidenzia eventuali limiti o mancanze di dati.",
                "",
                "4. RISPOSTA FINALE",
                "   - Fornisci la risposta chiara, sintetica e operativa.",
                "   - Mantieni lo stile tecnico NStone.",
                "",
                "In Reasoning Strutturato, il modello deve:",
                "- essere trasparente",
                "- essere rigoroso",
                "- non saltare passaggi",
                "- non fare assunzioni non supportate",
                "- non inventare dati",
                "- mantenere coerenza con la memoria evolutiva",
                "- dichiarare quando un dato non è disponibile.",
                ""
            ])
        
        # Istruzioni operative potenziate
        if structured_reasoning_active:
            # Reasoning Strutturato ha priorità - struttura obbligatoria
            prompt_parts.extend([
                "[ISTRUZIONI OPERATIVE]",
                "Se l'utente chiede reasoning o analisi dettagliata, DEVI produrre le 4 sezioni del Reasoning Strutturato:",
                "",
                "1. INTERPRETAZIONE DELLA DOMANDA (obbligatoria)",
                "2. DATI RILEVANTI TROVATI (obbligatoria)",
                "3. DECISIONE LOGICA (obbligatoria)",
                "4. RISPOSTA FINALE (obbligatoria)",
                "",
                "REGOLE STRETTE:",
                "- NON mischiare le sezioni",
                "- NON saltare nessuna sezione",
                "- NON rispondere in forma narrativa libera",
                "- Ogni sezione deve essere chiaramente identificata con il suo titolo",
                "- Mantieni coerenza tra le sezioni",
                "",
                "In Reasoning Strutturato, il modello deve:",
                "- essere trasparente",
                "- essere rigoroso",
                "- non saltare passaggi",
                "- non fare assunzioni non supportate",
                "- non inventare dati",
                "- mantenere coerenza con la memoria evolutiva",
                "- dichiarare quando un dato non è disponibile",
                "",
                "Priorità nella risposta:",
                "1. Dai priorità ai dati più rilevanti (Rilevanza: alta > media > bassa)",
                "2. Se la risposta si basa su memoria storica, indica chiaramente che stai usando informazioni da interazioni precedenti",
                "3. Non inventare tabelle o campi che non compaiono nel contesto",
                "4. Se il contesto indica 'Rilevanza: alta', usa quei dati come fonte primaria",
                "5. Mantieni coerenza con le risposte precedenti quando appropriato",
                "6. Se il contesto è limitato, indica chiaramente i limiti nella tua risposta"
            ])
        elif ocular_mode_active:
            prompt_parts.extend([
                "[ISTRUZIONI OPERATIVE]",
                "In Modalità Oculare, il motore neurale deve:",
                "",
                "- essere più vigile",
                "- essere più rigoroso",
                "- essere più coerente",
                "- essere più esplicito nel reasoning",
                "- non saltare passaggi logici",
                "- non dare nulla per scontato",
                "- non inventare dati",
                "- non ignorare dettagli della domanda",
                "",
                "Struttura la risposta così:",
                "",
                "[INTERPRETAZIONE DELLA DOMANDA]",
                "Spiega come hai interpretato la domanda, quali entità hai identificato, quali ambiguità hai risolto.",
                "",
                "[DATI RILEVANTI TROVATI]",
                "Elenca i dati trovati nel database e nella memoria, indicando la rilevanza di ciascuno.",
                "",
                "[CONFRONTO CON MEMORIA STORICA]",
                "Confronta la domanda con interazioni precedenti, segnala somiglianze e differenze.",
                "",
                "[ANALISI E DECISIONE]",
                "Spiega il ragionamento utilizzato per arrivare alla risposta, i passaggi logici, le considerazioni fatte.",
                "",
                "[RISPOSTA FINALE]",
                "Fornisci la risposta finale in modo chiaro, strutturato e completo.",
                "",
                "Priorità nella risposta:",
                "1. Dai priorità ai dati più rilevanti (Rilevanza: alta > media > bassa)",
                "2. Se la risposta si basa su memoria storica, indica chiaramente che stai usando informazioni da interazioni precedenti",
                "3. Non inventare tabelle o campi che non compaiono nel contesto",
                "4. Se il contesto indica 'Rilevanza: alta', usa quei dati come fonte primaria",
                "5. Mantieni coerenza con le risposte precedenti quando appropriato",
                "6. Se il contesto è limitato, indica chiaramente i limiti nella tua risposta"
            ])
        else:
            prompt_parts.extend([
                "[ISTRUZIONI OPERATIVE]",
                "Rispondi in modo tecnico, professionale, coerente con il dominio NStone.",
                "",
                "Priorità nella risposta:",
                "1. Dai priorità ai dati più rilevanti (Rilevanza: alta > media > bassa)",
                "2. Se la risposta si basa su memoria storica, indica chiaramente che stai usando informazioni da interazioni precedenti",
                "3. Non inventare tabelle o campi che non compaiono nel contesto",
                "4. Se il contesto indica 'Rilevanza: alta', usa quei dati come fonte primaria",
                "5. Mantieni coerenza con le risposte precedenti quando appropriato",
                "6. Se il contesto è limitato, indica chiaramente i limiti nella tua risposta",
                "",
                "Se l'utente richiede attenzione aumentata o usa termini come 'oculare', attiva automaticamente la Modalità Oculare.",
                "Se l'utente richiede reasoning o usa termini come 'spiega', 'mostra il ragionamento', attiva automaticamente il Reasoning Strutturato (Livello 2)."
            ])
        
        prompt = "\n".join(prompt_parts)
        
        # Step 3: Genera risposta con Gemini
        try:
            answer = self.gemini_service.send_message(
                prompt,
                system_instruction=self.GEMINI_PERSONALITY_PROFILE,
                business_context="offerte",
            )
            
            # Salva risposta
            self._last_answer = answer
            
            display_answer, embedded_reasoning = self._split_structured_answer(answer)

            result = {
                "context": context,
                "answer": display_answer,
                "reasoning": embedded_reasoning,
            }

            # Seconda chiamata LLM solo se serve reasoning aggiuntivo (evita doppio Ollama)
            if include_reasoning and not structured_reasoning_active:
                if answer.strip().startswith("Errore:"):
                    result["reasoning"] = ""
                else:
                    reasoning = self.explain_reasoning()
                    result["reasoning"] = reasoning
                    self._last_reasoning = reasoning
            elif embedded_reasoning:
                self._last_reasoning = embedded_reasoning
            
            # Step 4: Salva automaticamente l'interazione nella memoria
            self.save_interaction(
                question=question,
                context=context,
                answer=answer,
                reasoning=result.get("reasoning", ""),
                tags=""  # Tags possono essere aggiunti in futuro
            )
            
            return result
            
        except Exception as e:
            error_msg = str(e)[:200]
            self._last_answer = f"Errore nella generazione della risposta: {error_msg}"
            
            # Salva anche gli errori (utile per debugging)
            self.save_interaction(
                question=question,
                context=context,
                answer=self._last_answer,
                reasoning="",
                tags="error"
            )
            
            return {
                "context": context,
                "answer": self._last_answer,
                "reasoning": ""
            }

    def _generate_operational_answer(
        self, question: str, include_reasoning: bool = False
    ) -> Dict[str, str]:
        """Risposta rapida per Gestione macchine: solo contesto PLC, modello Ollama fast."""
        self._last_question = question
        self._last_context = "(modalità operativa — contesto macchina nel prompt)"
        self._last_reasoning = ""

        prompt = (
            "Domanda operatore in reparto:\n\n"
            f"{question.strip()}\n\n"
            "Usa il formato STATO / ANOMALIA / AZIONE."
        )

        try:
            from llm.llm_contexts import build_produzione_operator_prompt

            prompt = build_produzione_operator_prompt(
                question, include_reasoning=include_reasoning
            )

            answer = self.gemini_service.send_message(
                prompt,
                business_context="produzione",
            )

            reasoning = ""
            if include_reasoning:
                final_answer, reasoning = self._split_structured_answer(answer)
                if reasoning:
                    answer = final_answer

            self._last_answer = answer
            self._last_reasoning = reasoning
            self.save_interaction(
                question=question,
                context=self._last_context,
                answer=answer,
                reasoning=reasoning,
                tags="operational",
            )
            return {
                "context": self._last_context,
                "answer": answer,
                "reasoning": reasoning,
            }
        except Exception as e:
            err = f"Errore nella generazione della risposta: {str(e)[:200]}"
            self._last_answer = err
            return {"context": self._last_context, "answer": err, "reasoning": ""}
    
    def explain_reasoning(self) -> str:
        """
        Restituisce il reasoning dell'ultima risposta generata.
        Non mostrato automaticamente, solo quando richiesto dall'utente.
        
        Returns:
            Stringa con reasoning dell'ultima risposta
        """
        if not self._last_question or not self._last_answer:
            return "Reasoning non disponibile. Genera prima una risposta."
        
        # Genera reasoning usando Gemini
        try:
            reasoning_prompt = f"""Spiega il processo di reasoning utilizzato per rispondere a questa domanda.

**Domanda:**
{self._last_question}

**Contesto recuperato:**
{self._last_context[:500] if len(self._last_context) > 500 else self._last_context}

**Risposta generata:**
{self._last_answer[:500] if len(self._last_answer) > 500 else self._last_answer}

Fornisci un reasoning dettagliato del processo di ragionamento:
1. Come è stato interpretato il contesto recuperato
2. Quali informazioni sono state utilizzate
3. Come è stata costruita la risposta
4. Quali limiti o incertezze sono presenti

Mantieni un tono tecnico e professionale."""
            
            reasoning = self.gemini_service.send_message(
                reasoning_prompt,
                system_instruction=self.GEMINI_PERSONALITY_PROFILE
            )
            
            self._last_reasoning = reasoning
            return reasoning
            
        except Exception as e:
            return f"Errore nella generazione del reasoning: {str(e)[:200]}"
