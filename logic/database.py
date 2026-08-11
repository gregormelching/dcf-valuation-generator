import sqlite3
from pathlib import Path
from parser import *
from validation import *

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
            UNIQUE(company, year, metric_name)
        );
        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY,
            data_id INTEGER NOT NULL,
            flag TEXT,
            FOREIGN KEY (data_id) REFERENCES data(id) ON DELETE CASCADE,
            UNIQUE(data_id, flag)
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
                    cursor.execute("""
                                   INSERT INTO data (company, year, metric_name, value, tag, form, end_date)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(company, year, metric_name)
                                   DO UPDATE SET value = EXCLUDED.value, tag = EXCLUDED.tag, form = EXCLUDED.form, end_date = EXCLUDED.end_date
                                   RETURNING id"""
                                   ,(company, year, metric_name, values[year][metric_name]["Value"], tag, form, end)
                                   )
                    data_id = cursor.fetchone()[0] 
                else:
                    cursor.execute("""
                                   INSERT INTO data (company, year, metric_name, value, tag, form, end_date)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(company, year, metric_name)
                                   DO UPDATE SET value = EXCLUDED.value, tag = EXCLUDED.tag, form = EXCLUDED.form, end_date = EXCLUDED.end_date
                                   RETURNING id"""
                                   ,(company, year, metric_name, None, None, None, None)
                                   )
                    data_id = cursor.fetchone()[0]
                cursor.execute("DELETE FROM flags WHERE data_id = ?", (data_id,))
                for f in flag:
                    cursor.execute("INSERT INTO flags (data_id, flag) VALUES (?, ?)", (data_id, f))
        conn.commit()

def get_data(company: str) -> dict:
    values = {}
    query = "SELECT year, metric_name, value, tag, form, end_date, flag FROM data LEFT JOIN flags ON data.id = flags.data_id WHERE company = ?"
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (company,))
        for row in cursor.fetchall():
            values.setdefault(row[0], {}).setdefault(row[1], {"Value": row[2], "Tag": row[3], "Form": row[4], "End": row[5], "Flag": []})
            if not row[6] == None:
                values[row[0]][row[1]]["Flag"].append(row[6])
        return values



if __name__ == "__main__":
    init_db() 
    for c in companies:
        values = clean_values(get_values(20, c, metrics))
        rec_values = clean_values(get_values(20, c, RECON_TAGS))
        reconciled = reconcile_working_capital(values, rec_values)
        flag_vals = validate_values(values)
        checked_flags = check_recon_tolerance(flag_vals, reconciled)
        insert_data(c, values, checked_flags)
