#!/usr/bin/env python3
"""
Read-only schema/sanity inspector for Kalshi_Historical_DATA.db.

Run this locally against the real file - nothing is uploaded or sent
anywhere, it just prints to your terminal. Paste that output back so the
real MoneyBot backtest script can be written against your actual column
names instead of guessed ones.

Usage:
    python inspect_db.py "C:\\Users\\holde\\Desktop\\Kalshi_Historical_DATA.db"
"""
import sqlite3
import sys


def main():
    if len(sys.argv) != 2:
        print("Usage: python inspect_db.py <path-to-db>")
        sys.exit(1)

    path = sys.argv[1]
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = con.cursor()

    print("=" * 78)
    print("TABLES")
    print("=" * 78)
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cur.fetchall()
    for name, sql in tables:
        print(f"\n--- {name} ---")
        print(sql)

    for name, _ in tables:
        print("\n" + "=" * 78)
        print(f"TABLE: {name}")
        print("=" * 78)

        cur.execute(f"PRAGMA table_info('{name}')")
        cols = cur.fetchall()
        print("Columns:", [c[1] for c in cols])

        cur.execute(f"SELECT COUNT(*) FROM '{name}'")
        count = cur.fetchone()[0]
        print(f"Row count: {count}")

        if count > 0:
            cur.execute(f"SELECT * FROM '{name}' LIMIT 3")
            rows = cur.fetchall()
            print("Sample rows:")
            for r in rows:
                print(" ", r)

        # If there's an obvious timestamp-ish column, show min/max range
        col_names = [c[1] for c in cols]
        for cand in ("timestamp", "ts", "time", "timestampUtc", "date", "close_time", "created_at"):
            if cand in col_names:
                try:
                    cur.execute(f"SELECT MIN({cand}), MAX({cand}) FROM '{name}'")
                    lo, hi = cur.fetchone()
                    print(f"Range of '{cand}': {lo}  ->  {hi}")
                except sqlite3.OperationalError as e:
                    print(f"(couldn't range-check {cand}: {e})")
                break

    con.close()
    print("\nDone. Paste everything above back to Claude.")


if __name__ == "__main__":
    main()
