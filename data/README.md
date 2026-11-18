# Data directory

Runtime SQLite databases (`*.db`) are **not** versioned (see `.gitignore`).

- Schema + seed: `../database/` (SQL only — `python database/init_db.py`)
- Knowledge samples for RAG demos: `knowledge/`

Never commit real customer email, orders, or credentials into this folder.
