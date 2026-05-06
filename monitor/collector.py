import psycopg2
import time
import csv
import os
from datetime import datetime

class BufferPoolMonitor:
    def __init__(self, config):
        self.config      = config
        self.db_config   = config['database']
        self.interval    = config['monitor']['interval']
        self.results_dir = config['output']['results_dir']
        self.conn        = None
        self.csv_file    = None
        self.writer      = None

    def connect(self):
        self.conn = psycopg2.connect(
            host=self.db_config['host'],
            port=self.db_config['port'],
            dbname=self.db_config['name'],
            user=self.db_config['user'],
            password=self.db_config['password']
        )
        self.conn.autocommit = True

    def setup_output(self, run_id):
        os.makedirs(self.results_dir, exist_ok=True)
        filepath      = os.path.join(self.results_dir, f"metrics_{run_id}.csv")
        self.csv_file = open(filepath, 'w', newline='')
        self.writer   = csv.writer(self.csv_file)
        self.writer.writerow([
            'timestamp', 'elapsed_sec',
            'tps', 'commits', 'rollbacks',
            'blks_hit', 'blks_read', 'hit_rate_pct',
            'tup_inserted', 'tup_updated', 'tup_deleted', 'tup_fetched',
            'buffers_clean', 'buffers_alloc', 'maxwritten_clean', 'eviction_rate',
            'buffers_written', 'num_timed', 'num_requested',
            'write_time', 'sync_time', 'checkpoint_happened',
            'total_buffers', 'used_buffers', 'free_buffers',
            'dirty_buffers', 'buffer_utilization_pct', 'avg_usage_count', 'pinned_buffers',
            'autovacuum_count', 'dead_tuples', 'vacuum_happened',
            'heap_hit_rate_pct', 'index_hit_rate_pct',
        ])
        return filepath

    def collect_pg_stat_database(self, cur, prev):
        cur.execute("""
            SELECT xact_commit, xact_rollback, blks_hit, blks_read,
                   tup_inserted, tup_updated, tup_deleted, tup_fetched
            FROM pg_stat_database WHERE datname = %s
        """, (self.db_config['name'],))
        row = cur.fetchone()
        if not row:
            return {}, prev
        commits   = row[0] or 0
        rollbacks = row[1] or 0
        blks_hit  = row[2] or 0
        blks_read = row[3] or 0
        tps        = max((commits + rollbacks) - (prev.get('commits', 0) + prev.get('rollbacks', 0)), 0)
        total_blks = blks_hit + blks_read
        hit_rate   = round(blks_hit / total_blks * 100, 2) if total_blks > 0 else 0.0
        result = {
            'tps': tps, 'commits': commits, 'rollbacks': rollbacks,
            'blks_hit': blks_hit, 'blks_read': blks_read, 'hit_rate_pct': hit_rate,
            'tup_inserted': row[4] or 0, 'tup_updated': row[5] or 0,
            'tup_deleted': row[6] or 0, 'tup_fetched': row[7] or 0,
        }
        return result, {'commits': commits, 'rollbacks': rollbacks}

    def collect_pg_stat_bgwriter(self, cur, prev):
        cur.execute("SELECT buffers_clean, maxwritten_clean, buffers_alloc FROM pg_stat_bgwriter")
        row          = cur.fetchone()
        buf_cln      = row[0] or 0
        eviction_rate = max(buf_cln - prev.get('buffers_clean', 0), 0)
        result = {
            'buffers_clean': buf_cln, 'maxwritten_clean': row[1] or 0,
            'buffers_alloc': row[2] or 0, 'eviction_rate': eviction_rate,
        }
        return result, {'buffers_clean': buf_cln}

    def collect_pg_stat_checkpointer(self, cur, prev):
        cur.execute("""
            SELECT num_timed, num_requested, write_time, sync_time, buffers_written
            FROM pg_stat_checkpointer
        """)
        row         = cur.fetchone()
        num_timed   = row[0] or 0
        num_req     = row[1] or 0
        checkpoint_happened = 1 if (
            num_timed > prev.get('num_timed', 0) or
            num_req   > prev.get('num_requested', 0)
        ) else 0
        result = {
            'num_timed': num_timed, 'num_requested': num_req,
            'write_time': row[2] or 0, 'sync_time': row[3] or 0,
            'buffers_written': row[4] or 0,
            'checkpoint_happened': checkpoint_happened,
        }
        return result, {'num_timed': num_timed, 'num_requested': num_req}

    def collect_pg_buffercache(self, cur):
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE relfilenode IS NOT NULL) AS used,
                   COUNT(*) FILTER (WHERE relfilenode IS NULL)     AS free,
                   COUNT(*) FILTER (WHERE isdirty)                 AS dirty,
                   COUNT(*) FILTER (WHERE pinning_backends > 0)    AS pinned,
                   ROUND(AVG(usagecount)::numeric, 2)              AS avg_uc
            FROM pg_buffercache
        """)
        row      = cur.fetchone()
        total    = row[0] or 0
        used     = row[1] or 0
        util_pct = round(used / total * 100, 2) if total > 0 else 0.0
        return {
            'total_buffers': total, 'used_buffers': used,
            'free_buffers': row[2] or 0, 'dirty_buffers': row[3] or 0,
            'pinned_buffers': row[4] or 0,
            'buffer_utilization_pct': util_pct,
            'avg_usage_count': float(row[5]) if row[5] else 0.0,
        }

    def collect_pg_stat_user_tables(self, cur, prev):
        cur.execute("""
            SELECT COALESCE(SUM(autovacuum_count),0),
                   COALESCE(SUM(n_dead_tup),0),
                   COALESCE(SUM(seq_tup_read),0),
                   COALESCE(SUM(idx_tup_fetch),0)
            FROM pg_stat_user_tables
        """)
        row       = cur.fetchone()
        vac_count = row[0] or 0
        dead_tup  = row[1] or 0
        seq_read  = row[2] or 0
        idx_fetch = row[3] or 0
        vacuum_happened = 1 if vac_count > prev.get('autovacuum_count', 0) else 0
        prev_seq  = prev.get('seq_tup_read', 0)
        prev_idx  = prev.get('idx_tup_fetch', 0)
        total_access = (seq_read - prev_seq) + (idx_fetch - prev_idx)
        idx_hit_rate = round((idx_fetch - prev_idx) / total_access * 100, 2) if total_access > 0 else 0.0
        result = {
            'autovacuum_count': vac_count, 'dead_tuples': dead_tup,
            'vacuum_happened': vacuum_happened,
            'heap_hit_rate_pct': 0.0, 'index_hit_rate_pct': idx_hit_rate,
        }
        return result, {'autovacuum_count': vac_count, 'seq_tup_read': seq_read, 'idx_tup_fetch': idx_fetch}

    def collect_snapshot(self, elapsed, prev_db, prev_bgw, prev_ckpt, prev_vac):
        cur = self.conn.cursor()
        db_metrics,   new_prev_db   = self.collect_pg_stat_database(cur, prev_db)
        bgw_metrics,  new_prev_bgw  = self.collect_pg_stat_bgwriter(cur, prev_bgw)
        ckpt_metrics, new_prev_ckpt = self.collect_pg_stat_checkpointer(cur, prev_ckpt)
        buf_metrics                 = self.collect_pg_buffercache(cur)
        vac_metrics,  new_prev_vac  = self.collect_pg_stat_user_tables(cur, prev_vac)

        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        self.writer.writerow([
            now, elapsed,
            db_metrics.get('tps', 0), db_metrics.get('commits', 0), db_metrics.get('rollbacks', 0),
            db_metrics.get('blks_hit', 0), db_metrics.get('blks_read', 0), db_metrics.get('hit_rate_pct', 0),
            db_metrics.get('tup_inserted', 0), db_metrics.get('tup_updated', 0),
            db_metrics.get('tup_deleted', 0), db_metrics.get('tup_fetched', 0),
            bgw_metrics.get('buffers_clean', 0), bgw_metrics.get('buffers_alloc', 0),
            bgw_metrics.get('maxwritten_clean', 0), bgw_metrics.get('eviction_rate', 0),
            ckpt_metrics.get('buffers_written', 0), ckpt_metrics.get('num_timed', 0),
            ckpt_metrics.get('num_requested', 0), ckpt_metrics.get('write_time', 0),
            ckpt_metrics.get('sync_time', 0), ckpt_metrics.get('checkpoint_happened', 0),
            buf_metrics.get('total_buffers', 0), buf_metrics.get('used_buffers', 0),
            buf_metrics.get('free_buffers', 0), buf_metrics.get('dirty_buffers', 0),
            buf_metrics.get('buffer_utilization_pct', 0), buf_metrics.get('avg_usage_count', 0),
            buf_metrics.get('pinned_buffers', 0),
            vac_metrics.get('autovacuum_count', 0), vac_metrics.get('dead_tuples', 0),
            vac_metrics.get('vacuum_happened', 0), vac_metrics.get('heap_hit_rate_pct', 0),
            vac_metrics.get('index_hit_rate_pct', 0),
        ])
        self.csv_file.flush()
        cur.close()
        return new_prev_db, new_prev_bgw, new_prev_ckpt, new_prev_vac

    def run(self, run_id, stop_event):
        self.connect()
        filepath = self.setup_output(run_id)
        print(f"[Monitor] Started — writing to {filepath}")
        start_time = time.time()
        prev_db = prev_bgw = prev_ckpt = prev_vac = {}
        while not stop_event.is_set():
            elapsed = round(time.time() - start_time, 1)
            try:
                prev_db, prev_bgw, prev_ckpt, prev_vac = self.collect_snapshot(
                    elapsed, prev_db, prev_bgw, prev_ckpt, prev_vac)
            except Exception as e:
                print(f"[Monitor] Error at {elapsed}s: {e}")
            time.sleep(self.interval)
        self.csv_file.close()
        self.conn.close()
        print("[Monitor] Stopped.")
