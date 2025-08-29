# --- ids_store.py (Cloud-ready) ---
import sqlite3, contextlib, os, tempfile

# Prefer the app folder if writable; else /tmp in Streamlit Cloud
base_dir = os.path.dirname(__file__)
try:
    test = os.path.join(base_dir, ".write_test")
    open(test, "w").close(); os.remove(test)
    DATA_DIR = base_dir
except Exception:
    DATA_DIR = tempfile.gettempdir()

DB_PATH = os.path.join(DATA_DIR, "app_data.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS entity_ids (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT CHECK(entity_type IN ('client','law_firm')) NOT NULL,
  name TEXT NOT NULL,
  ext_id TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'Prod',
  UNIQUE(entity_type, ext_id, environment)
);
CREATE TABLE IF NOT EXISTS defaults (
  key TEXT PRIMARY KEY,             -- 'client_default' | 'law_firm_default'
  entity_row_id INTEGER,
  FOREIGN KEY(entity_row_id) REFERENCES entity_ids(id) ON DELETE SET NULL
);
"""

@contextlib.contextmanager
def get_conn():
  conn = sqlite3.connect(DB_PATH)
  try:
    yield conn
  finally:
    conn.commit()
    conn.close()

def init_db():
  with get_conn() as c:
    c.executescript(SCHEMA)

def list_envs(entity_type):
  with get_conn() as c:
    rows = c.execute(
      "SELECT DISTINCT environment FROM entity_ids WHERE entity_type=? ORDER BY environment",
      (entity_type,)
    ).fetchall()
  return [r[0] for r in rows] or ["Prod"]

def fetch_entities(entity_type, environment=None):
  q = "SELECT id,name,ext_id,environment FROM entity_ids WHERE entity_type=?"
  args = [entity_type]
  if environment and environment != "All":
    q += " AND environment=?"
    args.append(environment)
  q += " ORDER BY name COLLATE NOCASE"
  with get_conn() as c:
    rows = c.execute(q, args).fetchall()
  return [{"row_id":r[0], "name":r[1], "ext_id":r[2], "environment":r[3]} for r in rows]

def upsert_entity(entity_type, name, ext_id, environment, row_id=None):
  with get_conn() as c:
    if row_id:
      c.execute(
        "UPDATE entity_ids SET name=?, ext_id=?, environment=? WHERE id=? AND entity_type=?",
        (name, ext_id, environment, row_id, entity_type)
      )
      return row_id
    cur = c.execute(
        "INSERT OR IGNORE INTO entity_ids (entity_type,name,ext_id,environment) VALUES (?,?,?,?)",
        (entity_type, name, ext_id, environment)
    )
    if cur.rowcount == 0:
      got = c.execute(
        "SELECT id FROM entity_ids WHERE entity_type=? AND ext_id=? AND environment=?",
        (entity_type, ext_id, environment)
      ).fetchone()
      return got[0]
    return cur.lastrowid

def delete_entity(row_id):
  with get_conn() as c:
    c.execute("DELETE FROM entity_ids WHERE id=?", (row_id,))

def get_default(key):
  with get_conn() as c:
    row = c.execute("SELECT entity_row_id FROM defaults WHERE key=?", (key,)).fetchone()
  return row[0] if row else None

def set_default(key, row_id):
  with get_conn() as c:
    c.execute("INSERT INTO defaults(key,entity_row_id) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET entity_row_id=excluded.entity_row_id", (key, row_id))
