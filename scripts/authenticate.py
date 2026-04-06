import os
import sys
import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Path fix for monorepo imports
sys.path.append(str(Path(__file__).parent.parent / "packages" / "trading_core"))

from trading_core import get_adapter, AuthManager

async def authenticate():
    parser = argparse.ArgumentParser(description="Unified Broker Authenticator (CLI)")
    parser.add_argument("--provider", default="fyers", choices=["fyers", "upstox"], help="Broker to authenticate")
    args = parser.parse_args()

    print(f"=== 🔐 AUTHENTICATING: {args.provider.upper()} ===")
    
    try:
        adapter = get_adapter(args.provider)
        
        # 1. Generate Link
        auth_url = adapter.generate_auth_link()
        print(f"\n1. Please visit this URL in your browser to login:")
        print("-" * 50)
        print(auth_url)
        print("-" * 50)
        
        # 2. Get Callback URL
        print("\n2. After logging in, you will be redirected to a '127.0.0.1' address.")
        print("   Copy the ENTIRE URL from your browser address bar and paste it below.")
        
        full_callback_url = input("\nPASTE URL HERE: ").strip()
        
        if not full_callback_url:
            print("[ERROR] No URL provided. Aborting.")
            return

        # 3. Extract Code
        parsed_url = urlparse(full_callback_url)
        query_params = parse_qs(parsed_url.query)
        auth_code = query_params.get("auth_code") or query_params.get("code")
        
        if not auth_code:
            print("[ERROR] Could not find 'code' or 'auth_code' in the URL. Please ensure you copied the FULL address.")
            return
            
        code = auth_code[0]
        print(f"[*] Extracted Code: {code[:10]}...")

        # 4. Exchange for Token
        print("[*] Exchanging code for access token...")
        access_token = adapter.fetch_access_token(code)
        
        if access_token:
            # 5. Persist
            AuthManager.save_token(args.provider, access_token)
            print(f"\n[SUCCESS] {args.provider.upper()} authenticated and token saved to config/auth!")
        else:
            print(f"[FAILED] Could not retrieve access token from {args.provider}.")

    except Exception as e:
        print(f"[CRITICAL ERROR] {str(e)}")

if __name__ == "__main__":
    asyncio.run(authenticate())
