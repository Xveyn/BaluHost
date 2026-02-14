import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / 'baluhost.db'
print('Using DB:', db_path)
con = sqlite3.connect(str(db_path))
cur = con.cursor()

def table_exists(name):
    cur.execute("""SELECT name FROM sqlite_master WHERE type='table' AND name=?""", (name,))
    return cur.fetchone() is not None

for table in ('sync_states','sync_metadata'):
    if table_exists(table):
        cur.execute(f"SELECT count(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"{table}: {count} rows")
        cur.execute(f"SELECT * FROM {table} LIMIT 5")
        rows = cur.fetchall()
        for r in rows:
            print(r)
    else:
        print(f"Table {table} does not exist")

con.close()
