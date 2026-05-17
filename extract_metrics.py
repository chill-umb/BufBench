#!/usr/bin/env python3
"""
Extract key buffer pool metrics from a PGBufBench metrics CSV.
Usage: python3 extract_metrics.py results/metrics_<run_id>.csv
"""
import csv
import sys
import os
import subprocess

def get_db_size():
    try:
        env = {**os.environ, 'PGPASSWORD': 'bgbench123'}
        result = subprocess.run(
            ['psql', '-U', 'bgbench', '-h', 'localhost', '-d', 'bgbenchdb', '-t', '-c',
             'SELECT pg_size_pretty(pg_database_size(current_database()));'],
            capture_output=True, text=True, timeout=10, env=env
        )
        return result.stdout.strip()
    except Exception:
        return 'N/A'

def extract(filepath):
    with open(filepath, 'r') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("No data found.")
        return

    def col(name):
        return [float(r[name]) for r in rows if r.get(name, '')]
    def avg(lst): return sum(lst)/len(lst) if lst else 0

    hit_rates   = [v for v in col('hit_rate_pct') if v > 0]
    evictions   = col('eviction_rate')
    utilization = col('buffer_utilization_pct')
    tps_vals    = [v for v in col('tps') if v > 0]
    dirty       = col('dirty_buffers')
    avg_uc      = col('avg_usage_count')

    ckpt_rows = [r for r in rows if float(r.get('checkpoint_happened', 0)) == 1]
    vac_rows  = [r for r in rows if float(r.get('vacuum_happened', 0)) == 1]

    run_id = os.path.basename(filepath).replace('metrics_', '').replace('.csv', '')
    db_size = get_db_size()

    print(f"\n{'='*60}")
    print(f"Run: {run_id}")
    print(f"{'='*60}")
    print(f"\n-- Database --")
    print(f"  DB size:          {db_size}")
    print(f"\n-- Throughput --")
    print(f"  TPS avg:          {avg(tps_vals):.2f}")
    print(f"  TPS max:          {max(tps_vals):.2f}")
    print(f"  TPS min:          {min(tps_vals):.2f}")
    print(f"\n-- Buffer Pool --")
    print(f"  Hit rate avg:     {avg(hit_rates):.2f}%")
    print(f"  Hit rate min:     {min(hit_rates):.2f}%")
    print(f"  Hit rate max:     {max(hit_rates):.2f}%")
    print(f"  Eviction avg:     {avg(evictions):.2f} pages/s")
    print(f"  Eviction max:     {max(evictions):.2f} pages/s")
    print(f"  Utilization avg:  {avg(utilization):.2f}%")
    print(f"  Dirty bufs avg:   {avg(dirty):.0f}")
    print(f"  Avg usage count:  {avg(avg_uc):.2f}")
    print(f"\n-- Background Events --")
    print(f"  Checkpoint events: {len(ckpt_rows)}")
    print(f"  Vacuum events:     {len(vac_rows)}")
    print()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        import glob
        files = sorted(glob.glob('results/metrics_*.csv'))
        if files:
            extract(files[-1])
        else:
            print("No metrics files found.")
    else:
        extract(sys.argv[1])
