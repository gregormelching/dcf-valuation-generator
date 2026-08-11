import sqlite3
from pathlib import Path
from parser import *
from validation import validate_values

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
            flag TEXT NOT NULL,
            UNIQUE(company, year, metric_name)
        )
    '''

def init_db():
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute(create_table)   
        conn.commit()    
    
def insert_data(company: str, values: dict, flags: dict) -> None:
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        
        for year in values:
            for metric_name in values[year]:
                flag = flags[year][metric_name]
      
                if not flag == "missing":
                    if metric_name == "WorkingCapital":
                        tag_lst = []
                        for slot in values[year]["WorkingCapital"]:
                            if values[year]["WorkingCapital"][slot] and not slot == "Value": 
                                form = values[year]["WorkingCapital"][slot]["Form"]
                                end = values[year]["WorkingCapital"][slot]["End"]
                                tag_lst.append(slot)
                        tag = "+".join(tag_lst)
                    else: 
                        tag = values[year][metric_name]["Tag"]
                        form = values[year][metric_name]["Form"]
                        end = values[year][metric_name]["End"]
                    cursor.execute("""
                                   INSERT INTO data (company, year, metric_name, value, tag, form, end_date, flag)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(company, year, metric_name)
                                   DO UPDATE SET value = EXCLUDED.value, tag = EXCLUDED.tag, form = EXCLUDED.form, end_date = EXCLUDED.end_date, flag = EXCLUDED.flag"""
                                   ,(company, year, metric_name, values[year][metric_name]["Value"], tag, form, end, flag)
                                   )
                else:
                    cursor.execute("""
                                   INSERT INTO data (company, year, metric_name, value, tag, form, end_date, flag)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(company, year, metric_name)
                                   DO UPDATE SET value = EXCLUDED.value, tag = EXCLUDED.tag, form = EXCLUDED.form, end_date = EXCLUDED.end_date, flag = EXCLUDED.flag"""
                                   ,(company, year, metric_name, None, None, None, None, flag)
                                   )
        conn.commit()

def get_data(company: str) -> dict:
    values = {}
    query = "SELECT year, metric_name, value, tag, form, end_date, flag FROM data WHERE company = ?"
    with sqlite3.connect(database) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (company,))
        for row in cursor.fetchall():
            values.setdefault(row[0], {})[row[1]] = {"Value": row[2], "Tag": row[3], "Form": row[4], "End": row[5], "Flag": row[6]}
        return values



if __name__ == "__main__":
    init_db() 
    values = clean_values(get_values(10, "microsoft", metrics))
    insert_data("microsoft", values, validate_values(values))
    print(get_data("microsoft"))
