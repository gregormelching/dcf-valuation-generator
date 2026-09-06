if __name__ == "__main__":
    from pathlib import Path
    import shutil
    import sqlite3

    RATES_FROM = "2015-01-01"
    SOURCE = Path(__file__).resolve().parent.parent / "storage/values.db"
    TARGET = Path(__file__).resolve().parent / "fixtures/values.db"
    
    if not SOURCE.exists(): raise FileNotFoundError(f"Source file at {SOURCE} does not exist.")
    
    TARGET.parent.mkdir(parents = True, exist_ok = True)
    shutil.copy(SOURCE, TARGET)
    dct = {}
    
    with sqlite3.connect(TARGET) as conn:
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM raw_downloads")
        cursor.execute("DELETE FROM rates WHERE date < ?", (RATES_FROM,))
        conn.commit()
        conn.execute("VACUUM")
        names = cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
        min_date, max_date = cursor.execute("SELECT MIN(date), MAX(date) FROM rates").fetchone()
        for name in names:
            val = cursor.execute(f'SELECT count(*) FROM "{name[0]}"').fetchone()[0]
            dct[name[0]] = val
    conn.close()
        
    print(f"File size: {TARGET.stat().st_size} Bytes")
    print(dct)
    print(f"Maximum date: {max_date} and minimum date: {min_date} from rates.")
    
    
    