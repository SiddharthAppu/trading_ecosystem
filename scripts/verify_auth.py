import os
import sys
from pathlib import Path

# Add core package to path if not installed
sys.path.append(str(Path(__file__).parent.parent / "packages" / "trading_core"))

from trading_core import AuthManager, get_adapter

def verify():
    print("=== TRADING ECOSYSTEM AUTH VERIFICATION ===")
    
    for provider in ["fyers", "upstox"]:
        print(f"\nChecking {provider.upper()}:")
        try:
            adapter = get_adapter(provider)
            is_valid = adapter.validate_token()
            
            if is_valid:
                print(f"  [SUCCESS] Session is active and valid.")
            else:
                token = AuthManager.load_token(provider)
                if token:
                    print(f"  [EXPIRED] Token found but session is invalid. Re-auth required.")
                else:
                    print(f"  [MISSING] No access token found. Please login via UI.")
                
                auth_link = adapter.generate_auth_link()
                print(f"  Auth URL: {auth_link}")
                
        except Exception as e:
            print(f"  [ERROR] {str(e)}")

if __name__ == "__main__":
    verify()
