use serde::{Deserialize, Serialize};
use snap7_rs::S7Client;
use std::time::Duration;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MachineStatus {
    pub machine_state: i32,
    pub progress_percent: f32,
    pub remaining_time_sec: i32,
    pub alarm_code: i32,
    pub wire_speed_actual: f32,
    pub feed_rate_actual: f32,
    pub tension_actual: f32,
    pub block_counter: i32,
    pub sensor1: bool,
    pub sensor2: bool,
    pub sensor3: bool,
}

pub struct PlcClient {
    client: S7Client,
    db_number: i32,
}

impl PlcClient {
    pub fn new(ip_address: &str, db_number: i32) -> Result<Self, String> {
        let mut client = S7Client::create();
        
        match client.connect_to(ip_address, 0, 1) {
            Ok(_) => Ok(PlcClient {
                client,
                db_number,
            }),
            Err(e) => Err(format!("Failed to connect to PLC at {}: {:?}", ip_address, e)),
        }
    }

    pub fn disconnect(&mut self) {
        let _ = self.client.disconnect();
    }

    pub fn is_connected(&self) -> bool {
        let mut is_connected = 0i32;
        match self.client.get_connected(&mut is_connected) {
            Ok(_) => is_connected != 0,
            Err(_) => false,
        }
    }

    fn read_int(&self, offset: i32) -> Result<i32, String> {
        let mut buffer = vec![0u8; 2];
        match self.client.db_read(self.db_number, offset, 2, &mut buffer) {
            Ok(_) => {
                let value = i16::from_le_bytes([buffer[0], buffer[1]]) as i32;
                Ok(value)
            },
            Err(e) => Err(format!("Failed to read INT at offset {}: {:?}", offset, e)),
        }
    }

    fn read_dint(&self, offset: i32) -> Result<i32, String> {
        let mut buffer = vec![0u8; 4];
        match self.client.db_read(self.db_number, offset, 4, &mut buffer) {
            Ok(_) => {
                let value = i32::from_le_bytes([buffer[0], buffer[1], buffer[2], buffer[3]]);
                Ok(value)
            },
            Err(e) => Err(format!("Failed to read DINT at offset {}: {:?}", offset, e)),
        }
    }

    fn read_real(&self, offset: i32) -> Result<f32, String> {
        let mut buffer = vec![0u8; 4];
        match self.client.db_read(self.db_number, offset, 4, &mut buffer) {
            Ok(_) => {
                let bytes: [u8; 4] = [buffer[0], buffer[1], buffer[2], buffer[3]];
                let value = f32::from_le_bytes(bytes);
                Ok(value)
            },
            Err(e) => Err(format!("Failed to read REAL at offset {}: {:?}", offset, e)),
        }
    }

    fn read_bool(&self, byte_offset: i32, bit_offset: u8) -> Result<bool, String> {
        if bit_offset > 7 {
            return Err(format!("Bit offset must be 0-7, got {}", bit_offset));
        }
        
        let mut buffer = vec![0u8; 1];
        match self.client.db_read(self.db_number, byte_offset, 1, &mut buffer) {
            Ok(_) => {
                let byte = buffer[0];
                let mask = 1u8 << bit_offset;
                Ok((byte & mask) != 0)
            },
            Err(e) => Err(format!("Failed to read BOOL at {}.{}: {:?}", byte_offset, bit_offset, e)),
        }
    }
}

pub fn read_multifilo_inputs(plc: &PlcClient) -> Result<MachineStatus, String> {
    let machine_state = plc.read_dint(0)?;
    let progress_percent = plc.read_real(4)?;
    let remaining_time_sec = plc.read_dint(8)?;
    let alarm_code = plc.read_dint(12)?;
    let wire_speed_actual = plc.read_real(16)?;
    let feed_rate_actual = plc.read_real(20)?;
    let tension_actual = plc.read_real(24)?;
    let block_counter = plc.read_dint(28)?;
    let sensor1 = plc.read_bool(32, 0)?;
    let sensor2 = plc.read_bool(32, 1)?;
    let sensor3 = plc.read_bool(32, 2)?;

    Ok(MachineStatus {
        machine_state,
        progress_percent,
        remaining_time_sec,
        alarm_code,
        wire_speed_actual,
        feed_rate_actual,
        tension_actual,
        block_counter,
        sensor1,
        sensor2,
        sensor3,
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GestioneMultifiloUI {
    pub connessa: bool,
    pub avanzamento: f32,
    pub tempo_residuo: i32,
    pub allarmi: i32,
    pub spreco_reale: Option<f32>,
    pub tempo_reale: Option<f32>,
    pub deviazioni: Option<String>,
}

impl GestioneMultifiloUI {
    pub fn new() -> Self {
        GestioneMultifiloUI {
            connessa: false,
            avanzamento: 0.0,
            tempo_residuo: 0,
            allarmi: 0,
            spreco_reale: None,
            tempo_reale: None,
            deviazioni: None,
        }
    }
}

pub fn update_gestione_multifilo(plc: &PlcClient, ui: &mut GestioneMultifiloUI) -> Result<(), String> {
    let status = read_multifilo_inputs(plc)?;
    
    ui.connessa = plc.is_connected();
    ui.avanzamento = status.progress_percent;
    ui.tempo_residuo = status.remaining_time_sec;
    ui.allarmi = status.alarm_code;
    
    ui.spreco_reale = None;
    ui.tempo_reale = None;
    ui.deviazioni = None;
    
    Ok(())
}

pub fn example_update_loop(plc: &PlcClient, ui: &mut GestioneMultifiloUI) -> Result<(), String> {
    loop {
        update_gestione_multifilo(plc, ui)?;
        
        println!("UI aggiornata: Connessa={}, Avanzamento={:.1}%, Tempo residuo={}s, Allarmi={}",
            ui.connessa, ui.avanzamento, ui.tempo_residuo, ui.allarmi);
        
        std::thread::sleep(Duration::from_millis(100));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_machine_status_creation() {
        let status = MachineStatus {
            machine_state: 1,
            progress_percent: 50.5,
            remaining_time_sec: 120,
            alarm_code: 0,
            wire_speed_actual: 45.0,
            feed_rate_actual: 120.0,
            tension_actual: 2.5,
            block_counter: 10,
            sensor1: true,
            sensor2: false,
            sensor3: true,
        };
        
        assert_eq!(status.machine_state, 1);
        assert_eq!(status.progress_percent, 50.5);
        assert_eq!(status.sensor1, true);
    }
}

