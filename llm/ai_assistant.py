"""
Modulo AI Assistant per l'integrazione con Gemini e catalogo prodotti.
"""
from typing import Optional
from llm.gemini_service import GeminiService
from modules.catalog_db import load_catalog_products, get_catalog_info

# Dizionario di attributi riconosciuti
ATTRIBUTES = {
    "spessore": "Thickness",
    "thickness": "Thickness",
    "finitura": "Finish",
    "finish": "Finish",
    "misure": "Dimensions",
    "dimensioni": "Dimensions",
    "dimension": "Dimensions",
    "prezzo": "Price",
    "price": "Price",
    "€/m2": "Price",
    "€/m²": "Price",
    "euro": "Price",
    "costo": "Price",
    "cost": "Price"
}

# Dizionario di traduzioni automatiche
TRANSLATE = {
    "Polished": "Lucidato",
    "Honed": "Levigato",
    "White": "Bianco",
    "Black": "Nero",
    "Grey": "Grigio",
    "Red": "Rosso",
    "Beige": "Beige"
}


class AIAssistant:
    """
    Classe per gestire le richieste AI con catalogo prodotti (SQLite).
    """
    
    def __init__(self, csv_path: Optional[str] = None, api_key: Optional[str] = None):
        """
        Inizializza l'AI Assistant
        
        Args:
            csv_path: Deprecato, ignorato. Il catalogo usa modules.catalog_db.
            api_key: Chiave API per Gemini. Se None, viene caricata automaticamente.
        """
        _ = csv_path  # compatibilità chiamate esistenti
        self.gemini_service = GeminiService(api_key=api_key)
    
    def _load_catalog(self):
        return load_catalog_products()
    
    def rispondi(self, domanda: str) -> str:
        """
        Risponde a una domanda dell'utente, integrando dati CSV quando necessario
        
        Args:
            domanda: La domanda dell'utente
            
        Returns:
            La risposta generata da Gemini
        """
        # Normalizza la domanda in lowercase
        domanda_lower = domanda.lower()
        
        # Verifica se la domanda riguarda magazzino/stock/inventario
        has_stock_keywords = any(keyword in domanda_lower 
                                 for keyword in ["magazzino", "stock", "inventario", "disponibile", "quantità", "quante", "quanto", "how many"])
        
        # Verifica se la domanda riguarda altri attributi (spessore, finitura, dimensioni, prezzo)
        attribute_requested = None
        for key, column in ATTRIBUTES.items():
            if key in domanda_lower:
                attribute_requested = column
                break
        
        # Se non ci sono keyword di stock né di attributi, usa direttamente Gemini
        if not has_stock_keywords and not attribute_requested:
            return self.gemini_service.send_message(domanda, business_context="offerte")
        
        try:
            data = self._load_catalog()
            
            # Cerca prima un materiale specifico nella domanda
            materiale_trovato = None
            best_match_length = 0
            
            # Lista di keyword specifiche per materiali
            specific_keywords = ["carrara", "calacatta", "marquina", "verona", "statuario", "bardiglio", "botticino", "travertine", "granite", "quartz"]
            
            for row in data:
                name = row.get("Name", "").strip()
                if not name:
                    continue
                
                # Normalizza il nome per il matching (lowercase, rimuovi spazi extra)
                name_normalized = " ".join(name.lower().split())
                name_words = name_normalized.split()
                
                # Match esatto: il nome completo è nella domanda
                if name_normalized in domanda_lower:
                    materiale_trovato = row
                    break
                
                # Match parziale: cerca se tutte le parole significative del nome sono nella domanda
                # Esclude parole troppo corte o comuni, ma include "carrara", "calacatta", ecc.
                # Per "Bianco Carrara CD", le parole significative sono "carrara" (escludiamo "bianco" e "cd")
                significant_words = [w for w in name_words if len(w) > 3 and w not in ["white", "black", "grey", "beige", "red", "bianco", "nero", "grigio", "classic", "cd", "gold", "imperlae"]]
                
                # Se non ci sono parole significative dopo il filtro, prova con tutte le parole lunghe
                if not significant_words:
                    significant_words = [w for w in name_words if len(w) > 4]
                
                if significant_words:
                    # Controlla se tutte le parole significative sono nella domanda
                    all_words_match = all(word in domanda_lower for word in significant_words)
                    if all_words_match:
                        # Preferisci il match più lungo (più specifico)
                        match_length = len(name_normalized)
                        if match_length > best_match_length:
                            materiale_trovato = row
                            best_match_length = match_length
            
            # Se non abbiamo trovato un match, prova con keyword specifiche
            if not materiale_trovato:
                for row in data:
                    name = row.get("Name", "").strip()
                    if not name:
                        continue
                    
                    name_normalized = " ".join(name.lower().split())
                    
                    # Cerca keyword specifiche nel nome e nella domanda
                    for keyword in specific_keywords:
                        if keyword in name_normalized and keyword in domanda_lower:
                            materiale_trovato = row
                            break
                    
                    if materiale_trovato:
                        break
            
            # Se è stata trovata una domanda specifica su un materiale
            if materiale_trovato:
                materiale_name = materiale_trovato.get("Name", "").strip()
                
                # Se è stata richiesta un'attributo specifico (non stock)
                if attribute_requested and attribute_requested != "Stock":
                    try:
                        value = materiale_trovato.get(attribute_requested, "").strip()
                        
                        if not value:
                            # Se l'attributo non è presente, fallback a Gemini
                            return self.gemini_service.send_message(domanda, business_context="offerte")
                        
                        # Traduzione automatica se presente
                        if value in TRANSLATE:
                            value_translated = TRANSLATE[value]
                        else:
                            value_translated = value
                        
                        # Costruisce risposte personalizzate in italiano
                        if attribute_requested == "Thickness":
                            risposta = f"Lo spessore di {materiale_name} è {value_translated} cm."
                        elif attribute_requested == "Finish":
                            risposta = f"La finitura di {materiale_name} è {value_translated}."
                        elif attribute_requested == "Dimensions":
                            risposta = f"Le dimensioni di {materiale_name} sono {value_translated}."
                        elif attribute_requested == "Price":
                            risposta = f"Il prezzo di {materiale_name} è {value_translated} €/m²."
                        else:
                            risposta = f"{attribute_requested} di {materiale_name}: {value_translated}"
                        
                        # Invia il prompt a Gemini per una risposta più naturale
                        full_prompt = f"{risposta}\n\nL'utente ha chiesto: \"{domanda}\"\n\nRispondi in modo naturale e informativo in italiano, includendo il dato richiesto."
                        
                        response = self.gemini_service.send_message(
                            full_prompt, business_context="offerte"
                        )
                        return response
                        
                    except Exception as e:
                        print(f"Errore durante l'estrazione dell'attributo: {str(e)}")
                        # Fallback a Gemini
                        return self.gemini_service.send_message(domanda, business_context="offerte")
                
                # Se è stata richiesta la quantità/stock
                if has_stock_keywords:
                    try:
                        stock_value = materiale_trovato.get("Stock", "0").strip()
                        total_stock = int(stock_value) if stock_value else 0
                    except (ValueError, TypeError):
                        total_stock = 0
                    
                    # Costruisce il prompt con i dati del materiale specifico
                    prompt = f"In magazzino ci sono {total_stock} lastre di {materiale_name}."
                    
                    # Invia il prompt a Gemini per una risposta più naturale
                    full_prompt = f"{prompt}\n\nL'utente ha chiesto: \"{domanda}\"\n\nRispondi in modo naturale e informativo, includendo il dato del magazzino."
                    
                    response = self.gemini_service.send_message(
                        full_prompt, business_context="offerte"
                    )
                    return response
            
            # Altrimenti, controlla se è una domanda generica su marmo
            if ("marmo" in domanda_lower or "marble" in domanda_lower):
                # Filtra le righe dove Type == "Marble"
                marble_rows = [row for row in data if row.get("Type", "").strip().lower() == "marble"]
                
                # Somma la colonna Stock
                total_stock = 0
                for row in marble_rows:
                    try:
                        stock_value = row.get("Stock", "0").strip()
                        if stock_value:
                            total_stock += int(stock_value)
                    except (ValueError, TypeError):
                        # Ignora valori non numerici
                        continue
                
                # Costruisce il prompt con i dati
                prompt = f"In magazzino ci sono {total_stock} lastre di marmo."
                
                # Invia il prompt a Gemini per una risposta più naturale
                full_prompt = f"{prompt}\n\nL'utente ha chiesto: \"{domanda}\"\n\nRispondi in modo naturale e informativo, includendo il dato del magazzino."
                
                response = self.gemini_service.send_message(
                    full_prompt, business_context="offerte"
                )
                return response
            
            # Se nessun materiale è riconosciuto, fallback a Gemini
            return self.gemini_service.send_message(domanda, business_context="offerte")
                
        except FileNotFoundError:
            info = get_catalog_info()
            detail = info.get("error", "catalogo non trovato")
            return (
                "Errore: catalogo prodotti non disponibile. "
                f"{detail} — verifica data/nstonellm.db (python database/init_db.py)."
            )
        except Exception as e:
            # In caso di errore, fallback a Gemini con la domanda originale
            print(f"Errore durante l'elaborazione della richiesta: {str(e)}")
            return self.gemini_service.send_message(domanda, business_context="offerte")

