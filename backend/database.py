import hashlib
import os
import random
import secrets
import sqlite3
from datetime import datetime
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'retro.db')

LEVEL_THRESHOLDS = [
    ('bronze', 0, 0.0),
    ('prata', 100, 0.02),
    ('ouro', 500, 0.05),
    ('diamante', 2000, 0.10),
]


def _hash_password(password: str) -> str:
    return generate_password_hash(password)


def _check_password(password: str, stored: str) -> bool:
    try:
        if check_password_hash(stored, password):
            return True
    except ValueError:
        pass
    if ':' not in stored:
        return False
    salt, h = stored.split(':', 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def calculate_level(total_earned: float) -> tuple[str, float]:
    name = 'bronze'
    bonus = 0.0
    for n, threshold, b in LEVEL_THRESHOLDS:
        if total_earned >= threshold:
            name, bonus = n, b
    return name, bonus


class Database:
    def __init__(self) -> None:
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
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
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_code TEXT NOT NULL,
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (affiliate_code) REFERENCES affiliates(code)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                actor_email TEXT,
                details TEXT,
                ip TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_code TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT,
                amount REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
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
        try:
            conn.execute("ALTER TABLE users ADD COLUMN confirmed INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN confirm_token TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE affiliates ADD COLUMN commission_rate REAL")
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
            conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timeline_affiliate ON timeline(affiliate_code, created_at)')
        except sqlite3.OperationalError:
            pass
        # Seed default settings
        defaults = [
            ('commission_barbearia', '0.15'),
            ('commission_lavarapido', '0.10'),
        ]
        for k, v in defaults:
            conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))
        conn.commit()
        conn.close()

    # ── Auth ────────────────────────────────────────────────

    def register_user(self, affiliate_code: str, email: str, password: str, role: str = 'affiliate') -> dict[str, Any] | None:
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

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def verify_login(self, email: str, password: str) -> dict[str, Any] | None:
        user = self.get_user_by_email(email)
        if not user:
            return None
        if not _check_password(password, user['password_hash']):
            return None
        return user

    def create_session(self, email: str) -> str:
        token = secrets.token_urlsafe(32)
        conn = self._connect()
        conn.execute(
            "INSERT INTO sessions (token, email, expires_at) VALUES (?, ?, datetime('now', 'localtime', '+1 day'))",
            (token, email)
        )
        conn.commit()
        conn.close()
        return token

    def get_session(self, token: str) -> dict[str, Any] | None:
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

    def get_user_sessions(self, email):
        conn = self._connect()
        rows = conn.execute(
            "SELECT token, created_at FROM sessions WHERE email = ? AND (expires_at IS NULL OR expires_at > datetime('now', 'localtime')) ORDER BY created_at DESC",
            (email,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_session_by_token(self, token):
        conn = self._connect()
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()

    def delete_sessions_except(self, email, exclude_token):
        conn = self._connect()
        conn.execute("DELETE FROM sessions WHERE email = ? AND token != ?", (email, exclude_token))
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
                   'clicks', 'conversions', 'earnings', 'balance', 'level', 'commission_rate']
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

    def delete_user_account(self, email):
        user = self.get_user_by_email(email)
        if not user:
            return False
        code = user.get('affiliate_code')
        conn = self._connect()
        if code:
            conn.execute('DELETE FROM goals WHERE affiliate_code = ?', (code,))
            conn.execute('DELETE FROM payouts WHERE affiliate_code = ?', (code,))
            conn.execute('DELETE FROM push_subscriptions WHERE affiliate_code = ?', (code,))
            conn.execute('DELETE FROM timeline WHERE affiliate_code = ?', (code,))
            conn.execute('DELETE FROM affiliates WHERE code = ?', (code,))
        conn.execute('DELETE FROM sessions WHERE email = ?', (email,))
        conn.execute('DELETE FROM users WHERE email = ?', (email,))
        conn.commit()
        conn.close()
        return True

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

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def save_push_subscription(affiliate_code, endpoint, p256dh, auth):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO push_subscriptions (affiliate_code, endpoint, p256dh, auth)
        VALUES (?, ?, ?, ?)
    """, (affiliate_code, endpoint, p256dh, auth))
    conn.commit()
    conn.close()

def get_push_subscriptions(affiliate_code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT endpoint, p256dh, auth FROM push_subscriptions
        WHERE affiliate_code = ?
    """, (affiliate_code,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_all_push_subscriptions():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT endpoint, p256dh, auth FROM push_subscriptions
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

# ── Audit Log ──────────────────────────────────────────────

def log_action(action, actor_email=None, details=None, ip=None):
    conn = get_db()
    conn.execute(
        'INSERT INTO audit_log (action, actor_email, details, ip) VALUES (?, ?, ?, ?)',
        (action, actor_email, details, ip)
    )
    conn.commit()
    conn.close()

def get_audit_log(limit=100, offset=0):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Email Confirmation ─────────────────────────────────────

def generate_confirm_token(email):
    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute(
        'UPDATE users SET confirm_token = ? WHERE email = ?',
        (token, email)
    )
    conn.commit()
    conn.close()
    return token

def verify_confirm_token(token):
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM users WHERE confirm_token = ?',
        (token,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute(
        'UPDATE users SET confirmed = 1, confirm_token = NULL WHERE id = ?',
        (row['id'],)
    )
    conn.commit()
    conn.close()
    return dict(row)

def is_email_confirmed(email):
    conn = get_db()
    row = conn.execute(
        'SELECT confirmed FROM users WHERE email = ?', (email,)
    ).fetchone()
    conn.close()
    return row and row['confirmed'] == 1

# ── Settings ───────────────────────────────────────────────

def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        (key, str(value))
    )
    conn.commit()
    conn.close()


def get_affiliate_commission(code, default_barbearia=0.15, default_lavarapido=0.10):
    conn = get_db()
    row = conn.execute(
        'SELECT service, commission_rate FROM affiliates WHERE code = ?', (code,)
    ).fetchone()
    conn.close()
    if not row:
        return default_barbearia
    rate = row['commission_rate']
    if rate is not None and rate > 0:
        return rate
    service = row['service']
    return default_barbearia if service in ('barbearia', 'ambos') else default_lavarapido


def add_timeline_event(affiliate_code, event_type, description, amount=0):
    conn = get_db()
    conn.execute(
        'INSERT INTO timeline (affiliate_code, event_type, description, amount) VALUES (?, ?, ?, ?)',
        (affiliate_code, event_type, description, amount)
    )
    conn.commit()
    conn.close()


def get_timeline(affiliate_code, limit=50, offset=0):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM timeline WHERE affiliate_code = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
        (affiliate_code, limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
