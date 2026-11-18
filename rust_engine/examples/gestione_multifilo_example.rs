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

    match example_update_loop(&plc, &mut ui) {
        Ok(_) => {},
        Err(e) => {
            eprintln!("Errore nel loop di aggiornamento: {}", e);
        }
    }

    println!("Disconnessione dal PLC...");
    plc.disconnect();
    println!("✓ Disconnesso con successo.");
}

fn example_update_loop(plc: &PlcClient, ui: &mut GestioneMultifiloUI) -> Result<(), String> {
    loop {
        update_gestione_multifilo(plc, ui)?;
        
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("📊 STATO GESTIONE MULTIFILO");
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("Connessa:             {}", if ui.connessa { "✓ Sì" } else { "✗ No" });
        println!("Avanzamento:          {:.1}%", ui.avanzamento);
        println!("Tempo residuo:         {} s", ui.tempo_residuo);
        println!("Allarmi:              {}", ui.allarmi);
        println!("Spreco reale:         {}", 
            ui.spreco_reale.map(|v| format!("{:.2}", v)).unwrap_or_else(|| "--".to_string()));
        println!("Tempo reale:          {}", 
            ui.tempo_reale.map(|v| format!("{:.2} s", v)).unwrap_or_else(|| "--".to_string()));
        println!("Deviazioni:           {}", 
            ui.deviazioni.as_ref().unwrap_or(&"--".to_string()));
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
        
        std::thread::sleep(Duration::from_millis(100));
    }
}







