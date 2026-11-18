import rust_engine

def run_heavy_task(task_type: str, payload: dict) -> dict:
    try:
        if isinstance(payload, dict) and "trace_id" not in payload:
            try:
                from opentelemetry import trace
                span = trace.get_current_span()
                ctx = span.get_span_context()
                if ctx and ctx.is_valid:
                    payload = dict(payload)
                    payload["trace_id"] = format(ctx.trace_id, "032x")
            except Exception:
                pass
        return rust_engine.run_heavy_task(task_type, payload)
    except Exception as e:
        return {
            "status": "error",
            "task_type": task_type,
            "error": str(e),
        }

def run_quotations_api(url: str, headers: dict, params: dict) -> dict:
    payload = {
        "url": url,
        "headers": headers,
        "params": params
    }
    return run_heavy_task("quotations_api", payload)

def run_orders_parse(raw_text: str) -> dict:
    payload = {
        "raw_text": raw_text
    }
    return run_heavy_task("orders_parse", payload)

def run_orders_validate(order_data: dict) -> dict:
    payload = {
        "order_data": order_data
    }
    return run_heavy_task("orders_validate", payload)

def run_production_simulate(steps: int, intensity: int) -> dict:
    payload = {
        "steps": steps,
        "intensity": intensity
    }
    return run_heavy_task("production_simulate", payload)

def run_cnc_generate(parameters: dict) -> dict:
    payload = {
        "parameters": parameters
    }
    return run_heavy_task("cnc_generate", payload)

def run_waste_compute(items: list) -> dict:
    payload = {
        "items": items
    }
    return run_heavy_task("waste_compute", payload)

def run_dashboard_stats(dataset: dict) -> dict:
    payload = {
        "dataset": dataset
    }
    return run_heavy_task("dashboard_stats", payload)

def run_gcode_analyze(gcode_text: str) -> dict:
    payload = {
        "gcode_text": gcode_text
    }
    return run_heavy_task("gcode_analyze", payload)

def run_gcode_validate(gcode_text: str) -> dict:
    payload = {
        "gcode_text": gcode_text
    }
    return run_heavy_task("gcode_validate", payload)

def run_gcode_optimize(gcode_text: str) -> dict:
    payload = {
        "gcode_text": gcode_text
    }
    return run_heavy_task("gcode_optimize", payload)

