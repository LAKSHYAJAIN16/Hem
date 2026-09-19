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
            }
