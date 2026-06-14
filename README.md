# BufBench — PostgreSQL Buffer Pool Benchmarking Framework

BufBench is an open-source Python-based benchmarking framework for systematic analysis of PostgreSQL buffer pool behavior. It supports six workloads, collects 34 fine-grained buffer pool metrics per second, and includes an interference analyzer that automatically detects and quantifies the impact of background processes (checkpoints and autovacuum) on transaction throughput.

## Features

- **Six benchmark workloads**: TPC-B, TPC-C, TPC-H, YCSB, TATP, CH-benCHmark
- **34 buffer pool metrics** collected at 1-second granularity via `pg_buffercache` and `pg_stat_*` views
- **Background process interference analysis**: automatic detection and quantification of checkpoint and vacuum TPS drops
- **Pluggable page replacement policies**: Clock-Sweep (default), LRU, and LRU-WSR via a modified PostgreSQL build
- **Reproducible experiments**: fully driven by a single YAML configuration file

## Requirements

- Python 3.8+
- PostgreSQL 18
- psycopg2

Install dependencies:

```bash
pip install psycopg2-binary matplotlib pyyaml
```

## Usage

```bash
python3 main.py config/sample_tpcb.yaml
```

To skip database setup (e.g. when only varying `shared_buffers`):

```bash
python3 main.py config/sample_tpcb.yaml --skip-setup
```

## Configuration

Each experiment is defined by a YAML file. Sample configs for all six workloads are provided in `config/`:

| File | Workload |
|------|----------|
| `config/sample_tpcb.yaml` | TPC-B |
| `config/sample_tpcc.yaml` | TPC-C |
| `config/sample_tpch.yaml` | TPC-H |
| `config/sample_ycsb.yaml` | YCSB |
| `config/sample_tatp.yaml` | TATP |
| `config/sample_chbenchmark.yaml` | CH-benCHmark |

## Output

Each run produces the following in `results/`:

- `metrics_{run_id}.csv` — 34 buffer pool metrics at 1-second intervals
- `summary_{run_id}.csv` — throughput and latency summary
- `interference_{run_id}.txt` — human-readable interference report
- `interference_{run_id}.csv` — per-event interference log
- PDF charts — TPS, hit rate, buffer utilization, evictions, usage count

## Project Structure

```
BufBench/
├── main.py                  # Entry point
├── core/
│   └── runner.py            # Experiment runner
├── monitor/
│   └── collector.py         # Buffer pool monitor
├── reporter/
│   ├── interference.py      # Interference analyzer
│   └── plotter.py           # Chart generator
├── workloads/
│   ├── tpcb.py
│   ├── tpcc.py
│   ├── tpch.py
│   ├── ycsb.py
│   ├── tatp.py
│   └── chbenchmark.py
├── config/
│   └── sample_*.yaml        # Sample configurations
└── bufbench_pg18.patch      # PostgreSQL modification patch
```

## Page Replacement Policy Support

BufBench supports pluggable page replacement policies by targeting a modified PostgreSQL build that exposes an `eviction_algorithm` GUC parameter. The patch file `bufbench_pg18.patch` included in this repository contains all modifications made to the PostgreSQL source code to support alternative eviction algorithms.

### Modified files

- `src/backend/storage/buffer/bufmgr.c` — buffer manager, includes eviction policy dispatch
- `src/backend/storage/buffer/freelist.c` — eviction candidate selection logic
- `src/backend/storage/buffer/buf_init.c` — buffer pool initialization
- `src/include/storage/buf_internals.h` — buffer descriptor structures
- `src/include/storage/eviction.h` — new header defining eviction policy interface
- `src/backend/utils/misc/guc_tables.c` — GUC parameter registration
- `src/backend/utils/guc_tables.inc.c` — GUC table entries

### Applying the patch

```bash
# Clone PostgreSQL source
git clone https://github.com/postgres/postgres.git
cd postgres

# Apply the patch
patch -p1 < /path/to/bufbench_pg18.patch

# Build and install
./configure --prefix=$HOME/pg18
make -j$(nproc)
make install
```

### Configuring the eviction algorithm

Set the algorithm in `postgresql.conf`:

```
eviction_algorithm = lruwsr   # options: clock, lru, cflru, lruwsr
```

Then restart PostgreSQL for the change to take effect.

Currently supported policies:
- `clock` — PostgreSQL default Clock-Sweep algorithm
- `lru` — Least Recently Used
- `lruwsr` — LRU with Weak-Strong Reference distinction (designed to handle sequential scan flooding)

## Citation

If you use BufBench in your research, please cite:

```
@inproceedings{bufbench2026,
  title     = {BufBench: A Fine-Grained Buffer Pool Benchmarking Framework for PostgreSQL},
  author    = {Hoque, Aroma and Papon, Tarikul Islam},
  booktitle = {Proceedings of TPCTC 2026},
  year      = {2026}
}
```

## License

MIT License
