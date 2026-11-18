use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GCodeCommand {
    pub line_number: Option<usize>,
    pub command: String,
    pub parameters: HashMap<String, f64>,
    pub comment: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GCodeProgram {
    pub commands: Vec<GCodeCommand>,
    pub total_lines: usize,
    pub raw_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GCodeMetrics {
    pub total_commands: usize,
    pub movement_commands: usize,
    pub rapid_moves: usize,
    pub linear_moves: usize,
    pub circular_moves: usize,
    pub estimated_time_sec: f64,
    pub total_distance_mm: f64,
    pub max_feedrate: f64,
    pub min_feedrate: f64,
    pub avg_feedrate: f64,
    pub tool_changes: usize,
    pub coordinate_system: String,
    pub units: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GCodeValidation {
    pub is_valid: bool,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
    pub safety_checks: SafetyChecks,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyChecks {
    pub has_home_command: bool,
    pub has_units_set: bool,
    pub has_coordinate_system: bool,
    pub has_program_end: bool,
    pub feedrate_defined: bool,
    pub rapid_moves_safe: bool,
}

pub fn parse_gcode(gcode_text: &str) -> Result<GCodeProgram, String> {
    let lines: Vec<&str> = gcode_text.lines().collect();
    let mut commands = Vec::new();
    
    for (idx, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('(') {
            continue;
        }
        
        let parts: Vec<&str> = trimmed.split(';').collect();
        let code_part = parts[0].trim();
        let comment = if parts.len() > 1 {
            Some(parts[1..].join(";").trim().to_string())
        } else {
            None
        };
        
        if code_part.is_empty() {
            continue;
        }
        
        let mut command = String::new();
        let mut parameters: HashMap<String, f64> = HashMap::new();
        let mut chars = code_part.chars().peekable();
        let mut current_token = String::new();
        let mut current_letter: Option<char> = None;
        
        while let Some(ch) = chars.next() {
            if ch.is_alphabetic() {
                if !current_token.is_empty() && current_letter.is_some() {
                    if let Ok(val) = current_token.parse::<f64>() {
                        parameters.insert(current_letter.unwrap().to_string(), val);
                    }
                }
                current_letter = Some(ch.to_uppercase().next().unwrap());
                current_token.clear();
                if command.is_empty() {
                    command.push(ch.to_uppercase().next().unwrap());
                }
            } else if ch.is_ascii_digit() || ch == '.' || ch == '-' {
                current_token.push(ch);
            }
        }
        
        if !current_token.is_empty() && current_letter.is_some() {
            if let Ok(val) = current_token.parse::<f64>() {
                parameters.insert(current_letter.unwrap().to_string(), val);
            }
        }
        
        if !command.is_empty() || !parameters.is_empty() {
            commands.push(GCodeCommand {
                line_number: Some(idx + 1),
                command: if command.is_empty() { "MISC".to_string() } else { command },
                parameters,
                comment,
            });
        }
    }
    
    Ok(GCodeProgram {
        commands,
        total_lines: lines.len(),
        raw_text: gcode_text.to_string(),
    })
}

pub fn analyze_gcode(program: &GCodeProgram) -> GCodeMetrics {
    let mut movement_commands = 0;
    let mut rapid_moves = 0;
    let mut linear_moves = 0;
    let mut circular_moves = 0;
    let mut total_distance = 0.0;
    let mut feedrates = Vec::new();
    let mut tool_changes = 0;
    let mut coordinate_system = "G54".to_string();
    let mut units = "mm".to_string();
    
    let mut current_x = 0.0;
    let mut current_y = 0.0;
    let mut current_z = 0.0;
    let mut current_feedrate = 0.0;
    
    for cmd in &program.commands {
        let cmd_upper = cmd.command.to_uppercase();
        
        if cmd_upper.starts_with('G') {
            if let Some(g_num) = cmd_upper.strip_prefix('G') {
                if let Ok(g_code) = g_num.parse::<usize>() {
                    match g_code {
                        0 => {
                            rapid_moves += 1;
                            movement_commands += 1;
                        },
                        1 => {
                            linear_moves += 1;
                            movement_commands += 1;
                        },
                        2 | 3 => {
                            circular_moves += 1;
                            movement_commands += 1;
                        },
                        20 => units = "inch".to_string(),
                        21 => units = "mm".to_string(),
                        54..=59 => {
                            coordinate_system = format!("G{}", g_code);
                        },
                        _ => {}
                    }
                }
            }
        }
        
        if cmd_upper.starts_with('M') {
            if let Some(m_num) = cmd_upper.strip_prefix('M') {
                if let Ok(m_code) = m_num.parse::<usize>() {
                    if m_code == 6 {
                        tool_changes += 1;
                    }
                }
            }
        }
        
        if let Some(f) = cmd.parameters.get("F") {
            current_feedrate = *f;
            feedrates.push(*f);
        }
        
        if let Some(x) = cmd.parameters.get("X") {
            let dx = (x - current_x).abs();
            current_x = *x;
            total_distance += dx;
        }
        if let Some(y) = cmd.parameters.get("Y") {
            let dy = (y - current_y).abs();
            current_y = *y;
            total_distance += dy;
        }
        if let Some(z) = cmd.parameters.get("Z") {
            let dz = (z - current_z).abs();
            current_z = *z;
            total_distance += dz;
        }
    }
    
    let max_feedrate = feedrates.iter().fold(0.0f64, |a, &b| a.max(b));
    let min_feedrate = if feedrates.is_empty() {
        0.0
    } else {
        feedrates.iter().fold(f64::INFINITY, |a, &b| a.min(b))
    };
    let avg_feedrate = if feedrates.is_empty() {
        0.0
    } else {
        feedrates.iter().sum::<f64>() / feedrates.len() as f64
    };
    
    let estimated_time = if avg_feedrate > 0.0 {
        total_distance / (avg_feedrate / 60.0)
    } else {
        0.0
    };
    
    GCodeMetrics {
        total_commands: program.commands.len(),
        movement_commands,
        rapid_moves,
        linear_moves,
        circular_moves,
        estimated_time_sec: estimated_time,
        total_distance_mm: total_distance,
        max_feedrate,
        min_feedrate,
        avg_feedrate,
        tool_changes,
        coordinate_system,
        units,
    }
}

pub fn validate_gcode(program: &GCodeProgram) -> GCodeValidation {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    
    let mut has_home = false;
    let mut has_units = false;
    let mut has_coord_sys = false;
    let mut has_program_end = false;
    let mut feedrate_defined = false;
    let mut rapid_moves_safe = true;
    
    for cmd in &program.commands {
        let cmd_upper = cmd.command.to_uppercase();
        
        if cmd_upper == "G28" || cmd_upper.contains("G28") {
            has_home = true;
        }
        
        if cmd_upper == "G20" || cmd_upper == "G21" {
            has_units = true;
        }
        
        if cmd_upper.starts_with("G5") && cmd_upper.len() > 1 {
            has_coord_sys = true;
        }
        
        if cmd_upper == "M30" || cmd_upper == "M02" {
            has_program_end = true;
        }
        
        if cmd.parameters.contains_key("F") {
            feedrate_defined = true;
        }
        
        if cmd_upper == "G0" {
            if !cmd.parameters.contains_key("Z") && !has_home {
                warnings.push("Rapid move senza comando home precedente".to_string());
            }
        }
        
        if cmd_upper == "G1" && !cmd.parameters.contains_key("F") {
            warnings.push(format!("Comando G1 alla linea {} senza feedrate definito", 
                cmd.line_number.unwrap_or(0)));
        }
    }
    
    if !has_units {
        errors.push("Nessun comando di unità (G20/G21) trovato".to_string());
    }
    
    if !has_program_end {
        warnings.push("Nessun comando di fine programma (M30/M02) trovato".to_string());
    }
    
    if !feedrate_defined && program.commands.iter().any(|c| c.command.to_uppercase() == "G1") {
        warnings.push("Comandi di movimento lineare senza feedrate definito".to_string());
    }
    
    let safety_checks = SafetyChecks {
        has_home_command: has_home,
        has_units_set: has_units,
        has_coordinate_system: has_coord_sys,
        has_program_end,
        feedrate_defined,
        rapid_moves_safe,
    };
    
    GCodeValidation {
        is_valid: errors.is_empty(),
        errors,
        warnings,
        safety_checks,
    }
}

pub fn optimize_gcode(program: &GCodeProgram) -> GCodeProgram {
    let mut optimized_commands = Vec::new();
    let mut last_feedrate: Option<f64> = None;
    let mut last_coordinate_system = "G54".to_string();
    let mut units_set = false;
    
    for cmd in &program.commands {
        let cmd_upper = cmd.command.to_uppercase();
        let mut new_cmd = cmd.clone();
        
        if cmd_upper == "G20" || cmd_upper == "G21" {
            if !units_set {
                optimized_commands.push(new_cmd);
                units_set = true;
            }
            continue;
        }
        
        if cmd_upper.starts_with("G5") && cmd_upper.len() > 1 {
            if cmd_upper != last_coordinate_system {
                optimized_commands.push(new_cmd);
                last_coordinate_system = cmd_upper.clone();
            }
            continue;
        }
        
        if cmd_upper == "G1" || cmd_upper == "G2" || cmd_upper == "G3" {
            if let Some(f) = cmd.parameters.get("F") {
                last_feedrate = Some(*f);
            } else if let Some(f) = last_feedrate {
                new_cmd.parameters.insert("F".to_string(), f);
            }
        }
        
        optimized_commands.push(new_cmd);
    }
    
    GCodeProgram {
        commands: optimized_commands,
        total_lines: program.total_lines,
        raw_text: program.raw_text.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_gcode() {
        let gcode = "G21\nG90\nG0 X10 Y20\nG1 X20 F100\nM30";
        let program = parse_gcode(gcode).unwrap();
        assert_eq!(program.commands.len(), 5);
    }

    #[test]
    fn test_analyze_gcode() {
        let gcode = "G21\nG90\nG0 X10 Y20\nG1 X20 F100\nM30";
        let program = parse_gcode(gcode).unwrap();
        let metrics = analyze_gcode(&program);
        assert_eq!(metrics.rapid_moves, 1);
        assert_eq!(metrics.linear_moves, 1);
    }
}



