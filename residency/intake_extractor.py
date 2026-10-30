"""Outbound-only hosted intake worker. Never reads residency state or starts events."""
import json
import sqlite3
import time
import urllib.request
from urllib.parse import urlsplit

from .cv_pdf import pdf_text
from .hermes import NoRedirect
from .identity_extract import MODEL, extract
from .store import AppError


class IntakeClient:
    def __init__(self, origin, token):
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or parsed.netloc != 'zugrama-agent-residency.smudge0110.chatgpt.site' or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('Use the configured HTTPS Zugrama site origin')
        self.origin, self.token = origin.rstrip('/'), token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def post(self, path, payload):
        request = urllib.request.Request(self.origin + path, data=json.dumps(payload).encode(), headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
            'User-Agent': 'Zugrama-Extraction-Worker/1.0'})
        with self.opener.open(request, timeout=40) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError('Oversized intake response')
        return json.loads(raw)


class IntakeExtractor:
    def __init__(self, client, hermes, journal, daily_limit=50):
        self.client, self.hermes, self.daily_limit = client, hermes, daily_limit
        self.db = sqlite3.connect(journal)
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, started REAL NOT NULL)')
        self.db.commit()

    def step(self):
        job = self.client.post('/api/extractor/claim', {}).get('job')
        if not job:
            return 'idle'
        payload = {'id': job['id'], 'lease_token': job['lease_token'], 'status': 'failed'}
        try:
            if job.get('model') != MODEL or self.hermes.settings.hermes_model != MODEL:
                raise AppError('The configured GPT Terra model is required. No fallback was used.')
            # Journal before inference: uncertain model execution is never replayed.
            if self.db.execute('SELECT 1 FROM attempts WHERE id=?', (job['id'],)).fetchone():
                raise AppError('This extraction was already attempted. No automatic model retry was made.')
            count = self.db.execute('SELECT count(*) FROM attempts WHERE started>?', (time.time()-86400,)).fetchone()[0]
            if count >= self.daily_limit:
                raise AppError('The host daily extraction limit was reached. Try again tomorrow.')
            cv = pdf_text(job['pdf_base64'])
            self.db.execute('INSERT INTO attempts VALUES (?,?)', (job['id'], time.time()))
            self.db.commit()
            result = extract(self.hermes, 'zugrama-onboarding', job['id'], cv)
            payload.update(status='completed', result={'model': result['model'], 'suggestions': result['suggestions']})
        except AppError as exc:
            payload['error'] = str(exc)
        except Exception:
            payload['error'] = 'CV extraction could not complete. No automatic model retry was made.'
        # A failed delivery never reruns inference. Site leases expire after ten minutes.
        self.client.post('/api/extractor/complete', payload)
        return payload['status']
