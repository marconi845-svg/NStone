"""
FastAPI Backend per WordPress Form
Gestisce richieste da form HTML e salva i messaggi in JSON
"""

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import List, Dict, Optional
import json
import uuid
import sys
from pathlib import Path
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

# Root progetto in sys.path prima di import assoluti (uvicorn main:app da fastapi_backend/)
root_dir = Path(__file__).resolve().parent.parent
_root = str(root_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

from fastapi_backend.observability import setup_observability, current_trace_id

try:
    from modules.gemini_module import generate_reply_for_client, GeminiReplyError
except ImportError:
    generate_reply_for_client = None
    GeminiReplyError = None  # type: ignore

try:
    from modules.email_service import send_response_email, send_threaded_email
except ImportError:
    send_response_email = None
    send_threaded_email = None

try:
    from modules.quotation_auto_pipeline import (
        elaborate_quotation_request,
        maybe_auto_elaborate_new_request,
    )
except ImportError:
    elaborate_quotation_request = None  # type: ignore
    maybe_auto_elaborate_new_request = None  # type: ignore

try:
    from modules.incoming_requests_db import (
        delete_incoming_request,
        ensure_incoming_request_table,
        get_incoming_request,
        insert_incoming_request,
        list_incoming_requests,
        update_incoming_request,
    )
except ImportError:
    delete_incoming_request = None  # type: ignore
    ensure_incoming_request_table = None  # type: ignore
    get_incoming_request = None  # type: ignore
    insert_incoming_request = None  # type: ignore
    list_incoming_requests = None  # type: ignore
    update_incoming_request = None  # type: ignore

# Percorsi file legacy JSON
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MESSAGES_FILE = DATA_DIR / "messages.json"

# Assicura che la cartella data esista
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="WordPress Form Backend", version="1.0.0")
logger = setup_observability(app, service="fastapi-backend", env="local")

try:
    from fastapi_backend.logistics_routes import router as logistics_router

    app.include_router(logistics_router)
except ImportError:
    try:
        from logistics_routes import router as logistics_router

        app.include_router(logistics_router)
    except ImportError:
        logger.warning("Router logistica non caricato")

# CORS configuration - permette richieste da GitHub Pages e WordPress
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permette tutte le origini (GitHub Pages, WordPress, ngrok)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    clear_contextvars()
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    trace_id = current_trace_id()
    bind_contextvars(
        request_id=request_id,
        trace_id=trace_id,
        path=request.url.path,
        method=request.method,
    )
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


def read_messages() -> List[Dict]:
    """Legge richieste da SQLite (import legacy JSON al primo avvio)."""
    if list_incoming_requests is None:
        return []
    try:
        ensure_incoming_request_table()
        return list_incoming_requests()
    except Exception as e:
        logger.error("Errore lettura incoming_request", error=str(e))
        return []


def write_messages(messages: List[Dict]) -> bool:
    """Sincronizza l'elenco completo su SQLite (compat legacy)."""
    if list_incoming_requests is None:
        return False
    try:
        from modules.incoming_requests_db import replace_all_incoming_requests

        ensure_incoming_request_table()
        return replace_all_incoming_requests(messages)
    except Exception as e:
        logger.error("Errore scrittura incoming_request", error=str(e))
        return False


def _background_auto_elaborate(request_id: str) -> None:
    if maybe_auto_elaborate_new_request is None:
        return
    try:
        maybe_auto_elaborate_new_request(request_id)
    except Exception as exc:
        logger.error("Auto-elaborazione preventivo fallita", request_id=request_id, error=str(exc))


@app.post("/api/form")
async def receive_form(
    background_tasks: BackgroundTasks,
    nome: str = Form(...),
    email: str = Form(...),
    messaggio: str = Form(...),
):
    """
    Endpoint per ricevere dati dal form WordPress.
    Accetta dati in formato Form (application/x-www-form-urlencoded).
    """
    try:
        # Genera UUID univoco
        message_id = str(uuid.uuid4())
        
        # Timestamp ISO 8601
        timestamp = datetime.now().isoformat()
        
        # Crea il messaggio
        new_message = {
            "id": message_id,
            "timestamp": timestamp,
            "nome": nome,
            "email": email,
            "messaggio": messaggio,
            "stato": "NUOVA"
        }
        
        # Leggi messaggi esistenti (no-op check via insert)
        messages = read_messages()
        
        # Aggiungi nuovo messaggio in SQLite
        if insert_incoming_request is None or not insert_incoming_request(new_message).get("ok"):
            raise HTTPException(status_code=500, detail="Errore nel salvataggio del messaggio")
        
        messages.append(new_message)
        logger.info(
            "Nuovo messaggio ricevuto",
            message_id=message_id,
            nome=nome,
            email=email,
            stato="NUOVA",
        )

        background_tasks.add_task(_background_auto_elaborate, message_id)

        return {
            "success": True,
            "message": "Richiesta ricevuta!",
            "id": message_id,
            "timestamp": timestamp
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Errore nell'elaborazione della richiesta form", error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@app.get("/api/messages")
async def get_messages():
    """
    Endpoint per ottenere tutti i messaggi salvati.
    """
    try:
        messages = read_messages()
        logger.info("Recuperati messaggi", total=len(messages))
        return {
            "success": True,
            "total": len(messages),
            "messages": messages
        }
    except Exception as e:
        logger.error("Errore nel recupero dei messaggi", error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@app.get("/")
async def root():
    """
    Endpoint di test per verificare che il server sia attivo.
    """
    return {
        "status": "active",
        "message": "Server FastAPI attivo",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/form": "Riceve dati dal form",
            "GET /api/messages": "Ottiene tutti i messaggi",
            "GET /api/get_request": "Ottiene dettagli di una singola richiesta",
            "DELETE /api/delete_request": "Elimina una richiesta",
            "POST /api/elabora": "Elabora una richiesta con Gemini",
            "POST /api/logistics/scan": "Registra scan GPS materiale",
            "GET /api/logistics/positions": "Ultima posizione per blocco (mappa)",
        }
    }


@app.get("/health")
async def health_check():
    """
    Endpoint per health check.
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/get_request")
async def get_request(request_id: str = Query(..., description="ID della richiesta")):
    """
    Endpoint per ottenere i dettagli di una singola richiesta.
    """
    try:
        messages = read_messages()
        # Cerca la richiesta per ID
        for message in messages:
            if message.get("id") == request_id:
                logger.info("Richiesta recuperata", request_id=request_id)
                return {
                    "success": True,
                    "request": message
                }
        
        # Richiesta non trovata
        raise HTTPException(status_code=404, detail=f"Richiesta con ID {request_id} non trovata")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Errore nel recupero della richiesta", request_id=request_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@app.delete("/api/delete_request")
async def delete_request(request_id: str = Query(..., description="ID della richiesta da eliminare")):
    """
    Endpoint per eliminare una singola richiesta.
    """
    try:
        if delete_incoming_request is None:
            raise HTTPException(status_code=503, detail="Storage non disponibile")
        result = delete_incoming_request(request_id)
        if not result.get("ok"):
            raise HTTPException(
                status_code=404,
                detail=result.get("error", f"Richiesta con ID {request_id} non trovata"),
            )
        logger.info("Richiesta eliminata", request_id=request_id)
        return {
            "success": True,
            "message": f"Richiesta {request_id} eliminata con successo",
            "deleted_id": request_id,
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Errore nell'eliminazione della richiesta", request_id=request_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


@app.post("/api/elabora")
async def elabora_request(request_id: str = Query(..., description="ID della richiesta da elaborare")):
    """
    Endpoint per elaborare una richiesta con Gemini e generare una risposta.
    Invio email forzato (azione manuale da GUI).
    """
    try:
        if elaborate_quotation_request is None or generate_reply_for_client is None:
            raise HTTPException(status_code=503, detail="Modulo elaborazione non disponibile")

        if get_incoming_request is None or not get_incoming_request(request_id):
            raise HTTPException(status_code=404, detail=f"Richiesta con ID {request_id} non trovata")

        logger.info("Elaborazione manuale richiesta", request_id=request_id)
        result = elaborate_quotation_request(request_id, send_email=True)
        if not result.get("ok"):
            code = result.get("code", "")
            status = 503 if code == "missing_api_key" else 502
            raise HTTPException(
                status_code=status,
                detail=result.get("error", "Elaborazione fallita"),
            )

        logger.info(
            "Richiesta elaborata",
            request_id=request_id,
            email_sent=result.get("email_sent"),
        )
        return {
            "success": True,
            "request_id": request_id,
            "reply": result.get("reply", ""),
            "email_sent": bool(result.get("email_sent")),
            "email_error": result.get("email_error"),
            "timestamp": datetime.now().isoformat(),
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Errore nell'elaborazione della richiesta", request_id=request_id, error=str(e))
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Errore interno: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


