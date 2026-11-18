"""
Session Manager per gestione sessioni di analisi
Crea sessioni con timestamp e gestisce il salvataggio delle foto
"""
import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional


def create_simple_session(photo_paths: List[str]) -> Optional[Path]:
    """
    Crea una nuova sessione di analisi con timestamp.
    
    Args:
        photo_paths: Lista di percorsi alle foto da copiare nella sessione
        
    Returns:
        Path della cartella sessione creata, o None in caso di errore
    """
    try:
        # Crea la cartella base analysis_sessions se non esiste
        base_dir = Path(__file__).resolve().parents[1] / "analysis_sessions"
        base_dir.mkdir(exist_ok=True)
        
        # Genera un timestamp univoco per la sessione
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"session_{timestamp}"
        session_dir = base_dir / session_id
        session_dir.mkdir(exist_ok=True)
        
        # Copia le foto nella cartella sessione
        photo_filenames = []
        for i, photo_path in enumerate(photo_paths, start=1):
            if not photo_path or not os.path.exists(photo_path):
                continue
            
            source_path = Path(photo_path)
            # Genera nome file: photo_1.jpg, photo_2.jpg, ecc.
            ext = source_path.suffix or ".jpg"
            dest_filename = f"photo_{i}{ext}"
            dest_path = session_dir / dest_filename
            
            # Copia il file
            shutil.copy2(source_path, dest_path)
            photo_filenames.append(dest_filename)
        
        if not photo_filenames:
            # Nessuna foto valida, elimina la sessione
            session_dir.rmdir()
            return None
        
        # Crea il file request.json
        request_data = {
            "session_id": session_id,
            "photos": photo_filenames
        }
        
        request_file = session_dir / "request.json"
        with open(request_file, 'w', encoding='utf-8') as f:
            json.dump(request_data, f, indent=2, ensure_ascii=False)
        
        return session_dir
        
    except Exception as e:
        print(f"Errore nella creazione della sessione: {e}")
        return None




