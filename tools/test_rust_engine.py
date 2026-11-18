from plc.rust_bridge import run_heavy_task

if __name__ == "__main__":
    data_parallel = {"values": list(range(100000))}
    res_parallel = run_heavy_task("test_parallel", data_parallel)
    print("TEST PARALLEL:", res_parallel)

    data_sim = {"steps": 50000, "intensity": 3}
    res_sim = run_heavy_task("fake_simulation", data_sim)
    print("FAKE SIMULATION:", res_sim)










