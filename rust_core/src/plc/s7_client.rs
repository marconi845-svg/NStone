// S7 Client - Client generico per comunicazione con PLC Siemens S7-1200/S7-1500
// Predisposto per lettura DB via Ethernet

use crate::plc::ethernet_interface::{EthernetInterface, ConnectionStatus};
use crate::plc::plc_error::PlcError;
use std::time::Duration;

/// Client generico S7 per comunicazione con PLC Siemens
/// 
/// Predisposto per:
/// - connect(ip, port)
/// - read_db(db, start, size)
/// - Gestione errori Siemens
/// - Mapping DB → struct Rust
pub struct S7Client {
    interface: EthernetInterface,
}

impl S7Client {
    /// Crea un nuovo client S7
    /// 
    /// # Args
    /// - `ip`: Indirizzo IP del PLC
    /// - `port`: Porta TCP (default: 102)
    /// - `timeout`: Timeout per operazioni
    pub fn new(ip: String, port: u16, timeout: Duration) -> Self {
        Self {
            interface: EthernetInterface::new(ip, port, timeout),
        }
    }
    
    /// Connetti al PLC
    /// 
    /// # Returns
    /// - `Ok(())` se la connessione è riuscita
    /// - `Err(PlcError)` se la connessione è fallita
    pub fn connect(&mut self) -> Result<(), PlcError> {
        self.interface.connect()
    }
    
    /// Disconnetti dal PLC
    pub fn disconnect(&mut self) {
        self.interface.disconnect();
    }
    
    /// Verifica se è connesso
    pub fn is_connected(&self) -> bool {
        self.interface.is_connected()
    }
    
    /// Ottiene lo stato della connessione
    pub fn connection_status(&self) -> ConnectionStatus {
        self.interface.connection_status()
    }
    
    /// Legge un Data Block dal PLC
    /// 
    /// # Args
    /// - `db_number`: Numero del Data Block (es. 100 per Lucidatrice, 200 per Multifilo)
    /// - `start_offset`: Offset di partenza (byte)
    /// - `size`: Dimensione da leggere (byte)
    /// 
    /// # Returns
    /// - `Ok(Vec<u8>)` con i dati letti
    /// - `Err(PlcError)` se la lettura è fallita
    /// 
    /// # Note
    /// Predisposto per implementazione futura quando il PLC sarà disponibile
    pub fn read_db(&mut self, db_number: u16, start_offset: u16, size: u16) -> Result<Vec<u8>, PlcError> {
        if !self.is_connected() {
            return Err(PlcError::NotConnected);
        }
        
        // TODO: Implementare lettura DB S7 quando il PLC sarà disponibile
        // 1. Costruire pacchetto S7 READ REQUEST
        // 2. Inviare via EthernetInterface
        // 3. Ricevere risposta
        // 4. Parsare dati
        // 5. Restituire buffer
        
        // Per ora, simulazione (non invasiva)
        Err(PlcError::NotConnected)
    }
    
    /// Legge un valore INT dal DB
    /// 
    /// # Args
    /// - `db_number`: Numero del Data Block
    /// - `offset`: Offset del valore (byte)
    /// 
    /// # Returns
    /// - `Ok(i16)` con il valore letto
    /// - `Err(PlcError)` se la lettura è fallita
    pub fn read_int(&mut self, db_number: u16, offset: u16) -> Result<i16, PlcError> {
        let data = self.read_db(db_number, offset, 2)?;
        if data.len() < 2 {
            return Err(PlcError::ParseError("Dati insufficienti per INT".to_string()));
        }
        Ok(i16::from_le_bytes([data[0], data[1]]))
    }
    
    /// Legge un valore REAL dal DB
    /// 
    /// # Args
    /// - `db_number`: Numero del Data Block
    /// - `offset`: Offset del valore (byte)
    /// 
    /// # Returns
    /// - `Ok(f32)` con il valore letto
    /// - `Err(PlcError)` se la lettura è fallita
    pub fn read_real(&mut self, db_number: u16, offset: u16) -> Result<f32, PlcError> {
        let data = self.read_db(db_number, offset, 4)?;
        if data.len() < 4 {
            return Err(PlcError::ParseError("Dati insufficienti per REAL".to_string()));
        }
        Ok(f32::from_le_bytes([data[0], data[1], data[2], data[3]]))
    }
    
    /// Legge un valore BOOL dal DB
    /// 
    /// # Args
    /// - `db_number`: Numero del Data Block
    /// - `byte_offset`: Offset del byte
    /// - `bit_offset`: Offset del bit (0-7)
    /// 
    /// # Returns
    /// - `Ok(bool)` con il valore letto
    /// - `Err(PlcError)` se la lettura è fallita
    pub fn read_bool(&mut self, db_number: u16, byte_offset: u16, bit_offset: u8) -> Result<bool, PlcError> {
        if bit_offset > 7 {
            return Err(PlcError::ParseError("Bit offset deve essere 0-7".to_string()));
        }
        let data = self.read_db(db_number, byte_offset, 1)?;
        if data.is_empty() {
            return Err(PlcError::ParseError("Dati insufficienti per BOOL".to_string()));
        }
        Ok((data[0] & (1 << bit_offset)) != 0)
    }
    
    /// Esegue ping al PLC
    pub fn ping(&mut self) -> Result<u64, PlcError> {
        self.interface.ping()
    }
    
    /// Tenta riconnessione
    pub fn reconnect(&mut self) -> Result<(), PlcError> {
        self.interface.reconnect()
    }
    
    /// Ottiene la latenza (ms)
    pub fn latency_ms(&self) -> Option<u64> {
        self.interface.latency_ms()
    }
    
    /// Ottiene il timestamp dell'ultimo pacchetto
    pub fn last_packet_time(&self) -> Option<std::time::Instant> {
        self.interface.last_packet_time()
    }
}

