import yaml
import sys
import os
import glob
from core.runner import BenchmarkRunner
from reporter.plotter import BenchmarkReporter
from reporter.interference import InterferenceAnalyzer
from workloads.tpcb import TPCBWorkload
from workloads.ycsb import YCSBWorkload
from workloads.tpcc import TPCCWorkload
from workloads.chbenchmark import CHBenchmarkWorkload

def load_config(path='config/tpcb_test.yaml'):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def get_workload(config):
    workload_type = config['workload']['type']
    if workload_type == 'tpcb':
        return TPCBWorkload(config)
    elif workload_type == 'ycsb':
        return YCSBWorkload(config)
    elif workload_type == 'tpcc':
        return TPCCWorkload(config)
    elif workload_type == 'chbenchmark':
        return CHBenchmarkWorkload(config)
    else:
        print(f"[Main] Unknown workload type: {workload_type}")
        sys.exit(1)

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'config/tpcb_test.yaml'
    print(f"[Main] Loading config from {config_path}")
    config = load_config(config_path)

    workload = get_workload(config)
    runner   = BenchmarkRunner(config, workload)

    print("[Main] Cleaning database...")
    runner.clean_database()

    print("[Main] Setting up schema and loading data...")
    runner.setup()

    runner.print_db_size(label="After data loading")

    print("[Main] Starting benchmark...")
    runner.run()

    print("[Main] Generating charts...")
    reporter      = BenchmarkReporter(config['output']['results_dir'])
    results_dir   = config['output']['results_dir']
    workload_type = config['workload']['type']

    pattern = os.path.join(results_dir, f"summary_{workload_type}_*.csv")
    files   = sorted(glob.glob(pattern))
    if files:
        latest = os.path.basename(files[-1])
        run_id = latest.replace('summary_', '').replace('.csv', '')
        reporter.plot_all(run_id)
    else:
        print("[Main] No summary file found to plot.")

    if workload_type == 'chbenchmark':
        summary = workload.get_analytical_summary()
        if summary:
            print("\n[CH] ── Analytical Query Summary ────────────")
            print(f"  {'Query':<8} {'Count':>6} {'Avg(ms)':>10} {'P50(ms)':>10} {'P99(ms)':>10}")
            print(f"  {'-'*8} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
            for q in sorted(summary.keys(), key=lambda x: int(x[1:])):
                s = summary[q]
                print(f"  {q:<8} {s['count']:>6} {s['avg_ms']:>10} {s['p50_ms']:>10} {s['p99_ms']:>10}")
            print("[CH] ─────────────────────────────────────────")

    print("[Main] Running interference analysis...")
    analyzer = InterferenceAnalyzer(config['output']['results_dir'])
    analyzer.analyze(run_id)
    print("[Main] Done!")

if __name__ == '__main__':
    main()
