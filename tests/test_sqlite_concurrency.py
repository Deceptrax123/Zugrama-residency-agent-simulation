import sqlite3
import unittest
from residency.store import Store
from tests.support import settings

class SqliteConcurrencyTests(unittest.TestCase):
 def test_reader_keeps_snapshot_while_an_agent_commit_succeeds(self):
  with settings() as cfg:
   store=Store(cfg)
   with store.db() as writer:
    writer.execute("INSERT INTO metadata VALUES('concurrency','old')")
   reader=sqlite3.connect(store.path,timeout=.2)
   try:
    self.assertEqual(reader.execute('PRAGMA journal_mode').fetchone()[0],'wal')
    reader.execute('BEGIN');self.assertEqual(reader.execute("SELECT value FROM metadata WHERE key='concurrency'").fetchone()[0],'old')
    # In DELETE mode this commit is blocked by the open reader transaction.
    writer=sqlite3.connect(store.path,timeout=.2)
    try:
     writer.execute("UPDATE metadata SET value='new' WHERE key='concurrency'");writer.commit()
    finally:writer.close()
    self.assertEqual(reader.execute("SELECT value FROM metadata WHERE key='concurrency'").fetchone()[0],'old')
    reader.rollback()
    self.assertEqual(reader.execute("SELECT value FROM metadata WHERE key='concurrency'").fetchone()[0],'new')
   finally:reader.close()
   with Store(cfg).db() as db:self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'wal')
