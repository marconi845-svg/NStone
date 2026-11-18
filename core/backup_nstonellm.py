"""
Script per backup completo della cartella NSTONELLM
"""
import os
import shutil
import time
from pathlib import Path
from datetime import datetime

def get_backup_path(base_path, backup_name):
    """Trova un percorso di backup disponibile, aggiungendo suffisso numerico se necessario"""
    backup_path = base_path / backup_name
    
    if not backup_path.exists():
        return backup_path
    
    counter = 2
    while True:
        new_name = f"{backup_name} ({counter})"
        backup_path = base_path / new_name
        if not backup_path.exists():
            return backup_path
        counter += 1

def copy_directory(src, dst, file_count):
    """Copia ricorsivamente una directory e conta i file"""
    try:
        os.makedirs(dst, exist_ok=True)
        
        for item in os.listdir(src):
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dst, item)
            
            if os.path.isdir(src_path):
                file_count = copy_directory(src_path, dst_path, file_count)
            else:
                try:
                    shutil.copy2(src_path, dst_path)
                    file_count += 1
                except Exception as e:
                    print(f"Errore durante la copia di {src_path}: {e}")
        
        return file_count
    except Exception as e:
        print(f"Errore durante la copia della directory {src}: {e}")
        return file_count

def main():
    """Funzione principale per eseguire il backup"""
    source_dir = Path(r"C:\Users\marco\Desktop\NSTONELLM 0.0.12")
    backup_name = "backup nstonell"
    base_path = Path(r"C:\Users\marco\Desktop")
    
    print("=" * 60)
    print("BACKUP NSTONELLM")
    print("=" * 60)
    print(f"\nPercorso sorgente: {source_dir}")
    
    if not source_dir.exists():
        print(f"ERRORE: La cartella sorgente non esiste: {source_dir}")
        return
    
    if not source_dir.is_dir():
        print(f"ERRORE: Il percorso specificato non è una cartella: {source_dir}")
        return
    
    backup_path = get_backup_path(base_path, backup_name)
    print(f"Percorso destinazione: {backup_path}")
    
    if backup_path.exists():
        print(f"ERRORE: Impossibile creare la cartella di backup: {backup_path}")
        return
    
    try:
        start_time = time.time()
        file_count = 0
        
        print("\nAvvio backup...")
        file_count = copy_directory(str(source_dir), str(backup_path), file_count)
        
        elapsed_time = time.time() - start_time
        
        print("\n" + "=" * 60)
        print("BACKUP COMPLETATO")
        print("=" * 60)
        print(f"Percorso sorgente: {source_dir}")
        print(f"Percorso destinazione: {backup_path}")
        print(f"File copiati: {file_count}")
        print(f"Tempo impiegato: {elapsed_time:.2f} secondi")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nERRORE CRITICO durante il backup: {e}")
        if backup_path.exists():
            try:
                shutil.rmtree(backup_path)
                print(f"Cartella di backup incompleta rimossa: {backup_path}")
            except:
                pass

if __name__ == "__main__":
    main()

