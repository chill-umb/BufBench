import random
import threading
import time
from workloads.tpcc import TPCCWorkload

ANALYTICAL_QUERIES = {

    'Q1': """
        SELECT ol_number,
            SUM(ol_quantity) AS sum_qty, SUM(ol_amount) AS sum_amount,
            AVG(ol_quantity) AS avg_qty, AVG(ol_amount) AS avg_amount,
            COUNT(*) AS count_order
        FROM order_line
        WHERE ol_delivery_d IS NOT NULL
        GROUP BY ol_number ORDER BY ol_number
    """,

    'Q2': """
        SELECT s_w_id, s_i_id, i_name, i_price, MIN(s_quantity) AS min_qty
        FROM stock JOIN item ON i_id = s_i_id
        WHERE i_data LIKE '%b'
        GROUP BY s_w_id, s_i_id, i_name, i_price
        ORDER BY min_qty LIMIT 20
    """,

    'Q3': """
        SELECT ol_o_id, ol_w_id, ol_d_id, SUM(ol_amount) AS revenue, o_entry_d
        FROM customer
        JOIN orders      ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line  ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        WHERE c_state LIKE 'A%' AND o_entry_d > '2000-01-01' AND ol_delivery_d > '2000-01-01'
        GROUP BY ol_o_id, ol_w_id, ol_d_id, o_entry_d
        ORDER BY revenue DESC, o_entry_d LIMIT 20
    """,

    'Q4': """
        SELECT o_ol_cnt, COUNT(*) AS order_count
        FROM orders
        WHERE o_entry_d >= '2000-01-01' AND o_entry_d < '2025-01-01'
          AND EXISTS (
              SELECT 1 FROM order_line
              WHERE ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
                AND ol_delivery_d >= o_entry_d)
        GROUP BY o_ol_cnt ORDER BY o_ol_cnt
    """,

    'Q5': """
        SELECT c_state, SUM(ol_amount) AS revenue
        FROM customer
        JOIN orders     ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        JOIN stock      ON ol_i_id=s_i_id AND ol_supply_w_id=s_w_id
        WHERE ol_delivery_d >= '2000-01-01' AND ol_delivery_d < '2025-01-01'
        GROUP BY c_state ORDER BY revenue DESC
    """,

    'Q6': """
        SELECT SUM(ol_amount) AS revenue
        FROM order_line
        WHERE ol_delivery_d >= '2000-01-01' AND ol_delivery_d < '2025-01-01'
          AND ol_quantity BETWEEN 1 AND 100000
    """,

    'Q7': """
        SELECT c_state AS cust_nation,
               EXTRACT(YEAR FROM o_entry_d) AS l_year,
               SUM(ol_amount) AS revenue
        FROM customer
        JOIN orders     ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        WHERE ol_delivery_d BETWEEN '2000-01-01' AND '2025-12-31'
        GROUP BY c_state, EXTRACT(YEAR FROM o_entry_d)
        ORDER BY c_state, l_year
    """,

    'Q8': """
        SELECT EXTRACT(YEAR FROM o_entry_d) AS l_year,
               SUM(CASE WHEN c_state LIKE 'A%' THEN ol_amount ELSE 0 END)
               / NULLIF(SUM(ol_amount),0) AS mkt_share
        FROM customer
        JOIN orders     ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        JOIN item       ON i_id=ol_i_id
        WHERE i_data LIKE '%b' AND o_entry_d BETWEEN '2000-01-01' AND '2025-12-31'
        GROUP BY EXTRACT(YEAR FROM o_entry_d) ORDER BY l_year
    """,

    'Q9': """
        SELECT c_state AS nation,
               EXTRACT(YEAR FROM o_entry_d) AS o_year,
               SUM(ol_amount) AS sum_profit
        FROM customer
        JOIN orders     ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        JOIN stock      ON s_i_id=ol_i_id AND s_w_id=ol_supply_w_id
        JOIN item       ON i_id=ol_i_id
        WHERE i_data LIKE '%bb%'
        GROUP BY c_state, EXTRACT(YEAR FROM o_entry_d)
        ORDER BY nation, o_year DESC
    """,

    'Q10': """
        SELECT c_id, c_last, c_city, SUM(ol_amount) AS revenue
        FROM customer
        JOIN orders     ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        WHERE o_entry_d >= '2000-01-01' AND o_entry_d < '2025-01-01'
          AND ol_delivery_d IS NOT NULL
        GROUP BY c_id, c_last, c_city
        ORDER BY revenue DESC LIMIT 20
    """,

    'Q11': """
        SELECT s_i_id, SUM(s_quantity * s_ytd) AS value
        FROM stock WHERE s_quantity > 10
        GROUP BY s_i_id
        HAVING SUM(s_quantity * s_ytd) > (
            SELECT SUM(s_quantity * s_ytd) * 0.005 FROM stock)
        ORDER BY value DESC LIMIT 20
    """,

    'Q12': """
        SELECT ol_number,
               SUM(CASE WHEN o_carrier_id IN (1,2) THEN 1 ELSE 0 END) AS high_line_count,
               SUM(CASE WHEN o_carrier_id NOT IN (1,2) THEN 1 ELSE 0 END) AS low_line_count
        FROM orders
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        WHERE o_entry_d >= '2000-01-01' AND o_entry_d < '2025-01-01'
          AND ol_delivery_d >= o_entry_d
        GROUP BY ol_number ORDER BY ol_number
    """,

    'Q13': """
        SELECT c_count, COUNT(*) AS custdist
        FROM (
            SELECT c_id, COUNT(o_id) AS c_count
            FROM customer
            LEFT JOIN orders ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
                AND o_carrier_id > 8
            GROUP BY c_id
        ) AS sub
        GROUP BY c_count ORDER BY custdist DESC, c_count DESC
    """,

    'Q14': """
        SELECT 100.00 * SUM(CASE WHEN i_data LIKE 'PR%' THEN ol_amount ELSE 0 END)
               / NULLIF(SUM(ol_amount),0) AS promo_revenue
        FROM order_line JOIN item ON ol_i_id=i_id
        WHERE ol_delivery_d >= '2000-01-01' AND ol_delivery_d < '2025-01-01'
    """,

    'Q15': """
        SELECT s_i_id, SUM(ol_amount) AS total_revenue
        FROM stock
        JOIN order_line ON ol_i_id=s_i_id AND ol_supply_w_id=s_w_id
        WHERE ol_delivery_d >= '2000-01-01' AND ol_delivery_d < '2025-01-01'
        GROUP BY s_i_id ORDER BY total_revenue DESC LIMIT 20
    """,

    'Q16': """
        SELECT i_name, i_price, COUNT(DISTINCT s_w_id) AS supplier_cnt
        FROM stock JOIN item ON i_id=s_i_id
        WHERE i_data NOT LIKE '%b%' AND i_price BETWEEN 1 AND 40
          AND s_quantity BETWEEN 0 AND 100
        GROUP BY i_name, i_price ORDER BY supplier_cnt DESC LIMIT 20
    """,

    'Q17': """
        SELECT SUM(ol.ol_amount) / 7.0 AS avg_yearly
        FROM order_line ol
        JOIN item ON i_id=ol.ol_i_id
        JOIN (
            SELECT ol_i_id, AVG(ol_quantity) * 0.2 AS avg_qty
            FROM order_line GROUP BY ol_i_id
        ) avg_table ON avg_table.ol_i_id=ol.ol_i_id
        WHERE i_data LIKE '%b' AND ol.ol_quantity < avg_table.avg_qty
    """,

    'Q18': """
        SELECT c_last, c_id, o_id, o_entry_d, o_ol_cnt, SUM(ol_amount) AS total_amount
        FROM customer
        JOIN orders     ON c_id=o_c_id AND c_w_id=o_w_id AND c_d_id=o_d_id
        JOIN order_line ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
        GROUP BY c_last, c_id, o_id, o_entry_d, o_ol_cnt
        HAVING SUM(ol_amount) > 200
        ORDER BY total_amount DESC, o_entry_d LIMIT 20
    """,

    'Q19': """
        SELECT SUM(ol_amount) AS revenue
        FROM order_line JOIN item ON ol_i_id=i_id
        WHERE (i_data LIKE '%a' AND ol_quantity BETWEEN 1 AND 10)
           OR (i_data LIKE '%b' AND ol_quantity BETWEEN 10 AND 20)
           OR (i_data LIKE '%c' AND ol_quantity BETWEEN 20 AND 30)
    """,

    'Q20': """
        SELECT s_i_id, s_w_id, s_quantity
        FROM stock
        WHERE s_quantity > (SELECT AVG(s_quantity) * 0.5 FROM stock)
          AND s_i_id IN (
              SELECT ol_i_id FROM order_line
              WHERE ol_delivery_d >= '2000-01-01' AND ol_delivery_d < '2025-01-01')
        ORDER BY s_quantity DESC LIMIT 20
    """,

    'Q21': """
        SELECT s_w_id, COUNT(DISTINCT s_i_id) AS num_items,
               SUM(s_quantity) AS total_qty, AVG(s_quantity) AS avg_qty
        FROM stock
        WHERE s_quantity < 50 AND s_order_cnt > 0
          AND s_i_id IN (
              SELECT ol_i_id FROM order_line
              JOIN orders ON ol_o_id=o_id AND ol_w_id=o_w_id AND ol_d_id=o_d_id
              WHERE ol_w_id != ol_supply_w_id AND o_entry_d > '2000-01-01')
        GROUP BY s_w_id ORDER BY num_items DESC
    """,

    'Q22': """
        SELECT SUBSTR(c_state,1,1) AS cntrycode,
               COUNT(*) AS numcust, SUM(c_balance) AS totacctbal
        FROM customer
        WHERE SUBSTR(c_state,1,1) IN ('A','B','C','D','E','F','G')
          AND c_balance > (
              SELECT AVG(c_balance) FROM customer
              WHERE c_balance > 0.00
                AND SUBSTR(c_state,1,1) IN ('A','B','C','D','E','F','G'))
          AND NOT EXISTS (
              SELECT 1 FROM orders
              WHERE o_c_id=c_id AND o_w_id=c_w_id AND o_d_id=c_d_id)
        GROUP BY SUBSTR(c_state,1,1) ORDER BY cntrycode
    """,
}


class CHBenchmarkWorkload(TPCCWorkload):

    def __init__(self, config):
        super().__init__(config)
        ch_cfg = config['workload'].get('chbenchmark', {})
        self.num_analytical_threads = ch_cfg.get('analytical_threads', 2)
        self.analytical_results     = []
        self.analytical_lock        = threading.Lock()
        print(f"[CH] OLTP clients:       {self.num_clients}")
        print(f"[CH] Analytical threads: {self.num_analytical_threads}")

    def analytical_worker(self, worker_id, stop_event):
        conn        = self.get_connection()
        conn.autocommit = True
        query_names = list(ANALYTICAL_QUERIES.keys())
        count       = 0
        print(f"[CH-Analytical {worker_id}] Started")
        while not stop_event.is_set():
            q_name = random.choice(query_names)
            q_sql  = ANALYTICAL_QUERIES[q_name]
            start  = time.time()
            try:
                cur = conn.cursor()
                cur.execute(q_sql)
                cur.fetchall()
                cur.close()
                latency = (time.time() - start) * 1000
                with self.analytical_lock:
                    self.analytical_results.append({'query': q_name, 'latency': round(latency, 2)})
                count += 1
            except Exception as e:
                print(f"[CH-Analytical {worker_id}] Error in {q_name}: {e}")
        conn.close()
        print(f"[CH-Analytical {worker_id}] Finished — {count} queries")

    def get_analytical_summary(self):
        if not self.analytical_results:
            return {}
        by_query = {}
        for r in self.analytical_results:
            q = r['query']
            if q not in by_query:
                by_query[q] = []
            by_query[q].append(r['latency'])
        summary = {}
        for q, latencies in by_query.items():
            latencies.sort()
            n = len(latencies)
            summary[q] = {
                'count':  n,
                'avg_ms': round(sum(latencies) / n, 2),
                'p50_ms': round(latencies[int(n * 0.50)], 2),
                'p99_ms': round(latencies[int(n * 0.99)], 2),
            }
        return summary
