import csv
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

class BenchmarkReporter:
    def __init__(self, results_dir):
        self.results_dir = results_dir

    def load_metrics(self, run_id):
        filepath = os.path.join(self.results_dir, f"metrics_{run_id}.csv")
        if not os.path.exists(filepath):
            print(f"[Reporter] Metrics file not found: {filepath}")
            return None
        rows = []
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k: self._parse(v) for k, v in row.items()})
        print(f"[Reporter] Loaded {len(rows)} snapshots from {filepath}")
        return rows

    def _parse(self, value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value

    def _get_col(self, rows, col):
        return [r.get(col, 0) for r in rows]

    def _mark_events(self, ax, rows, event_col, color):
        for r in rows:
            if r.get(event_col, 0) == 1:
                ax.axvline(x=r['elapsed_sec'], color=color, alpha=0.4, linewidth=1.2, linestyle='--')

    def plot_all(self, run_id):
        rows = self.load_metrics(run_id)
        if not rows:
            return
        elapsed = self._get_col(rows, 'elapsed_sec')
        prefix  = os.path.join(self.results_dir, run_id)

        # 1 — TPS
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(elapsed, self._get_col(rows, 'tps'), color='steelblue', linewidth=1.2)
        self._mark_events(ax, rows, 'checkpoint_happened', 'red')
        self._mark_events(ax, rows, 'vacuum_happened', 'orange')
        ax.legend(handles=[
            mpatches.Patch(color='steelblue', label='TPS'),
            mpatches.Patch(color='red',       alpha=0.4, label='Checkpoint'),
            mpatches.Patch(color='orange',    alpha=0.4, label='Vacuum'),
        ])
        ax.set_xlabel('Elapsed (s)'); ax.set_ylabel('Transactions/sec')
        ax.set_title(f'TPS Over Time — {run_id}'); ax.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_tps.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_tps.pdf")

        # 2 — Hit rate
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(elapsed, self._get_col(rows, 'hit_rate_pct'), color='green', linewidth=1.2)
        ax.set_ylim(0, 100); ax.set_xlabel('Elapsed (s)'); ax.set_ylabel('Hit Rate (%)')
        ax.set_title(f'Buffer Pool Hit Rate — {run_id}'); ax.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_hitrate.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_hitrate.pdf")

        # 3 — Utilization
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(elapsed, self._get_col(rows, 'buffer_utilization_pct'), color='purple', linewidth=1.2)
        ax.set_ylim(0, 100); ax.set_xlabel('Elapsed (s)'); ax.set_ylabel('Utilization (%)')
        ax.set_title(f'Buffer Pool Utilization — {run_id}'); ax.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_utilization.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_utilization.pdf")

        # 4 — Eviction rate
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(elapsed, self._get_col(rows, 'eviction_rate'), color='red', linewidth=1.2)
        ax.set_xlabel('Elapsed (s)'); ax.set_ylabel('Pages evicted/sec')
        ax.set_title(f'Page Eviction Rate — {run_id}'); ax.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_evictions.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_evictions.pdf")

        # 5 — Buffer state
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(elapsed, self._get_col(rows, 'dirty_buffers'), color='red',   linewidth=1.2, label='Dirty')
        ax.plot(elapsed, self._get_col(rows, 'free_buffers'),  color='green', linewidth=1.2, label='Free')
        ax.plot(elapsed, self._get_col(rows, 'used_buffers'),  color='blue',  linewidth=1.2, label='Used')
        ax.set_xlabel('Elapsed (s)'); ax.set_ylabel('Buffer count')
        ax.set_title(f'Buffer Pool State — {run_id}'); ax.legend(); ax.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_bufferstate.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_bufferstate.pdf")

        # 6 — Checkpoint vs TPS
        fig, ax1 = plt.subplots(figsize=(12, 4))
        ax1.plot(elapsed, self._get_col(rows, 'tps'), color='steelblue', linewidth=1.2)
        ax1.set_ylabel('TPS', color='steelblue')
        ax2 = ax1.twinx()
        ax2.plot(elapsed, self._get_col(rows, 'write_time'), color='red', linewidth=1.0, alpha=0.7)
        ax2.set_ylabel('Checkpoint write time (ms)', color='red')
        ax1.set_xlabel('Elapsed (s)')
        ax1.set_title(f'TPS vs Checkpoint Write Time — {run_id}'); ax1.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_checkpoint.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_checkpoint.pdf")

        # 7 — Usage count
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(elapsed, self._get_col(rows, 'avg_usage_count'), color='darkorange', linewidth=1.2)
        ax.set_xlabel('Elapsed (s)'); ax.set_ylabel('Avg usage count')
        ax.set_title(f'Buffer Usage Count (Page Hotness) — {run_id}'); ax.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{prefix}_usagecount.pdf"); plt.close()
        print(f"[Reporter] Saved {prefix}_usagecount.pdf")

        print(f"\n[Reporter] All charts saved to {self.results_dir}")
