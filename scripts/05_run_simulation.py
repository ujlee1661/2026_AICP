#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import ssl
import urllib.parse
import urllib.request
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_ORIG_GETADDRINFO = socket.getaddrinfo
_DNS_CACHE: dict[str, str] = {}


def _resolve_via_doh(host: str) -> str | None:
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    endpoints = (
        "https://1.1.1.1/dns-query",
        "https://8.8.8.8/resolve",
    )
    for endpoint in endpoints:
        try:
            query = urllib.parse.urlencode({"name": host, "type": "A"})
            url = f"{endpoint}?{query}"
            req = urllib.request.Request(
                url,
                headers={
                    "accept": "application/dns-json",
                    "user-agent": "TwinMarketKRDNS/1.0",
                },
            )
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            answers = payload.get("Answer") or []
            for answer in answers:
                ip = answer.get("data")
                if ip:
                    _DNS_CACHE[host] = str(ip)
                    return _DNS_CACHE[host]
        except Exception:
            continue
    return None


def _patched_getaddrinfo(host, port, *args, **kwargs):
    if isinstance(host, str) and host and not host.replace(".", "").isdigit():
        ip = _resolve_via_doh(host)
        if ip:
            return _ORIG_GETADDRINFO(ip, port, *args, **kwargs)
    return _ORIG_GETADDRINFO(host, port, *args, **kwargs)


socket.getaddrinfo = _patched_getaddrinfo

import config
from twinmarket_kr.simulation import run_simulation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-agents", type=int, default=None)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--random-agents", action="store_true")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--information-mode",
        choices=("pre_close_cutoff", "same_day", "prior_close"),
        default="pre_close_cutoff",
        help="Information cutoff for each decision turn.",
    )
    parser.add_argument(
        "--decision-space",
        choices=("buy_sell_only",),
        default="buy_sell_only",
        help="Allowed trading actions for the decision parser.",
    )
    parser.add_argument("--balanced-depths", action="store_true")
    parser.add_argument(
        "--use-fake-news-injection",
        action="store_true",
        help="Use outputs/processed_news_injection.csv and outputs/daily_news_selection_injection.csv.",
    )
    parser.add_argument(
        "--fake-news-mode",
        choices=("off", "on"),
        default=None,
        help="Control whether rows marked is_fake=true are visible to agents.",
    )
    parser.add_argument("--processed-news-csv", default=None)
    parser.add_argument("--daily-news-csv", default=None)
    parser.add_argument("--no-logs", action="store_true", help="Disable detailed output logs.")
    args = parser.parse_args()
    processed_news_csv = args.processed_news_csv
    daily_news_csv = args.daily_news_csv
    fake_news_mode = args.fake_news_mode
    if fake_news_mode is None:
        fake_news_mode = "on" if args.use_fake_news_injection else "off"
    if args.use_fake_news_injection or fake_news_mode == "on":
        processed_news_csv = processed_news_csv or str(config.PROCESSED_NEWS_INJECTION_CSV)
        daily_news_csv = daily_news_csv or str(config.DAILY_NEWS_SELECTION_INJECTION_CSV)
    asyncio.run(
        run_simulation(
            max_agents=args.max_agents,
            max_days=args.max_days,
            concurrency=args.concurrency,
            enable_logs=not args.no_logs,
            random_agents=args.random_agents,
            random_seed=args.seed,
            start_date=args.start_date,
            end_date=args.end_date,
            information_mode=args.information_mode,
            decision_space=args.decision_space,
            balanced_depths=args.balanced_depths,
            processed_news_csv=processed_news_csv,
            daily_news_csv=daily_news_csv,
            fake_news_mode=fake_news_mode,
        )
    )


if __name__ == "__main__":
    main()
