#!/usr/bin/env python3
"""
scripts/record_revenue.py
Manual revenue/burn entry when Stripe is not configured yet.

Usage:
  python scripts/record_revenue.py --venture-id ven_wedge_001 --amount 49.00 --source STRIPE
  python scripts/record_revenue.py --venture-id ven_wedge_001 --burn 47.20
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from packages.revenue.store import upsert_ledger_row, is_local_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Record manual revenue ledger row")
    parser.add_argument("--venture-id", required=True)
    parser.add_argument("--amount", type=float, default=0.0, help="Revenue USD (MRR period)")
    parser.add_argument("--burn", type=float, default=0.0, help="Burn USD for period")
    parser.add_argument("--source", default="OTHER", choices=["STRIPE", "ADSENSE", "AFFILIATE", "OTHER"])
    args = parser.parse_args()

    today = date.today()
    period_start = today.replace(day=1).isoformat()

    upsert_ledger_row({
        "venture_id": args.venture_id,
        "period_start": period_start,
        "period_end": today.isoformat(),
        "revenue_source": args.source,
        "amount_usd": args.amount,
        "burn_usd": args.burn,
    })

    storage = "local JSON (data/day2_store.json)" if is_local_mode() else "Supabase revenue_ledger"
    print(f"Recorded | venture={args.venture_id} amount=${args.amount:.2f} burn=${args.burn:.2f}")
    print(f"Storage: {storage}")
    print("Run: python -m apps.revenue_engine.main --mode once")


if __name__ == "__main__":
    main()
