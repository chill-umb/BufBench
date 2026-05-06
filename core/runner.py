import threading
import time
import csv
import os
import numpy as np
from queue import Queue, Empty
from datetime import datetime
from monitor.collector import BufferPoolMonitor

class BenchmarkRunner:
    def __init__(self, config, workload):
        self.config      = config
        self.workload    = workload
        self.results_dir = config['output']['results_dir']
        self.duration    = config['workload']['duration']
        self.num_clients = config['workload']['clients']

    def apply_pg_settings(self):
        pg = self.config.get('postgresql', {})
        if not pg:
            return
        conn = self.workload.get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        for key, value in pg.items():
            try:
                cur.execute(f"ALTER SYSTEM SET {key} = %s", (str(value),))
                print(f"[Runner] SET {key} = {value}")
            except Exception as e:
                print(f"[Runner] Could not set {key}: {e}")
        cur.execute("SELECT pg_reload_conf()")
        cur.close()
        conn.close()

    def reset_stats(self):
        conn = self.workload.get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT pg_stat_reset()")
        cur.execute("SELECT pg_stat_reset_shared('bgwriter')")
        cur.execute("SELECT pg_stat_reset_shared('checkpointer')")
        cur.close()
        conn.close()
        print("[Runner] Stats reset.")

    def get_db_size(self):
        conn = self.workload.get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT pg_size_pretty(pg_database_size(%s))",
            (self.config['database']['name'],)
        )
        total = cur.fetchone()[0]
        cur.execute("""
            SELECT
                relname AS tablename,
                pg_size_pretty(pg_total_relation_size(oid)) AS total,
                pg_size_pretty(pg_relation_size(oid))       AS table_only,
                pg_size_pretty(pg_indexes_size(oid))        AS indexes
            FROM pg_class
            WHERE relkind = 'r'
              AND relnamespace = (
                  SELECT oid FROM pg_namespace WHERE nspname = 'public'
              )
              AND pg_total_relation_size(oid) > 8192
            ORDER BY pg_total_relation_size(oid) DESC
        """)
        tables = cur.fetchall()
        cur.close()
        conn.close()
        return total, tables

    def print_db_size(self, label=""):
        total, tables = self.get_db_size()
        print(f"\n[DB Size] {label}")
        print(f"  {'Table':<20} {'Total':>10} {'Data':>10} {'Indexes':>10}")
        print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10}")
        for t in tables:
            print(f"  {t[0]:<20} {t[1]:>10} {t[2]:>10} {t[3]:>10}")
        print(f"  {'─'*52}")
        print(f"  Total database size: {total}\n")

    def clean_database(self):
        conn = self.workload.get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename NOT LIKE 'pg_%'
        """)
        tables = [row[0] for row in cur.fetchall()]
        if tables:
            cur.execute("DROP TABLE IF EXISTS " + ", ".join(tables) + " CASCADE")
            print(f"[Runner] Dropped {len(tables)} existing tables: {', '.join(tables)}")
        else:
            print("[Runner] Database is already clean.")
        cur.close()
        conn.close()

    def setup(self):
        print("[Runner] Setting up workload...")
        conn = self.workload.get_connection()
        self.workload.create_schema(conn)
        self.workload.load_data(conn)
        conn.close()
        print("[Runner] Setup complete.")

    def run(self):
        os.makedirs(self.results_dir, exist_ok=True)
        run_id        = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        workload_type = self.config['workload']['type']
        run_id        = f"{workload_type}_{run_id}"

        print(f"\n[Runner] Starting run: {run_id}")
        print(f"[Runner] Workload:  {workload_type}")
        print(f"[Runner] Clients:   {self.num_clients}")
        print(f"[Runner] Duration:  {self.duration}s\n")

        self.apply_pg_settings()
        self.reset_stats()

        stop_event    = threading.Event()
        results_queue = Queue()

        monitor = BufferPoolMonitor(self.config)
        monitor_thread = threading.Thread(
            target=monitor.run, args=(run_id, stop_event), daemon=True)
        monitor_thread.start()

        worker_threads = []
        for i in range(self.num_clients):
            t = threading.Thread(
                target=self.workload.worker,
                args=(i + 1, results_queue, stop_event), daemon=True)
            t.start()
            worker_threads.append(t)

        analytical_threads = []
        if hasattr(self.workload, 'analytical_worker'):
            num_at = getattr(self.workload, 'num_analytical_threads', 2)
            for i in range(num_at):
                t = threading.Thread(
                    target=self.workload.analytical_worker,
                    args=(i + 1, stop_event), daemon=True)
                t.start()
                analytical_threads.append(t)
            print(f"[Runner] Started {num_at} analytical thread(s).")

        print(f"[Runner] All threads started. Running for {self.duration}s...")
        time.sleep(self.duration)

        print("[Runner] Stopping...")
        stop_event.set()

        for t in worker_threads:
            t.join(timeout=10)
        for t in analytical_threads:
            t.join(timeout=10)
        monitor_thread.join(timeout=10)

        all_latencies = []
        while True:
            try:
                batch = results_queue.get_nowait()
                all_latencies.extend(batch)
            except Empty:
                break

        self.save_summary(run_id, all_latencies)
        print(f"\n[Runner] Run complete. Results in {self.results_dir}")

    def save_summary(self, run_id, latencies):
        if not latencies:
            print("[Runner] No latency data collected.")
            return
        latencies_arr = sorted(latencies)
        total   = len(latencies_arr)
        summary = {
            'run_id':      run_id,
            'total_txns':  total,
            'avg_latency': round(sum(latencies_arr) / total, 2),
            'min_latency': round(min(latencies_arr), 2),
            'max_latency': round(max(latencies_arr), 2),
            'p50_latency': round(latencies_arr[int(total * 0.50)], 2),
            'p95_latency': round(latencies_arr[int(total * 0.95)], 2),
            'p99_latency': round(latencies_arr[int(total * 0.99)], 2),
            'tps':         round(total / self.duration, 2),
        }
        filepath = os.path.join(self.results_dir, f"summary_{run_id}.csv")
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary.keys())
            writer.writeheader()
            writer.writerow(summary)
        print("\n[Runner] ── Summary ──────────────────────")
        for k, v in summary.items():
            print(f"  {k:<20} {v}")
        print("[Runner] ─────────────────────────────────")
        print(f"[Runner] Summary saved to {filepath}")
