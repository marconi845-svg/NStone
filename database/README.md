# Database (SQL only)

Single source of truth for the NStone SQLite schema. No CSV migration path.

| File | Role |
|------|------|
| `schema.sql` | Core tables (stock, quotations, orders, production, …) |
| `orders_schema.sql` | Orders / email / invoice extensions |
| `seed.sql` | Demo rows for local development |
| `init_db.py` | Creates `data/nstonellm.db` from the SQL files above |

## Initialize

```bash
python database/init_db.py
```

Creates (or recreates) `data/nstonellm.db`. Runtime `*.db` files stay gitignored.

```bash
# schema only (empty tables)
python database/init_db.py --no-seed

# custom path
python database/init_db.py --db path/to/nstonellm.db
```

## Notes

- Canonical runtime DB path: `data/nstonellm.db`
- Knowledge / RAG samples live under `data/knowledge/` (not SQL)
- Do not commit real customer data into seed or any `*.db`
