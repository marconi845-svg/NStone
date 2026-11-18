use rusqlite::{Connection, Result};

#[test]
fn test_database_basic() -> Result<()> {
    // 1. Apri il database
    let conn = Connection::open("../data/nstonellm.db")?;

    // 2. Verifica che il DB risponda
    let _: i64 = conn.query_row("SELECT 1;", [], |row| row.get(0))?;

    // 3. Verifica che la tabella esista
    let count: i64 = conn.query_row(
        "SELECT COUNT(*) FROM online_stock;",
        [],
        |row| row.get(0),
    )?;
    println!("Righe in online_stock: {}", count);

    // 4. Leggi una riga reale
    let mut stmt = conn.prepare("SELECT id, name FROM online_stock LIMIT 1;")?;
    let mut rows = stmt.query([])?;

    if let Some(row) = rows.next()? {
        let id: i64 = row.get(0)?;
        let name: String = row.get(1)?;
        println!("Record trovato: {} - {}", id, name);
    } else {
        panic!("Nessun record trovato in online_stock");
    }

    Ok(())
}





