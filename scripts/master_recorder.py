import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
QUICK_RECORDER = SCRIPT_DIR / "quick_live_recorder.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch multi-provider live recorder workers for next four Tuesday expiries.")
    parser.add_argument("--strike-count", type=int, default=21, help="Strikes on each side of ATM for each provider worker.")
    parser.add_argument("--heartbeat-seconds", type=int, default=20, help="Heartbeat print interval in seconds.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to launch child processes.")
    return parser.parse_args()


def next_tuesday_expiries(count: int = 4) -> list[str]:
    today = datetime.now().date()
    days_until_tuesday = (1 - today.weekday()) % 7
    first_tuesday = today + timedelta(days=days_until_tuesday)
    return [(first_tuesday + timedelta(days=7 * i)).isoformat() for i in range(count)]


def build_command(python_exec: str, provider: str, expiries: list[str], strike_count: int) -> list[str]:
    mode = "full" if provider == "upstox" else "lite"
    return [
        python_exec,
        str(QUICK_RECORDER),
        "--provider",
        provider,
        "--expiries",
        ",".join(expiries),
        "--strike-count",
        str(strike_count),
        "--mode",
        mode,
        "--non-interactive",
    ]


def launch_workers(python_exec: str, expiries: list[str], strike_count: int):
    workers = []
    for provider in ("upstox", "fyers"):
        cmd = build_command(python_exec, provider, expiries, strike_count)
        proc = subprocess.Popen(cmd)
        workers.append({"provider": provider, "expiries": expiries, "proc": proc, "cmd": cmd})
        print(f"[LAUNCH] {provider.upper()} expiries={','.join(expiries)} | pid={proc.pid}")
    return workers


def print_plan(expiries: list[str], strike_count: int) -> None:
    symbols_per_expiry = (2 * strike_count) + 1
    symbols_per_provider = len(expiries) * symbols_per_expiry
    total_symbols = symbols_per_provider * 2
    print("\n=== MASTER RECORDER PLAN ===")
    print(f"Expiries: {', '.join(expiries)}")
    print(f"Per expiry symbols: {symbols_per_expiry}")
    print(f"Per provider symbols: {symbols_per_provider}")
    print(f"Total symbols across providers: {total_symbols}")
    print("Processes to launch: 2 (1 per provider, each handles all expiries)")


def monitor(workers, heartbeat_seconds: int) -> None:
    print("\n[MONITOR] Press Ctrl+C to stop all workers.")
    try:
        while True:
            alive = [w for w in workers if w["proc"].poll() is None]
            dead = [w for w in workers if w["proc"].poll() is not None]
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] Active workers: {len(alive)} | Exited workers: {len(dead)}")

            for w in dead:
                code = w["proc"].returncode
                print(f"[EXIT] {w['provider'].upper()} expiries={','.join(w['expiries'])} | code={code}")

            if not alive:
                print("[MONITOR] All workers exited.")
                break

            time.sleep(max(2, heartbeat_seconds))
    except KeyboardInterrupt:
        print("\n[MONITOR] Interrupt received. Terminating workers...")
    finally:
        for w in workers:
            proc = w["proc"]
            if proc.poll() is None:
                proc.terminate()
        for w in workers:
            proc = w["proc"]
            if proc.poll() is None:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("[MONITOR] Shutdown complete.")


def main() -> None:
    args = parse_args()

    if not QUICK_RECORDER.exists():
        print(f"[ERROR] Missing script: {QUICK_RECORDER}")
        raise SystemExit(1)

    expiries = next_tuesday_expiries(4)
    print_plan(expiries, args.strike_count)

    workers = launch_workers(args.python, expiries, args.strike_count)
    monitor(workers, args.heartbeat_seconds)


if __name__ == "__main__":
    main()
