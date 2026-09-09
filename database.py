import os
import json
import sqlite3
from datetime import datetime, date

# Try importing psycopg2 for PostgreSQL
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Database Config from Environment
DATABASE_URL = os.environ.get("DATABASE_URL")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "habit_tracker_db")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_PORT = os.environ.get("DB_PORT", "5432")

# If DATABASE_URL is present, we force PostgreSQL usage.
USE_POSTGRES = bool(DATABASE_URL) or (os.environ.get("USE_POSTGRES", "false").lower() == "true" and PSYCOPG2_AVAILABLE)

SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "habit_tracker.db")


def get_db():
    """Connect to PostgreSQL (Production/Local) or fallback to SQLite (Local only)."""
    
    # 1. Production PostgreSQL via DATABASE_URL
    if DATABASE_URL:
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed.")
        try:
            conn = psycopg2.connect(
                DATABASE_URL, 
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            return conn, "postgres"
        except Exception as e:
            # Raise exception immediately. DO NOT fall back to SQLite.
            # Masking full URL in logs to prevent password leak.
            print(f"[Database] CRITICAL: Production PostgreSQL connection failed. Error: {e}")
            raise Exception("Failed to connect to production database. Check deployment logs.")

    # 2. Local PostgreSQL via DB_ environment variables
    if USE_POSTGRES:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                port=DB_PORT,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            return conn, "postgres"
        except Exception as e:
            print(f"[Database] CRITICAL: Local PostgreSQL connection failed. Error: {e}")
            raise Exception("Failed to connect to local PostgreSQL database. No SQLite fallback permitted when USE_POSTGRES is true.")

    # 3. Local SQLite Fallback (Only if explicitly not using Postgres)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def init_db():
    """Initialize database tables."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    try:
        if db_type == "postgres":
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    cursor.execute(f.read())
            else:
                # Inline Postgres DDL ensuring JSONB and proper SERIAL keys
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS habit (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    habit_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    repeat_type TEXT NOT NULL,
                    repeat_pattern JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS habit_log (
                    id SERIAL PRIMARY KEY,
                    habit_id INTEGER NOT NULL,
                    log_date TEXT NOT NULL,
                    completed INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ready',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(habit_id, log_date),
                    FOREIGN KEY (habit_id) REFERENCES habit(id) ON DELETE CASCADE
                );

                """)
        else:
            # SQLite is retained only for local application-data inspection.
            # Login requires DATABASE_URL because the shared users table is PostgreSQL-owned.
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS habit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                habit_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                repeat_type TEXT NOT NULL,
                repeat_pattern TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS habit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL,
                log_date TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ready',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(habit_id, log_date),
                FOREIGN KEY (habit_id) REFERENCES habit(id) ON DELETE CASCADE
            );
            """)

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[DB Error] init_db: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def get_user_by_email(email):
    """Fetch the verified identity record from the Auth Service users table."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    try:
        placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f'SELECT id, email, password_hash, is_verified FROM users WHERE email = {placeholder};',
            (email,)
        )
        row = cursor.fetchone()
        if row and db_type == "sqlite":
            row = dict(row)
        return row
    finally:
        cursor.close()
        conn.close()


def create_habit(user_id, habit_name, start_time, end_time, repeat_type, repeat_pattern):
    """Create a new habit definition."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    pattern_json = json.dumps(repeat_pattern) if isinstance(repeat_pattern, dict) else repeat_pattern

    try:
        if db_type == "postgres":
            cursor.execute(
                """
                INSERT INTO habit (user_id, habit_name, start_time, end_time, repeat_type, repeat_pattern)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
                """,
                (user_id, habit_name, start_time, end_time, repeat_type, psycopg2.extras.Json(repeat_pattern))
            )
            habit_id = cursor.fetchone()['id']
        else:
            cursor.execute(
                """
                INSERT INTO habit (user_id, habit_name, start_time, end_time, repeat_type, repeat_pattern)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (user_id, habit_name, start_time, end_time, repeat_type, pattern_json)
            )
            habit_id = cursor.lastrowid

        conn.commit()
        return {
            "id": habit_id,
            "user_id": user_id,
            "habit_name": habit_name,
            "start_time": str(start_time),
            "end_time": str(end_time),
            "repeat_type": repeat_type,
            "repeat_pattern": repeat_pattern
        }
    except Exception as e:
        conn.rollback()
        print(f"[DB Error] create_habit: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def get_user_habits(user_id):
    """Fetch all habits owned by user."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    try:
        if db_type == "postgres":
            cursor.execute('SELECT * FROM habit WHERE user_id = %s ORDER BY id DESC;', (user_id,))
            rows = cursor.fetchall()
        else:
            cursor.execute('SELECT * FROM habit WHERE user_id = ? ORDER BY id DESC;', (user_id,))
            rows = [dict(row) for row in cursor.fetchall()]
        
        # Ensure repeat_pattern is parsed back into a dictionary
        for row in rows:
            if isinstance(row.get('repeat_pattern'), str):
                try:
                    row['repeat_pattern'] = json.loads(row['repeat_pattern'])
                except Exception:
                    pass
        return rows
    finally:
        cursor.close()
        conn.close()


def verify_habit_ownership(habit_id, user_id):
    """Verify that a habit belongs to a specific user_id."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    try:
        if db_type == "postgres":
            cursor.execute('SELECT id FROM habit WHERE id = %s AND user_id = %s;', (habit_id, user_id))
            row = cursor.fetchone()
        else:
            cursor.execute('SELECT id FROM habit WHERE id = ? AND user_id = ?;', (habit_id, user_id))
            row = cursor.fetchone()
        return row is not None
    finally:
        cursor.close()
        conn.close()


def delete_habit(habit_id):
    """Delete habit by ID."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    try:
        if db_type == "postgres":
            cursor.execute('DELETE FROM habit WHERE id = %s;', (habit_id,))
        else:
            cursor.execute('DELETE FROM habit WHERE id = ?;', (habit_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB Error] delete_habit: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def upsert_habit_log(habit_id, log_date, status):
    """Insert or update habit log stage status."""
    conn, db_type = get_db()
    cursor = conn.cursor()

    if isinstance(status, bool):
        status_str = "complete" if status else "ready"
    else:
        status_str = str(status)

    is_completed = 1 if status_str in ["complete", "done"] else 0

    try:
        if db_type == "postgres":
            cursor.execute(
                """
                INSERT INTO habit_log (habit_id, log_date, completed, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (habit_id, log_date)
                DO UPDATE SET completed = EXCLUDED.completed, status = EXCLUDED.status;
                """,
                (habit_id, log_date, bool(is_completed), status_str)
            )
        else:
            cursor.execute(
                """
                INSERT INTO habit_log (habit_id, log_date, completed, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(habit_id, log_date)
                DO UPDATE SET completed = excluded.completed, status = excluded.status;
                """,
                (habit_id, str(log_date), is_completed, status_str)
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB Error] upsert_habit_log: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def get_user_habit_logs(user_id):
    """Fetch habit log records for a user as a nested dictionary."""
    habits = get_user_habits(user_id)
    if not habits:
        return {}

    conn, db_type = get_db()
    cursor = conn.cursor()
    habit_ids = [h['id'] for h in habits]
    logs_map = {}

    try:
        if habit_ids:
            if db_type == "postgres":
                cursor.execute(
                    "SELECT habit_id, log_date::text as log_date, status, completed FROM habit_log WHERE habit_id = ANY(%s);",
                    (habit_ids,)
                )
                rows = cursor.fetchall()
            else:
                placeholders = ','.join(['?'] * len(habit_ids))
                cursor.execute(
                    f"SELECT habit_id, log_date, status, completed FROM habit_log WHERE habit_id IN ({placeholders});",
                    habit_ids
                )
                rows = [dict(r) for r in cursor.fetchall()]

            for r in rows:
                h_id = str(r['habit_id'])
                l_date = str(r['log_date'])
                st = r.get('status')
                if not st:
                    st = "done" if r.get('completed') else "ready"

                if h_id not in logs_map:
                    logs_map[h_id] = {}
                logs_map[h_id][l_date] = st
        return logs_map
    finally:
        cursor.close()
        conn.close()

def get_all_users():
    """Fetch shared Auth Service users without exposing password hashes."""
    conn, db_type = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, email, created_at FROM users ORDER BY created_at DESC;')
        rows = cursor.fetchall()
        if db_type == "sqlite":
            rows = [dict(row) for row in rows]
        return rows
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id):
    """Fetch a shared Auth Service user's public info."""
    conn, db_type = get_db()
    cursor = conn.cursor()
    try:
        placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(f'SELECT id, email, created_at FROM users WHERE id = {placeholder};', (user_id,))
        row = cursor.fetchone()
        if row and db_type == "sqlite":
            row = dict(row)
        return row
    finally:
        cursor.close()
        conn.close()


def get_formatted_habit_logs(user_id, log_date=None):
    """
    User ရဲ့ Habit Log များကို Habit Details (name, start_time, end_time) များနှင့်တကွ
    ဆွဲထုတ်ပေးသည့် Function
    """
    conn, db_type = get_db()
    cursor = conn.cursor()

    try:
        placeholder = "%s" if db_type == "postgres" else "?"

        sql = f"""
            SELECT 
                h.habit_name, 
                hl.log_date, 
                h.start_time, 
                h.end_time, 
                hl.completed, 
                hl.created_at
            FROM habit_log hl
            JOIN habit h ON hl.habit_id = h.id
            WHERE h.user_id = {placeholder}
        """
        params = [user_id]

        # သီးသန့် ရက်စွဲတစ်ခုတည်းအတွက် စစ်ချင်လျှင် log_date ထည့်ပေးနိုင်သည်
        if log_date:
            sql += f" AND hl.log_date = {placeholder}"
            params.append(str(log_date))

        sql += " ORDER BY hl.log_date DESC, h.start_time ASC;"

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        habit_logs = []
        for r in rows:
            # dict သို့မဟုတ် tuple ဖြင့် ထွက်လာသော Database Cursor များအတွက် ကိုင်တွယ်ခြင်း
            if isinstance(r, dict):
                h_name = r['habit_name']
                l_date = str(r['log_date'])
                s_time = str(r['start_time'])
                e_time = str(r['end_time'])
                is_completed = bool(r['completed'])
                c_at = str(r['created_at'])
            else:
                h_name, l_date, s_time, e_time, completed, c_at = r
                is_completed = bool(completed)

            habit_logs.append({
                "habit_name": h_name,
                "log_date": l_date,
                "start_time": s_time,
                "end_time": e_time,
                "completed": is_completed,  # 0/1 ကို True/False ပြောင်းပေးသည်
                "created_at": str(c_at)
            })

        return habit_logs

    finally:
        cursor.close()
        conn.close()
