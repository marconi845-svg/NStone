use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde::{Deserialize, Serialize};
use serde_json;
use std::time::Instant;
use std::sync::Once;
use rayon::prelude::*;
use tracing::{error, info};
use tracing_subscriber::{fmt, EnvFilter};

mod plc_multifilo;
use plc_multifilo::{MachineStatus, PlcClient, GestioneMultifiloUI, read_multifilo_inputs, update_gestione_multifilo};

mod plc_engine;
use plc_engine::PyPlcEngineSession;

mod gcode_pipeline;
use gcode_pipeline::{parse_gcode, analyze_gcode, validate_gcode, optimize_gcode, GCodeProgram, GCodeMetrics, GCodeValidation};

pub mod database;
pub use database::{DatabaseActorHandle, DatabasePool, OnlineStock, Quotation, Order, Collection, Production, Administration};

static TRACING_INIT: Once = Once::new();

fn init_tracing() {
    TRACING_INIT.call_once(|| {
        let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
        let subscriber = fmt::Subscriber::builder()
            .with_env_filter(filter)
            .json()
            .finish();
        let _ = tracing::subscriber::set_global_default(subscriber);
    });
}

#[derive(Debug, Deserialize)]
struct ParallelTask {
    values: Vec<i64>,
}

#[derive(Debug, Deserialize)]
struct SimulationTask {
    steps: usize,
    intensity: usize,
}

#[derive(Debug, Deserialize)]
struct ApiTask {
    url: String,
    headers: Option<serde_json::Map<String, serde_json::Value>>,
    params: Option<serde_json::Map<String, serde_json::Value>>,
}

#[derive(Debug, Deserialize)]
struct OrdersParseTask {
    raw_text: String,
}

#[derive(Debug, Deserialize)]
struct OrdersValidateTask {
    order_data: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct ProductionSimulateTask {
    steps: usize,
    intensity: usize,
}

#[derive(Debug, Deserialize)]
struct CNCGenerateTask {
    parameters: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct GCodeAnalyzeTask {
    gcode_text: String,
}

#[derive(Debug, Deserialize)]
struct GCodeValidateTask {
    gcode_text: String,
}

#[derive(Debug, Deserialize)]
struct GCodeOptimizeTask {
    gcode_text: String,
}

#[derive(Debug, Deserialize)]
struct WasteComputeTask {
    items: Vec<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct DashboardStatsTask {
    dataset: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct TaskResult {
    status: String,
    task_type: String,
    result: serde_json::Value,
    metrics: serde_json::Value,
}

impl TaskResult {
    fn error(task_type: &str, error_msg: String) -> Self {
        TaskResult {
            status: "error".to_string(),
            task_type: task_type.to_string(),
            result: serde_json::Value::Null,
            metrics: serde_json::json!({
                "error": error_msg
            }),
        }
    }
}

#[pymodule]
fn rust_engine(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_heavy_task, m)?)?;
    m.add_class::<PyPlcClient>()?;
    m.add_class::<PyMachineStatus>()?;
    m.add_class::<PyGestioneMultifiloUI>()?;
    m.add_function(wrap_pyfunction!(read_multifilo_inputs_py, m)?)?;
    m.add_function(wrap_pyfunction!(update_gestione_multifilo_py, m)?)?;
    m.add_class::<PyPlcEngineSession>()?;
    m.add_function(wrap_pyfunction!(plc_engine_available, m)?)?;
    Ok(())
}

#[pyfunction]
fn plc_engine_available() -> bool {
    true
}

pub(crate) fn python_to_json(py: Python, obj: &PyAny) -> PyResult<serde_json::Value> {
    if obj.is_none() {
        return Ok(serde_json::Value::Null);
    }
    if let Ok(b) = obj.extract::<bool>() {
        return Ok(serde_json::Value::Bool(b));
    }
    if let Ok(i) = obj.extract::<i64>() {
        return Ok(serde_json::Value::Number(serde_json::Number::from(i)));
    }
    if let Ok(f) = obj.extract::<f64>() {
        if let Some(n) = serde_json::Number::from_f64(f) {
            return Ok(serde_json::Value::Number(n));
        }
        return Ok(serde_json::Value::Null);
    }
    if let Ok(s) = obj.extract::<String>() {
        return Ok(serde_json::Value::String(s));
    }
    if let Ok(list) = obj.downcast::<PyList>() {
        let mut arr = Vec::new();
        for item in list.iter() {
            arr.push(python_to_json(py, item)?);
        }
        return Ok(serde_json::Value::Array(arr));
    }
    if let Ok(dict) = obj.downcast::<PyDict>() {
        let mut map = serde_json::Map::new();
        for (key, value) in dict.iter() {
            let k: String = key.extract()?;
            let v = python_to_json(py, value)?;
            map.insert(k, v);
        }
        return Ok(serde_json::Value::Object(map));
    }
    Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>("Unsupported type"))
}

#[pyfunction]
fn run_heavy_task(task_type: &str, payload: &PyAny) -> PyResult<PyObject> {
    init_tracing();
    let start = Instant::now();
    
    let py = payload.py();
    let payload_json = python_to_json(py, payload)?;
    let trace_id = payload_json
        .as_object()
        .and_then(|obj| obj.get("trace_id"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    info!(task_type = %task_type, trace_id = %trace_id, event = "rust.task.started");
    
    let result = match task_type {
        "test_parallel" => {
            let task: ParallelTask = serde_json::from_value(payload_json.clone())
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid parallel task: {}", e)))?;
            
            let compute_start = Instant::now();
            let processed: Vec<i64> = task.values
                .into_par_iter()
                .map(|x| x * x + 1)
                .collect();
            let compute_time = compute_start.elapsed();
            
            let sum: i64 = processed.par_iter().sum();
            let max = processed.par_iter().max().copied().unwrap_or(0);
            
            let metrics = serde_json::json!({
                "compute_time_ms": compute_time.as_millis(),
                "items_processed": processed.len(),
                "sum": sum,
                "max": max
            });
            
            TaskResult {
                status: "ok".to_string(),
                task_type: task_type.to_string(),
                result: serde_json::json!({
                    "sum": sum,
                    "max": max,
                    "sample": processed.iter().take(10).collect::<Vec<_>>()
                }),
                metrics,
            }
        },
        "fake_simulation" => {
            let task: SimulationTask = serde_json::from_value(payload_json.clone())
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid simulation task: {}", e)))?;
            
            let compute_start = Instant::now();
            let threads_used = rayon::current_num_threads();
            let results: Vec<f64> = (0..task.steps)
                .into_par_iter()
                .map(|i| {
                    let mut acc = 0.0;
                    for _ in 0..task.intensity {
                        acc += (i as f64).sin().cos() * 2.0;
                    }
                    acc
                })
                .collect();
            let compute_time = compute_start.elapsed();
            
            let total: f64 = results.par_iter().sum();
            
            let metrics = serde_json::json!({
                "compute_time_ms": compute_time.as_millis(),
                "steps_processed": results.len(),
                "intensity": task.intensity,
                "threads_used": threads_used
            });
            
            TaskResult {
                status: "ok".to_string(),
                task_type: task_type.to_string(),
                result: serde_json::json!({
                    "total": total,
                    "steps": results.len()
                }),
                metrics,
            }
        },
        "quotations_api" => {
            let task_result = match serde_json::from_value::<ApiTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    let client = reqwest::blocking::Client::new();
                    let mut request = client.get(&task.url);
                    
                    if let Some(ref headers) = task.headers {
                        for (key, value) in headers {
                            if let Some(header_value) = value.as_str() {
                                request = request.header(key, header_value);
                            }
                        }
                    }
                    
                    if let Some(ref params) = task.params {
                        for (key, value) in params {
                            if let Some(param_value) = value.as_str() {
                                request = request.query(&[(key, param_value)]);
                            } else {
                                request = request.query(&[(key, &value.to_string())]);
                            }
                        }
                    }
                    
                    match request.send() {
                        Ok(response) => {
                            let status_code = response.status().as_u16();
                            if response.status().is_success() {
                                match response.json::<serde_json::Value>() {
                                    Ok(json_data) => {
                                        let compute_time = compute_start.elapsed();
                                        
                                        let metrics = serde_json::json!({
                                            "duration_ms": compute_time.as_millis(),
                                            "status_code": status_code
                                        });
                                        
                                        TaskResult {
                                            status: "ok".to_string(),
                                            task_type: task_type.to_string(),
                                            result: json_data,
                                            metrics,
                                        }
                                    },
                                    Err(e) => {
                                        TaskResult {
                                            status: "error".to_string(),
                                            task_type: task_type.to_string(),
                                            result: serde_json::Value::Null,
                                            metrics: serde_json::json!({
                                                "error": format!("JSON parsing error: {}", e)
                                            }),
                                        }
                                    }
                                }
                            } else {
                                let status = response.status();
                                TaskResult {
                                    status: "error".to_string(),
                                    task_type: task_type.to_string(),
                                    result: serde_json::Value::Null,
                                    metrics: serde_json::json!({
                                        "error": format!("HTTP error: {} {}", status.as_u16(), status.as_str())
                                    }),
                                }
                            }
                        },
                        Err(e) => {
                            TaskResult {
                                status: "error".to_string(),
                                task_type: task_type.to_string(),
                                result: serde_json::Value::Null,
                                metrics: serde_json::json!({
                                    "error": format!("Request error: {}", e)
                                }),
                            }
                        }
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid API task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "orders_parse" => {
            let task_result = match serde_json::from_value::<OrdersParseTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    let words: Vec<&str> = task.raw_text.split_whitespace().collect();
                    let lines: Vec<&str> = task.raw_text.lines().collect();
                    
                    let mut extracted = serde_json::Map::new();
                    extracted.insert("word_count".to_string(), serde_json::Value::Number(serde_json::Number::from(words.len())));
                    extracted.insert("line_count".to_string(), serde_json::Value::Number(serde_json::Number::from(lines.len())));
                    extracted.insert("char_count".to_string(), serde_json::Value::Number(serde_json::Number::from(task.raw_text.len())));
                    
                    let numbers: Vec<f64> = words.iter()
                        .filter_map(|w| w.parse::<f64>().ok())
                        .collect();
                    
                    if !numbers.is_empty() {
                        let sum: f64 = numbers.iter().sum();
                        let avg = sum / numbers.len() as f64;
                        extracted.insert("numbers_found".to_string(), serde_json::Value::Number(serde_json::Number::from(numbers.len())));
                        extracted.insert("numbers_sum".to_string(), serde_json::json!(sum));
                        extracted.insert("numbers_avg".to_string(), serde_json::json!(avg));
                    }
                    
                    let compute_time = compute_start.elapsed();
                    
                    TaskResult {
                        status: "ok".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Object(extracted),
                        metrics: serde_json::json!({
                            "duration_ms": compute_time.as_millis()
                        }),
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "orders_validate" => {
            let task_result = match serde_json::from_value::<OrdersValidateTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    let mut errors = Vec::new();
                    let mut warnings = Vec::new();
                    
                    if let serde_json::Value::Object(ref obj) = task.order_data {
                        if !obj.contains_key("id") {
                            errors.push("Missing 'id' field");
                        }
                        if !obj.contains_key("status") {
                            errors.push("Missing 'status' field");
                        }
                        if let Some(serde_json::Value::String(ref status)) = obj.get("status") {
                            if !["pending", "processing", "completed", "cancelled"].contains(&status.as_str()) {
                                warnings.push(format!("Unknown status: {}", status));
                            }
                        }
                    } else {
                        errors.push("order_data must be an object");
                    }
                    
                    let compute_time = compute_start.elapsed();
                    
                    TaskResult {
                        status: if errors.is_empty() { "ok".to_string() } else { "error".to_string() },
                        task_type: task_type.to_string(),
                        result: serde_json::json!({
                            "valid": errors.is_empty(),
                            "errors": errors,
                            "warnings": warnings
                        }),
                        metrics: serde_json::json!({
                            "duration_ms": compute_time.as_millis()
                        }),
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "production_simulate" => {
            let task_result = match serde_json::from_value::<ProductionSimulateTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    let threads_used = rayon::current_num_threads();
                    let results: Vec<f64> = (0..task.steps)
                        .into_par_iter()
                        .map(|i| {
                            let mut acc = 0.0;
                            for _ in 0..task.intensity {
                                acc += (i as f64).sin().cos() * 2.0;
                            }
                            acc
                        })
                        .collect();
                    let compute_time = compute_start.elapsed();
                    
                    let total: f64 = results.par_iter().sum();
                    let avg = total / results.len() as f64;
                    let max = results.par_iter().fold(|| 0.0f64, |a, &b| a.max(b)).reduce(|| 0.0f64, |a, b| a.max(b));
                    let min = results.par_iter().fold(|| f64::INFINITY, |a, &b| a.min(b)).reduce(|| f64::INFINITY, |a, b| a.min(b));
                    
                    TaskResult {
                        status: "ok".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::json!({
                            "total": total,
                            "avg": avg,
                            "max": max,
                            "min": min,
                            "steps": results.len()
                        }),
                        metrics: serde_json::json!({
                            "duration_ms": compute_time.as_millis(),
                            "threads_used": threads_used,
                            "steps_processed": results.len()
                        }),
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "cnc_generate" => {
            let task_result = match serde_json::from_value::<CNCGenerateTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    let mut gcode_lines = Vec::new();
                    gcode_lines.push("G21".to_string());
                    gcode_lines.push("G90".to_string());
                    
                    if let serde_json::Value::Object(ref params) = task.parameters {
                        if let Some(serde_json::Value::Number(ref x)) = params.get("x") {
                            if let Some(x_val) = x.as_f64() {
                                gcode_lines.push(format!("G0 X{}", x_val));
                            }
                        }
                        if let Some(serde_json::Value::Number(ref y)) = params.get("y") {
                            if let Some(y_val) = y.as_f64() {
                                gcode_lines.push(format!("G0 Y{}", y_val));
                            }
                        }
                        if let Some(serde_json::Value::Number(ref z)) = params.get("z") {
                            if let Some(z_val) = z.as_f64() {
                                gcode_lines.push(format!("G0 Z{}", z_val));
                            }
                        }
                        if let Some(serde_json::Value::Number(ref speed)) = params.get("speed") {
                            if let Some(speed_val) = speed.as_f64() {
                                gcode_lines.push(format!("F{}", speed_val));
                            }
                        }
                    }
                    
                    gcode_lines.push("M30".to_string());
                    
                    let compute_time = compute_start.elapsed();
                    
                    TaskResult {
                        status: "ok".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::json!({
                            "gcode": gcode_lines.join("\n"),
                            "line_count": gcode_lines.len()
                        }),
                        metrics: serde_json::json!({
                            "duration_ms": compute_time.as_millis()
                        }),
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "waste_compute" => {
            let task_result = match serde_json::from_value::<WasteComputeTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    let mut total_weight = 0.0;
                    let mut total_volume = 0.0;
                    let mut item_count = 0;
                    
                    for item in &task.items {
                        if let serde_json::Value::Object(ref obj) = item {
                            if let Some(serde_json::Value::Number(ref weight)) = obj.get("weight") {
                                if let Some(w) = weight.as_f64() {
                                    total_weight += w;
                                }
                            }
                            if let Some(serde_json::Value::Number(ref volume)) = obj.get("volume") {
                                if let Some(v) = volume.as_f64() {
                                    total_volume += v;
                                }
                            }
                            item_count += 1;
                        }
                    }
                    
                    let compute_time = compute_start.elapsed();
                    
                    TaskResult {
                        status: "ok".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::json!({
                            "total_weight": total_weight,
                            "total_volume": total_volume,
                            "item_count": item_count,
                            "avg_weight": if item_count > 0 { total_weight / item_count as f64 } else { 0.0 },
                            "avg_volume": if item_count > 0 { total_volume / item_count as f64 } else { 0.0 }
                        }),
                        metrics: serde_json::json!({
                            "duration_ms": compute_time.as_millis(),
                            "items_processed": item_count
                        }),
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "dashboard_stats" => {
            let task_result = match serde_json::from_value::<DashboardStatsTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    let mut stats = serde_json::Map::new();
                    
                    if let serde_json::Value::Object(ref dataset) = task.dataset {
                        let mut total = 0.0;
                        let mut count = 0;
                        let mut values = Vec::new();
                        
                        for (key, value) in dataset {
                            if let serde_json::Value::Number(ref num) = value {
                                if let Some(n) = num.as_f64() {
                                    total += n;
                                    count += 1;
                                    values.push(n);
                                }
                            }
                        }
                        
                        if count > 0 {
                            let avg = total / count as f64;
                            values.sort_by(|a, b| a.partial_cmp(b).unwrap());
                            let median = if values.len() % 2 == 0 {
                                (values[values.len() / 2 - 1] + values[values.len() / 2]) / 2.0
                            } else {
                                values[values.len() / 2]
                            };
                            
                            stats.insert("total".to_string(), serde_json::json!(total));
                            stats.insert("count".to_string(), serde_json::Value::Number(serde_json::Number::from(count)));
                            stats.insert("avg".to_string(), serde_json::json!(avg));
                            stats.insert("median".to_string(), serde_json::json!(median));
                            stats.insert("min".to_string(), serde_json::json!(values[0]));
                            stats.insert("max".to_string(), serde_json::json!(values[values.len() - 1]));
                        }
                    }
                    
                    let compute_time = compute_start.elapsed();
                    
                    TaskResult {
                        status: "ok".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Object(stats),
                        metrics: serde_json::json!({
                            "duration_ms": compute_time.as_millis()
                        }),
                    }
                },
                Err(e) => {
                    TaskResult {
                        status: "error".to_string(),
                        task_type: task_type.to_string(),
                        result: serde_json::Value::Null,
                        metrics: serde_json::json!({
                            "error": format!("Invalid task: {}", e)
                        }),
                    }
                }
            };
            task_result
        },
        "gcode_analyze" => {
            let task_result = match serde_json::from_value::<GCodeAnalyzeTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    match parse_gcode(&task.gcode_text) {
                        Ok(program) => {
                            let metrics = analyze_gcode(&program);
                            let compute_time = compute_start.elapsed();
                            
                            TaskResult {
                                status: "ok".to_string(),
                                task_type: task_type.to_string(),
                                result: serde_json::json!({
                                    "total_commands": metrics.total_commands,
                                    "movement_commands": metrics.movement_commands,
                                    "rapid_moves": metrics.rapid_moves,
                                    "linear_moves": metrics.linear_moves,
                                    "circular_moves": metrics.circular_moves,
                                    "estimated_time_sec": metrics.estimated_time_sec,
                                    "total_distance_mm": metrics.total_distance_mm,
                                    "max_feedrate": metrics.max_feedrate,
                                    "min_feedrate": metrics.min_feedrate,
                                    "avg_feedrate": metrics.avg_feedrate,
                                    "tool_changes": metrics.tool_changes,
                                    "coordinate_system": metrics.coordinate_system,
                                    "units": metrics.units,
                                }),
                                metrics: serde_json::json!({
                                    "duration_ms": compute_time.as_millis(),
                                    "lines_parsed": program.total_lines,
                                }),
                            }
                        },
                        Err(e) => TaskResult::error(task_type, format!("Failed to parse G-code: {}", e)),
                    }
                },
                Err(e) => TaskResult::error(task_type, format!("Invalid gcode_analyze task: {}", e)),
            };
            task_result
        },
        "gcode_validate" => {
            let task_result = match serde_json::from_value::<GCodeValidateTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    match parse_gcode(&task.gcode_text) {
                        Ok(program) => {
                            let validation = validate_gcode(&program);
                            let compute_time = compute_start.elapsed();
                            
                            TaskResult {
                                status: "ok".to_string(),
                                task_type: task_type.to_string(),
                                result: serde_json::json!({
                                    "is_valid": validation.is_valid,
                                    "errors": validation.errors,
                                    "warnings": validation.warnings,
                                    "safety_checks": {
                                        "has_home_command": validation.safety_checks.has_home_command,
                                        "has_units_set": validation.safety_checks.has_units_set,
                                        "has_coordinate_system": validation.safety_checks.has_coordinate_system,
                                        "has_program_end": validation.safety_checks.has_program_end,
                                        "feedrate_defined": validation.safety_checks.feedrate_defined,
                                        "rapid_moves_safe": validation.safety_checks.rapid_moves_safe,
                                    },
                                }),
                                metrics: serde_json::json!({
                                    "duration_ms": compute_time.as_millis(),
                                    "error_count": validation.errors.len(),
                                    "warning_count": validation.warnings.len(),
                                }),
                            }
                        },
                        Err(e) => TaskResult::error(task_type, format!("Failed to parse G-code: {}", e)),
                    }
                },
                Err(e) => TaskResult::error(task_type, format!("Invalid gcode_validate task: {}", e)),
            };
            task_result
        },
        "gcode_optimize" => {
            let task_result = match serde_json::from_value::<GCodeOptimizeTask>(payload_json.clone()) {
                Ok(task) => {
                    let compute_start = Instant::now();
                    
                    match parse_gcode(&task.gcode_text) {
                        Ok(program) => {
                            let optimized = optimize_gcode(&program);
                            let compute_time = compute_start.elapsed();
                            
                            let optimized_text = optimized.commands.iter()
                                .map(|cmd| {
                                    let mut line = String::new();
                                    if !cmd.command.is_empty() && cmd.command != "MISC" {
                                        line.push_str(&cmd.command);
                                    }
                                    for (key, val) in &cmd.parameters {
                                        line.push_str(&format!(" {}{}", key, val));
                                    }
                                    if let Some(comment) = &cmd.comment {
                                        line.push_str(&format!(" ; {}", comment));
                                    }
                                    line
                                })
                                .collect::<Vec<_>>()
                                .join("\n");
                            
                            TaskResult {
                                status: "ok".to_string(),
                                task_type: task_type.to_string(),
                                result: serde_json::json!({
                                    "optimized_gcode": optimized_text,
                                    "original_commands": program.commands.len(),
                                    "optimized_commands": optimized.commands.len(),
                                    "reduction_percent": if program.commands.len() > 0 {
                                        ((program.commands.len() - optimized.commands.len()) as f64 / program.commands.len() as f64) * 100.0
                                    } else {
                                        0.0
                                    },
                                }),
                                metrics: serde_json::json!({
                                    "duration_ms": compute_time.as_millis(),
                                }),
                            }
                        },
                        Err(e) => TaskResult::error(task_type, format!("Failed to parse G-code: {}", e)),
                    }
                },
                Err(e) => TaskResult::error(task_type, format!("Invalid gcode_optimize task: {}", e)),
            };
            task_result
        },
        _ => {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Unknown task_type: {}", task_type)
            ));
        }
    };
    
    let elapsed = start.elapsed();
    if result.status == "error" {
        error!(
            task_type = %task_type,
            trace_id = %trace_id,
            duration_ms = elapsed.as_millis() as u64,
            event = "rust.task.failed"
        );
    } else {
        info!(
            task_type = %task_type,
            trace_id = %trace_id,
            duration_ms = elapsed.as_millis() as u64,
            event = "rust.task.completed"
        );
    }
    let mut final_result = serde_json::to_value(&result).unwrap();
    
    if let serde_json::Value::Object(ref mut obj) = final_result {
        if result.status == "error" {
            if let Some(serde_json::Value::Object(ref metrics)) = obj.get("metrics") {
                if let Some(serde_json::Value::String(ref error_msg)) = metrics.get("error") {
                    let error_msg_clone = error_msg.clone();
                    obj.insert("error".to_string(), serde_json::Value::String(error_msg_clone));
                    if let Some(serde_json::Value::Object(ref mut metrics_mut)) = obj.get_mut("metrics") {
                        metrics_mut.remove("error");
                    }
                }
            }
        } else {
            if let Some(serde_json::Value::Object(ref mut metrics)) = obj.get_mut("metrics") {
                metrics.insert("total_time_ms".to_string(), serde_json::Value::Number(serde_json::Number::from(elapsed.as_millis() as u64)));
            }
            if let Some(data) = obj.remove("result") {
                obj.insert("data".to_string(), data);
            }
        }
    }
    
    let dict = PyDict::new(py);
    if let serde_json::Value::Object(map) = final_result {
        for (k, v) in map {
            let py_val: PyObject = serde_json_to_python(py, &v)?;
            dict.set_item(k, py_val)?;
        }
    }
    Ok(dict.to_object(py))
}

fn serde_json_to_python(py: Python, value: &serde_json::Value) -> PyResult<PyObject> {
    match value {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(b) => Ok(b.to_object(py)),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.to_object(py))
            } else {
                Ok(n.to_string().to_object(py))
            }
        },
        serde_json::Value::String(s) => Ok(s.to_object(py)),
        serde_json::Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(serde_json_to_python(py, item)?)?;
            }
            Ok(list.to_object(py))
        },
        serde_json::Value::Object(obj) => {
            let dict = PyDict::new(py);
            for (k, v) in obj {
                dict.set_item(k, serde_json_to_python(py, v)?)?;
            }
            Ok(dict.to_object(py))
        },
    }
}

#[pyclass]
pub struct PyPlcClient {
    client: PlcClient,
}

#[pymethods]
impl PyPlcClient {
    #[new]
    fn new(ip_address: &str, db_number: i32) -> PyResult<Self> {
        match PlcClient::new(ip_address, db_number) {
            Ok(client) => Ok(PyPlcClient { client }),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyConnectionError, _>(e)),
        }
    }

    fn disconnect(&mut self) {
        self.client.disconnect();
    }
}

#[pyclass]
#[derive(Clone)]
pub struct PyMachineStatus {
    #[pyo3(get, set)]
    pub machine_state: i32,
    #[pyo3(get, set)]
    pub progress_percent: f32,
    #[pyo3(get, set)]
    pub remaining_time_sec: i32,
    #[pyo3(get, set)]
    pub alarm_code: i32,
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
}

#[pyfunction]
fn read_multifilo_inputs_py(plc: &PyPlcClient) -> PyResult<PyMachineStatus> {
    match read_multifilo_inputs(&plc.client) {
        Ok(status) => Ok(PyMachineStatus {
            machine_state: status.machine_state,
            progress_percent: status.progress_percent,
            remaining_time_sec: status.remaining_time_sec,
            alarm_code: status.alarm_code,
            wire_speed_actual: status.wire_speed_actual,
            feed_rate_actual: status.feed_rate_actual,
            tension_actual: status.tension_actual,
            block_counter: status.block_counter,
            sensor1: status.sensor1,
            sensor2: status.sensor2,
            sensor3: status.sensor3,
        }),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyIOError, _>(e)),
    }
}

#[pyclass]
pub struct PyGestioneMultifiloUI {
    ui: GestioneMultifiloUI,
}

#[pymethods]
impl PyGestioneMultifiloUI {
    #[new]
    fn new() -> Self {
        PyGestioneMultifiloUI {
            ui: GestioneMultifiloUI::new(),
        }
    }

    #[getter]
    fn connessa(&self) -> bool {
        self.ui.connessa
    }

    #[getter]
    fn avanzamento(&self) -> f32 {
        self.ui.avanzamento
    }

    #[getter]
    fn tempo_residuo(&self) -> i32 {
        self.ui.tempo_residuo
    }

    #[getter]
    fn allarmi(&self) -> i32 {
        self.ui.allarmi
    }

    #[getter]
    fn spreco_reale(&self) -> Option<f32> {
        self.ui.spreco_reale
    }

    #[getter]
    fn tempo_reale(&self) -> Option<f32> {
        self.ui.tempo_reale
    }

    #[getter]
    fn deviazioni(&self) -> Option<String> {
        self.ui.deviazioni.clone()
    }
}

#[pyfunction]
fn update_gestione_multifilo_py(plc: &PyPlcClient, ui: &mut PyGestioneMultifiloUI) -> PyResult<()> {
    match update_gestione_multifilo(&plc.client, &mut ui.ui) {
        Ok(_) => Ok(()),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyIOError, _>(e)),
    }
}

