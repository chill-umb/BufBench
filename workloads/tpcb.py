import random
import time
from workloads.base import BaseWorkload

class TPCBWorkload(BaseWorkload):

    def create_schema(self, conn):
        cur = conn.cursor()
        print("[TPC-B] Creating schema...")

        cur.execute("DROP TABLE IF EXISTS history CASCADE")
        cur.execute("DROP TABLE IF EXISTS accounts CASCADE")
        cur.execute("DROP TABLE IF EXISTS tellers CASCADE")
        cur.execute("DROP TABLE IF EXISTS branches CASCADE")

        cur.execute("""
            CREATE TABLE branches (
                bid      INT PRIMARY KEY,
                bbalance BIGINT NOT NULL,
                filler   CHAR(88) NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE tellers (
                tid      INT PRIMARY KEY,
                bid      INT NOT NULL,
                tbalance BIGINT NOT NULL,
                filler   CHAR(84) NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE accounts (
                aid      INT PRIMARY KEY,
                bid      INT NOT NULL,
                abalance BIGINT NOT NULL,
                filler   CHAR(84) NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE history (
                tid    INT NOT NULL,
                bid    INT NOT NULL,
                aid    INT NOT NULL,
                delta  BIGINT NOT NULL,
                mtime  TIMESTAMP NOT NULL,
                filler CHAR(22) NOT NULL
            )
        """)
        conn.commit()
        cur.close()
        print("[TPC-B] Schema created.")

    def load_data(self, conn):
        cur = conn.cursor()
        scale = self.scale
        print(f"[TPC-B] Loading data (scale={scale})...")

        for bid in range(1, scale + 1):
            cur.execute("INSERT INTO branches VALUES (%s, 0, %s)", (bid, ' ' * 88))
        conn.commit()

        for tid in range(1, scale * 10 + 1):
            bid = ((tid - 1) // 10) + 1
            cur.execute("INSERT INTO tellers VALUES (%s, %s, 0, %s)", (tid, bid, ' ' * 84))
        conn.commit()

        total_accounts = scale * 100000
        batch_size = 10000
        print("[TPC-B] Loading accounts (this may take a while)...")
        for start in range(1, total_accounts + 1, batch_size):
            end = min(start + batch_size - 1, total_accounts)
            batch = []
            for aid in range(start, end + 1):
                bid = ((aid - 1) // 100000) + 1
                batch.append((aid, bid, 0, ' ' * 84))
            cur.executemany("INSERT INTO accounts VALUES (%s, %s, %s, %s)", batch)
            conn.commit()
            if end % 500000 == 0 or end == total_accounts:
                print(f"[TPC-B] Accounts loaded: {end}/{total_accounts}")

        cur.close()
        print("[TPC-B] Data loading complete.")

    def run_transaction(self, conn):
        scale = self.scale
        aid   = random.randint(1, scale * 100000)
        bid   = random.randint(1, scale)
        tid   = random.randint(1, scale * 10)
        delta = random.randint(-999999, 999999)
        cur   = conn.cursor()

        cur.execute("UPDATE accounts SET abalance = abalance + %s WHERE aid = %s", (delta, aid))
        cur.execute("SELECT abalance FROM accounts WHERE aid = %s", (aid,))
        cur.execute("UPDATE tellers SET tbalance = tbalance + %s WHERE tid = %s", (delta, tid))
        cur.execute("UPDATE branches SET bbalance = bbalance + %s WHERE bid = %s", (delta, bid))
        cur.execute("INSERT INTO history VALUES (%s, %s, %s, %s, NOW(), %s)",
                    (tid, bid, aid, delta, ' ' * 22))
        conn.commit()
        cur.close()
