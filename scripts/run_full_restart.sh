#!/bin/sh
set -eu
exec python3 -u scripts/05_run_simulation.py --max-agents 30 --seed 2 --start-date 2026-02-27 --end-date 2026-06-01 --community-mode on --use-fake-news-injection --fake-news-mode on --fake-news-variant bearish --sim-db /Users/leeyujeong/Downloads/MD_File/twinmarket_kr_project/outputs/runtime_dbs/sim_restart_full_20260714.db
