# FastAPI Backend - WordPress Form

Backend FastAPI per gestire richieste da form HTML (WordPress, GitHub Pages, etc.).

## Struttura Progetto

```
fastapi_backend/
├── main.py              # Applicazione FastAPI principale
├── requirements.txt     # Dipendenze Python
├── README.md           # Questa documentazione
└── data/
    └── messages.json   # File JSON con i messaggi salvati
```

## Installazione

```bash
pip install -r requirements.txt
```

## Avvio Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Oppure:

```bash
python main.py
```

## Endpoint

### POST `/api/form`
Riceve dati dal form in formato `application/x-www-form-urlencoded`.

**Parametri Form:**
- `nome` (string, obbligatorio)
- `email` (string, obbligatorio)
- `messaggio` (string, obbligatorio)

**Risposta:**
```json
{
  "success": true,
  "message": "Richiesta ricevuta!",
  "id": "uuid-generato",
  "timestamp": "2025-12-27T10:30:45.123456"
}
```

### GET `/api/messages`
Restituisce tutti i messaggi salvati.

**Risposta:**
```json
{
  "success": true,
  "total": 2,
  "messages": [
    {
      "id": "uuid",
      "timestamp": "2025-12-27T10:30:45.123456",
      "nome": "Mario Rossi",
      "email": "mario@example.com",
      "messaggio": "Il mio messaggio",
      "stato": "NUOVA"
    }
  ]
}
```

### GET `/`
Endpoint di test per verificare che il server sia attivo.

### GET `/health`
Health check endpoint.

## Caratteristiche

- ✅ Accetta dati in formato Form (application/x-www-form-urlencoded)
- ✅ Genera UUID univoci per ogni messaggio
- ✅ Timestamp ISO 8601
- ✅ Salvataggio persistente in JSON file
- ✅ Logging completo
- ✅ CORS configurato per GitHub Pages e WordPress
- ✅ Gestione errori robusta
- ✅ Funzioni helper per lettura/scrittura JSON

## Esposizione con ngrok

```bash
ngrok http 8000
```

## Note

- I messaggi vengono salvati in `data/messages.json`
- Il file JSON viene creato automaticamente se non esiste
- Il formato timestamp è ISO 8601 standard
- Il CORS è configurato per accettare richieste da qualsiasi origine



