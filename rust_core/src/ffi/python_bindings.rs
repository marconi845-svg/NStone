// Python Bindings - FFI per esporre funzionalità PLC a Python
// Predisposto per integrazione con Python → UI → RAG Engine

use pyo3::prelude::*;
use pyo3::types::PyDict;
use crate::plc::lucidatrice_reader::{LucidatriceReader, LucidatriceStatus};
use crate::plc::multifilo_reader::{MultifiloReader, MultifiloStatus};
use crate::plc::plc_error::PlcError;
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// Wrapper Python per LucidatriceStatus
#[pyclass]
#[derive(Clone)]
pub struct PyLucidatriceStatus {
    #[pyo3(get, set)]
    pub stato_macchina: String,
    #[pyo3(get, set)]
    pub velocita_nastro: f32,
    #[pyo3(get, set)]
    pub pressione_teste: f32,
    #[pyo3(get, set)]
    pub temperatura_motori: f32,
    #[pyo3(get, set)]
    pub consumo_acqua: f32,
    #[pyo3(get, set)]
    pub allarmi: i32,
    #[pyo3(get, set)]
    pub metri_lavorati: f32,
    #[pyo3(get, set)]
    pub produzione_ora: f32,
    #[pyo3(get, set)]
    pub qualita_superficie: String,
    #[pyo3(get, set)]
    pub contatore_pezzi: i32,
    #[pyo3(get, set)]
    pub setpoint_velocita: f32,
    #[pyo3(get, set)]
    pub setpoint_pressione: f32,
    #[pyo3(get, set)]
    pub setpoint_abrasivi: String,
    #[pyo3(get, set)]
    pub modalita_lavoro: String,
    #[pyo3(get, set)]
    pub ethernet_connected: bool,
    #[pyo3(get, set)]
    pub ethernet_latency_ms: u64,
}

impl From<LucidatriceStatus> for PyLucidatriceStatus {
    fn from(status: LucidatriceStatus) -> Self {
        Self {
            stato_macchina: status.stato_macchina,
            velocita_nastro: status.velocita_nastro,
            pressione_teste: status.pressione_teste,
            temperatura_motori: status.temperatura_motori,
            consumo_acqua: status.consumo_acqua,
            allarmi: status.allarmi,
            metri_lavorati: status.metri_lavorati,
            produzione_ora: status.produzione_ora,
            qualita_superficie: status.qualita_superficie,
            contatore_pezzi: status.contatore_pezzi,
            setpoint_velocita: status.setpoint_velocita,
            setpoint_pressione: status.setpoint_pressione,
            setpoint_abrasivi: status.setpoint_abrasivi,
            modalita_lavoro: status.modalita_lavoro,
            ethernet_connected: status.ethernet_connected,
            ethernet_latency_ms: status.ethernet_latency_ms,
        }
    }
}

/// Wrapper Python per MultifiloStatus
#[pyclass]
#[derive(Clone)]
pub struct PyMultifiloStatus {
    #[pyo3(get, set)]
    pub connessa: bool,
    #[pyo3(get, set)]
    pub avanzamento: f32,
    #[pyo3(get, set)]
    pub tempo_residuo: i32,
    #[pyo3(get, set)]
    pub allarmi: i32,
    #[pyo3(get, set)]
    pub spreco_reale: Option<f32>,
    #[pyo3(get, set)]
    pub tempo_reale: Option<f32>,
    #[pyo3(get, set)]
    pub deviazioni: Option<String>,
    #[pyo3(get, set)]
    pub wire_speed_actual: f32,
    #[pyo3(get, set)]
    pub feed_rate_actual: f32,
    #[pyo3(get, set)]
    pub tension_actual: f32,
    #[pyo3(get, set)]
    pub block_counter: i32,
    #[pyo3(get, set)]
    pub sensor1: bool,
    #[pyo3(get, set)]
    pub sensor2: bool,
    #[pyo3(get, set)]
    pub sensor3: bool,
    #[pyo3(get, set)]
    pub ethernet_connected: bool,
    #[pyo3(get, set)]
    pub ethernet_latency_ms: u64,
}

impl From<MultifiloStatus> for PyMultifiloStatus {
    fn from(status: MultifiloStatus) -> Self {
        Self {
            connessa: status.connessa,
            avanzamento: status.avanzamento,
            tempo_residuo: status.tempo_residuo,
            allarmi: status.allarmi,
            spreco_reale: status.spreco_reale,
            tempo_reale: status.tempo_reale,
            deviazioni: status.deviazioni,
            wire_speed_actual: status.wire_speed_actual,
            feed_rate_actual: status.feed_rate_actual,
            tension_actual: status.tension_actual,
            block_counter: status.block_counter,
            sensor1: status.sensor1,
            sensor2: status.sensor2,
            sensor3: status.sensor3,
            ethernet_connected: status.ethernet_connected,
            ethernet_latency_ms: status.ethernet_latency_ms,
        }
    }
}

/// Manager per connessioni PLC (thread-safe)
struct PlcManager {
    lucidatrice_reader: Arc<Mutex<Option<LucidatriceReader>>>,
    multifilo_reader: Arc<Mutex<Option<MultifiloReader>>>,
}

impl PlcManager {
    fn new() -> Self {
        Self {
            lucidatrice_reader: Arc::new(Mutex::new(None)),
            multifilo_reader: Arc::new(Mutex::new(None)),
        }
    }
}

static PLC_MANAGER: once_cell::sync::Lazy<Mutex<PlcManager>> = once_cell::sync::Lazy::new(|| {
    Mutex::new(PlcManager::new())
});

/// Verifica connessione PLC
/// 
/// # Returns
/// - `True` se connesso
/// - `False` se non connesso
#[pyfunction]
pub fn check_plc_connection(ip: String, port: u16) -> PyResult<bool> {
    // TODO: Implementare verifica connessione quando il PLC sarà disponibile
    // Per ora, sempre False (non invasivo)
    Ok(false)
}

/// Legge stato Lucidatrice dal PLC via Ethernet
/// 
/// # Args
/// - `ip`: Indirizzo IP del PLC
/// - `port`: Porta TCP (default: 102)
/// - `db_number`: Numero DB (default: 100)
/// 
/// # Returns
/// - `PyLucidatriceStatus` con i dati letti
/// - `None` se non connesso o errore
#[pyfunction]
pub fn read_lucidatrice_status(ip: String, port: u16, db_number: u16) -> PyResult<Option<PyLucidatriceStatus>> {
    let mut manager = PLC_MANAGER.lock().unwrap();
    
    // Crea o riusa reader
    let mut reader = manager.lucidatrice_reader.lock().unwrap();
    if reader.is_none() {
        *reader = Some(LucidatriceReader::new(ip.clone(), port, db_number));
    }
    
    if let Some(ref mut r) = *reader {
        // Tenta connessione se non connesso
        if !r.is_connected() {
            let _ = r.connect(); // Ignora errori per ora
        }
        
        // Legge stato
        match r.read_status() {
            Ok(status) => Ok(Some(status.into())),
            Err(_) => Ok(None),
        }
    } else {
        Ok(None)
    }
}

/// Legge stato Multifilo dal PLC via Ethernet
/// 
/// # Args
/// - `ip`: Indirizzo IP del PLC
/// - `port`: Porta TCP (default: 102)
/// - `db_number`: Numero DB (default: 200)
/// 
/// # Returns
/// - `PyMultifiloStatus` con i dati letti
/// - `None` se non connesso o errore
#[pyfunction]
pub fn read_multifilo_status(ip: String, port: u16, db_number: u16) -> PyResult<Option<PyMultifiloStatus>> {
    let mut manager = PLC_MANAGER.lock().unwrap();
    
    // Crea o riusa reader
    let mut reader = manager.multifilo_reader.lock().unwrap();
    if reader.is_none() {
        *reader = Some(MultifiloReader::new(ip.clone(), port, db_number));
    }
    
    if let Some(ref mut r) = *reader {
        // Tenta connessione se non connesso
        if !r.is_connected() {
            let _ = r.connect(); // Ignora errori per ora
        }
        
        // Legge stato
        match r.read_status() {
            Ok(status) => Ok(Some(status.into())),
            Err(_) => Ok(None),
        }
    } else {
        Ok(None)
    }
}

/// Modulo Python per comunicazione PLC
#[pymodule]
fn rust_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyLucidatriceStatus>()?;
    m.add_class::<PyMultifiloStatus>()?;
    m.add_function(wrap_pyfunction!(check_plc_connection, m)?)?;
    m.add_function(wrap_pyfunction!(read_lucidatrice_status, m)?)?;
    m.add_function(wrap_pyfunction!(read_multifilo_status, m)?)?;
    Ok(())
}

