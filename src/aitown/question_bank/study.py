"""Personal study records, independent of replaceable course parsing records."""
import json
import sqlite3
import shutil
import time
from pathlib import Path
from typing import Literal

StudyState = Literal['unattempted', 'attempted', 'correct', 'incorrect']
STATES = {'unattempted': '未做过', 'attempted': '做过', 'correct': '做对', 'incorrect': '做错'}


class StudyStore:
    def __init__(self, path, owner='anotherme', *, readonly=False):
        self.path = Path(path).resolve()
        self.owner = owner
        self.conn = None
        if readonly and not self.path.is_file():
            return
        if not readonly:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True) if readonly else sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        if not readonly:
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS study_items(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, course TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('unattempted','attempted','correct','incorrect')),
                    snapshot TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS study_origins(
                    owner TEXT NOT NULL, course TEXT NOT NULL, path TEXT NOT NULL, member TEXT NOT NULL,
                    number TEXT NOT NULL, text TEXT NOT NULL, item_id INTEGER NOT NULL REFERENCES study_items(id),
                    PRIMARY KEY(owner,course,path,member,number,text));
                CREATE TABLE IF NOT EXISTS study_solutions(
                    item_id INTEGER PRIMARY KEY REFERENCES study_items(id), payload TEXT NOT NULL, created REAL NOT NULL);
            ''')

    def _keys(self, question):
        return [(self.owner, question['course_id'], o['path'], o.get('member', ''), o['number'], question['text'])
                for o in question.get('origins', [question])]

    def _items(self, question):
        if self.conn is None:
            return []
        ids = set()
        for key in self._keys(question):
            row = self.conn.execute('SELECT item_id FROM study_origins WHERE owner=? AND course=? AND path=? AND member=? AND number=? AND text=?', key).fetchone()
            if row:
                ids.add(row[0])
        return [self.conn.execute('SELECT * FROM study_items WHERE id=? AND owner=?', (i, self.owner)).fetchone() for i in ids]

    def record(self, question):
        rows = self._items(question)
        row = max(rows, key=lambda r: (r['updated'], r['id'])) if rows else None
        result = {'state': row['state'] if row else 'unattempted', 'updated': row['updated'] if row else None,
                  'item_id': row['id'] if row else None, 'solution': None}
        if row:
            for candidate in sorted(rows, key=lambda r: (r['updated'], r['id']), reverse=True):
                solution = self.conn.execute('SELECT payload FROM study_solutions WHERE item_id=?', (candidate['id'],)).fetchone()
                if solution:
                    result['solution'] = json.loads(solution[0])
                    break
        return result

    def _ensure(self, question):
        rows = self._items(question)
        now = time.time()
        if rows:
            item = max(rows, key=lambda r: (r['updated'], r['id']))['id']
            # Later source deduplication can join two previously saved problems.
            saved = self.record(question)['solution']
            if saved:
                self.conn.execute('INSERT OR IGNORE INTO study_solutions VALUES(?,?,?)',
                    (item, json.dumps(saved, ensure_ascii=False), saved.get('created', now)))
        else:
            # Keep the chosen problem and provenance when source parsing is replaced.
            snapshot = {k: v for k, v in question.items() if k not in ('study', 'solution', 'answers')}
            item = self.conn.execute('INSERT INTO study_items(owner,course,state,snapshot,created,updated) VALUES(?,?,\'unattempted\',?,?,?)',
                (self.owner, question['course_id'], json.dumps(snapshot, ensure_ascii=False), now, now)).lastrowid
            images = []
            previews = []
            for index, name in enumerate(question.get('images', [])):
                source = Path(name).resolve()
                if not source.is_relative_to(self.path.parent/'processed') or not source.is_file():
                    continue
                destination = self.path.parent/'study-assets'/str(item)/(str(index)+source.suffix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                previews.extend({**preview, 'index': len(images)} for preview in question.get('image_previews', []) if preview['index']==index)
                images.append(str(destination))
            snapshot['images'] = images
            snapshot['image_previews'] = previews
            self.conn.execute('UPDATE study_items SET snapshot=? WHERE id=?', (json.dumps(snapshot, ensure_ascii=False), item))
        for key in self._keys(question):
            self.conn.execute('INSERT INTO study_origins VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner,course,path,member,number,text) DO UPDATE SET item_id=excluded.item_id', (*key, item))
        return item

    def mark(self, question, state):
        if state not in STATES:
            raise ValueError('请选择未做过、做过、做对或做错。')
        with self.conn:
            item = self._ensure(question)
            self.conn.execute('UPDATE study_items SET state=?,updated=? WHERE id=?', (state, time.time(), item))
        return self.record(question)

    def save_solution(self, question, solution):
        with self.conn:
            item = self._ensure(question)
            self.conn.execute('INSERT INTO study_solutions VALUES(?,?,?) ON CONFLICT(item_id) DO UPDATE SET payload=excluded.payload,created=excluded.created',
                (item, json.dumps(solution, ensure_ascii=False), time.time()))
        return self.record(question)

    def library(self, course='', state='all'):
        if state not in ('all', *STATES):
            raise ValueError('学习状态不正确。')
        rows = self.conn.execute('SELECT * FROM study_items WHERE owner=? AND (?=\'\' OR course=?) ORDER BY updated DESC,id DESC',
                                 (self.owner, course, course)).fetchall()
        items = []
        for row in rows:
            question = json.loads(row['snapshot'])
            question['study'] = self.record(question)
            if question['study']['item_id'] != row['id'] or not matches(question['study']['state'], state):
                continue
            question['study_snapshot'] = True
            items.append(question)
        return items

    def snapshot(self, item_id):
        row = self.conn.execute('SELECT snapshot FROM study_items WHERE id=? AND owner=?', (item_id, self.owner)).fetchone()
        if not row:
            raise ValueError('个人题目不存在。')
        return json.loads(row[0])

    def close(self):
        if self.conn is not None:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def matches(state, selected):
    return selected == 'all' or (selected == 'attempted' and state != 'unattempted') or state == selected


def state_in_query(query):
    import re
    for pattern, state in [(r'未做过|没做过|未做的|没做的', 'unattempted'),
                           (r'做错|错题', 'incorrect'), (r'做对', 'correct'), (r'做过|已做', 'attempted')]:
        if re.search(pattern, query):
            return state
    return None
