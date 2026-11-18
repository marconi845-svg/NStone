"""
Banco di prova CNC LIVE contro il server Snap7 simulato locale (127.0.0.1).

Esercita il percorso di produzione VERO:
  CNCLiveUpdater -> CNCLiveWorker -> Snap7 client -> read_db_chunked
  -> plc_map_decoder -> ruoli mappa -> CNCLiveStatus -> segnali Qt

Il server simulato (snap7_multifilo_server.py) espone DB1/DB2/DB3: qui viene
iniettata una mappa "da banco" con ruoli CNC su quei DB, così si vede il giro
completo connessione -> lettura -> decode -> status -> diagnostica.

Uso:  python tests/bench_cnc_live.py   (con snap7_multifilo_server.py attivo)
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtCore import QCoreApplication, QTimer

import plc.plc_map_loader as plc_map_loader
from machines.cnc_live_integration import CNCLiveUpdater

BENCH_SECONDS = 10

# Mappa da banco: ruoli CNC applicati ai DB del server sim multifilo.
# NON è la mappa OEM: serve solo a validare il giro tecnico end-to-end.
BENCH_DOC = {
    "schema": "nstone_cnc_db_map",
    "version": "bench",
    "title": "BENCH — server sim locale con ruoli CNC",
    "data_blocks": [
        {
            "number": 1,
            "symbolic_name": "Bench_Stato_DB",
            "size_bytes": 4,
            "direction": "plc_to_sw",
            "poll_interval_ms": 200,
            "variables": [
                {"offset": 0, "type": "BYTE", "name": "stato", "role": "machine_state",
                 "state_map": {"0": "STOP", "1": "RUN", "2": "ERROR"}},
                {"offset": 1, "type": "BOOL", "name": "allarme", "role": "alarm_code"},
            ],
        },
        {
            "number": 2,
            "symbolic_name": "Bench_Parametri_DB",
            "size_bytes": 28,
            "direction": "plc_to_sw",
            "poll_interval_ms": 200,
            "variables": [
                {"offset": 0, "type": "REAL", "name": "velocita", "role": "spindle_speed"},
                {"offset": 4, "type": "REAL", "name": "tensione", "role": "feed_rate"},
                {"offset": 8, "type": "REAL", "name": "pressione", "role": "axis_x"},
                {"offset": 12, "type": "REAL", "name": "assorbimento", "role": "spindle_load"},
            ],
        },
    ],
    "machine_profiles": {"cnc": {"priority_dbs": [1, 2]}},
}


def main() -> int:
    # Inietta la mappa da banco nella cache del loader sotto il profilo CNC
    plc_map_loader._CACHE["oem_cnc_v1"] = BENCH_DOC

    settings = {
        "ip": "127.0.0.1",
        "port": 102,
        "rack": 0,
        "slot": 1,
        "mode": "live",
        "map_profile": "oem_cnc_v1",
    }

    # Metti la macchina simulata in RUN (scrittura da banco, fuori NStone):
    # così DB2 si popola con valori che oscillano.
    try:
        from plc.snap7_multifilo_client import MultifiloPLCClient
        ctl = MultifiloPLCClient(ip="127.0.0.1")
        if ctl.connect():
            ctl.write_start()
            time.sleep(1.0)
            ctl.disconnect()
            print("[bench] comando Start inviato al server sim (macchina in RUN)")
    except Exception as e:
        print(f"[bench] impossibile mettere il sim in RUN: {e}")

    app = QCoreApplication(sys.argv)

    results = {
        "connected_events": [],
        "statuses": 0,
        "last_status": None,
        "diagnostics": None,
    }

    updater = CNCLiveUpdater(settings)

    def on_conn(connected: bool):
        results["connected_events"].append(connected)
        print(f"[bench] connection_changed -> {connected}")

    def on_status(status):
        results["statuses"] += 1
        results["last_status"] = status
        if results["statuses"] in (1, 10, 25, 40):
            print(
                f"[bench] status #{results['statuses']}: "
                f"state={status.machine_state.value} "
                f"spindle={status.spindle_speed:.3f} "
                f"feed={status.feed_rate:.3f} "
                f"x={status.position.x:.3f} "
                f"load={status.spindle_load:.3f} "
                f"alarm={status.alarm_code} "
                f"latency={status.plc_latency}ms"
            )

    def on_diag(stats: dict):
        results["diagnostics"] = stats
        print(
            f"[bench] diagnostica: ping_ok={stats.get('ping_ok')} "
            f"ping={stats.get('ping_ms')}ms read={stats.get('read_latency_ms')}ms "
            f"cpu={stats.get('cpu_state')!r} snap7={stats.get('snap7_connected')} "
            f"err={stats.get('last_error')!r}"
        )

    updater.connection_changed.connect(on_conn)
    updater.status_updated.connect(on_status)
    updater.diagnostics_updated.connect(on_diag)
    updater.start()

    def finish():
        updater.stop()
        app.quit()

    QTimer.singleShot(BENCH_SECONDS * 1000, finish)
    app.exec_()

    print()
    print("=" * 60)
    print("ESITO BANCO DI PROVA")
    print("=" * 60)
    ok = True

    if True in results["connected_events"]:
        print("[OK] Connessione S7 stabilita")
    else:
        print("[KO] MAI connesso al server S7")
        ok = False

    if results["statuses"] >= 10:
        print(f"[OK] Status ricevuti: {results['statuses']} in {BENCH_SECONDS}s")
    else:
        print(f"[KO] Pochi status: {results['statuses']}")
        ok = False

    st = results["last_status"]
    if st is not None:
        print(f"  Ultimo status: state={st.machine_state.value} "
              f"spindle={st.spindle_speed:.3f} feed={st.feed_rate:.3f} "
              f"x={st.position.x:.3f} load={st.spindle_load:.3f}")
        print(f"  raw_values: { {k: (round(v, 3) if isinstance(v, float) else v) for k, v in st.raw_values.items()} }")
        if st.machine_state.value == "RUN":
            print("[OK] Stato macchina RUN decodificato correttamente")
        else:
            print(f"[KO] Stato atteso RUN, letto {st.machine_state.value}")
            ok = False
        # Con la macchina in RUN il server porta tensione>=50, pressione>=2,
        # assorbimento>=5: valori plausibili = endianness corretta.
        plausible = (
            0.0 <= st.spindle_speed <= 2.5
            and 40.0 <= st.feed_rate <= 220.0
            and 1.5 <= st.position.x <= 9.0
            and 4.0 <= st.spindle_load <= 16.0
        )
        if plausible:
            print("[OK] Valori REAL plausibili (endianness corretta)")
        else:
            print("[KO] Valori REAL NON plausibili: probabile errore di endianness nel decoder")
            ok = False

    diag = results["diagnostics"]
    if diag and diag.get("snap7_connected"):
        print(f"[OK] Diagnostica attiva (ping={diag.get('ping_ms')}ms, "
              f"read={diag.get('read_latency_ms')}ms, cpu={diag.get('cpu_state')!r})")
    else:
        print("[KO] Diagnostica assente o disconnessa")
        ok = False

    print()
    print("BENCH: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
