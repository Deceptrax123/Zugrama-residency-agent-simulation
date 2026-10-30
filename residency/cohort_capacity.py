"""Backed-up capacity expansion, used only by the separate live cohort."""
import re
import sqlite3
import time

MAX_RESIDENTS=50


def expand_capacity(store,limit):
    if type(limit) is not int or not 2<=limit<=MAX_RESIDENTS:
        raise ValueError(f'Choose a live capacity from 2 to {MAX_RESIDENTS}')
    with store.db() as db:
        row=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='agent_identities'").fetchone()
        if not row:return
        sql=row[0];match=re.search(r'CHECK\(slot BETWEEN 1 AND (\d+)\)',sql)
        if not match:raise ValueError('Unrecognized identity capacity schema; database preserved')
        old=int(match[1])
        if old==limit:return
        if old>limit:raise ValueError('Automatic capacity reduction is not supported; database preserved')
        # No table in this schema refers to agent_identities. Refuse an unfamiliar
        # dependency rather than risking cascading deletes during table replacement.
        for table in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            if any(fk[2]=='agent_identities' for fk in db.execute('PRAGMA foreign_key_list("'+table[0].replace('"','""')+'")')):
                raise ValueError('Identity schema has dependent tables; database preserved')
        backup=store.path.with_name('before-capacity-'+str(time.time_ns())+'.sqlite3')
        with sqlite3.connect(backup) as destination:db.backup(destination)
        backup.chmod(0o600)
        objects=[r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='agent_identities' AND type IN ('index','trigger') AND sql IS NOT NULL")]
        replacement=sql.replace('agent_identities','expanded_agent_identities',1)
        replacement=re.sub(r'CHECK\(slot BETWEEN 1 AND \d+\)',f'CHECK(slot BETWEEN 1 AND {limit})',replacement,count=1)
        db.execute('BEGIN IMMEDIATE')
        db.execute(replacement)
        db.execute('INSERT INTO expanded_agent_identities SELECT * FROM agent_identities')
        db.execute('DROP TABLE agent_identities')
        db.execute('ALTER TABLE expanded_agent_identities RENAME TO agent_identities')
        for statement in objects:db.execute(statement)
        if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Capacity expansion failed integrity check')
