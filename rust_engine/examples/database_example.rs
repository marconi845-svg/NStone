/*
 * Esempio di utilizzo del modulo database Rust
 * Dimostra entrambi i pattern: Actor e Pool
 * 
 * Esegui con: cargo run --example database_example
 */

use rust_engine::database::{DatabaseActorHandle, DatabasePool};
use std::sync::Arc;
use std::thread;

fn main() {
    // Inizializza logger
    env_logger::Builder::from_default_env()
        .filter_level(log::LevelFilter::Info)
        .init();
    
    let db_path = "../data/nstonellm.db";

    println!("=== Esempio 1: DatabaseActor (Pattern Actor) ===");
    example_actor_pattern(db_path);

    println!("\n=== Esempio 2: DatabasePool (Pattern Pool) ===");
    example_pool_pattern(db_path);

    println!("\n=== Esempio 3: Accesso Concorrente ===");
    example_concurrent_access(db_path);
}

fn example_actor_pattern(db_path: &str) {
    // Crea l'actor handle (avvia il thread dedicato)
    let db = DatabaseActorHandle::new(db_path.to_string());

    // Leggi online_stock
    match db.get_online_stock(10, 0) {
        Ok(stocks) => {
            println!("✓ Trovati {} materiali in stock", stocks.len());
            for stock in stocks.iter().take(3) {
                println!("  - {}: {} ({} mq disponibili)", 
                    stock.name, stock.r#type, stock.stock);
            }
        }
        Err(e) => println!("✗ Errore: {}", e),
    }

    // Leggi orders
    match db.get_orders(5, 0) {
        Ok(orders) => {
            println!("✓ Trovati {} ordini", orders.len());
            for order in &orders {
                println!("  - {}: {} ({})", 
                    order.order_id, order.client, order.status);
            }
        }
        Err(e) => println!("✗ Errore: {}", e),
    }

    // Chiudi l'actor
    db.shutdown();
}

fn example_pool_pattern(db_path: &str) {
    // Crea il pool di connessioni (max 5 connessioni)
    let db = match DatabasePool::new(db_path, Some(5)) {
        Ok(pool) => pool,
        Err(e) => {
            eprintln!("Errore creazione pool: {}", e);
            return;
        }
    };

    // Leggi quotations
    match db.get_quotations(5, 0) {
        Ok(quotations) => {
            println!("✓ Trovati {} preventivi", quotations.len());
            for quot in &quotations {
                println!("  - {}: {} mq @ {} €/mq", 
                    quot.cliente, quot.quantita_mq, quot.prezzo_mq);
            }
        }
        Err(e) => println!("✗ Errore: {}", e),
    }

    // Leggi production
    match db.get_productions(10, 0) {
        Ok(productions) => {
            println!("✓ Trovate {} macchine", productions.len());
            for prod in &productions {
                println!("  - {}: {} ({}% completato)", 
                    prod.machine, prod.status, prod.completion);
            }
        }
        Err(e) => println!("✗ Errore: {}", e),
    }
}

fn example_concurrent_access(db_path: &str) {
    // Usa Arc per condividere il pool tra thread
    let db = match DatabasePool::new(db_path, Some(10)) {
        Ok(pool) => Arc::new(pool),
        Err(e) => {
            eprintln!("Errore creazione pool: {}", e);
            return;
        }
    };

    let mut handles = vec![];

    // Thread 1: Legge online_stock
    let db1 = db.clone();
    handles.push(thread::spawn(move || {
        match db1.get_online_stock(5, 0) {
            Ok(stocks) => println!("[Thread 1] Letti {} materiali", stocks.len()),
            Err(e) => println!("[Thread 1] Errore: {}", e),
        }
    }));

    // Thread 2: Legge orders
    let db2 = db.clone();
    handles.push(thread::spawn(move || {
        match db2.get_orders(5, 0) {
            Ok(orders) => println!("[Thread 2] Letti {} ordini", orders.len()),
            Err(e) => println!("[Thread 2] Errore: {}", e),
        }
    }));

    // Thread 3: Legge quotations
    let db3 = db.clone();
    handles.push(thread::spawn(move || {
        match db3.get_quotations(5, 0) {
            Ok(quotations) => println!("[Thread 3] Letti {} preventivi", quotations.len()),
            Err(e) => println!("[Thread 3] Errore: {}", e),
        }
    }));

    // Attendi che tutti i thread finiscano
    for handle in handles {
        handle.join().unwrap();
    }

    println!("✓ Tutti i thread hanno completato le letture in parallelo");
}

