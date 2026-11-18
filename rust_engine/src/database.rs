/*
 * NSTONELLM - Modulo Database Rust
 * Gestione thread-safe del database SQLite con pattern Actor e Connection Pool
 * 
 * ARCHITETTURA:
 * - Python è l'unico writer (scritture serializzate)
 * - Rust è solo reader (letture parallele)
 * - WAL mode abilitato per massima concorrenza
 * - Due pattern disponibili:
 *   1. DatabaseActor: Pattern Actor con canali (singolo thread dedicato)
 *   2. DatabasePool: Pool r2d2 per accesso parallelo da più thread
 */

use rusqlite::{Connection, Result as SqliteResult, Row, params};
use r2d2::{Pool, PooledConnection, ManageConnection};
use serde::{Deserialize, Serialize};
use std::sync::mpsc;
use std::thread;
use std::path::Path;
use log::{info, warn, error};

// ============================================================================
// Strutture dati per le tabelle
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OnlineStock {
    pub id: i64,
    pub name: String,
    pub r#type: String,
    pub color: String,
    pub origin: String,
    pub finish: String,
    pub thickness: f64,
    pub dimensions: String,
    pub stock: f64,
    pub price: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Quotation {
    pub id: i64,
    pub cliente: String,
    pub materiale: String,
    pub numero_blocco: String,
    pub misure_cm: String,
    pub quantita_mq: f64,
    pub prezzo_mq: f64,
    pub status: i32,
    pub valid_until: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub id: i64,
    pub order_id: String,
    pub client: String,
    pub product: String,
    pub machine: String,
    pub status: String,
    pub scheduled: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Collection {
    pub id: i64,
    pub transporter: String,
    pub transport_id: String,
    pub status: String,
    pub progress: i32,
    pub driver: Option<String>,
    pub eta: Option<String>,
    pub destination: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Production {
    pub id: i64,
    pub machine: String,
    pub status: String,
    pub current_work: Option<String>,
    pub completion: i32,
    pub efficiency: f64,
    pub consumption: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Administration {
    pub id: i64,
    pub invoice_number: String,
    pub client: String,
    pub amount_eur: f64,
    pub date: String,
    pub status: String,
}

// ============================================================================
// Helper per mappare Row -> Struct
// ============================================================================

impl OnlineStock {
    fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(OnlineStock {
            id: row.get(0)?,
            name: row.get(1)?,
            r#type: row.get(2)?,
            color: row.get(3)?,
            origin: row.get(4)?,
            finish: row.get(5)?,
            thickness: row.get(6)?,
            dimensions: row.get(7)?,
            stock: row.get(8)?,
            price: row.get(9)?,
        })
    }
}

impl Quotation {
    fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Quotation {
            id: row.get(0)?,
            cliente: row.get(1)?,
            materiale: row.get(2)?,
            numero_blocco: row.get(3)?,
            misure_cm: row.get(4)?,
            quantita_mq: row.get(5)?,
            prezzo_mq: row.get(6)?,
            status: row.get(7)?,
            valid_until: row.get(8)?,
        })
    }
}

impl Order {
    fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Order {
            id: row.get(0)?,
            order_id: row.get(1)?,
            client: row.get(2)?,
            product: row.get(3)?,
            machine: row.get(4)?,
            status: row.get(5)?,
            scheduled: row.get(6)?,
        })
    }
}

impl Collection {
    fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Collection {
            id: row.get(0)?,
            transporter: row.get(1)?,
            transport_id: row.get(2)?,
            status: row.get(3)?,
            progress: row.get(4)?,
            driver: row.get(5)?,
            eta: row.get(6)?,
            destination: row.get(7)?,
        })
    }
}

impl Production {
    fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Production {
            id: row.get(0)?,
            machine: row.get(1)?,
            status: row.get(2)?,
            current_work: row.get(3)?,
            completion: row.get(4)?,
            efficiency: row.get(5)?,
            consumption: row.get(6)?,
        })
    }
}

impl Administration {
    fn from_row(row: &Row) -> SqliteResult<Self> {
        Ok(Administration {
            id: row.get(0)?,
            invoice_number: row.get(1)?,
            client: row.get(2)?,
            amount_eur: row.get(3)?,
            date: row.get(4)?,
            status: row.get(5)?,
        })
    }
}

// ============================================================================
// Funzioni helper per query (condivise tra Actor e Pool)
// ============================================================================

pub fn configure_connection(conn: &Connection) -> SqliteResult<()> {
    // Lista dei PRAGMA da applicare
    let pragmas = [
        "PRAGMA journal_mode = WAL;",
        "PRAGMA synchronous = NORMAL;",
        "PRAGMA foreign_keys = ON;",
        "PRAGMA cache_size = -20000;",
        "PRAGMA temp_store = MEMORY;",
        "PRAGMA mmap_size = 67108864;",
        "PRAGMA locking_mode = NORMAL;",
        "PRAGMA busy_timeout = 5000;",
        "PRAGMA page_size = 4096;",
        "PRAGMA auto_vacuum = NONE;",
    ];

    for p in pragmas {
        // prepare + query → funziona SEMPRE, anche se non ci sono righe
        let mut stmt = conn.prepare(p)?;
        let _ = stmt.query([])?; // ignoriamo il risultato
    }

    Ok(())
}

fn get_online_stock(conn: &Connection, limit: usize, offset: usize) -> SqliteResult<Vec<OnlineStock>> {
    let mut stmt = conn.prepare(
        "SELECT id, name, type, color, origin, finish, thickness, dimensions, stock, price 
         FROM online_stock 
         ORDER BY id 
         LIMIT ? OFFSET ?"
    )?;
    let rows = stmt.query_map(params![limit, offset], |row| OnlineStock::from_row(row))?;
    let mut results = Vec::new();
    for row in rows {
        results.push(row?);
    }
    Ok(results)
}

fn get_quotations(conn: &Connection, limit: usize, offset: usize) -> SqliteResult<Vec<Quotation>> {
    let mut stmt = conn.prepare(
        "SELECT id, cliente, materiale, numero_blocco, misure_cm, quantita_mq, prezzo_mq, status, valid_until 
         FROM quotations 
         ORDER BY id 
         LIMIT ? OFFSET ?"
    )?;
    let rows = stmt.query_map(params![limit, offset], |row| Quotation::from_row(row))?;
    let mut results = Vec::new();
    for row in rows {
        results.push(row?);
    }
    Ok(results)
}

fn get_orders(conn: &Connection, limit: usize, offset: usize) -> SqliteResult<Vec<Order>> {
    let mut stmt = conn.prepare(
        "SELECT id, order_id, client, product, machine, status, scheduled 
         FROM orders 
         ORDER BY id 
         LIMIT ? OFFSET ?"
    )?;
    let rows = stmt.query_map(params![limit, offset], |row| Order::from_row(row))?;
    let mut results = Vec::new();
    for row in rows {
        results.push(row?);
    }
    Ok(results)
}

fn get_collections(conn: &Connection, limit: usize, offset: usize) -> SqliteResult<Vec<Collection>> {
    let mut stmt = conn.prepare(
        "SELECT id, transporter, transport_id, status, progress, driver, eta, destination 
         FROM collection 
         ORDER BY id 
         LIMIT ? OFFSET ?"
    )?;
    let rows = stmt.query_map(params![limit, offset], |row| Collection::from_row(row))?;
    let mut results = Vec::new();
    for row in rows {
        results.push(row?);
    }
    Ok(results)
}

fn get_productions(conn: &Connection, limit: usize, offset: usize) -> SqliteResult<Vec<Production>> {
    let mut stmt = conn.prepare(
        "SELECT id, machine, status, current_work, completion, efficiency, consumption 
         FROM production 
         ORDER BY id 
         LIMIT ? OFFSET ?"
    )?;
    let rows = stmt.query_map(params![limit, offset], |row| Production::from_row(row))?;
    let mut results = Vec::new();
    for row in rows {
        results.push(row?);
    }
    Ok(results)
}

fn get_administrations(conn: &Connection, limit: usize, offset: usize) -> SqliteResult<Vec<Administration>> {
    let mut stmt = conn.prepare(
        "SELECT id, invoice_number, client, amount_eur, date, status 
         FROM administration 
         ORDER BY id 
         LIMIT ? OFFSET ?"
    )?;
    let rows = stmt.query_map(params![limit, offset], |row| Administration::from_row(row))?;
    let mut results = Vec::new();
    for row in rows {
        results.push(row?);
    }
    Ok(results)
}

fn get_online_stock_by_id(conn: &Connection, id: i64) -> SqliteResult<Option<OnlineStock>> {
    let mut stmt = conn.prepare(
        "SELECT id, name, type, color, origin, finish, thickness, dimensions, stock, price 
         FROM online_stock 
         WHERE id = ?"
    )?;
    let mut rows = stmt.query_map(params![id], |row| OnlineStock::from_row(row))?;
    match rows.next() {
        Some(Ok(stock)) => Ok(Some(stock)),
        Some(Err(e)) => Err(e),
        None => Ok(None),
    }
}

fn get_order_by_id(conn: &Connection, order_id: &str) -> SqliteResult<Option<Order>> {
    let mut stmt = conn.prepare(
        "SELECT id, order_id, client, product, machine, status, scheduled 
         FROM orders 
         WHERE order_id = ?"
    )?;
    let mut rows = stmt.query_map(params![order_id], |row| Order::from_row(row))?;
    match rows.next() {
        Some(Ok(order)) => Ok(Some(order)),
        Some(Err(e)) => Err(e),
        None => Ok(None),
    }
}

// ============================================================================
// Pattern 1: DatabaseActor (Actor Pattern con canali)
// Thread dedicato al database, tutte le operazioni serializzate
// IDEALE PER: Applicazioni single-threaded o con poche letture
// ============================================================================

pub enum DatabaseCommand {
    GetOnlineStock(usize, usize, mpsc::Sender<SqliteResult<Vec<OnlineStock>>>),
    GetQuotations(usize, usize, mpsc::Sender<SqliteResult<Vec<Quotation>>>),
    GetOrders(usize, usize, mpsc::Sender<SqliteResult<Vec<Order>>>),
    GetCollections(usize, usize, mpsc::Sender<SqliteResult<Vec<Collection>>>),
    GetProductions(usize, usize, mpsc::Sender<SqliteResult<Vec<Production>>>),
    GetAdministrations(usize, usize, mpsc::Sender<SqliteResult<Vec<Administration>>>),
    GetOnlineStockById(i64, mpsc::Sender<SqliteResult<Option<OnlineStock>>>),
    GetOrderById(String, mpsc::Sender<SqliteResult<Option<Order>>>),
    Shutdown,
}

pub struct DatabaseActor {
    db_path: String,
    command_rx: mpsc::Receiver<DatabaseCommand>,
}

impl DatabaseActor {
    pub fn new(db_path: String, command_rx: mpsc::Receiver<DatabaseCommand>) -> Self {
        Self { db_path, command_rx }
    }

    pub fn run(&self) {
        let conn = match Connection::open(&self.db_path) {
            Ok(c) => {
                if let Err(e) = configure_connection(&c) {
                    error!("Errore configurazione database: {}", e);
                    return;
                }
                info!("DatabaseActor: connessione configurata con WAL mode");
                c
            }
            Err(e) => {
                error!("Errore apertura database: {}", e);
                return;
            }
        };

        loop {
            match self.command_rx.recv() {
                Ok(DatabaseCommand::GetOnlineStock(limit, offset, sender)) => {
                    let result = get_online_stock(&conn, limit, offset);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetQuotations(limit, offset, sender)) => {
                    let result = get_quotations(&conn, limit, offset);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetOrders(limit, offset, sender)) => {
                    let result = get_orders(&conn, limit, offset);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetCollections(limit, offset, sender)) => {
                    let result = get_collections(&conn, limit, offset);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetProductions(limit, offset, sender)) => {
                    let result = get_productions(&conn, limit, offset);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetAdministrations(limit, offset, sender)) => {
                    let result = get_administrations(&conn, limit, offset);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetOnlineStockById(id, sender)) => {
                    let result = get_online_stock_by_id(&conn, id);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::GetOrderById(order_id, sender)) => {
                    let result = get_order_by_id(&conn, &order_id);
                    let _ = sender.send(result);
                }
                Ok(DatabaseCommand::Shutdown) => {
                    info!("DatabaseActor: shutdown richiesto");
                    break;
                }
                Err(_) => {
                    warn!("DatabaseActor: errore ricezione comando");
                    break;
                }
            }
        }
    }
}

pub struct DatabaseActorHandle {
    command_tx: mpsc::Sender<DatabaseCommand>,
    actor_thread: Option<thread::JoinHandle<()>>,
}

impl DatabaseActorHandle {
    pub fn new(db_path: String) -> Self {
        let (tx, rx) = mpsc::channel();
        let actor = DatabaseActor::new(db_path, rx);
        let actor_thread = thread::spawn(move || actor.run());
        
        info!("DatabaseActorHandle creato");
        
        Self {
            command_tx: tx,
            actor_thread: Some(actor_thread),
        }
    }

    pub fn get_online_stock(&self, limit: usize, offset: usize) -> SqliteResult<Vec<OnlineStock>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetOnlineStock(limit, offset, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_quotations(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Quotation>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetQuotations(limit, offset, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_orders(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Order>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetOrders(limit, offset, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_collections(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Collection>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetCollections(limit, offset, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_productions(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Production>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetProductions(limit, offset, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_administrations(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Administration>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetAdministrations(limit, offset, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_online_stock_by_id(&self, id: i64) -> SqliteResult<Option<OnlineStock>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetOnlineStockById(id, tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn get_order_by_id(&self, order_id: &str) -> SqliteResult<Option<Order>> {
        let (tx, rx) = mpsc::channel();
        self.command_tx.send(DatabaseCommand::GetOrderById(order_id.to_string(), tx))
            .map_err(|_| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some("Errore invio comando al database actor".to_string())
            ))?;
        rx.recv().unwrap_or_else(|_| Err(rusqlite::Error::SqliteFailure(
            rusqlite::ffi::Error::new(1),
            Some("Errore ricezione risposta dal database actor".to_string())
        )))
    }

    pub fn shutdown(self) {
        let _ = self.command_tx.send(DatabaseCommand::Shutdown);
        if let Some(thread) = self.actor_thread {
            let _ = thread.join();
        }
        info!("DatabaseActorHandle chiuso");
    }
}

// ============================================================================
// Pattern 2: DatabasePool (r2d2 Connection Pool)
// Pool di connessioni thread-safe per accesso parallelo
// IDEALE PER: Applicazioni multi-threaded con molte letture simultanee
// ============================================================================

// Manager personalizzato per r2d2 con rusqlite
struct SqliteConnectionManager {
    db_path: String,
}

impl ManageConnection for SqliteConnectionManager {
    type Connection = Connection;
    type Error = rusqlite::Error;

    fn connect(&self) -> Result<Self::Connection, Self::Error> {
        let conn = Connection::open(&self.db_path)?;
        configure_connection(&conn)?;
        Ok(conn)
    }

    fn is_valid(&self, _conn: &mut Self::Connection) -> Result<(), Self::Error> {
        // Disabilitiamo la validazione per evitare problemi con WAL mode
        // Le connessioni SQLite sono generalmente valide se aperte correttamente
        Ok(())
    }

    fn has_broken(&self, _conn: &mut Self::Connection) -> bool {
        false
    }
}

pub struct DatabasePool {
    pool: Pool<SqliteConnectionManager>,
}

impl DatabasePool {
    /// Crea un nuovo pool di connessioni
    /// 
    /// Args:
    ///   - db_path: Percorso del database SQLite
    ///   - max_connections: Numero massimo di connessioni nel pool (default: 10)
    /// 
    /// Returns:
    ///   - DatabasePool configurato con WAL mode
    pub fn new(db_path: &str, max_connections: Option<u32>) -> SqliteResult<Self> {
        let manager = SqliteConnectionManager {
            db_path: db_path.to_string(),
        };
        let max = max_connections.unwrap_or(10);
        
        let pool = Pool::builder()
            .max_size(max)
            .test_on_check_out(false)  // Disabilitato temporaneamente per debug
            .build(manager)
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore creazione pool: {}", e))
            ))?;
        
        info!("DatabasePool creato con {} connessioni max", max);
        
        Ok(Self { pool })
    }

    /// Ottiene una connessione dal pool
    /// La connessione viene automaticamente restituita al pool quando viene droppata
    fn get_connection(&self) -> Result<PooledConnection<SqliteConnectionManager>, r2d2::Error> {
        self.pool.get()
    }

    pub fn get_online_stock(&self, limit: usize, offset: usize) -> SqliteResult<Vec<OnlineStock>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_online_stock(&conn, limit, offset)
    }

    pub fn get_quotations(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Quotation>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_quotations(&conn, limit, offset)
    }

    pub fn get_orders(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Order>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_orders(&conn, limit, offset)
    }

    pub fn get_collections(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Collection>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_collections(&conn, limit, offset)
    }

    pub fn get_productions(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Production>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_productions(&conn, limit, offset)
    }

    pub fn get_administrations(&self, limit: usize, offset: usize) -> SqliteResult<Vec<Administration>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_administrations(&conn, limit, offset)
    }

    pub fn get_online_stock_by_id(&self, id: i64) -> SqliteResult<Option<OnlineStock>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_online_stock_by_id(&conn, id)
    }

    pub fn get_order_by_id(&self, order_id: &str) -> SqliteResult<Option<Order>> {
        let conn = self.get_connection()
            .map_err(|e| rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(1),
                Some(format!("Errore pool: {}", e))
            ))?;
        get_order_by_id(&conn, order_id)
    }
}

// Implementazione Clone per permettere condivisione tra thread
impl Clone for DatabasePool {
    fn clone(&self) -> Self {
        Self {
            pool: self.pool.clone(),
        }
    }
}
