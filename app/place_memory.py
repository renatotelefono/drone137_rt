"""Evidence-backed place memory. The LLM is not the persistent database."""
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path


class PlaceMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS places(id TEXT PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS visits(id TEXT PRIMARY KEY, place_id TEXT NOT NULL REFERENCES places(id), started REAL NOT NULL, state TEXT NOT NULL, summary TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS observations(visit_id TEXT NOT NULL REFERENCES visits(id), sequence INTEGER NOT NULL, image_sha256 TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(visit_id,sequence));
              CREATE TABLE IF NOT EXISTS maps(visit_id TEXT PRIMARY KEY REFERENCES visits(id), revision INTEGER NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS visits_by_place ON visits(place_id,started);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def begin(self, place, name, visit):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', place) or not re.fullmatch(r'[a-f0-9]{32}', visit):
            raise ValueError('Invalid place or visit ID')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('A place name is required')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO places VALUES(?,?,?)', (place, name, time.time()))
            db.execute('INSERT INTO visits VALUES(?,?,?,?,?)', (visit, place, time.time(), 'exploring', '{}'))

    def observe(self, visit, sequence, image, data):
        if not image or type(sequence) is not int or sequence < 1:
            raise ValueError('Observation needs image evidence and sequence')
        encoded = json.dumps(data, allow_nan=False)
        with self.connect() as db:
            db.execute('INSERT INTO observations VALUES(?,?,?,?)',
                       (visit, sequence, hashlib.sha256(image).hexdigest(), encoded))

    def save_map(self, visit, data):
        encoded = json.dumps(data, allow_nan=False)
        with self.connect() as db:
            db.execute('INSERT INTO maps VALUES(?,1,?,?) ON CONFLICT(visit_id) DO UPDATE SET revision=revision+1,data=excluded.data,updated=excluded.updated', (visit, encoded, time.time()))

    def finish(self, visit, state, summary):
        if state not in ('complete', 'failed', 'cancelled', 'partial'):
            raise ValueError('Unknown final state')
        with self.connect() as db:
            db.execute('UPDATE visits SET state=?,summary=? WHERE id=?', (state, json.dumps(summary, allow_nan=False), visit))

    def record_evaluation(self,visit,evaluation):
        """Attach the independent post-flight result without altering evidence."""
        gates=evaluation.get('gates')
        if (not isinstance(gates,dict) or not gates or any(type(v) is not bool for v in gates.values())
                or evaluation.get('accepted') is not all(gates.values())):
            raise ValueError('Evaluation must include consistent acceptance gates')
        data={k:evaluation[k] for k in ('accepted','gates','metrics','protocol_sha256')}
        with self.connect() as db:
            row=db.execute('SELECT state,summary FROM visits WHERE id=?',(visit,)).fetchone()
            if row is None:raise KeyError('Unknown visit')
            if row['state']=='exploring':raise ValueError('Cannot evaluate a running visit')
            summary=json.loads(row['summary']);summary['evaluation']=data
            state='complete' if data['accepted'] else row['state']
            db.execute('UPDATE visits SET state=?,summary=? WHERE id=?',
                       (state,json.dumps(summary,allow_nan=False),visit))

    def recall(self, place, selected_visit=None, compact=False):
        with self.connect() as db:
            p = db.execute('SELECT * FROM places WHERE id=?', (place,)).fetchone()
            if not p:
                raise KeyError('Unknown place')
            visits = [dict(r) for r in db.execute('SELECT * FROM visits WHERE place_id=? ORDER BY started', (place,))]
            selected_visit=selected_visit or (visits[-1]['id'] if visits else None)
            if selected_visit is not None and not any(v['id']==selected_visit for v in visits):
                raise KeyError('Unknown visit for this place')
            for v in visits:
                v['summary'] = json.loads(v['summary'])
                if compact and v['id']!=selected_visit:
                    v['map']=None;v['observations']=[]
                    continue
                row = db.execute('SELECT revision,data FROM maps WHERE visit_id=?', (v['id'],)).fetchone()
                v['map'] = {'revision': row['revision'], **json.loads(row['data'])} if row else None
                v['observations'] = [json.loads(r['data']) | {'sequence':r['sequence'],'image_sha256': r['image_sha256']} for r in db.execute('SELECT * FROM observations WHERE visit_id=? ORDER BY sequence', (v['id'],))]
            return dict(p) | {'visits': visits, 'reuse_policy': 'Historical evidence; requires visual relocalization and freshness checks before navigation'}

    def context(self, place, limit=6000, question=''):
        """Bounded retrieval for the local model; no weights or hidden maps."""
        with self.connect() as db:
            record=db.execute('SELECT name FROM places WHERE id=?',(place,)).fetchone()
            if record is None:raise KeyError('Unknown place')
            data={'place':record['name'],'place_id':place,
                  'reuse_policy':'Historical evidence; current presence and navigation safety require a new observation',
                  'visits':[],'observations':[]}
            latest=db.execute('SELECT id,state,started,summary FROM visits WHERE place_id=? ORDER BY started DESC LIMIT 1',(place,)).fetchone()
            if latest is not None:
                evaluation=json.loads(latest['summary']).get('evaluation')
                data['latest_visit']={'visit':latest['id'][:8],'mission_state':latest['state'],
                    'started_at':latest['started'],
                    'independent_test':('passed' if evaluation['accepted'] else 'not_passed') if evaluation else 'not_evaluated'}
                if evaluation:
                    data['latest_visit']['failed_checks']=[k for k,v in evaluation['gates'].items() if not v]
            # Latest mission status must not depend on which older captions
            # happen to match an object-specific question.
            rows=list(db.execute('''SELECT v.id,v.state,v.started,o.sequence,o.image_sha256,
                json_extract(o.data,'$.observation') AS description
                FROM observations o JOIN visits v ON v.id=o.visit_id
                WHERE v.place_id=? AND json_extract(o.data,'$.observation') IS NOT NULL
                ORDER BY v.started DESC,o.sequence DESC LIMIT 1000''',(place,)))
            # Bounded lexical retrieval costs no embedding model/RAM. Diversity
            # prevents repeated shelf captions from hiding an earlier sighting.
            stop=set('a an and are as at be been did do does for from had has have here how i in is it me of on or place recorded see seen show that the there these this to was we were what when where which with you objects observed observations room workshop visit visits complete completed incomplete'.split())
            def words(value):
                return {w.rstrip('s') for w in re.findall(r'[a-z0-9]+',value.lower()) if w not in stop and len(w)>2}
            requested=words(question)
            chosen=[];all_tokens=set()
            while rows:
                # Match explicit object questions first; otherwise retain one
                # recent sighting, then choose descriptions adding new facts.
                def rank(o):
                    tokens=words(o['description'])
                    novelty=len(tokens-all_tokens)/max(1,len(tokens))**.5 if chosen else 0
                    return (len(tokens&requested),novelty)
                best=max(range(len(rows)),key=lambda i:rank(rows[i]))
                o=rows.pop(best)
                tokens=words(o['description'])
                if any(len(tokens&old)/max(1,len(tokens|old))>.65 for old in chosen):continue
                item={'visit':o['id'][:8],'sequence':o['sequence'],
                      'visual_observation':o['description']}
                new_visit=not any(v['visit']==o['id'][:8] for v in data['visits'])
                if new_visit:data['visits'].append({'visit':o['id'][:8],'mission_state':o['state'],'started_at':o['started']})
                data['observations'].append(item)
                if len(json.dumps(data))>limit:
                    data['observations'].pop()
                    if new_visit:data['visits'].pop()
                    break
                chosen.append(tokens)
                all_tokens.update(tokens)
            return data
