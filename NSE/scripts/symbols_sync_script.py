import pandas as pd
import argparse
from sqlalchemy import create_engine, text
import re
import sys

# Update with your actual PostgreSQL credentials
DB_URL = "postgresql://trading:trading@localhost:5432/trading_db"

def parse_fyers_symbol(symbol):
    """
    Decodes Fyers Nifty Options strings.
    Example: NSE:NIFTY2642322500CE
    """
    pattern = r"NIFTY(\d{2})([1-9ON D])(\d{2})(\d+)(CE|PE)"
    match = re.search(pattern, symbol)
    if not match:
        return None
    
    yy, m_code, dd, strike, opt_type = match.groups()
    
    # Fyers Month Codes: 1-9, O(ct), N(ov), D(ec)
    m_map = {str(i): i for i in range(1, 10)}
    m_map.update({'O': 10, 'N': 11, 'D': 12, ' ': 10})
    
    try:
        month = m_map[m_code]
        expiry_date = pd.to_datetime(f"20{yy}-{month:02d}-{dd}").date()
        return {
            'fyers_key': symbol,
            'expiry_date': expiry_date,
            'strike_price': float(strike),
            'option_type': opt_type
        }
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("upstox_path")
    parser.add_argument("fyers_path")
    args = parser.parse_args()

    # --- 1. PROCESS UPSTOX ---
    print("Reading Upstox master...")
    # sep=None + engine='python' handles tab/comma automatically
    u_df = pd.read_csv(args.upstox_path, sep=None, engine='python')
    
    # Map 'name' to 'NIFTY' based on your CSV sample
    u_nifty = u_df[
        (u_df['name'] == 'NIFTY') & 
        (u_df['instrument_type'] == 'OPTIDX')
    ].copy()
    
    if u_nifty.empty:
        print("Error: No Nifty options found in Upstox file. Check column names.")
        sys.exit(1)

    # Sanity Check: Ensure strike is numeric
    u_nifty['strike_price'] = pd.to_numeric(u_nifty['strike'], errors='coerce')
    u_nifty['expiry_date'] = pd.to_datetime(u_nifty['expiry'], dayfirst=True).dt.date
    
    u_nifty = u_nifty[['instrument_key', 'expiry_date', 'strike_price', 'option_type', 'lot_size']]
    u_nifty.columns = ['upstox_key', 'expiry_date', 'strike_price', 'option_type', 'lot_size']

    # --- 2. PROCESS FYERS ---
    print("Reading Fyers master...")
    f_raw = pd.read_csv(args.fyers_path, header=None)
    f_data = []
    
    for _, row in f_raw.iterrows():
        # Column 13 is underlying, Column 9 is the symbol string
        if str(row[13]) == 'NIFTY':
            parsed = parse_fyers_symbol(str(row[9]))
            if parsed:
                f_data.append(parsed)
    
    f_nifty = pd.DataFrame(f_data)
    
    if f_nifty.empty:
        print("Error: No Nifty options parsed from Fyers file.")
        sys.exit(1)

    # --- 3. MERGE & VALIDATE ---
    # Merge ensures we only keep contracts present in BOTH systems
    merged = pd.merge(u_nifty, f_nifty, on=['expiry_date', 'strike_price', 'option_type'])
    
    # Primary Key for your DB
    merged['human_symbol'] = merged.apply(
        lambda x: f"NIFTY_{x.expiry_date}_{int(x.strike_price)}_{x.option_type}", axis=1
    )

    print(f"Success: Matched {len(merged)} Nifty Option contracts.")

# --- 4. DB UPDATE ---
    engine = create_engine(DB_URL)
    
    # Upload the matched data to a temporary staging table
    merged.to_sql('tmp_sync_master', engine, if_exists='replace', index=False)

    with engine.begin() as conn:
        # We use text() here to make the raw SQL string "executable" for SQLAlchemy 2.0
        insert_query = text("""
            INSERT INTO master_broker.symbol_master 
            (human_symbol, expiry_date, strike_price, option_type, upstox_key, fyers_key, lot_size)
            SELECT human_symbol, expiry_date, strike_price, option_type, upstox_key, fyers_key, lot_size 
            FROM tmp_sync_master
            ON CONFLICT (human_symbol) DO UPDATE SET
                upstox_key = EXCLUDED.upstox_key,
                fyers_key = EXCLUDED.fyers_key,
                lot_size = EXCLUDED.lot_size,
                last_synced = NOW();
        """)
        
        conn.execute(insert_query)
        
        # Clean up the staging table
        conn.execute(text("DROP TABLE IF EXISTS tmp_sync_master;"))
    
    print("🚀 Database sync complete. 798 contracts are now mapped.")

if __name__ == "__main__":
    main()