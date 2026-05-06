import csv
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


class InterferenceAnalyzer:
    def __init__(self, results_dir):
        self.results_dir = results_dir

    def load_metrics(self, run_id):
        filepath = os.path.join(self.results_dir, f"metrics_{run_id}.csv")
        if not os.path.exists(filepath):
            print(f"[Interference] Metrics file not found: {filepath}")
            return None
        rows = []
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                parsed = {}
                for k, v in row.items():
                    try:
                        parsed[k] = float(v)
                    except (ValueError, TypeError):
                        parsed[k] = v
                rows.append(parsed)
        return rows

    def detect_events(self, rows):
        """
        Detect checkpoint and vacuum events from the metrics rows.
        For each event, calculate:
          - timestamp it fired
          - TPS before the event (avg of 3 seconds before)
          - TPS during the event (avg while event active)
          - TPS drop percentage
          - recovery time (seconds until TPS returns to 90% of pre-event TPS)
        """
        events = []

        for i, row in enumerate(rows):
            elapsed = row.get('elapsed_sec', 0)
            tps     = row.get('tps', 0)

            for event_col, event_type in [
                ('checkpoint_happened', 'CHECKPOINT'),
                ('vacuum_happened',     'VACUUM')
            ]:
                if row.get(event_col, 0) != 1:
                    continue

                # skip if previous row also had this event (same event continuing)
                if i > 0 and rows[i-1].get(event_col, 0) == 1:
                    continue

                # TPS before — avg of up to 3 rows before event
                pre_rows = [rows[j].get('tps', 0) for j in range(max(0, i-3), i)
                           if rows[j].get('tps', 0) > 0]
                tps_before = round(sum(pre_rows) / len(pre_rows), 1) if pre_rows else tps

                # TPS during — collect while event is active
                during_tps = []
                j = i
                while j < len(rows) and rows[j].get(event_col, 0) == 1:
                    during_tps.append(rows[j].get('tps', 0))
                    j += 1
                tps_during = round(sum(during_tps) / len(during_tps), 1) if during_tps else tps

                # TPS drop %
                drop_pct = round((tps_before - tps_during) / tps_before * 100, 1) \
                           if tps_before > 0 else 0.0
                drop_pct = max(drop_pct, 0.0)

                # recovery time — how many seconds until TPS >= 90% of pre-event TPS
                recovery_threshold = tps_before * 0.90
                recovery_time      = None
                event_end_idx      = j
                for k in range(event_end_idx, min(event_end_idx + 30, len(rows))):
                    if rows[k].get('tps', 0) >= recovery_threshold:
                        recovery_time = round(
                            rows[k].get('elapsed_sec', 0) - elapsed, 1
                        )
                        break
                if recovery_time is None:
                    recovery_time = '>30s'

                events.append({
                    'type':         event_type,
                    'elapsed':      elapsed,
                    'tps_before':   tps_before,
                    'tps_during':   tps_during,
                    'drop_pct':     drop_pct,
                    'recovery_sec': recovery_time,
                })

        return events

    def compute_statistics(self, events):
        """Compute aggregate statistics per event type."""
        stats = {}
        for event_type in ['CHECKPOINT', 'VACUUM']:
            group = [e for e in events if e['type'] == event_type]
            if not group:
                stats[event_type] = None
                continue
            drop_pcts      = [e['drop_pct'] for e in group]
            recovery_times = [e['recovery_sec'] for e in group
                              if isinstance(e['recovery_sec'], float)]
            stats[event_type] = {
                'count':            len(group),
                'avg_drop_pct':     round(sum(drop_pcts) / len(drop_pcts), 1),
                'max_drop_pct':     round(max(drop_pcts), 1),
                'avg_recovery_sec': round(sum(recovery_times) / len(recovery_times), 1)
                                    if recovery_times else 'N/A',
            }
        return stats

    def print_report(self, run_id, events, stats):
        print(f"\n[Interference] ── Background Event Analysis — {run_id} ──")

        if not events:
            print("  No checkpoint or vacuum events detected during this run.")
        else:
            print(f"\n  {'Event':<12} {'Time':>6} {'TPS Before':>10} "
                  f"{'TPS During':>10} {'Drop %':>8} {'Recovery':>10}")
            print(f"  {'-'*12} {'-'*6} {'-'*10} {'-'*10} {'-'*8} {'-'*10}")
            for e in events:
                print(f"  {e['type']:<12} {e['elapsed']:>5}s "
                      f"{e['tps_before']:>10} {e['tps_during']:>10} "
                      f"{e['drop_pct']:>7}% {str(e['recovery_sec']):>9}s")

        print(f"\n  ── Aggregate Statistics ──")
        for event_type, s in stats.items():
            if s is None:
                print(f"  {event_type:<12} — no events detected")
            else:
                print(f"  {event_type:<12} "
                      f"count={s['count']}  "
                      f"avg_drop={s['avg_drop_pct']}%  "
                      f"max_drop={s['max_drop_pct']}%  "
                      f"avg_recovery={s['avg_recovery_sec']}s")
        print(f"[Interference] ─────────────────────────────────────────────\n")

    def save_event_csv(self, run_id, events, stats):
        """Save event log to CSV for paper results table."""
        if not events:
            return
        filepath = os.path.join(self.results_dir, f"interference_{run_id}.csv")
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'run_id', 'event_type', 'elapsed_sec',
                'tps_before', 'tps_during', 'drop_pct', 'recovery_sec'
            ])
            writer.writeheader()
            for e in events:
                writer.writerow({
                    'run_id':       run_id,
                    'event_type':   e['type'],
                    'elapsed_sec':  e['elapsed'],
                    'tps_before':   e['tps_before'],
                    'tps_during':   e['tps_during'],
                    'drop_pct':     e['drop_pct'],
                    'recovery_sec': e['recovery_sec'],
                })
        print(f"[Interference] Event log saved to {filepath}")

    def plot_interference(self, run_id, rows, events):
        """Generate annotated TPS chart with interference events marked."""
        if not rows:
            return

        elapsed = [r.get('elapsed_sec', 0) for r in rows]
        tps     = [r.get('tps', 0)         for r in rows]

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(elapsed, tps, color='steelblue', linewidth=1.5, label='TPS', zorder=3)

        checkpoint_events = [e for e in events if e['type'] == 'CHECKPOINT']
        vacuum_events     = [e for e in events if e['type'] == 'VACUUM']

        for e in checkpoint_events:
            ax.axvline(x=e['elapsed'], color='red', alpha=0.7,
                      linewidth=1.5, linestyle='--', zorder=2)
            ax.annotate(
                f"CKPT\n-{e['drop_pct']}%",
                xy=(e['elapsed'], e['tps_during']),
                xytext=(e['elapsed'] + 0.5, e['tps_during'] + max(tps) * 0.05),
                fontsize=7, color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=0.8)
            )

        for e in vacuum_events:
            ax.axvline(x=e['elapsed'], color='orange', alpha=0.7,
                      linewidth=1.5, linestyle='--', zorder=2)
            ax.annotate(
                f"VAC\n-{e['drop_pct']}%",
                xy=(e['elapsed'], e['tps_during']),
                xytext=(e['elapsed'] + 0.5, e['tps_during'] + max(tps) * 0.05),
                fontsize=7, color='darkorange',
                arrowprops=dict(arrowstyle='->', color='darkorange', lw=0.8)
            )

        ax.legend(handles=[
            mpatches.Patch(color='steelblue', label='TPS'),
            mpatches.Patch(color='red',       alpha=0.7, label='Checkpoint'),
            mpatches.Patch(color='orange',    alpha=0.7, label='Vacuum'),
        ])
        ax.set_xlabel('Elapsed (s)')
        ax.set_ylabel('Transactions/sec')
        ax.set_title(f'TPS with Background Event Interference — {run_id}')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        filepath = os.path.join(self.results_dir, f"{run_id}_interference.pdf")
        plt.savefig(filepath)
        plt.close()
        print(f"[Interference] Chart saved to {filepath}")

    def analyze(self, run_id):
        rows   = self.load_metrics(run_id)
        if not rows:
            return
        events = self.detect_events(rows)
        stats  = self.compute_statistics(events)
        self.print_report(run_id, events, stats)
        self.save_event_csv(run_id, events, stats)
        self.save_summary_txt(run_id, events, stats)
        self.plot_interference(run_id, rows, events)


    def save_summary_txt(self, run_id, events, stats):
        """Save human-readable interference summary as a text file."""
        filepath = os.path.join(self.results_dir, f"interference_{run_id}.txt")
        with open(filepath, 'w') as f:
            f.write(f"Background Event Interference Report\n")
            f.write(f"Run ID: {run_id}\n")
            f.write(f"{'='*60}\n\n")

            if not events:
                f.write("No checkpoint or vacuum events detected during this run.\n")
            else:
                f.write(f"{'Event':<12} {'Time':>6} {'TPS Before':>10} "
                        f"{'TPS During':>10} {'Drop %':>8} {'Recovery':>10}\n")
                f.write(f"{'-'*12} {'-'*6} {'-'*10} {'-'*10} {'-'*8} {'-'*10}\n")
                for e in events:
                    f.write(f"{e['type']:<12} {e['elapsed']:>5}s "
                            f"{e['tps_before']:>10} {e['tps_during']:>10} "
                            f"{e['drop_pct']:>7}% {str(e['recovery_sec']):>9}s\n")

            f.write(f"\n{'='*60}\n")
            f.write(f"Aggregate Statistics\n")
            f.write(f"{'='*60}\n")
            for event_type, s in stats.items():
                if s is None:
                    f.write(f"{event_type:<12} — no events detected\n")
                else:
                    f.write(f"{event_type:<12}\n")
                    f.write(f"  Total events:       {s['count']}\n")
                    f.write(f"  Avg TPS drop:       {s['avg_drop_pct']}%\n")
                    f.write(f"  Max TPS drop:       {s['max_drop_pct']}%\n")
                    f.write(f"  Avg recovery time:  {s['avg_recovery_sec']}s\n\n")

        print(f"[Interference] Summary saved to {filepath}")
