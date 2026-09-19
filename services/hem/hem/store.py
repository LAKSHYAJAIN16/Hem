import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS garments (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  category TEXT NOT NULL, description TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS preferences (
  user_id TEXT NOT NULL REFERENCES users(id), value TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK(sentiment IN ('like','dislike')),
  PRIMARY KEY(user_id, value)
);
CREATE TABLE IF NOT EXISTS outfits (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), item_ids TEXT NOT NULL,
  occasion TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS wears (
  user_id TEXT NOT NULL REFERENCES users(id), outfit_id TEXT NOT NULL REFERENCES outfits(id),
  worn_on TEXT NOT NULL, PRIMARY KEY(user_id, outfit_id, worn_on)
);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, message_id TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL,
  chat_id TEXT NOT NULL, reply TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id), latitude REAL NOT NULL,
  longitude REAL NOT NULL, label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS photo_drafts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  garments TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS photo_assets (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  draft_id TEXT NOT NULL REFERENCES photo_drafts(id), image TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS garment_details (
  garment_id TEXT PRIMARY KEY REFERENCES garments(id), attributes TEXT NOT NULL,
  asset_id TEXT REFERENCES photo_assets(id)
);
CREATE TABLE IF NOT EXISTS source_documents (
  id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
  url TEXT NOT NULL, source_url TEXT NOT NULL, published_at TEXT NOT NULL,
  summary TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id,id)
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS receipts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, reply TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox (
  id TEXT PRIMARY KEY, message_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS care_rules (
  garment_id TEXT PRIMARY KEY REFERENCES garments(id), method TEXT NOT NULL,
  every_wears INTEGER NOT NULL, wears_since_clean INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS action_requests (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
  item_ids TEXT NOT NULL, brief TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dialogue_focus (
  user_id TEXT PRIMARY KEY REFERENCES users(id), kind TEXT NOT NULL, target_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_opt_out (user_id TEXT PRIMARY KEY REFERENCES users(id));
"""


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def snapshot(self, user_id):
        with self.connect() as db:
            return {
                'wardrobe': [dict(r) for r in db.execute('SELECT * FROM garments WHERE user_id=? ORDER BY rowid', (user_id,))],
                'preferences': [dict(r) for r in db.execute('SELECT value,sentiment FROM preferences WHERE user_id=?', (user_id,))],
                'wears': [dict(r) for r in db.execute('SELECT outfit_id,worn_on FROM wears WHERE user_id=? ORDER BY worn_on DESC', (user_id,))],
                'outfits': [dict(r) for r in db.execute('SELECT id,item_ids,occasion,created_at FROM outfits WHERE user_id=? ORDER BY rowid DESC LIMIT 20', (user_id,))],
                'details': [dict(r) for r in db.execute('SELECT d.* FROM garment_details d JOIN garments g ON g.id=d.garment_id WHERE g.user_id=?', (user_id,))],
            }
