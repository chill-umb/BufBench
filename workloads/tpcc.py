import random
import string
import datetime
from workloads.base import BaseWorkload

class TPCCWorkload(BaseWorkload):

    def __init__(self, config):
        super().__init__(config)
        self.num_warehouses          = self.scale
        self.items_per_warehouse     = 100000
        self.districts_per_warehouse = 10
        self.customers_per_district  = 3000

    def _rand_string(self, min_len, max_len):
        length = random.randint(min_len, max_len)
        return ''.join(random.choices(string.ascii_letters, k=length))

    def _rand_numeric_string(self, min_len, max_len):
        length = random.randint(min_len, max_len)
        return ''.join(random.choices(string.digits, k=length))

    def _rand_zip(self):
        return self._rand_numeric_string(4, 4) + '11111'

    def _rand_last_name(self, n=None):
        syllables = ['BAR','OUGHT','ABLE','PRI','PRES','ESE','ANTI','CALLY','ATION','EING']
        if n is None:
            n = random.randint(0, 999)
        s = str(n).zfill(3)
        return syllables[int(s[0])] + syllables[int(s[1])] + syllables[int(s[2])]

    def _nurand(self, a, x, y):
        c = random.randint(0, a)
        return (((random.randint(0, a) | random.randint(x, y)) + c) % (y - x + 1)) + x

    def create_schema(self, conn):
        cur = conn.cursor()
        print("[TPC-C] Creating schema...")
        tables = ['order_line','new_orders','orders','history','customer','stock','district','warehouse','item']
        for t in tables:
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

        cur.execute("""CREATE TABLE item (
            i_id INT PRIMARY KEY, i_im_id INT NOT NULL,
            i_name VARCHAR(24) NOT NULL, i_price NUMERIC(5,2) NOT NULL,
            i_data VARCHAR(50) NOT NULL)""")

        cur.execute("""CREATE TABLE warehouse (
            w_id INT PRIMARY KEY, w_name VARCHAR(10) NOT NULL,
            w_street_1 VARCHAR(20) NOT NULL, w_street_2 VARCHAR(20) NOT NULL,
            w_city VARCHAR(20) NOT NULL, w_state CHAR(2) NOT NULL,
            w_zip CHAR(9) NOT NULL, w_tax NUMERIC(4,4) NOT NULL,
            w_ytd NUMERIC(12,2) NOT NULL)""")

        cur.execute("""CREATE TABLE district (
            d_id INT NOT NULL, d_w_id INT NOT NULL,
            d_name VARCHAR(10) NOT NULL, d_street_1 VARCHAR(20) NOT NULL,
            d_street_2 VARCHAR(20) NOT NULL, d_city VARCHAR(20) NOT NULL,
            d_state CHAR(2) NOT NULL, d_zip CHAR(9) NOT NULL,
            d_tax NUMERIC(4,4) NOT NULL, d_ytd NUMERIC(12,2) NOT NULL,
            d_next_o_id INT NOT NULL, PRIMARY KEY (d_w_id, d_id))""")

        cur.execute("""CREATE TABLE customer (
            c_id INT NOT NULL, c_d_id INT NOT NULL, c_w_id INT NOT NULL,
            c_first VARCHAR(16) NOT NULL, c_middle CHAR(2) NOT NULL,
            c_last VARCHAR(16) NOT NULL, c_street_1 VARCHAR(20) NOT NULL,
            c_street_2 VARCHAR(20) NOT NULL, c_city VARCHAR(20) NOT NULL,
            c_state CHAR(2) NOT NULL, c_zip CHAR(9) NOT NULL,
            c_phone CHAR(16) NOT NULL, c_since TIMESTAMP NOT NULL,
            c_credit CHAR(2) NOT NULL, c_credit_lim NUMERIC(12,2) NOT NULL,
            c_discount NUMERIC(4,4) NOT NULL, c_balance NUMERIC(12,2) NOT NULL,
            c_ytd_payment NUMERIC(12,2) NOT NULL, c_payment_cnt INT NOT NULL,
            c_delivery_cnt INT NOT NULL, c_data VARCHAR(500) NOT NULL,
            PRIMARY KEY (c_w_id, c_d_id, c_id))""")

        cur.execute("""CREATE TABLE history (
            h_c_id INT NOT NULL, h_c_d_id INT NOT NULL, h_c_w_id INT NOT NULL,
            h_d_id INT NOT NULL, h_w_id INT NOT NULL, h_date TIMESTAMP NOT NULL,
            h_amount NUMERIC(6,2) NOT NULL, h_data VARCHAR(24) NOT NULL)""")

        cur.execute("""CREATE TABLE orders (
            o_id INT NOT NULL, o_d_id INT NOT NULL, o_w_id INT NOT NULL,
            o_c_id INT NOT NULL, o_entry_d TIMESTAMP NOT NULL,
            o_carrier_id INT, o_ol_cnt INT NOT NULL, o_all_local INT NOT NULL,
            PRIMARY KEY (o_w_id, o_d_id, o_id))""")

        cur.execute("""CREATE TABLE new_orders (
            no_o_id INT NOT NULL, no_d_id INT NOT NULL, no_w_id INT NOT NULL,
            PRIMARY KEY (no_w_id, no_d_id, no_o_id))""")

        cur.execute("""CREATE TABLE order_line (
            ol_o_id INT NOT NULL, ol_d_id INT NOT NULL, ol_w_id INT NOT NULL,
            ol_number INT NOT NULL, ol_i_id INT NOT NULL,
            ol_supply_w_id INT NOT NULL, ol_delivery_d TIMESTAMP,
            ol_quantity INT NOT NULL, ol_amount NUMERIC(6,2) NOT NULL,
            ol_dist_info CHAR(24) NOT NULL,
            PRIMARY KEY (ol_w_id, ol_d_id, ol_o_id, ol_number))""")

        cur.execute("""CREATE TABLE stock (
            s_i_id INT NOT NULL, s_w_id INT NOT NULL,
            s_quantity INT NOT NULL,
            s_dist_01 CHAR(24) NOT NULL, s_dist_02 CHAR(24) NOT NULL,
            s_dist_03 CHAR(24) NOT NULL, s_dist_04 CHAR(24) NOT NULL,
            s_dist_05 CHAR(24) NOT NULL, s_dist_06 CHAR(24) NOT NULL,
            s_dist_07 CHAR(24) NOT NULL, s_dist_08 CHAR(24) NOT NULL,
            s_dist_09 CHAR(24) NOT NULL, s_dist_10 CHAR(24) NOT NULL,
            s_ytd INT NOT NULL, s_order_cnt INT NOT NULL,
            s_remote_cnt INT NOT NULL, s_data VARCHAR(50) NOT NULL,
            PRIMARY KEY (s_w_id, s_i_id))""")

        cur.execute("CREATE INDEX idx_customer_last ON customer (c_w_id, c_d_id, c_last)")
        cur.execute("CREATE INDEX idx_orders_cid ON orders (o_w_id, o_d_id, o_c_id)")
        cur.execute("CREATE INDEX idx_new_orders ON new_orders (no_w_id, no_d_id)")
        cur.execute("CREATE INDEX idx_ol_i_id ON order_line (ol_i_id)")
        cur.execute("CREATE INDEX idx_ol_quantity ON order_line (ol_i_id, ol_quantity)")

        conn.commit()
        cur.close()
        print("[TPC-C] Schema created.")

    def load_data(self, conn):
        self._load_items(conn)
        self._load_warehouses(conn)
        print("[TPC-C] Data loading complete.")

    def _load_items(self, conn):
        cur   = conn.cursor()
        total = self.items_per_warehouse
        batch = 5000
        print(f"[TPC-C] Loading {total} items...")
        for start in range(1, total + 1, batch):
            end  = min(start + batch - 1, total)
            rows = []
            for i_id in range(start, end + 1):
                i_data = self._rand_string(26, 50)
                if random.randint(1, 10) == 1:
                    pos    = random.randint(0, len(i_data) - 8)
                    i_data = i_data[:pos] + 'ORIGINAL' + i_data[pos + 8:]
                rows.append((i_id, random.randint(1, 10000),
                             self._rand_string(14, 24),
                             round(random.uniform(1.00, 100.00), 2), i_data))
            cur.executemany("INSERT INTO item VALUES (%s,%s,%s,%s,%s)", rows)
            conn.commit()
            if end % 25000 == 0 or end == total:
                print(f"[TPC-C] Items: {end}/{total}")
        cur.close()

    def _load_warehouses(self, conn):
        for w_id in range(1, self.num_warehouses + 1):
            print(f"[TPC-C] Loading warehouse {w_id}/{self.num_warehouses}...")
            cur = conn.cursor()
            cur.execute("INSERT INTO warehouse VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (w_id, self._rand_string(6,10), self._rand_string(10,20),
                 self._rand_string(10,20), self._rand_string(10,20),
                 self._rand_string(2,2).upper(), self._rand_zip(),
                 round(random.uniform(0.0, 0.2), 4), 300000.00))
            conn.commit()
            cur.close()
            self._load_stock(conn, w_id)
            self._load_districts(conn, w_id)

    def _load_stock(self, conn, w_id):
        cur   = conn.cursor()
        total = self.items_per_warehouse
        batch = 5000
        print(f"[TPC-C] Loading stock for warehouse {w_id}...")
        for start in range(1, total + 1, batch):
            end  = min(start + batch - 1, total)
            rows = []
            for s_i_id in range(start, end + 1):
                s_data = self._rand_string(26, 50)
                if random.randint(1, 10) == 1:
                    pos    = random.randint(0, len(s_data) - 8)
                    s_data = s_data[:pos] + 'ORIGINAL' + s_data[pos + 8:]
                rows.append((s_i_id, w_id, random.randint(10, 100),
                             self._rand_string(24,24), self._rand_string(24,24),
                             self._rand_string(24,24), self._rand_string(24,24),
                             self._rand_string(24,24), self._rand_string(24,24),
                             self._rand_string(24,24), self._rand_string(24,24),
                             self._rand_string(24,24), self._rand_string(24,24),
                             0, 0, 0, s_data))
            cur.executemany(
                "INSERT INTO stock VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                rows)
            conn.commit()
        cur.close()

    def _load_districts(self, conn, w_id):
        for d_id in range(1, self.districts_per_warehouse + 1):
            cur = conn.cursor()
            cur.execute("INSERT INTO district VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (d_id, w_id, self._rand_string(6,10), self._rand_string(10,20),
                 self._rand_string(10,20), self._rand_string(10,20),
                 self._rand_string(2,2).upper(), self._rand_zip(),
                 round(random.uniform(0.0, 0.2), 4), 30000.00, 3001))
            conn.commit()
            cur.close()
            self._load_customers(conn, w_id, d_id)
            self._load_orders(conn, w_id, d_id)

    def _load_customers(self, conn, w_id, d_id):
        cur   = conn.cursor()
        total = self.customers_per_district
        batch = 500
        for start in range(1, total + 1, batch):
            end  = min(start + batch - 1, total)
            rows = []
            for c_id in range(start, end + 1):
                c_last   = self._rand_last_name(c_id - 1 if c_id <= 1000 else None)
                c_credit = 'GC' if random.randint(1, 10) <= 9 else 'BC'
                rows.append((c_id, d_id, w_id, self._rand_string(8,16), 'OE',
                             c_last, self._rand_string(10,20), self._rand_string(10,20),
                             self._rand_string(10,20), self._rand_string(2,2).upper(),
                             self._rand_zip(), self._rand_numeric_string(16,16),
                             datetime.datetime.now(), c_credit, 50000.00,
                             round(random.uniform(0.0, 0.5), 4),
                             -10.00, 10.00, 1, 0, self._rand_string(300, 500)))
            cur.executemany(
                "INSERT INTO customer VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                rows)
            conn.commit()
        cur.close()

    def _load_orders(self, conn, w_id, d_id):
        cur   = conn.cursor()
        total = self.customers_per_district
        c_ids = list(range(1, total + 1))
        random.shuffle(c_ids)
        for o_id, c_id in enumerate(c_ids, start=1):
            o_carrier_id = random.randint(1, 10) if o_id < 2101 else None
            ol_cnt       = random.randint(5, 15)
            cur.execute("INSERT INTO orders VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (o_id, d_id, w_id, c_id, datetime.datetime.now(), o_carrier_id, ol_cnt, 1))
            if o_id >= 2101:
                cur.execute("INSERT INTO new_orders VALUES (%s,%s,%s)", (o_id, d_id, w_id))
            for ol_num in range(1, ol_cnt + 1):
                ol_amount   = 0.00 if o_id < 2101 else round(random.uniform(0.01, 9999.99), 2)
                ol_delivery = datetime.datetime.now() if o_id < 2101 else None
                cur.execute("INSERT INTO order_line VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (o_id, d_id, w_id, ol_num,
                     random.randint(1, self.items_per_warehouse),
                     w_id, ol_delivery, 5, ol_amount, self._rand_string(24,24)))
        conn.commit()
        cur.close()

    def _txn_new_order(self, conn):
        w_id   = random.randint(1, self.num_warehouses)
        d_id   = random.randint(1, self.districts_per_warehouse)
        c_id   = self._nurand(1023, 1, self.customers_per_district)
        ol_cnt = random.randint(5, 15)
        cur    = conn.cursor()

        cur.execute("SELECT w_tax FROM warehouse WHERE w_id = %s", (w_id,))
        cur.fetchone()

        cur.execute("SELECT d_tax, d_next_o_id FROM district WHERE d_w_id=%s AND d_id=%s FOR UPDATE", (w_id, d_id))
        row   = cur.fetchone()
        o_id  = row[1]

        cur.execute("UPDATE district SET d_next_o_id = d_next_o_id + 1 WHERE d_w_id=%s AND d_id=%s", (w_id, d_id))
        cur.execute("SELECT c_discount, c_last, c_credit FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s", (w_id, d_id, c_id))
        cur.fetchone()
        cur.execute("INSERT INTO orders VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (o_id, d_id, w_id, c_id, datetime.datetime.now(), None, ol_cnt, 1))
        cur.execute("INSERT INTO new_orders VALUES (%s,%s,%s)", (o_id, d_id, w_id))

        for ol_num in range(1, ol_cnt + 1):
            i_id    = self._nurand(8191, 1, self.items_per_warehouse)
            ol_qty  = random.randint(1, 10)
            cur.execute("SELECT i_price, i_name, i_data FROM item WHERE i_id = %s", (i_id,))
            item_row = cur.fetchone()
            if item_row is None:
                conn.rollback(); cur.close(); return
            i_price = item_row[0]
            cur.execute(
                f"SELECT s_quantity, s_dist_{str(d_id).zfill(2)}, s_data FROM stock WHERE s_w_id=%s AND s_i_id=%s FOR UPDATE",
                (w_id, i_id))
            stock_row  = cur.fetchone()
            s_quantity = stock_row[0]
            s_dist     = stock_row[1]
            new_qty    = s_quantity - ol_qty
            if new_qty < 10:
                new_qty += 91
            cur.execute("UPDATE stock SET s_quantity=%s, s_ytd=s_ytd+%s, s_order_cnt=s_order_cnt+1 WHERE s_w_id=%s AND s_i_id=%s",
                (new_qty, ol_qty, w_id, i_id))
            cur.execute("INSERT INTO order_line VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (o_id, d_id, w_id, ol_num, i_id, w_id, None, ol_qty, ol_qty * float(i_price), s_dist))

        conn.commit()
        cur.close()

    def _txn_payment(self, conn):
        w_id     = random.randint(1, self.num_warehouses)
        d_id     = random.randint(1, self.districts_per_warehouse)
        h_amount = round(random.uniform(1.00, 5000.00), 2)
        cur      = conn.cursor()

        cur.execute("UPDATE warehouse SET w_ytd = w_ytd + %s WHERE w_id = %s", (h_amount, w_id))
        cur.execute("SELECT w_name FROM warehouse WHERE w_id = %s", (w_id,))
        w_row = cur.fetchone()
        cur.execute("UPDATE district SET d_ytd = d_ytd + %s WHERE d_w_id=%s AND d_id=%s", (h_amount, w_id, d_id))

        if random.random() < 0.60:
            c_last = self._rand_last_name()
            cur.execute("SELECT c_id FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_last=%s ORDER BY c_first LIMIT 1",
                (w_id, d_id, c_last))
            row = cur.fetchone()
            if row is None:
                conn.rollback(); cur.close(); return
            c_id = row[0]
        else:
            c_id = self._nurand(1023, 1, self.customers_per_district)

        cur.execute("SELECT c_balance, c_credit FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s FOR UPDATE",
            (w_id, d_id, c_id))
        c_row       = cur.fetchone()
        new_balance = float(c_row[0]) - h_amount
        cur.execute("UPDATE customer SET c_balance=%s, c_ytd_payment=c_ytd_payment+%s, c_payment_cnt=c_payment_cnt+1 WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s",
            (new_balance, h_amount, w_id, d_id, c_id))
        h_data = (w_row[0] if w_row else '') + '    '
        cur.execute("INSERT INTO history VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (c_id, d_id, w_id, d_id, w_id, datetime.datetime.now(), h_amount, h_data))
        conn.commit()
        cur.close()

    def _txn_order_status(self, conn):
        w_id = random.randint(1, self.num_warehouses)
        d_id = random.randint(1, self.districts_per_warehouse)
        cur  = conn.cursor()
        if random.random() < 0.60:
            c_last = self._rand_last_name()
            cur.execute("SELECT c_id FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_last=%s ORDER BY c_first LIMIT 1",
                (w_id, d_id, c_last))
        else:
            c_id = self._nurand(1023, 1, self.customers_per_district)
            cur.execute("SELECT c_id FROM customer WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s", (w_id, d_id, c_id))
        c_row = cur.fetchone()
        if c_row is None:
            conn.rollback(); cur.close(); return
        c_id = c_row[0]
        cur.execute("SELECT o_id, o_entry_d, o_carrier_id FROM orders WHERE o_w_id=%s AND o_d_id=%s AND o_c_id=%s ORDER BY o_id DESC LIMIT 1",
            (w_id, d_id, c_id))
        o_row = cur.fetchone()
        if o_row:
            cur.execute("SELECT ol_i_id, ol_supply_w_id, ol_quantity, ol_amount, ol_delivery_d FROM order_line WHERE ol_w_id=%s AND ol_d_id=%s AND ol_o_id=%s",
                (w_id, d_id, o_row[0]))
            cur.fetchall()
        conn.commit()
        cur.close()

    def _txn_delivery(self, conn):
        w_id         = random.randint(1, self.num_warehouses)
        o_carrier_id = random.randint(1, 10)
        cur          = conn.cursor()
        for d_id in range(1, self.districts_per_warehouse + 1):
            cur.execute("SELECT no_o_id FROM new_orders WHERE no_w_id=%s AND no_d_id=%s ORDER BY no_o_id LIMIT 1 FOR UPDATE",
                (w_id, d_id))
            row = cur.fetchone()
            if row is None: continue
            no_o_id = row[0]
            cur.execute("DELETE FROM new_orders WHERE no_w_id=%s AND no_d_id=%s AND no_o_id=%s", (w_id, d_id, no_o_id))
            cur.execute("SELECT o_c_id FROM orders WHERE o_w_id=%s AND o_d_id=%s AND o_id=%s", (w_id, d_id, no_o_id))
            o_row = cur.fetchone()
            if o_row is None: continue
            c_id = o_row[0]
            cur.execute("UPDATE orders SET o_carrier_id=%s WHERE o_w_id=%s AND o_d_id=%s AND o_id=%s",
                (o_carrier_id, w_id, d_id, no_o_id))
            cur.execute("UPDATE order_line SET ol_delivery_d=%s WHERE ol_w_id=%s AND ol_d_id=%s AND ol_o_id=%s",
                (datetime.datetime.now(), w_id, d_id, no_o_id))
            cur.execute("SELECT SUM(ol_amount) FROM order_line WHERE ol_w_id=%s AND ol_d_id=%s AND ol_o_id=%s",
                (w_id, d_id, no_o_id))
            ol_total = cur.fetchone()[0] or 0
            cur.execute("UPDATE customer SET c_balance=c_balance+%s, c_delivery_cnt=c_delivery_cnt+1 WHERE c_w_id=%s AND c_d_id=%s AND c_id=%s",
                (ol_total, w_id, d_id, c_id))
        conn.commit()
        cur.close()

    def _txn_stock_level(self, conn):
        w_id      = random.randint(1, self.num_warehouses)
        d_id      = random.randint(1, self.districts_per_warehouse)
        threshold = random.randint(10, 20)
        cur       = conn.cursor()
        cur.execute("SELECT d_next_o_id FROM district WHERE d_w_id=%s AND d_id=%s", (w_id, d_id))
        row = cur.fetchone()
        if row is None:
            conn.rollback(); cur.close(); return
        next_o_id = row[0]
        cur.execute("""
            SELECT COUNT(DISTINCT s_i_id) FROM order_line
            JOIN stock ON ol_i_id = s_i_id AND ol_supply_w_id = s_w_id
            WHERE ol_w_id=%s AND ol_d_id=%s
              AND ol_o_id BETWEEN %s AND %s
              AND s_w_id=%s AND s_quantity < %s
        """, (w_id, d_id, next_o_id - 20, next_o_id - 1, w_id, threshold))
        cur.fetchone()
        conn.commit()
        cur.close()

    def run_transaction(self, conn):
        r = random.random()
        if r < 0.45:
            self._txn_new_order(conn)
        elif r < 0.88:
            self._txn_payment(conn)
        elif r < 0.92:
            self._txn_order_status(conn)
        elif r < 0.96:
            self._txn_delivery(conn)
        else:
            self._txn_stock_level(conn)
