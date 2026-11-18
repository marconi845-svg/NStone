from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict

app = FastAPI(title="WordPress Form Backend")

# CORS configuration - allows all origins (necessary for ngrok and WordPress.com)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for ngrok compatibility
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage in memoria per le richieste
richieste_storage: List[Dict] = []
contatore_richieste = 0


class FormData(BaseModel):
    nome: str
    email: str
    messaggio: str


@app.post("/api/form")
async def receive_form(data: FormData):
    """Endpoint per ricevere dati dal form WordPress e salvarli"""
    global contatore_richieste
    
    # Incrementa il contatore
    contatore_richieste += 1
    
    # Crea la richiesta con data/ora in formato ISO
    richiesta = {
        "numero": contatore_richieste,
        "data_ora": datetime.now().isoformat(sep=' ', timespec='seconds'),
        "nome": data.nome,
        "email": data.email,
        "messaggio": data.messaggio,
        "stato": "NUOVA"
    }
    
    # Salva nella lista in memoria
    richieste_storage.append(richiesta)
    
    # Stampa i dati ricevuti nella console
    print("=" * 50)
    print("NUOVA RICHIESTA RICEVUTA:")
    print(f"Numero: {richiesta['numero']}")
    print(f"Data/Ora: {richiesta['data_ora']}")
    print(f"Nome: {data.nome}")
    print(f"Email: {data.email}")
    print(f"Messaggio: {data.messaggio}")
    print(f"Stato: {richiesta['stato']}")
    print("=" * 50)
    
    # Ritorna risposta semplice
    return {"message": "Richiesta ricevuta!", "numero": contatore_richieste}


@app.get("/api/richieste")
async def get_richieste():
    """Endpoint per ottenere tutte le richieste salvate"""
    return {
        "totale": len(richieste_storage),
        "richieste": richieste_storage
    }


@app.get("/")
async def root():
    """Endpoint di test"""
    return {"status": "Server attivo", "message": "Il server è in esecuzione"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

