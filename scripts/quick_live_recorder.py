import argparse
import json
import time
import requests
import webbrowser
from datetime import datetime, timedelta
import sys

# Assume Data Collector API is already running via start_platform.bat
BACKEND_URL = "http://localhost:8080"
INDEX_SYMBOL = "NSE:NIFTY50-INDEX"
REQUEST_TIMEOUT = 15

def is_backend_running():
    try:
        r = requests.get(f"{BACKEND_URL}/auth/status?provider=upstox", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False

def check_auth(provider):
    r = requests.get(f"{BACKEND_URL}/auth/status?provider={provider}", timeout=REQUEST_TIMEOUT)
    return r.json().get("authenticated")

def login(provider):
    if check_auth(provider):
        print(f"[*] Already authenticated with {provider.upper()}.")
        return True
        
    print(f"[*] Extracting {provider.upper()} login URL...")
    r = requests.get(f"{BACKEND_URL}/auth/url?provider={provider}", timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        print(f"[ERROR] Getting {provider} auth URL: {r.status_code}")
        return False
        
    url = r.json().get("url")
    print(f"Opening browser... Please authorize {provider.upper()}.")
    webbrowser.open(url)
    
    # Wait for completion pipeline
    for _ in range(120):
        if check_auth(provider):
            print(f"[SUCCESS] {provider.upper()} authentication synced!")
            return True
        time.sleep(3)
    return False

def get_next_expiry_default():
    today = datetime.now()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def get_live_chain(provider, expiry, strike_count=10, max_symbols=None):
    req = {
        "underlying_symbol": INDEX_SYMBOL,
        "expiry_date": expiry,
        "strike_count": strike_count,
        "provider": provider
    }
    r = requests.post(f"{BACKEND_URL}/chain/generate", json=req, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        print(f"[ERROR] Generating chain: {r.json().get('detail')}")
        return None
    symbols = r.json().get("data", {}).get("symbols", [])
    if max_symbols is not None:
        symbols = symbols[: max(0, int(max_symbols))]
    return symbols

def start_recording(provider, symbols, include_index=True):
    subscribe_symbols = list(symbols)
    if include_index and INDEX_SYMBOL not in subscribe_symbols:
        subscribe_symbols.append(INDEX_SYMBOL)

    # 1. Start Server Instance Target
    r = requests.post(f"{BACKEND_URL}/recorder/start?provider={provider}", timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        print(f"[ERROR] Starting recorder logic: {r.json().get('detail')}")
        return False
        
    # 2. Subscribe Symbols
    req = {"symbols": subscribe_symbols, "provider": provider}
    r = requests.post(f"{BACKEND_URL}/recorder/subscribe", json=req, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        print(f"[ERROR] Pushing symbols to stream: {r.json().get('detail')}")
        return False
    
    option_count = len([s for s in subscribe_symbols if s != INDEX_SYMBOL])
    print(f"[LIVE] Websocket started for {option_count} OPTS + Index ({INDEX_SYMBOL}) on {provider.upper()}.")
    return True

def stop_recording_for_provider(provider):
    try:
        requests.post(f"{BACKEND_URL}/recorder/stop?provider={provider}", timeout=REQUEST_TIMEOUT)
        print(f"[*] Stream cleanly stopped for {provider}.")
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="Live Options Data Tick Orchestrator")
    args = parser.parse_args()

    if not is_backend_running():
        print("[CRITICAL ERROR] The unified Data Collector API is NOT running at http://localhost:8080.")
        print("Please ensure you run `start_platform.bat` first before orchestrating Live Downloads.")
        exit(1)

    print("\n=== 📡 TRADING CORE: LIVE WEBSOCKET ORCHESTRATOR ===")
    
    # Provider mapping
    provider = input("Select Provider (fyers/upstox) [Default fyers]: ").strip().lower() or "fyers"

    if not login(provider):
        print("Login pipeline failed. Exiting automation.")
        exit(2)

    next_expiry = get_next_expiry_default()
    expiry = input(f"Enter target active Expiry (MMMDD or YYYY-MM-DD) [Default {next_expiry}]: ").strip() or next_expiry

    print(f"[*] Extracting Options Chain for {INDEX_SYMBOL} ({expiry})...")
    symbols = get_live_chain(provider, expiry, strike_count=10)
    
    if not symbols:
        print("Empty contract payload received. Exiting.")
        exit(3)

    if not start_recording(provider, symbols, include_index=True):
        exit(4)
        
    # Standard Market Timings logic block
    now = datetime.now()
    market_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=45, second=0, microsecond=0)
    
    if now > market_end:
        print("\n[WARN] Market is officially closed for today.")
        proceed = input("Force start the diagnostic recording anyway? (y/n): ").strip().lower() == 'y'
        if not proceed:
            stop_recording_for_provider(provider)
            exit(0)

    print("\n✅ LIVE CONNECTION SECURED. Auto-recording is currently spooling to TimescaleDB.")
    print("-> Press Ctrl+C at any time to gracefully teardown the stream.")
    
    try:
        while True:
            now = datetime.now()
            if now >= market_end:
                print("\n[!] Reached 15:45 bounds. Clean shut down initialized.")
                break
                
            r = requests.get(f"{BACKEND_URL}/recorder/status?provider={provider}", timeout=REQUEST_TIMEOUT)
            status = r.json()
            is_connected = "🟢" if status.get("ws_connected") else "🔴"
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {provider.upper()} Heartbeat... Socket: {is_connected} | Tracking: {len(status.get('symbols', []))} Active Strips")
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Stopping streaming engine manually...")
    finally:
        stop_recording_for_provider(provider)
        print("Teardown complete.")

if __name__ == "__main__":
    main()
