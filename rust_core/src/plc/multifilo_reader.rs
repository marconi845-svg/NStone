// Multifilo Reader - Lettura dati Multifilo dal PLC via Ethernet
// Predisposto per DB 200

use crate::plc::s7_client::S7Client;
use crate::plc::plc_error::PlcError;
use serde::{Deserialize, Serialize};
use std::time::Instant;

/// Struttura dati per stato Multifilo
/// 
/// Mappata dal DB 200 del PLC Siemens S7
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultifiloStatus {
    // Stato macchina
    pub connessa: bool,
    pub avanzamento: f32,              // %
    pub tempo_residuo: i32,           // secondi
    pub allarmi: i32,                 // Codice allarme
    
    // Produzione
    pub spreco_reale: Option<f32>,    // %
    pub tempo_reale: Option<f32>,     // secondi
    pub deviazioni: Option<String>,   // Descrizione deviazioni
    
    // Parametri operativi
    pub wire_speed_actual: f32,       // m/s
    pub feed_rate_actual: f32,        // mm/min
    pub tension_actual: f32,          // N
    pub block_counter: i32,           // Contatore blocchi
    
    // Sensori
    pub sensor1: bool,
    pub sensor2: bool,
    pub sensor3: bool,
    
    // Metadati Ethernet
    pub ethernet_connected: bool,
    pub ethernet_latency_ms: u64,
    pub last_packet_time: Option<Instant>,
}

impl Default for MultifiloStatus {
    fn default() -> Self {
        Self {
            connessa: false,
            avanzamento: 0.0,
            tempo_residuo: 0,
            allarmi: 0,
            spreco_reale: None,
            tempo_reale: None,
            deviazioni: None,
            wire_speed_actual: 0.0,
            feed_rate_actual: 0.0,
            tension_actual: 0.0,
            block_counter: 0,
            sensor1: false,
            sensor2: false,
            sensor3: false,
            ethernet_connected: false,
            ethernet_latency_ms: 0,
            last_packet_time: None,
        }
    }
}

/// Reader per dati Multifilo dal PLC
/// 
/// Predisposto per:
/// - Leggere DB 200 via Ethernet
/// - Convertire dati in struct Rust
/// - Esportare verso Python via FFI
pub struct MultifiloReader {
    client: S7Client,
    db_number: u16,
}

impl MultifiloReader {
    /// Crea un nuovo reader per Multifilo
    /// 
    /// # Args
    /// - `ip`: Indirizzo IP del PLC
    /// - `port`: Porta TCP (default: 102)
    /// - `db_number`: Numero DB (default: 200 per Multifilo)
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
    
    /// Legge lo stato completo del Multifilo dal PLC
    /// 
    /// # Returns
    /// - `Ok(MultifiloStatus)` con i dati letti
    /// - `Err(PlcError)` se la lettura è fallita
    /// 
    /// # Note
    /// Predisposto per implementazione futura quando il PLC sarà disponibile
    /// 
    /// Mapping DB 200 (esempio):
    /// - DB200.DBX0.0: Connessa (BOOL)
    /// - DB200.DBD2: Avanzamento (REAL)
    /// - DB200.DBW6: Tempo residuo (INT)
    /// - DB200.DBW8: Allarmi (INT)
    /// - DB200.DBD10: Spreco reale (REAL)
    /// - DB200.DBD14: Tempo reale (REAL)
    /// - DB200.DBS18: Deviazioni (STRING)
    /// - DB200.DBD30: Wire speed actual (REAL)
    /// - DB200.DBD34: Feed rate actual (REAL)
    /// - DB200.DBD38: Tension actual (REAL)
    /// - DB200.DBW42: Block counter (INT)
    /// - DB200.DBX44.0: Sensor1 (BOOL)
    /// - DB200.DBX44.1: Sensor2 (BOOL)
    /// - DB200.DBX44.2: Sensor3 (BOOL)
    pub fn read_status(&mut self) -> Result<MultifiloStatus, PlcError> {
        if !self.client.is_connected() {
            return Err(PlcError::NotConnected);
        }
        
        // TODO: Implementare lettura DB quando il PLC sarà disponibile
        // Esempio struttura:
        // let connessa = self.client.read_bool(self.db_number, 0, 0)?;
        // let avanzamento = self.client.read_real(self.db_number, 2)?;
        // let tempo_residuo = self.client.read_int(self.db_number, 6)? as i32;
        // ...
        
        // Per ora, restituisce stato di default (non invasivo)
        let mut status = MultifiloStatus::default();
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

