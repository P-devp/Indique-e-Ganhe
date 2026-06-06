import sqlite3
import os
import random
import hashlib
import secrets
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'retro.db')

LEVEL_THRESHOLDS = [
    ('bronze', 0, 0.0),
    ('prata', 100, 0.02),
    ('ouro', 500, 0.05),
    ('diamante', 2000, 0.10),
]


def _hash_password(password):
    return generate_password_hash(password)


def _check_password(password, stored):
    try:
        if check_password_hash(stored, password):
            return True
    except ValueError:
        pass
    if ':' not in stored:
        return False
    salt, h = stored.split(':', 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def calculate_level(total_earned):
    name = 'bronze'
    bonus = 0.0
    for n, threshold, b in LEVEL_THRESHOLDS:
        if total_earned >= threshold:
            name, bonus = n, b
    return name, bonus


class Database:
    def __init__(self):
        self.init_db()

    def _connect(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        conn = self._connect()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS affiliates (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT DEFAULT '',
                service TEXT DEFAULT 'ambos',
                registered_date TEXT,
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                earnings REAL DEFAULT 0.0,
                balance REAL DEFAULT 0.0,
                level TEXT DEFAULT 'bronze'
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_code TEXT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'affiliate',
                reset_token TEXT,
                reset_token_expiry TEXT,
                FOREIGN KEY (affiliate_code) REFERENCES affiliates(code)
            );
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_code TEXT NOT NULL,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                clicks_target INTEGER DEFAULT 0,
                conversions_target INTEGER DEFAULT 0,
                earnings_target REAL DEFAULT 0.0,
                FOREIGN KEY (affiliate_code) REFERENCES affiliates(code)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_code TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                requested_at TEXT DEFAULT (datetime('now', 'localtime')),
                paid_at TEXT,
                approved_by TEXT,
                FOREIGN KEY (affiliate_code) REFERENCES affiliates(code)
            );
        ''')
        # Migration: add reset_token columns for existing databases
        try:
            conn.execute('ALTER TABLE users ADD COLUMN reset_token TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute('ALTER TABLE users ADD COLUMN reset_token_expiry TEXT')
        except sqlite3.OperationalError:
            pass
        # Migration: add expires_at for existing databases
        try:
            conn.execute('ALTER TABLE sessions ADD COLUMN expires_at TEXT')
        except sqlite3.OperationalError:
            pass
        # Clean expired sessions
        conn.execute("DELETE FROM sessions WHERE expires_at IS NOT NULL AND expires_at <= datetime('now', 'localtime')")
        # Indexes for performance
        try:
            conn.execute('CREATE INDEX IF NOT EXISTS idx_sessions_email ON sessions(email)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_payouts_status ON payouts(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_payouts_affiliate ON payouts(affiliate_code)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_goals_affiliate ON goals(affiliate_code, month, year)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    # ── Auth ────────────────────────────────────────────────

    def register_user(self, affiliate_code, email, password, role='affiliate'):
        import re
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return None
        if len(password) < 6:
            return None
        conn = self._connect()
        existing = conn.execute(
            'SELECT id FROM users WHERE email = ?', (email,)
        ).fetchone()
        if existing:
            conn.close()
            return None
        pw = _hash_password(password)
        conn.execute(
            'INSERT INTO users (affiliate_code, email, password_hash, role) VALUES (?, ?, ?, ?)',
            (affiliate_code, email, pw, role)
        )
        conn.commit()
        conn.close()
        return self.get_user_by_email(email)

    def get_user_by_email(self, email):
        conn = self._connect()
        row = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def verify_login(self, email, password):
        user = self.get_user_by_email(email)
        if not user:
            return None
        if not _check_password(password, user['password_hash']):
            return None
        return user

    def create_session(self, email):
        token = secrets.token_urlsafe(32)
        conn = self._connect()
        conn.execute(
            "INSERT INTO sessions (token, email, expires_at) VALUES (?, ?, datetime('now', 'localtime', '+1 day'))",
            (token, email)
        )
        conn.commit()
        conn.close()
        return token

    def get_session(self, token):
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM sessions WHERE token = ? AND (expires_at IS NULL OR expires_at > datetime('now', 'localtime'))",
            (token,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_session(self, token):
        conn = self._connect()
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()

    def get_user_by_token(self, token):
        sess = self.get_session(token)
        if not sess:
            return None
        return self.get_user_by_email(sess['email'])

    def generate_reset_token(self, email):
        user = self.get_user_by_email(email)
        if not user:
            return None
        token = secrets.token_urlsafe(32)
        conn = self._connect()
        conn.execute(
            'UPDATE users SET reset_token = ?, reset_token_expiry = datetime("now", "+1 hour") WHERE email = ?',
            (token, email)
        )
        conn.commit()
        conn.close()
        return token

    def verify_reset_token(self, token):
        conn = self._connect()
        row = conn.execute(
            'SELECT * FROM users WHERE reset_token = ? AND reset_token_expiry > datetime("now", "localtime")',
            (token,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def reset_password(self, token, new_password):
        if len(new_password) < 6:
            return None
        user = self.verify_reset_token(token)
        if not user:
            return None
        pw = _hash_password(new_password)
        conn = self._connect()
        conn.execute(
            'UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?',
            (pw, user['id'])
        )
        conn.commit()
        conn.close()
        return True

    # ── Affiliates ──────────────────────────────────────────

    def all_affiliates(self, limit=None, offset=None):
        conn = self._connect()
        query = 'SELECT * FROM affiliates ORDER BY earnings DESC'
        params = []
        if limit is not None:
            query += ' LIMIT ?'
            params.append(limit)
        if offset is not None:
            query += ' OFFSET ?'
            params.append(offset)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def count_affiliates(self):
        conn = self._connect()
        row = conn.execute('SELECT COUNT(*) as total FROM affiliates').fetchone()
        conn.close()
        return row['total']

    def get_affiliate(self, code):
        conn = self._connect()
        row = conn.execute(
            'SELECT * FROM affiliates WHERE code = ?', (code,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_affiliate(self, data):
        conn = self._connect()
        for _ in range(100):
            code = f"RETRO-{datetime.now().year}-{random.randint(0, 9999):04d}"
            exists = conn.execute(
                'SELECT 1 FROM affiliates WHERE code = ?', (code,)
            ).fetchone()
            if not exists:
                break
        else:
            conn.close()
            return None
        today = datetime.now().strftime('%d/%m/%Y')
        conn.execute('''
            INSERT INTO affiliates (code, name, email, phone, service, registered_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (code, data['name'], data['email'], data.get('phone', ''),
              data.get('service', 'ambos'), today))
        conn.commit()
        row = conn.execute(
            'SELECT * FROM affiliates WHERE code = ?', (code,)
        ).fetchone()
        conn.close()
        return dict(row)

    def update_affiliate(self, code, updates):
        allowed = ['name', 'email', 'phone', 'service',
                   'clicks', 'conversions', 'earnings', 'balance', 'level']
        conn = self._connect()
        for key, value in updates.items():
            if key in allowed:
                conn.execute(
                    f'UPDATE affiliates SET {key} = ? WHERE code = ?',
                    (value, code)
                )
        conn.commit()
        conn.close()
        if 'level' not in updates and any(k in updates for k in ('earnings', 'balance', 'clicks', 'conversions')):
            self._recalc_level(code)
        return self.get_affiliate(code)

    def _recalc_level(self, code):
        aff = self.get_affiliate(code)
        if not aff:
            return
        level_name, _ = calculate_level(aff['earnings'])
        conn = self._connect()
        conn.execute(
            'UPDATE affiliates SET level = ? WHERE code = ?',
            (level_name, code)
        )
        conn.commit()
        conn.close()

    def delete_affiliate(self, code):
        conn = self._connect()
        conn.execute('DELETE FROM affiliates WHERE code = ?', (code,))
        conn.execute('DELETE FROM users WHERE affiliate_code = ?', (code,))
        conn.execute('DELETE FROM goals WHERE affiliate_code = ?', (code,))
        conn.execute('DELETE FROM payouts WHERE affiliate_code = ?', (code,))
        conn.commit()
        conn.close()

    # ── Clicks & Conversions ────────────────────────────────

    def record_click(self, code):
        conn = self._connect()
        conn.execute(
            'UPDATE affiliates SET clicks = clicks + 1 WHERE code = ?',
            (code,)
        )
        conn.commit()
        conn.close()

    def record_conversion(self, code, earnings=0):
        conn = self._connect()
        conn.execute('''
            UPDATE affiliates
            SET conversions = conversions + 1,
                earnings = earnings + ?,
                balance = balance + ?
            WHERE code = ?
        ''', (earnings, earnings, code))
        conn.commit()
        conn.close()
        self._recalc_level(code)

    # ── Stats ───────────────────────────────────────────────

    def stats(self):
        conn = self._connect()
        row = conn.execute('''
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(clicks), 0) as clicks,
                COALESCE(SUM(conversions), 0) as conversions,
                COALESCE(SUM(earnings), 0.0) as earnings
            FROM affiliates
        ''').fetchone()
        conn.close()
        return dict(row)

    def top_affiliates(self, limit=10):
        conn = self._connect()
        rows = conn.execute(
            'SELECT * FROM affiliates ORDER BY earnings DESC LIMIT ?',
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Levels ──────────────────────────────────────────────

    def get_level_info(self, total_earned):
        name, bonus = calculate_level(total_earned)
        levels = []
        for n, threshold, b in LEVEL_THRESHOLDS:
            levels.append({
                'name': n,
                'threshold': threshold,
                'bonus': b,
                'unlocked': total_earned >= threshold
            })
        next_level = None
        current_idx = -1
        for i, (n, _, _) in enumerate(LEVEL_THRESHOLDS):
            if n == name:
                current_idx = i
                break
        if current_idx < len(LEVEL_THRESHOLDS) - 1:
            next_name, next_threshold, next_bonus = LEVEL_THRESHOLDS[current_idx + 1]
            prev_threshold = LEVEL_THRESHOLDS[current_idx][1]
            progress = 0
            if next_threshold > prev_threshold:
                progress = min(100, ((total_earned - prev_threshold) / (next_threshold - prev_threshold)) * 100)
            next_level = {
                'name': next_name,
                'threshold': next_threshold,
                'bonus': next_bonus,
                'progress': round(progress, 1)
            }
        return {
            'current': name,
            'bonus': bonus,
            'levels': levels,
            'next': next_level
        }

    # ── Goals ───────────────────────────────────────────────

    def get_goals(self, code, month, year):
        conn = self._connect()
        row = conn.execute(
            'SELECT * FROM goals WHERE affiliate_code = ? AND month = ? AND year = ?',
            (code, month, year)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def set_goals(self, code, month, year, clicks=0, conversions=0, earnings=0):
        existing = self.get_goals(code, month, year)
        conn = self._connect()
        if existing:
            conn.execute('''
                UPDATE goals SET clicks_target=?, conversions_target=?, earnings_target=?
                WHERE affiliate_code=? AND month=? AND year=?
            ''', (clicks, conversions, earnings, code, month, year))
        else:
            conn.execute('''
                INSERT INTO goals (affiliate_code, month, year, clicks_target, conversions_target, earnings_target)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (code, month, year, clicks, conversions, earnings))
        conn.commit()
        conn.close()
        return self.get_goals(code, month, year)

    # ── Payouts ──────────────────────────────────────────────

    def request_payout(self, code, amount):
        aff = self.get_affiliate(code)
        if not aff:
            return None
        if aff['balance'] < amount:
            return None
        conn = self._connect()
        conn.execute(
            'INSERT INTO payouts (affiliate_code, amount, status) VALUES (?, ?, ?)',
            (code, amount, 'pending')
        )
        conn.execute(
            'UPDATE affiliates SET balance = balance - ? WHERE code = ?',
            (amount, code)
        )
        conn.commit()
        row = conn.execute(
            'SELECT * FROM payouts WHERE id = last_insert_rowid()'
        ).fetchone()
        conn.close()
        return dict(row)

    def get_payouts(self, code=None, status=None):
        conn = self._connect()
        sql = 'SELECT * FROM payouts'
        params = []
        where = []
        if code:
            where.append('affiliate_code = ?')
            params.append(code)
        if status:
            where.append('status = ?')
            params.append(status)
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY requested_at DESC'
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_payout(self, payout_id, status, approved_by=None):
        conn = self._connect()
        payout = conn.execute(
            'SELECT * FROM payouts WHERE id = ?', (payout_id,)
        ).fetchone()
        if not payout:
            conn.close()
            return None
        payout = dict(payout)
        if status == 'rejected' and payout['status'] == 'pending':
            conn.execute(
                'UPDATE affiliates SET balance = balance + ? WHERE code = ?',
                (payout['amount'], payout['affiliate_code'])
            )
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('''
            UPDATE payouts SET status=?, paid_at=?, approved_by=?
            WHERE id=?
        ''', (status, now if status in ('approved', 'paid') else None, approved_by, payout_id))
        conn.commit()
        row = conn.execute(
            'SELECT * FROM payouts WHERE id = ?', (payout_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def payout_stats(self):
        conn = self._connect()
        rows = conn.execute('''
            SELECT status, COUNT(*) as count, COALESCE(SUM(amount), 0) as total
            FROM payouts GROUP BY status
        ''').fetchall()
        conn.close()
        stats = {'pending': {'count': 0, 'total': 0},
                 'approved': {'count': 0, 'total': 0},
                 'paid': {'count': 0, 'total': 0},
                 'rejected': {'count': 0, 'total': 0}}
        for r in rows:
            d = dict(r)
            stats[d['status']] = {'count': d['count'], 'total': d['total']}
        return stats

    def get_goal_progress(self, code, month, year):
        aff = self.get_affiliate(code)
        goals = self.get_goals(code, month, year)
        if not goals or not aff:
            return None
        ct = goals['clicks_target']
        cvt = goals['conversions_target']
        et = goals['earnings_target']
        return {
            'affiliate_code': code,
            'month': month,
            'year': year,
            'clicks': {'current': aff.get('clicks', 0), 'target': ct, 'progress': min(100, round((aff.get('clicks', 0) / ct) * 100, 1)) if ct else 0},
            'conversions': {'current': aff.get('conversions', 0), 'target': cvt, 'progress': min(100, round((aff.get('conversions', 0) / cvt) * 100, 1)) if cvt else 0},
            'earnings': {'current': round(aff.get('earnings', 0), 2), 'target': et, 'progress': min(100, round((aff.get('earnings', 0) / et) * 100, 1)) if et else 0}
        }
