// Modulo PLC - Comunicazione Ethernet con Siemens S7-1200/S7-1500

pub mod plc_error;
pub mod ethernet_interface;
pub mod s7_client;
pub mod lucidatrice_reader;
pub mod multifilo_reader;

// Re-export
pub use plc_error::PlcError;
pub use ethernet_interface::{EthernetInterface, ConnectionStatus};
pub use s7_client::S7Client;
pub use lucidatrice_reader::{LucidatriceReader, LucidatriceStatus};
pub use multifilo_reader::{MultifiloReader, MultifiloStatus};

