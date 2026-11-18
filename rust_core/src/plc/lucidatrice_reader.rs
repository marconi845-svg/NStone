// Lucidatrice Reader - Lettura dati Lucidatrice/Calibratrice dal PLC via Ethernet
// Predisposto per DB 100

use crate::plc::s7_client::S7Client;
use crate::plc::plc_error::PlcError;
use serde::{Deserialize, Serialize};
use std::time::Instant;

/// Struttura dati per stato Lucidatrice/Calibratrice
/// 
/// Mappata dal DB 100 del PLC Siemens S7
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LucidatriceStatus {
    // Stato macchina
    pub stato_macchina: String,        // "RUN", "STOP", "ALLARME"
    pub velocita_nastro: f32,          // m/min
    pub pressione_teste: f32,          // bar
    pub temperatura_motori: f32,       // °C
    pub consumo_acqua: f32,            // L/min
    pub allarmi: i32,                  // Codice allarme
    
    // Produzione
    pub metri_lavorati: f32,           // m
    pub produzione_ora: f32,           // m/h
    pub qualita_superficie: String,    // Qualità superficie
    pub contatore_pezzi: i32,          // Contatore pezzi
    
    // Parametri
    pub setpoint_velocita: f32,        // m/min
    pub setpoint_pressione: f32,       // bar
    pub setpoint_abrasivi: String,     // Tipo abrasivi
    pub modalita_lavoro: String,       // Modalità lavoro
    
    // Metadati Ethernet
    pub ethernet_connected: bool,
    pub ethernet_latency_ms: u64,
    pub last_packet_time: Option<Instant>,
}

impl Default for LucidatriceStatus {
    fn default() -> Self {
        Self {
            stato_macchina: "STOP".to_string(),
            velocita_nastro: 0.0,
            pressione_teste: 0.0,
            temperatura_motori: 0.0,
            consumo_acqua: 0.0,
            allarmi: 0,
            metri_lavorati: 0.0,
            produzione_ora: 0.0,
            qualita_superficie: "N/A".to_string(),
            contatore_pezzi: 0,
            setpoint_velocita: 0.0,
            setpoint_pressione: 0.0,
            setpoint_abrasivi: "N/A".to_string(),
            modalita_lavoro: "N/A".to_string(),
            ethernet_connected: false,
            ethernet_latency_ms: 0,
            last_packet_time: None,
        }
    }
}

/// Reader per dati Lucidatrice dal PLC
/// 
/// Predisposto per:
/// - Leggere DB 100 via Ethernet
/// - Convertire dati in struct Rust
/// - Esportare verso Python via FFI
pub struct LucidatriceReader {
    client: S7Client,
    db_number: u16,
}

impl LucidatriceReader {
    /// Crea un nuovo reader per Lucidatrice
    /// 
    /// # Args
    /// - `ip`: Indirizzo IP del PLC
    /// - `port`: Porta TCP (default: 102)
    /// - `db_number`: Numero DB (default: 100 per Lucidatrice)
    pub fn new(ip: String, port: u16, db_number: u16) -> Self {
        Self {
            client: S7Client::new(ip, port, std::time::Duration::from_secs(5)),
            db_number,
        }
    }
    
    /// Connetti al PLC
    pub fn connect(&mut self) -> Result<(), PlcError> {
        self.client.connect()
    }
    
    /// Disconnetti dal PLC
    pub fn disconnect(&mut self) {
        self.client.disconnect();
    }
    
    /// Verifica se è connesso
    pub fn is_connected(&self) -> bool {
        self.client.is_connected()
    }
    
    /// Legge lo stato completo della Lucidatrice dal PLC
    /// 
    /// # Returns
    /// - `Ok(LucidatriceStatus)` con i dati letti
    /// - `Err(PlcError)` se la lettura è fallita
    /// 
    /// # Note
    /// Predisposto per implementazione futura quando il PLC sarà disponibile
    /// 
    /// Mapping DB 100 (esempio):
    /// - DB100.DBX0.0: Stato macchina (BOOL)
    /// - DB100.DBD2: Velocità nastro (REAL)
    /// - DB100.DBD6: Pressione teste (REAL)
    /// - DB100.DBD10: Temperatura motori (REAL)
    /// - DB100.DBD14: Consumo acqua (REAL)
    /// - DB100.DBW18: Allarmi (INT)
    /// - DB100.DBD20: Metri lavorati (REAL)
    /// - DB100.DBD24: Produzione ora (REAL)
    /// - DB100.DBS28: Qualità superficie (STRING)
    /// - DB100.DBW40: Contatore pezzi (INT)
    /// - DB100.DBD42: Setpoint velocità (REAL)
    /// - DB100.DBD46: Setpoint pressione (REAL)
    /// - DB100.DBS50: Setpoint abrasivi (STRING)
    /// - DB100.DBS60: Modalità lavoro (STRING)
    pub fn read_status(&mut self) -> Result<LucidatriceStatus, PlcError> {
        if !self.client.is_connected() {
            return Err(PlcError::NotConnected);
        }
        
        // TODO: Implementare lettura DB quando il PLC sarà disponibile
        // Esempio struttura:
        // let db_data = self.client.read_db(self.db_number, 0, 200)?;
        // 
        // let stato = if self.client.read_bool(self.db_number, 0, 0)? { "RUN" } else { "STOP" };
        // let velocita = self.client.read_real(self.db_number, 2)?;
        // let pressione = self.client.read_real(self.db_number, 6)?;
        // ...
        
        // Per ora, restituisce stato di default (non invasivo)
        let mut status = LucidatriceStatus::default();
        status.ethernet_connected = self.client.is_connected();
        status.ethernet_latency_ms = self.client.latency_ms().unwrap_or(0);
        status.last_packet_time = self.client.last_packet_time();
        
        Ok(status)
    }
    
    /// Ottiene la latenza Ethernet (ms)
    pub fn latency_ms(&self) -> Option<u64> {
        self.client.latency_ms()
    }
    
    /// Ottiene il timestamp dell'ultimo pacchetto
    pub fn last_packet_time(&self) -> Option<Instant> {
        self.client.last_packet_time()
    }
}

