import random
import string
import math
from workloads.base import BaseWorkload

class ZipfianGenerator:
    def __init__(self, n, theta=0.99):
        self.n     = n
        self.theta = theta
        self.zetan = self._zeta(n, theta)
        self.eta   = (1 - math.pow(2.0 / n, 1 - theta)) / (1 - self._zeta(2, theta) / self.zetan)

    def _zeta(self, n, theta):
        total = 0.0
        for i in range(1, n + 1):
            total += 1.0 / math.pow(i, theta)
        return total

    def next(self):
        u  = random.random()
        uz = u * self.zetan
        if uz < 1.0:
            return 0
        if uz < 1.0 + math.pow(0.5, self.theta):
            return 1
        return int(self.n * math.pow(self.eta * u - self.eta + 1, 1.0 / (1 - self.theta)))


WORKLOAD_PROFILES = {
    'A': {'read': 0.50, 'update': 0.50, 'insert': 0.00, 'scan': 0.00, 'rmw': 0.00, 'delete': 0.00},
    'B': {'read': 0.95, 'update': 0.05, 'insert': 0.00, 'scan': 0.00, 'rmw': 0.00, 'delete': 0.00},
    'C': {'read': 1.00, 'update': 0.00, 'insert': 0.00, 'scan': 0.00, 'rmw': 0.00, 'delete': 0.00},
    'D': {'read': 0.95, 'update': 0.00, 'insert': 0.05, 'scan': 0.00, 'rmw': 0.00, 'delete': 0.00},
    'E': {'read': 0.00, 'update': 0.00, 'insert': 0.05, 'scan': 0.95, 'rmw': 0.00, 'delete': 0.00},
    'F': {'read': 0.50, 'update': 0.00, 'insert': 0.00, 'scan': 0.00, 'rmw': 0.50, 'delete': 0.00},
}


class YCSBWorkload(BaseWorkload):

    def __init__(self, config):
        super().__init__(config)
        ycsb_cfg         = config['workload'].get('ycsb', {})
        self.num_records = self.scale * 100000
        self.field_count = 10
        self.field_size  = 100
        self.scan_length = 100
        self.zipfian     = None
        self.insert_counter = self.num_records
        self.mix = self._resolve_mix(ycsb_cfg)
        self._validate_mix(self.mix)
        print(f"[YCSB] Workload mix: {self.mix}")

    def _resolve_mix(self, ycsb_cfg):
        if 'mix' in ycsb_cfg:
            raw   = ycsb_cfg['mix']
            total = sum(raw.values())
            if total > 1.1:
                return {k: v / 100.0 for k, v in raw.items()}
            else:
                return {k: float(v) for k, v in raw.items()}
        profile = ycsb_cfg.get('profile', 'A')
        if profile not in WORKLOAD_PROFILES:
            raise ValueError(f"Unknown YCSB profile '{profile}'.")
        print(f"[YCSB] Using named profile: {profile}")
        return WORKLOAD_PROFILES[profile]

    def _validate_mix(self, mix):
        ops = ['read', 'update', 'insert', 'scan', 'rmw', 'delete']
        for op in ops:
            if op not in mix:
                mix[op] = 0.0
        total = sum(mix[op] for op in ops)
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"YCSB mix must sum to 1.0 (got {total:.3f})")

    def _random_string(self, length=100):
        return ''.join(random.choices(string.ascii_lowercase, k=length))

    def _make_key(self, i):
        return f"user{str(i).zfill(12)}"

    def _random_key_zipfian(self):
        if self.zipfian is None:
            self.zipfian = ZipfianGenerator(self.num_records)
        return self._make_key(self.zipfian.next())

    def _random_field(self):
        return f"field{random.randint(0, self.field_count - 1)}"

    def create_schema(self, conn):
        cur = conn.cursor()
        print("[YCSB] Creating schema...")
        cur.execute("DROP TABLE IF EXISTS usertable CASCADE")
        fields = ', '.join([f"field{i} VARCHAR(128)" for i in range(self.field_count)])
        cur.execute(f"""
            CREATE TABLE usertable (
                ycsb_key VARCHAR(24) PRIMARY KEY,
                {fields}
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS usertable_key_idx ON usertable (ycsb_key)")
        conn.commit()
        cur.close()
        print("[YCSB] Schema created.")

    def load_data(self, conn):
        cur   = conn.cursor()
        total = self.num_records
        batch = 5000
        print(f"[YCSB] Loading {total} records...")
        for start in range(0, total, batch):
            end  = min(start + batch, total)
            rows = []
            for i in range(start, end):
                key    = self._make_key(i)
                fields = [self._random_string(self.field_size) for _ in range(self.field_count)]
                rows.append((key, *fields))
            placeholders = '(' + ','.join(['%s'] * (self.field_count + 1)) + ')'
            cur.executemany(f"INSERT INTO usertable VALUES {placeholders}", rows)
            conn.commit()
            if end % 100000 == 0 or end == total:
                print(f"[YCSB] Loaded {end}/{total} records")
        cur.close()
        print("[YCSB] Data loading complete.")

    def do_read(self, conn):
        key = self._random_key_zipfian()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usertable WHERE ycsb_key = %s", (key,))
        cur.fetchone()
        conn.commit()
        cur.close()

    def do_update(self, conn):
        key   = self._random_key_zipfian()
        field = self._random_field()
        value = self._random_string(self.field_size)
        cur   = conn.cursor()
        cur.execute(f"UPDATE usertable SET {field} = %s WHERE ycsb_key = %s", (value, key))
        conn.commit()
        cur.close()

    def do_insert(self, conn):
        self.insert_counter += 1
        key    = self._make_key(self.insert_counter)
        fields = [self._random_string(self.field_size) for _ in range(self.field_count)]
        cur    = conn.cursor()
        placeholders = ','.join(['%s'] * (self.field_count + 1))
        cur.execute(f"INSERT INTO usertable VALUES ({placeholders})", (key, *fields))
        conn.commit()
        cur.close()

    def do_scan(self, conn):
        key    = self._random_key_zipfian()
        length = random.randint(1, self.scan_length)
        cur    = conn.cursor()
        cur.execute(
            "SELECT * FROM usertable WHERE ycsb_key >= %s ORDER BY ycsb_key LIMIT %s",
            (key, length)
        )
        cur.fetchall()
        conn.commit()
        cur.close()

    def do_read_modify_write(self, conn):
        key   = self._random_key_zipfian()
        field = self._random_field()
        cur   = conn.cursor()
        cur.execute(f"SELECT {field} FROM usertable WHERE ycsb_key = %s", (key,))
        cur.fetchone()
        value = self._random_string(self.field_size)
        cur.execute(f"UPDATE usertable SET {field} = %s WHERE ycsb_key = %s", (value, key))
        conn.commit()
        cur.close()

    def do_delete(self, conn):
        key = self._random_key_zipfian()
        cur = conn.cursor()
        cur.execute("DELETE FROM usertable WHERE ycsb_key = %s", (key,))
        conn.commit()
        cur.close()

    def run_transaction(self, conn):
        r          = random.random()
        mix        = self.mix
        cumulative = mix['read']
        if r < cumulative:
            self.do_read(conn); return
        cumulative += mix['update']
        if r < cumulative:
            self.do_update(conn); return
        cumulative += mix['insert']
        if r < cumulative:
            self.do_insert(conn); return
        cumulative += mix['scan']
        if r < cumulative:
            self.do_scan(conn); return
        cumulative += mix['rmw']
        if r < cumulative:
            self.do_read_modify_write(conn); return
        self.do_delete(conn)
