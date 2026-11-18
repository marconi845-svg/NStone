"""
Script interattivo per interrogare il database NSTONELLM usando Gemini AI
Permette di fare domande in linguaggio naturale sul database
"""
import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Aggiungi la root del progetto al path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from llm.gemini_service import GeminiService


class DatabaseQueryAssistant:
    """Assistente per interrogare il database usando Gemini AI"""
    
    def __init__(self, db_path: str = "../data/nstonellm.db"):
        """
        Inizializza l'assistente
        
        Args:
            db_path: Percorso al database SQLite
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            # Prova percorso assoluto
            abs_path = root_dir / "data" / "nstonellm.db"
            if abs_path.exists():
                self.db_path = abs_path
            else:
                raise FileNotFoundError(f"Database non trovato: {db_path}")
        
        self.gemini_service = GeminiService()
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Permette accesso per nome colonna
        
        # Schema del database per Gemini
        self.schema_info = """
Database NSTONELLM - Schema:

1. online_stock: Stock materiali disponibili
   - id, name, type, color, origin, finish, thickness, dimensions, stock, price

2. quotations: Preventivi per clienti
   - id, cliente, materiale, numero_blocco, misure_cm, quantita_mq, prezzo_mq, status, valid_until

3. orders: Ordini di produzione
   - id, order_id, client, product, machine, status, scheduled

4. collection: Trasporti e consegne
   - id, transporter, transport_id, status, progress, driver, eta, destination

5. production: Stato macchine di produzione
   - id, machine, status, current_work, completion, efficiency, consumption

6. administration: Fatture e amministrazione
   - id, invoice_number, client, amount_eur, date, status
"""
    
    def get_table_info(self) -> str:
        """Ottiene informazioni sulle tabelle e record"""
        cursor = self.conn.cursor()
        info = []
        
        tables = ['online_stock', 'quotations', 'orders', 'collection', 'production', 'administration']
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                info.append(f"{table}: {count} record")
            except:
                pass
        
        return "\n".join(info)
    
    def execute_query(self, query: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Esegue una query SQL e restituisce i risultati
        
        Args:
            query: Query SQL da eseguire
            
        Returns:
            Tupla (risultati, errore)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Converti in lista di dizionari
            results = []
            for row in rows:
                results.append(dict(row))
            
            return results, None
        except Exception as e:
            return [], str(e)
    
    def interpret_query(self, question: str) -> Optional[str]:
        """
        Usa Gemini per interpretare una domanda e generare una query SQL
        
        Args:
            question: Domanda in linguaggio naturale
            
        Returns:
            Query SQL generata, o None se errore
        """
        table_info = self.get_table_info()
        
        prompt = f"""Sei un assistente SQL esperto. Il tuo compito è convertire domande in linguaggio naturale in query SQL valide per SQLite.

{self.schema_info}

Stato attuale del database:
{table_info}

IMPORTANTE:
- Genera SOLO la query SQL, senza spiegazioni aggiuntive
- Usa nomi di tabelle e colonne esatti come nello schema
- Per "primi N" usa LIMIT N
- Per ordinamenti usa ORDER BY appropriato
- Non includere commenti o testo extra, solo SQL

Domanda dell'utente: {question}

Query SQL:"""
        
        try:
            response = self.gemini_service.send_message(prompt)
            # Pulisci la risposta (rimuovi markdown code blocks se presenti)
            query = response.strip()
            if query.startswith("```sql"):
                query = query[6:]
            if query.startswith("```"):
                query = query[3:]
            if query.endswith("```"):
                query = query[:-3]
            query = query.strip()
            
            # Verifica che sia una SELECT (sicurezza)
            if not query.upper().strip().startswith("SELECT"):
                return None
            
            return query
        except Exception as e:
            print(f"Errore nell'interpretazione: {e}")
            return None
    
    def format_results(self, results: List[Dict], limit: int = 50) -> str:
        """
        Formatta i risultati per la visualizzazione
        
        Args:
            results: Lista di dizionari con i risultati
            limit: Numero massimo di righe da mostrare
            
        Returns:
            Stringa formattata
        """
        if not results:
            return "Nessun risultato trovato."
        
        # Limita i risultati
        display_results = results[:limit]
        
        if len(results) > limit:
            header = f"Trovati {len(results)} risultati (mostrati i primi {limit}):\n"
        else:
            header = f"Trovati {len(results)} risultati:\n"
        
        # Ottieni le colonne
        if not display_results:
            return header + "Nessun risultato."
        
        columns = list(display_results[0].keys())
        
        # Calcola larghezza colonne
        col_widths = {}
        for col in columns:
            col_widths[col] = max(
                len(str(col)),
                max(len(str(row.get(col, ""))) for row in display_results)
            )
            col_widths[col] = min(col_widths[col], 30)  # Max 30 caratteri
        
        # Header
        header_line = " | ".join(str(col).ljust(col_widths[col]) for col in columns)
        separator = "-" * len(header_line)
        
        # Righe
        rows = []
        for row in display_results:
            row_line = " | ".join(
                str(row.get(col, "")).ljust(col_widths[col])[:30] 
                for col in columns
            )
            rows.append(row_line)
        
        return header + "\n" + separator + "\n" + header_line + "\n" + separator + "\n" + "\n".join(rows)
    
    def process_question(self, question: str) -> str:
        """
        Processa una domanda completa: interpreta, esegue query, formatta risultati
        
        Args:
            question: Domanda in linguaggio naturale
            
        Returns:
            Risposta formattata
        """
        # Interpreta la domanda
        query = self.interpret_query(question)
        
        if not query:
            return "Errore: Impossibile interpretare la domanda o generare una query SQL valida."
        
        print(f"\n[Query generata]: {query}\n")
        
        # Esegui la query
        results, error = self.execute_query(query)
        
        if error:
            return f"Errore nell'esecuzione della query: {error}"
        
        # Formatta i risultati
        return self.format_results(results)
    
    def close(self):
        """Chiude la connessione al database"""
        if self.conn:
            self.conn.close()


def main():
    """Funzione principale - loop interattivo"""
    print("=" * 60)
    print("NSTONELLM - Database Query Assistant con Gemini AI")
    print("=" * 60)
    print()
    
    try:
        assistant = DatabaseQueryAssistant()
        print(f"[OK] Database connesso: {assistant.db_path}")
        print(f"[OK] Gemini Service inizializzato")
        print()
        print("Puoi fare domande sul database in linguaggio naturale.")
        print("Esempi:")
        print("  - 'Mostrami i primi 5 prodotti in online_stock'")
        print("  - 'Quanti ordini ci sono?'")
        print("  - 'Mostrami i preventivi con status 1'")
        print("  - 'Quali materiali hanno stock maggiore di 100?'")
        print()
        print("Digita 'exit' o 'quit' per uscire")
        print("=" * 60)
        print()
        
        while True:
            try:
                question = input("\nDomanda: ").strip()
                
                if not question:
                    continue
                
                if question.lower() in ['exit', 'quit', 'esci', 'q']:
                    print("\nArrivederci!")
                    break
                
                # Processa la domanda
                response = assistant.process_question(question)
                print("\n" + response)
                
            except KeyboardInterrupt:
                print("\n\nInterrotto dall'utente. Arrivederci!")
                break
            except Exception as e:
                print(f"\nErrore: {e}")
                import traceback
                traceback.print_exc()
        
        assistant.close()
        
    except FileNotFoundError as e:
        print(f"Errore: {e}")
        print("Assicurati che il database esista in data/nstonellm.db")
        sys.exit(1)
    except Exception as e:
        print(f"Errore inizializzazione: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

