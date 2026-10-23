"""Local paired-device registry. Public records never contain aircraft secrets."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from hardware.esp32.link_client import AircraftLink, endpoint
from hardware.esp32.link_protocol import identifier


class DeviceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Pairing is sensitive local state, separate from component catalogues.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS aircraft(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, endpoint TEXT NOT NULL,
                fingerprint TEXT NOT NULL, credential TEXT NOT NULL,
                kind TEXT NOT NULL, assembly TEXT NOT NULL, paired_at REAL NOT NULL)''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, *, profile, address, name, assembly):
        if not isinstance(profile, dict):
            raise ValueError('Expected a pairing profile')
        identity = identifier(profile.get('device_id'))
        kind = profile.get('kind')
        if kind not in ('protocol-emulator', 'aircraft'):
            raise ValueError('Unsupported aircraft kind')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Aircraft name must have 1–80 characters')
        if not isinstance(assembly, str) or not re.fullmatch('[a-z][a-z0-9-]{1,63}@[1-9][0-9]*', assembly):
            raise ValueError('Pin the component assembly to an ID@revision')
        # Validate pin and secret without opening a connection or exposing either.
        AircraftLink(address, profile.get('certificate_sha256'), profile.get('credential'), 'validation')
        with self.connection() as db:
            if db.execute('SELECT 1 FROM aircraft WHERE id=?', (identity,)).fetchone():
                raise ValueError('Aircraft already paired; forget it before replacing its identity')
            db.execute('INSERT INTO aircraft VALUES(?,?,?,?,?,?,?,?)',
                       (identity, name.strip(), endpoint(address), profile['certificate_sha256'].lower(),
                        profile['credential'], kind, assembly, time.time()))
        return self.get(identity)

    def get(self, identity, *, private=False):
        identifier(identity)
        with self.connection() as db:
            row = db.execute('SELECT * FROM aircraft WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('Aircraft is not paired')
        result = dict(row)
        if not private:
            result.pop('credential')
        return result

    def list(self):
        with self.connection() as db:
            identities = [r[0] for r in db.execute('SELECT id FROM aircraft ORDER BY name,id')]
        return [self.get(identity) for identity in identities]

    def remove(self, identity):
        identifier(identity)
        with self.connection() as db:
            db.execute('DELETE FROM aircraft WHERE id=?', (identity,))
