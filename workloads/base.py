import psycopg2
import time
import random
from abc import ABC, abstractmethod
from queue import Queue

class BaseWorkload(ABC):
    def __init__(self, config):
        self.config = config
        self.db_config = config['database']
        self.scale = config['workload']['scale']
        self.duration = config['workload']['duration']
        self.num_clients = config['workload']['clients']

    def get_connection(self):
        return psycopg2.connect(
            host=self.db_config['host'],
            port=self.db_config['port'],
            dbname=self.db_config['name'],
            user=self.db_config['user'],
            password=self.db_config['password']
        )

    @abstractmethod
    def create_schema(self, conn):
        pass

    @abstractmethod
    def load_data(self, conn):
        pass

    @abstractmethod
    def run_transaction(self, conn):
        pass

    def worker(self, worker_id, results_queue, stop_event):
        conn = self.get_connection()
        conn.autocommit = False
        local_latencies = []
        txn_count = 0

        print(f"[Worker {worker_id}] Started")

        while not stop_event.is_set():
            try:
                start = time.time()
                self.run_transaction(conn)
                latency = (time.time() - start) * 1000
                local_latencies.append(latency)
                txn_count += 1

                if len(local_latencies) >= 100:
                    results_queue.put(local_latencies.copy())
                    local_latencies.clear()

            except Exception as e:
                conn.rollback()
                print(f"[Worker {worker_id}] Error: {e}")

        if local_latencies:
            results_queue.put(local_latencies)

        conn.close()
        print(f"[Worker {worker_id}] Finished — {txn_count} transactions")
