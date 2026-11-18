//! Motore PLC on-demand: read chunk Snap7, decode plant/sim, decode parallelo (rayon).

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use rayon::prelude::*;
use serde::Deserialize;
use serde_json::{Map, Value};
use snap7_rs::S7Client;
use std::time::Instant;

const CHUNK_SIZE: i32 = 240;

#[derive(Debug, Clone, Deserialize)]
struct VarSpec {
    name: String,
    offset: i32,
    #[serde(rename = "type")]
    var_type: String,
}

#[derive(Debug, Clone, Deserialize)]
struct BlockRequest {
    db_number: i32,
    size_bytes: i32,
    variables: Vec<VarSpec>,
}

#[derive(Debug, Clone, Deserialize)]
struct ExploreRequest {
    db_number: i32,
    size_bytes: i32,
    variables: Vec<VarSpec>,
}

#[derive(Debug, Clone, Deserialize)]
struct PollPlan {
    blocks: Vec<BlockRequest>,
    explore: Option<ExploreRequest>,
    #[serde(default = "default_parallel_limit")]
    parallel_limit: usize,
}

fn default_parallel_limit() -> usize {
    3
}

pub struct PlcEngineSession {
    client: S7Client,
    connected: bool,
}

impl PlcEngineSession {
    pub fn connect(ip: &str, rack: i32, slot: i32) -> Result<Self, String> {
        let mut client = S7Client::create();
        client
            .connect_to(ip, rack, slot)
            .map_err(|e| format!("Snap7 connect failed: {:?}", e))?;
        Ok(PlcEngineSession {
            client,
            connected: true,
        })
    }

    pub fn disconnect(&mut self) {
        if self.connected {
            let _ = self.client.disconnect();
            self.connected = false;
        }
    }

    pub fn is_connected(&self) -> bool {
        let mut flag = 0i32;
        match self.client.get_connected(&mut flag) {
            Ok(_) => flag != 0,
            Err(_) => false,
        }
    }

    fn read_db_chunked(&self, db_number: i32, total_size: i32) -> Result<Vec<u8>, String> {
        if total_size <= 0 {
            return Ok(Vec::new());
        }
        let mut out = Vec::with_capacity(total_size as usize);
        let mut pos = 0i32;
        while pos < total_size {
            let chunk = CHUNK_SIZE.min(total_size - pos);
            let mut buf = vec![0u8; chunk as usize];
            self.client
                .db_read(db_number, pos, chunk, &mut buf)
                .map_err(|e| format!("db_read DB{} @{}: {:?}", db_number, pos, e))?;
            out.extend_from_slice(&buf);
            pos += chunk;
        }
        Ok(out)
    }

    fn decode_variable(data: &[u8], offset: i32, var_type: &str) -> Value {
        let off = offset as usize;
        match var_type.to_uppercase().as_str() {
            "BOOL" => {
                if off >= data.len() {
                    Value::Null
                } else {
                    Value::Bool(data[off] != 0)
                }
            }
            "BYTE" => {
                if off >= data.len() {
                    Value::Null
                } else {
                    Value::Number((data[off] as i64).into())
                }
            }
            "INT" => {
                if off + 2 > data.len() {
                    Value::Null
                } else {
                    let v = i16::from_le_bytes([data[off], data[off + 1]]) as i64;
                    Value::Number(v.into())
                }
            }
            "REAL" => {
                if off + 4 > data.len() {
                    Value::Null
                } else {
                    let v = f32::from_le_bytes([
                        data[off],
                        data[off + 1],
                        data[off + 2],
                        data[off + 3],
                    ]);
                    serde_json::Number::from_f64(v as f64)
                        .map(Value::Number)
                        .unwrap_or(Value::Null)
                }
            }
            _ => Value::Null,
        }
    }

    fn decode_variables(data: &[u8], variables: &[VarSpec]) -> Map<String, Value> {
        let mut map = Map::new();
        for var in variables {
            map.insert(
                var.name.clone(),
                Self::decode_variable(data, var.offset, &var.var_type),
            );
        }
        map
    }

    pub fn poll_snapshot(&self, plan: &PollPlan) -> Result<Value, String> {
        let t0 = Instant::now();
        let mut db_sizes = Map::new();
        let mut size_sources = Map::new();

        let mut raw_blocks: Vec<(BlockRequest, Vec<u8>)> =
            Vec::with_capacity(plan.blocks.len());
        for block in &plan.blocks {
            let size = block.size_bytes.max(0);
            let raw = self.read_db_chunked(block.db_number, size)?;
            db_sizes.insert(
                block.db_number.to_string(),
                Value::Number((raw.len() as i64).into()),
            );
            size_sources.insert(
                block.db_number.to_string(),
                Value::String("rust".into()),
            );
            raw_blocks.push((block.clone(), raw));
        }

        let parallel = plan.parallel_limit.max(1);
        let blocks_map: Map<String, Value> = if parallel > 1 && raw_blocks.len() > 1 {
            raw_blocks
                .par_iter()
                .map(|(req, raw)| {
                    let decoded = Self::decode_variables(raw, &req.variables);
                    (req.db_number.to_string(), Value::Object(decoded))
                })
                .collect::<Vec<_>>()
                .into_iter()
                .collect()
        } else {
            raw_blocks
                .iter()
                .map(|(req, raw)| {
                    let decoded = Self::decode_variables(raw, &req.variables);
                    (req.db_number.to_string(), Value::Object(decoded))
                })
                .collect()
        };

        let explore = if let Some(ref exp) = plan.explore {
            if exp.size_bytes > 0 {
                let raw = self.read_db_chunked(exp.db_number, exp.size_bytes)?;
                db_sizes.insert(
                    exp.db_number.to_string(),
                    Value::Number((raw.len() as i64).into()),
                );
                size_sources.insert(
                    exp.db_number.to_string(),
                    Value::String("rust".into()),
                );
                let decoded = Self::decode_variables(&raw, &exp.variables);
                let raw_json: Vec<Value> = raw.iter().map(|b| Value::Number((*b as u64).into())).collect();
                Some(serde_json::json!({
                    "db_number": exp.db_number,
                    "raw": raw_json,
                    "decoded": decoded,
                    "size": exp.size_bytes,
                    "source": "rust",
                }))
            } else {
                None
            }
        } else {
            None
        };

        let elapsed = t0.elapsed().as_secs_f64() * 1000.0;
        Ok(serde_json::json!({
            "blocks": blocks_map,
            "explore": explore,
            "db_sizes": db_sizes,
            "size_sources": size_sources,
            "read_latency_ms": (elapsed * 100.0).round() / 100.0,
            "engine": "rust",
        }))
    }
}

#[pyclass(name = "PlcEngineSession")]
pub struct PyPlcEngineSession {
    inner: Option<PlcEngineSession>,
}

#[pymethods]
impl PyPlcEngineSession {
    #[new]
    fn new(ip: &str, rack: i32, slot: i32) -> PyResult<Self> {
        match PlcEngineSession::connect(ip, rack, slot) {
            Ok(inner) => Ok(PyPlcEngineSession { inner: Some(inner) }),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyConnectionError, _>(e)),
        }
    }

    fn disconnect(&mut self) {
        if let Some(ref mut s) = self.inner {
            s.disconnect();
        }
        self.inner = None;
    }

    fn is_connected(&self) -> bool {
        self.inner
            .as_ref()
            .map(|s| s.is_connected())
            .unwrap_or(false)
    }

    fn poll_snapshot(&self, py: Python<'_>, plan: &PyAny) -> PyResult<PyObject> {
        let session = self.inner.as_ref().ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("Sessione PLC non connessa")
        })?;
        let plan_value = crate::python_to_json(py, plan)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        let plan_json: PollPlan = serde_json::from_value(plan_value)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid poll plan: {}", e)))?;

        let snapshot = session
            .poll_snapshot(&plan_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e))?;

        json_to_python(py, &snapshot)
    }
}

pub fn json_to_python(py: Python<'_>, value: &Value) -> PyResult<PyObject> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => Ok(b.to_object(py)),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.to_object(py))
            } else {
                Ok(n.to_string().to_object(py))
            }
        }
        Value::String(s) => Ok(s.to_object(py)),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(json_to_python(py, item)?)?;
            }
            Ok(list.to_object(py))
        }
        Value::Object(obj) => {
            let dict = PyDict::new(py);
            for (k, v) in obj {
                if k == "raw" {
                    if let Value::Array(bytes) = v {
                        let raw: Vec<u8> = bytes
                            .iter()
                            .filter_map(|x| x.as_u64().map(|n| n as u8))
                            .collect();
                        dict.set_item(k, PyBytes::new(py, &raw))?;
                        continue;
                    }
                }
                dict.set_item(k, json_to_python(py, v)?)?;
            }
            Ok(dict.to_object(py))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_bool_int_real() {
        let mut data = vec![1u8, 0, 0x2A, 0x00];
        data.extend_from_slice(&1.0f32.to_le_bytes());
        let vars = vec![
            VarSpec {
                name: "a".into(),
                offset: 0,
                var_type: "BOOL".into(),
            },
            VarSpec {
                name: "b".into(),
                offset: 2,
                var_type: "INT".into(),
            },
            VarSpec {
                name: "c".into(),
                offset: 4,
                var_type: "REAL".into(),
            },
        ];
        let m = PlcEngineSession::decode_variables(&data, &vars);
        assert_eq!(m.get("a").and_then(|v| v.as_bool()), Some(true));
        assert_eq!(m.get("b").and_then(|v| v.as_i64()), Some(42));
    }
}
