import sqlite3
from pathlib import Path
from parser import *
from validation import *
import yfinance as yf

storage_path = Path(Path(__file__).parent.parent.joinpath("storage"))
database = storage_path / 'values.db'
create_table = '''
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY,
            company TEXT NOT NULL,
            year INT NOT NULL,
            metric_name TEXT NOT NULL,
            value REAL,
            tag TEXT,
            form TEXT,
            end_date DATE,
            filed DATE,
            UNIQUE(company, year, metric_name)
        );
        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY,
            data_id INTEGER NOT NULL,
            flag TEXT,
            FOREIGN KEY (data_id) REFERENCES data(id) ON DELETE CASCADE,
            UNIQUE(data_id, flag)
        );
        CREATE TABLE IF NOT EXISTS prices (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL, 
            close REAL NOT NULL,
            freq TEXT NOT NULL,
            adjusted INTEGER NOT NULL,
            UNIQUE(symbol, date, freq)
        );
        CREATE TABLE IF NOT EXISTS raw_downloads (
            symbol TEXT NOT NULL,
            freq TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            body TEXT NOT NULL,
            lib_version TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rates (
            series TEXT NOT NULL,
            date TEXT NOT NULL,
            rate REAL NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(series, date)
        )
    '''

def init_db():
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.executescript(create_table)   
        conn.commit()    
    
def insert_data(company: str, values: dict, flags: dict) -> None:
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        
        for year in values:
            for metric_name in values[year]:
                flag = flags[year][metric_name]
                if "missing" not in flag: 
                    tag = values[year][metric_name]["Tag"]
                    form = values[year][metric_name]["Form"]
                    end = values[year][metric_name]["End"]
                    filed = values[year][metric_name].get("Filed")
                    cursor.execute("""
                                   INSERT INTO data (company, year, metric_name, value, tag, form, end_date, filed)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(company, year, metric_name)
                                   DO UPDATE SET value = EXCLUDED.value, tag = EXCLUDED.tag, form = EXCLUDED.form, end_date = EXCLUDED.end_date, filed = EXCLUDED.filed
                                   RETURNING id"""
                                   ,(company, year, metric_name, values[year][metric_name]["Value"], tag, form, end, filed)
                                   )
                    data_id = cursor.fetchone()[0] 
                else:
                    cursor.execute("""
                                   INSERT INTO data (company, year, metric_name, value, tag, form, end_date, filed)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(company, year, metric_name)
                                   DO UPDATE SET value = EXCLUDED.value, tag = EXCLUDED.tag, form = EXCLUDED.form, end_date = EXCLUDED.end_date, filed = EXCLUDED.filed
                                   RETURNING id"""
                                   ,(company, year, metric_name, None, None, None, None, None)
                                   )
                    data_id = cursor.fetchone()[0]
                cursor.execute("DELETE FROM flags WHERE data_id = ?", (data_id,))
                for f in flag:
                    cursor.execute("INSERT INTO flags (data_id, flag) VALUES (?, ?)", (data_id, f))
        conn.commit()

def get_data(company: str, start_year: int) -> dict:
    years = range(start_year, datetime.now().year + 1)
    values = {}
    query = "SELECT year, metric_name, value, tag, form, end_date, filed, flag FROM data LEFT JOIN flags ON data.id = flags.data_id WHERE company = ?"
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (company,))
        for row in cursor.fetchall():
            if row[0] in years:
                values.setdefault(row[0], {}).setdefault(row[1], {"Value": row[2], "Tag": row[3], "Form": row[4], "End": row[5], "Filed": row[6], "Flag": []})
                if not row[7] == None:
                    values[row[0]][row[1]]["Flag"].append(row[7])
        return values

def insert_prices(symbol: str, freq: str, rows: list, adjusted: int) -> None: 
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        for row in rows:
            cursor.execute("""INSERT INTO prices (symbol, date, close, freq, adjusted) 
                           VALUES (?, ?, ?, ?, ?)
                           ON CONFLICT(symbol, date, freq) DO UPDATE SET close = EXCLUDED.close, adjusted = EXCLUDED.adjusted
                           WHERE EXCLUDED.adjusted >= prices.adjusted""",
                           (symbol, row[0], row[1], freq, adjusted)
                           )
        conn.commit()

def insert_rates(series: str, rows: list) -> None:
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in rows: 
            cursor.execute("""INSERT INTO rates (series, date, rate, fetched_at)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(series, date) DO UPDATE SET rate = EXCLUDED.rate, fetched_at = EXCLUDED.fetched_at
                           """, (series, row[0], row[1], now))
        conn.commit()
        
def get_rate(series: str, as_of: str) -> tuple | None:
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        query = "SELECT date, rate, fetched_at FROM rates WHERE series = ? AND date <= ? ORDER BY date DESC LIMIT 1"
        cursor.execute(query, (series, as_of))
        return cursor.fetchone()

def get_prices(symbol: str, freq: str, n: int, as_of: str) -> list:
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        query = "SELECT date, close FROM prices WHERE symbol = ? AND freq = ? AND adjusted = 1 AND date <= ? ORDER BY date DESC LIMIT ?"
        cursor.execute(query, (symbol, freq, as_of, n))
        rows = cursor.fetchall()
        if len(rows) < n: raise ValueError(f"Too few prices for the given symbol and frequency as_of {as_of}")
        return sorted(rows)

def insert_raw_download(symbol: str, freq: str, body: str, lib_version: str):
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO raw_downloads (symbol, freq, fetched_at, body, lib_version) VALUES (?, ?, ?, ?, ?)", (symbol, freq, datetime.now().isoformat(), body, lib_version))

if __name__ == "__main__":
    init_db() 
    for c in companies:
        values = clean_values(get_values(20, c, metrics))
        values = {year: m for year, m in values.items() if any(slot for metric in m.values() for slot in metric.values())}
        rec_values = clean_values(get_values(20, c, RECON_TAGS))
        reconciled = reconcile_working_capital(values, rec_values)
        flag_vals = validate_values(values)
        checked_flags = check_recon_tolerance(flag_vals, reconciled)
        insert_data(c, values, checked_flags)