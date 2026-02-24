import sqlite3
import threading
from datetime import datetime
import pandas as pd

class HistoryDB:
    def __init__(self, db_name="stock_history.db"):
        self.db_name = db_name
        self.lock = threading.Lock()
        self.init_db()

    def init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS history
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          analysis_date TEXT,
                          ticker TEXT,
                          stock_name TEXT,
                          close_price REAL,
                          verdict TEXT,
                          reason TEXT,
                          eps REAL,
                          roe REAL,
                          pe REAL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS users
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          username TEXT UNIQUE NOT NULL,
                          password_hash TEXT NOT NULL)''')
            conn.commit()
            conn.close()

    def register_user(self, username, password_hash):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def verify_user(self, username, password_hash):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=? AND password_hash=?", (username, password_hash))
            user = c.fetchone()
            conn.close()
            return user is not None

    def add_record(self, ticker, name, price, verdict, reason, eps, roe, pe):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            eps = eps if eps else 0.0
            roe = roe if roe else 0.0
            pe = pe if pe else 0.0
            c.execute("INSERT INTO history (analysis_date, ticker, stock_name, close_price, verdict, reason, eps, roe, pe) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (date_str, ticker, name, price, verdict, reason, eps, roe, pe))
            conn.commit()
            conn.close()

    def get_all_records(self):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
            conn.close()
            return df

    def delete_record(self, record_id):
        with self.lock:
            conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=10)
            c = conn.cursor()
            c.execute("DELETE FROM history WHERE id=?", (record_id,))
            conn.commit()
            conn.close()

# 實例化供全域使用
db = HistoryDB()
