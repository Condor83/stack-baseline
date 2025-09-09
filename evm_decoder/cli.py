import os
import time
import json
from typing import Optional

import httpx
import typer


app = typer.Typer(help="EVM Decoder CLI – interact with the local API")


def base_url() -> str:
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def pretty(obj):
    typer.echo(json.dumps(obj, indent=2, sort_keys=False))


def client() -> httpx.Client:
    return httpx.Client(timeout=60)


def _date_only_to_iso(day: str, end: bool = False) -> str:
    d = day.strip()
    if len(d) == 10 and d.count("-") == 2:
        return f"{d}T23:59:59Z" if end else f"{d}T00:00:00Z"
    return d


@app.command("ingest-by-date")
def ingest_by_date(
    chain_id: int = typer.Option(..., help="Chain ID (e.g., 1 for Ethereum)"),
    address: str = typer.Option(..., help="Hex address 0x..."),
    start_date: str = typer.Option(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Option(..., help="End date (YYYY-MM-DD)"),
    window: int = typer.Option(10000, help="Block window size"),
    wait: bool = typer.Option(False, help="Wait for task to finish"),
    timeout: int = typer.Option(300, help="Wait timeout seconds"),
):
    b = base_url()
    with client() as c:
        r = c.post(f"{b}/api/v1/ingest/address_by_date", json={
            "chain_id": chain_id,
            "address": address,
            "start": _date_only_to_iso(start_date, end=False),
            "end": _date_only_to_iso(end_date, end=True),
            "window": window,
        })
        r.raise_for_status()
        data = r.json()
        pretty(data)
        if wait:
            task_id = data.get("task_id")
            if not task_id:
                raise typer.Exit(code=1)
            _wait_task(c, b, task_id, timeout)


def _wait_task(c: httpx.Client, b: str, task_id: str, timeout: int):
    start = time.time()
    while True:
        s = c.get(f"{b}/api/v1/tasks/{task_id}")
        s.raise_for_status()
        st = s.json()
        state = st.get("state")
        meta = st.get("meta") or {}
        line = f"task {task_id}: {state}"
        if isinstance(meta, dict) and meta:
            # show compact progress hints
            hints = []
            for k in ("stage", "pages", "txs", "receipts", "logs", "transfers", "internal_pages", "internal_count"):
                if k in meta:
                    hints.append(f"{k}={meta[k]}")
            if hints:
                line += " (" + ", ".join(hints) + ")"
        typer.echo(line)
        if state in ("SUCCESS", "FAILURE", "REVOKED"):
            pretty(st)
            return
        if time.time() - start > timeout:
            typer.echo("timeout waiting for task")
            pretty(st)
            raise typer.Exit(code=2)
        time.sleep(2)


@app.command("ingest-address")
def ingest_address(
    chain_id: int = typer.Option(...),
    address: str = typer.Option(...),
    start_block: int = typer.Option(...),
    end_block: int = typer.Option(...),
    window: int = typer.Option(10000),
    wait: bool = typer.Option(False),
    timeout: int = typer.Option(300),
):
    b = base_url()
    with client() as c:
        r = c.post(f"{b}/api/v1/ingest/address", json={
            "chain_id": chain_id,
            "address": address,
            "start_block": start_block,
            "end_block": end_block,
            "window": window,
        })
        r.raise_for_status()
        data = r.json()
        pretty(data)
        if wait:
            task_id = data.get("task_id")
            if task_id:
                _wait_task(c, b, task_id, timeout)


@app.command("task")
def task_status(task_id: str):
    b = base_url()
    with client() as c:
        r = c.get(f"{b}/api/v1/tasks/{task_id}")
        r.raise_for_status()
        pretty(r.json())


@app.command("summary")
def summary(
    chain_id: int = typer.Option(...),
    address: str = typer.Option(...),
    from_block: Optional[int] = typer.Option(None),
    to_block: Optional[int] = typer.Option(None),
):
    b = base_url()
    params = {}
    if from_block is not None:
        params["from_block"] = str(from_block)
    if to_block is not None:
        params["to_block"] = str(to_block)
    with client() as c:
        r = c.get(f"{b}/api/v1/address/{chain_id}/{address}/summary", params=params)
        r.raise_for_status()
        pretty(r.json())


@app.command("txs")
def txs(
    chain_id: int = typer.Option(...),
    address: str = typer.Option(...),
    limit: int = typer.Option(10),
    offset: int = typer.Option(0),
    from_block: Optional[int] = typer.Option(None),
    to_block: Optional[int] = typer.Option(None),
):
    b = base_url()
    params = {"limit": str(limit), "offset": str(offset)}
    if from_block is not None:
        params["from_block"] = str(from_block)
    if to_block is not None:
        params["to_block"] = str(to_block)
    with client() as c:
        r = c.get(f"{b}/api/v1/address/{chain_id}/{address}/transactions", params=params)
        r.raise_for_status()
        pretty(r.json())


@app.command("logs")
def logs_cmd(
    chain_id: int = typer.Option(...),
    address: str = typer.Option(...),
    limit: int = typer.Option(10),
    offset: int = typer.Option(0),
    from_block: Optional[int] = typer.Option(None),
    to_block: Optional[int] = typer.Option(None),
):
    b = base_url()
    params = {"limit": str(limit), "offset": str(offset)}
    if from_block is not None:
        params["from_block"] = str(from_block)
    if to_block is not None:
        params["to_block"] = str(to_block)
    with client() as c:
        r = c.get(f"{b}/api/v1/address/{chain_id}/{address}/logs", params=params)
        r.raise_for_status()
        pretty(r.json())


@app.command("transfers")
def transfers(
    chain_id: int = typer.Option(...),
    address: str = typer.Option(...),
    limit: int = typer.Option(10),
    offset: int = typer.Option(0),
    from_block: Optional[int] = typer.Option(None),
    to_block: Optional[int] = typer.Option(None),
):
    b = base_url()
    params = {"limit": str(limit), "offset": str(offset)}
    if from_block is not None:
        params["from_block"] = str(from_block)
    if to_block is not None:
        params["to_block"] = str(to_block)
    with client() as c:
        r = c.get(f"{b}/api/v1/address/{chain_id}/{address}/token_transfers", params=params)
        r.raise_for_status()
        pretty(r.json())


@app.command("traces")
def traces(
    chain_id: int = typer.Option(...),
    tx_hash: str = typer.Option(...),
    wait: bool = typer.Option(False),
    timeout: int = typer.Option(120),
):
    b = base_url()
    with client() as c:
        r = c.post(f"{b}/api/v1/traces/{chain_id}/{tx_hash}")
        r.raise_for_status()
        data = r.json()
        pretty(data)
        if wait:
            task_id = data.get("task_id")
            if task_id:
                _wait_task(c, b, task_id, timeout)


@app.command("price")
def price(chain_id: int = typer.Option(...), contract: str = typer.Option(...), ts: Optional[int] = typer.Option(None)):
    b = base_url()
    params = {}
    if ts is not None:
        params["ts"] = str(ts)
    with client() as c:
        r = c.get(f"{b}/api/v1/price/{chain_id}/{contract}", params=params)
        r.raise_for_status()
        pretty(r.json())


@app.command("pipeline")
def pipeline(
    chain_id: int = typer.Option(..., help="Chain ID (e.g., 1 for Ethereum)"),
    address: str = typer.Option(..., help="Hex address 0x..."),
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(..., help="End date YYYY-MM-DD"),
    window: int = typer.Option(10000, help="Block window size"),
    traces: bool = typer.Option(False, help="Request traces for ingested txs (budgeted)"),
    max_traces: int = typer.Option(10, help="Max txs to trace (to respect budgets)"),
    wait: bool = typer.Option(True, help="Wait for ingest to complete"),
):
    """Run an end-to-end pipeline: ingest by date → optional traces → print summary."""
    b = base_url()
    with client() as c:
        payload = {
            "chain_id": chain_id,
            "address": address,
            "start": _date_only_to_iso(start_date, end=False),
            "end": _date_only_to_iso(end_date, end=True),
            "window": window,
        }
        r = c.post(f"{b}/api/v1/ingest/address_by_date", json=payload)
        r.raise_for_status()
        job = r.json()
        pretty({"ingest": job})
        if wait and job.get("task_id"):
            _wait_task(c, b, job["task_id"], timeout=600)
        start_block = job.get("start_block")
        end_block = job.get("end_block")
        if traces and start_block is not None and end_block is not None:
            params = {"limit": str(max_traces), "from_block": str(start_block), "to_block": str(end_block)}
            txr = c.get(f"{b}/api/v1/address/{chain_id}/{address}/transactions", params=params)
            txr.raise_for_status()
            items = txr.json().get("items", [])
            out = []
            for it in items[:max_traces]:
                txh = it.get("tx_hash")
                if not txh:
                    continue
                tr = c.post(f"{b}/api/v1/traces/{chain_id}/{txh}")
                tr.raise_for_status()
                out.append({"tx_hash": txh, **tr.json()})
            pretty({"trace_jobs": out})
        sr = c.get(f"{b}/api/v1/address/{chain_id}/{address}/summary")
        sr.raise_for_status()
        pretty({"summary": sr.json()})


# -------- Interactive shell (menu) --------

def _env_default(key: str, fallback: str) -> str:
    return os.getenv(key, fallback)


def _input_prompt(label: str, default: Optional[str] = None) -> str:
    if default is not None and default != "":
        raw = input(f"{label} [{default}]: ").strip()
        return raw or default
    return input(f"{label}: ").strip()


def _print_menu():
    typer.echo("\n=== EVM Decoder Menu ===")
    typer.echo("1) Ingest by date")
    typer.echo("2) Ingest by block")
    typer.echo("3) Check task status")
    typer.echo("4) Address summary")
    typer.echo("5) Address transactions")
    typer.echo("6) Address logs")
    typer.echo("7) Address token transfers")
    typer.echo("8) Request traces for tx")
    typer.echo("9) Price lookup")
    typer.echo("10) Pipeline (ingest + optional traces)")
    typer.echo("0) Quit")
    typer.echo("(Type / at any time to re-open this menu)")


@app.command("shell")
def shell():
    """Interactive menu-driven CLI (type / to show menu)."""
    b = base_url()
    default_wallet = _env_default(
        "DEFAULT_WALLET", "0xbce83d5060a7d7007fd7ca17301c1e5131b2d50e"
    )
    default_chain = int(_env_default("DEFAULT_CHAIN_ID", "1"))
    default_window = int(_env_default("DEFAULT_WINDOW", "10000"))
    typer.echo(f"Connecting to API: {b}")
    _print_menu()
    with client() as c:
        while True:
            cmd = input("\n> ").strip()
            if cmd == "/":
                _print_menu()
                continue
            if cmd.lower() in ("0", "q", "quit", "exit"):
                typer.echo("Goodbye.")
                return
            try:
                choice = int(cmd)
            except Exception:
                typer.echo("Enter a number (0-9), or / for menu.")
                continue

            try:
                if choice == 1:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    start = _input_prompt("Start date (YYYY-MM-DD)")
                    end = _input_prompt("End date (YYYY-MM-DD)")
                    r = c.post(f"{b}/api/v1/ingest/address_by_date", json={
                        "chain_id": chain_id,
                        "address": address,
                        "start": _date_only_to_iso(start, end=False),
                        "end": _date_only_to_iso(end, end=True),
                        "window": default_window,
                    })
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 2:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    start_block = int(_input_prompt("Start block"))
                    end_block = int(_input_prompt("End block"))
                    window = int(_input_prompt("Block window", str(default_window)))
                    r = c.post(f"{b}/api/v1/ingest/address", json={
                        "chain_id": chain_id,
                        "address": address,
                        "start_block": start_block,
                        "end_block": end_block,
                        "window": window,
                    })
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 3:
                    task_id = _input_prompt("Task ID")
                    r = c.get(f"{b}/api/v1/tasks/{task_id}")
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 4:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    r = c.get(f"{b}/api/v1/address/{chain_id}/{address}/summary")
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 5:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    limit = int(_input_prompt("Limit", "10"))
                    r = c.get(
                        f"{b}/api/v1/address/{chain_id}/{address}/transactions",
                        params={"limit": str(limit)},
                    )
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 6:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    limit = int(_input_prompt("Limit", "10"))
                    r = c.get(
                        f"{b}/api/v1/address/{chain_id}/{address}/logs",
                        params={"limit": str(limit)},
                    )
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 7:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    limit = int(_input_prompt("Limit", "10"))
                    r = c.get(
                        f"{b}/api/v1/address/{chain_id}/{address}/token_transfers",
                        params={"limit": str(limit)},
                    )
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 8:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    tx_hash = _input_prompt("Tx hash (0x...)")
                    r = c.post(f"{b}/api/v1/traces/{chain_id}/{tx_hash}")
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 9:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    contract = _input_prompt("Contract (0x... or native)", "native")
                    ts = _input_prompt("Timestamp (epoch) [optional]", "")
                    params = {"ts": ts} if ts else {}
                    r = c.get(f"{b}/api/v1/price/{chain_id}/{contract}", params=params)
                    r.raise_for_status()
                    pretty(r.json())
                elif choice == 10:
                    chain_id = int(_input_prompt("Chain ID", str(default_chain)))
                    address = _input_prompt("Address", default_wallet)
                    sday = _input_prompt("Start date (YYYY-MM-DD)")
                    eday = _input_prompt("End date (YYYY-MM-DD)")
                    do_traces = _input_prompt("Request traces? (y/N)", "N").lower().startswith("y")
                    max_t = int(_input_prompt("Max traces", "10")) if do_traces else 0
                    # run pipeline
                    payload = {
                        "chain_id": chain_id,
                        "address": address,
                        "start": _date_only_to_iso(sday, end=False),
                        "end": _date_only_to_iso(eday, end=True),
                        "window": default_window,
                    }
                    r = c.post(f"{b}/api/v1/ingest/address_by_date", json=payload)
                    r.raise_for_status()
                    job = r.json()
                    pretty({"ingest": job})
                    if job.get("task_id"):
                        _wait_task(c, b, job["task_id"], timeout=600)
                    if do_traces:
                        sb = job.get("start_block")
                        eb = job.get("end_block")
                        if sb is not None and eb is not None:
                            params = {"limit": str(max_t), "from_block": str(sb), "to_block": str(eb)}
                            txr = c.get(f"{b}/api/v1/address/{chain_id}/{address}/transactions", params=params)
                            txr.raise_for_status()
                            items = txr.json().get("items", [])
                            out = []
                            for it in items[:max_t]:
                                txh = it.get("tx_hash")
                                if not txh:
                                    continue
                                tr = c.post(f"{b}/api/v1/traces/{chain_id}/{txh}")
                                tr.raise_for_status()
                                out.append({"tx_hash": txh, **tr.json()})
                            pretty({"trace_jobs": out})
                else:
                    typer.echo("Invalid selection. Use / for menu.")
            except httpx.HTTPError as e:
                typer.echo(f"HTTP error: {e}")
                if getattr(e, "response", None) is not None:
                    try:
                        typer.echo(e.response.text)
                    except Exception:
                        pass
            except Exception as e:
                typer.echo(f"Error: {e}")


if __name__ == "__main__":
    app()
