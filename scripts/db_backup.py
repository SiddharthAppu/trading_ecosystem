import os
import glob
import subprocess
from datetime import datetime
import argparse

# Ensure we have a backups directory at the root of the monorepo
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "db_backups")
MAX_BACKUPS = 5

def backup_db(max_backups):
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"trading_db_backup_{timestamp}.sql")
    
    print(f"=== 💾 TRADING DB BACKUP UTILITY ===")
    print(f"[*] Extracting full DB snapshot from TimescaleDB Docker Container...")
    
    # We pipe pg_dump directly from inside the docker container securely to the host file system
    zip_cmd = f"docker exec trading_timescaledb pg_dump -U trading -d trading_db > {backup_file}"
    
    try:
        # Use shell=True for output redirection natively in os format
        subprocess.run(zip_cmd, shell=True, check=True)
        print(f"[SUCCESS] Snapshot securely saved to: {backup_file}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Database backup failed: {str(e)}")
        if os.path.exists(backup_file):
            os.remove(backup_file)
        return

    # Clean up older backups (Versioning Control)
    all_backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "trading_db_backup_*.sql")), key=os.path.getmtime)
    
    if len(all_backups) > max_backups:
        print(f"\n[*] Storage Policy enforcing max {max_backups} recent backups. Cleaning up...")
        for old_backup in all_backups[:-max_backups]:
            os.remove(old_backup)
            print(f"  -> Deleted archived legacy backup: {os.path.basename(old_backup)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Secure Database Backup & Versioning Utility")
    parser.add_argument("--max", type=int, default=MAX_BACKUPS, help="Max number of rolling backups to retain (Default: 5)")
    args = parser.parse_args()
    
    backup_db(args.max)
