// Rust Core - Modulo principale per comunicazione Ethernet con PLC Siemens S7
// Architettura: Rust → Python → UI → RAG Engine

pub mod plc;
pub mod ffi;

// Re-export principali per facilità d'uso
pub use plc::plc_error::PlcError;
pub use plc::ethernet_interface::{EthernetInterface, ConnectionStatus};
pub use plc::s7_client::S7Client;
pub use plc::lucidatrice_reader::{LucidatriceReader, LucidatriceStatus};
pub use plc::multifilo_reader::{MultifiloReader, MultifiloStatus};

// Python module initialization
#[cfg(feature = "extension-module")]
use pyo3::prelude::*;

#[cfg(feature = "extension-module")]
#[pymodule]
fn rust_core(_py: Python, m: &PyModule) -> PyResult<()> {
    ffi::python_bindings::rust_core(_py, m)
}

