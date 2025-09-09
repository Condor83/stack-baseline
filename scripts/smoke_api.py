#!/usr/bin/env python3
import argparse
import json
import sys
import time

import httpx


def pretty(obj):
    print(json.dumps(obj, indent=2, sort_keys=False))


def main():
    p = argparse.ArgumentParser(description="Smoke-test EVM Decoder API endpoints")
    p.add_argument("address", help="Hex address (0x...)")
    p.add_argument("--chain-id", type=int, default=1)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--from-block", type=int, default=None)
    p.add_argument("--to-block", type=int, default=None)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--price-ts", type=int, default=None, help="Unix timestamp for price")
    p.add_argument("--ingest", action="store_true", help="Trigger ingest before reading")
    p.add_argument("--ingest-window", type=int, default=10000)
    args = p.parse_args()

    client = httpx.Client(timeout=30)
    base = args.base_url.rstrip("/")

    # Health
    r = client.get(f"{base}/health")
    r.raise_for_status()
    print("/health:")
    pretty(r.json())

    if args.ingest:
        # Trigger ingest
        payload = {
            "chain_id": args.chain_id,
            "address": args.address,
            "start_block": args.from_block or 0,
            "end_block": args.to_block or 99999999,
            "window": args.ingest_window,
        }
        r = client.post(f"{base}/api/v1/ingest/address", json=payload)
        r.raise_for_status()
        job = r.json()
        print("Queued ingest:")
        pretty(job)
        task_id = job.get("task_id")
        if task_id:
            # Poll for completion up to ~60s
            for _ in range(30):
                s = client.get(f"{base}/api/v1/tasks/{task_id}")
                s.raise_for_status()
                state = s.json()
                print("Task state:", state.get("state"))
                if state.get("state") in ("SUCCESS", "FAILURE"):
                    break
                time.sleep(2)

    # Summary
    q = {}
    if args.from_block is not None:
        q["from_block"] = str(args.from_block)
    if args.to_block is not None:
        q["to_block"] = str(args.to_block)
    r = client.get(f"{base}/api/v1/address/{args.chain_id}/{args.address}/summary", params=q)
    r.raise_for_status()
    print("\n/address/summary:")
    pretty(r.json())

    # Transactions
    q = {"limit": str(args.limit), "offset": str(args.offset)}
    if args.from_block is not None:
        q["from_block"] = str(args.from_block)
    if args.to_block is not None:
        q["to_block"] = str(args.to_block)
    r = client.get(f"{base}/api/v1/address/{args.chain_id}/{args.address}/transactions", params=q)
    r.raise_for_status()
    print("\n/address/transactions:")
    pretty(r.json())

    # Logs
    r = client.get(f"{base}/api/v1/address/{args.chain_id}/{args.address}/logs", params=q)
    r.raise_for_status()
    print("\n/address/logs:")
    pretty(r.json())

    # Price (native)
    ts = args.price_ts or int(time.time())
    r = client.get(f"{base}/api/v1/price/{args.chain_id}/native", params={"ts": str(ts)})
    r.raise_for_status()
    print("\n/price/native:")
    pretty(r.json())


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
