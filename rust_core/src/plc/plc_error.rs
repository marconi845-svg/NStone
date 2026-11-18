// Gestione errori PLC - Centralizzata e tipizzata

use thiserror::Error;

#[derive(Error, Debug, Clone)]
pub enum PlcError {
    #[error("Errore connessione TCP: {0}")]
    TcpConnectionError(String),
    
    #[error("Errore handshake S7: {0}")]
    S7HandshakeError(String),
    
    #[error("Timeout connessione: {0}")]
    TimeoutError(String),
    
    #[error("Errore lettura DB: {0}")]
    DbReadError(String),
    
    #[error("PLC non connesso")]
    NotConnected,
    
    #[error("Errore protocollo S7: {0}")]
    ProtocolError(String),
    
    #[error("Errore parsing dati: {0}")]
    ParseError(String),
    
    #[error("Errore riconnessione: {0}")]
    ReconnectionError(String),
    
    #[error("Errore generico: {0}")]
    GenericError(String),
}

impl PlcError {
    pub fn is_recoverable(&self) -> bool {
        matches!(
            self,
            PlcError::TcpConnectionError(_)
                | PlcError::TimeoutError(_)
                | PlcError::NotConnected
                | PlcError::ReconnectionError(_)
        )
    }
}

