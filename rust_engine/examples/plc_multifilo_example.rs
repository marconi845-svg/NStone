use rust_engine::plc_multifilo::{PlcClient, GestioneMultifiloUI, update_gestione_multifilo};
use std::time::Duration;

fn main() {
    let ip_address = "192.168.0.1";
    let db_number = 1;

    println!("Connessione al PLC Siemens S7-1200/S7-1500...");
    println!("IP: {}", ip_address);
    println!("Data Block: DB_Multifilo (DB{})", db_number);

    let mut plc = match PlcClient::new(ip_address, db_number) {
        Ok(client) => {
            println!("✓ Connessione al PLC stabilita con successo!");
            client
        },
        Err(e) => {
            eprintln!("✗ Errore di connessione: {}", e);
            eprintln!("Nota: Assicurati che il PLC sia raggiungibile e che l'IP sia corretto.");
            return;
        }
    };

    let mut ui = GestioneMultifiloUI::new();

    println!("\nAvvio loop di aggiornamento UI (100 ms)...");
    println!("Premi Ctrl+C per interrompere.\n");

    for iteration in 0..100 {
        match update_gestione_multifilo(&plc, &mut ui) {
            Ok(_) => {
                println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
                println!("📊 STATO MACCHINA MULTIFILO (Iterazione {})", iteration + 1);
                println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
                println!("Stato macchina:        {}", ui.machine_state);
                println!("Progresso:             {:.1}%", ui.progress_percent);
                println!("Tempo residuo:         {} s", ui.remaining_time_sec);
                println!("Codice allarme:        {}", ui.alarm_code);
                println!("Velocità filo:         {:.2} m/s", ui.wire_speed_actual);
                println!("Velocità avanzamento:  {:.2} mm/min", ui.feed_rate_actual);
                println!("Tensione:              {:.2} N", ui.tension_actual);
                println!("Contatore blocchi:     {}", ui.block_counter);
                println!("Sensore 1:             {}", if ui.sensor1 { "✓" } else { "✗" });
                println!("Sensore 2:             {}", if ui.sensor2 { "✓" } else { "✗" });
                println!("Sensore 3:             {}", if ui.sensor3 { "✓" } else { "✗" });
                println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
            },
            Err(e) => {
                eprintln!("⚠ Errore durante l'aggiornamento: {}", e);
            }
        }
        
        std::thread::sleep(Duration::from_millis(100));
    }

    println!("Disconnessione dal PLC...");
    plc.disconnect();
    println!("✓ Disconnesso con successo.");
}

