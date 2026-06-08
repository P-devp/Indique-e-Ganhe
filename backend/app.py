import json
import logging
import os
import smtplib
import sys
import time
from datetime import datetime
from email.mime.text import MIMEText
from functools import wraps
from urllib.request import Request, urlopen

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    HAS_SENTRY = True
except ImportError:
    HAS_SENTRY = False

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.dirname(__file__))

from database import (
    LEVEL_THRESHOLDS,
    Database,
    add_timeline_event,
    generate_confirm_token,
    get_affiliate_commission,
    get_all_push_subscriptions,
    get_audit_log,
    get_push_subscriptions,
    get_setting,
    get_timeline,
    log_action,
    save_push_subscription,
    set_setting,
    verify_confirm_token,
)

ROOT = os.path.dirname(os.path.dirname(__file__))
app = Flask(__name__)

# ── Configuration ────────────────────────────────────────────

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'indiqueeganhe-dev-key-change-in-production')
app.config['MAX_LOGIN_ATTEMPTS'] = int(os.environ.get('MAX_LOGIN_ATTEMPTS', 5))
app.config['RATE_LIMIT_WINDOW'] = int(os.environ.get('RATE_LIMIT_WINDOW', 60))
app.config['MIN_PAYOUT'] = float(os.environ.get('MIN_PAYOUT', 10))
app.config['CORS_ORIGIN'] = os.environ.get('CORS_ORIGIN', '')
app.config['DISABLE_SEED'] = os.environ.get('DISABLE_SEED', '0') == '1'
app.config['PUBLIC_AFFILIATES'] = os.environ.get('PUBLIC_AFFILIATES', '1') == '1'
app.config['SMTP_HOST'] = os.environ.get('SMTP_HOST', '')
app.config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', 587))
app.config['SMTP_USER'] = os.environ.get('SMTP_USER', '')
app.config['SMTP_PASS'] = os.environ.get('SMTP_PASS', '')
app.config['SMTP_FROM'] = os.environ.get('SMTP_FROM', 'noreply@indiqueeganhe.com.br')
app.config['CONVERSION_WEBHOOK'] = os.environ.get('CONVERSION_WEBHOOK', '')
app.config['VAPID_PUBLIC_KEY'] = app.config.get('VAPID_PUBLIC_KEY', '')
app.config['VAPID_PRIVATE_KEY'] = app.config.get('VAPID_PRIVATE_KEY', '')

if HAS_SENTRY and os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(
        dsn=os.environ['SENTRY_DSN'],
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.1,
    )

db = Database()

# ── Email ────────────────────────────────────────────────────

def send_email(to, subject, body):
    if not app.config['SMTP_HOST']:
        log.info(f"[EMAIL SIMULADO] Para: {to} | Assunto: {subject} | {body[:100]}...")
        return
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = app.config['SMTP_FROM']
        msg['To'] = to
        with smtplib.SMTP(app.config['SMTP_HOST'], app.config['SMTP_PORT']) as s:
            s.starttls()
            s.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
            s.send_message(msg)
        log.info(f"Email enviado para {to}: {subject}")
    except Exception as e:
        log.error(f"Falha ao enviar email para {to}: {e}")


# ── Webhook ──────────────────────────────────────────────────

def fire_webhook(event, data):
    url = app.config['CONVERSION_WEBHOOK']
    if not url:
        return
    try:
        payload = json.dumps({'event': event, 'data': data}).encode()
        req = Request(url, data=payload, headers={'Content-Type': 'application/json'})
        urlopen(req, timeout=5)
        log.info(f"Webhook disparado: {event}")
    except Exception as e:
        log.error(f"Webhook falhou: {e}")

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'app.log'), delay=True)
    ]
)
log = logging.getLogger(__name__)

if app.config['SECRET_KEY'] in ('indiqueeganhe-dev-key-change-in-production', 'change-this-to-a-random-secret-key', ''):
    log.warning("SECRET_KEY padrão! Gere uma segura com: python -c \"import secrets; print(secrets.token_hex(32))\"")

# ── Rate Limiter ─────────────────────────────────────────────

_rate_store = {}

def reset_rate_limiter():
    _rate_store.clear()

def rate_limit(max_attempts=5, window=60):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = f"{request.remote_addr}:{request.path}"
            now = time.time()
            entries = [t for t in _rate_store.get(key, []) if now - t < window]
            if len(entries) >= max_attempts:
                log.warning(f"Rate limit hit for {key}")
                return jsonify({'error': 'too many requests, try again later'}), 429
            entries.append(now)
            _rate_store[key] = entries
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Security helpers ─────────────────────────────────────────

def get_token():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token()
        if not token:
            return jsonify({'error': 'token required'}), 401
        user = db.get_user_by_token(token)
        if not user:
            return jsonify({'error': 'invalid token'}), 401
        return f(user=user, *args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token()
        if not token:
            return jsonify({'error': 'token required'}), 401
        user = db.get_user_by_token(token)
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'admin required'}), 403
        return f(user=user, *args, **kwargs)
    return wrapper

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token()
        if not token:
            return jsonify({'error': 'token required'}), 401
        user = db.get_user_by_token(token)
        if not user:
            return jsonify({'error': 'invalid token'}), 401
        affiliate = db.get_affiliate(user['affiliate_code']) if user['affiliate_code'] else None
        if not affiliate:
            return jsonify({'error': 'affiliate not found'}), 404
        return f(auth_affiliate=affiliate, *args, **kwargs)
    return wrapper


def audit(action, details=None):
    token = get_token()
    user = db.get_user_by_token(token) if token else None
    email = user['email'] if user else None
    log_action(action, actor_email=email, details=details, ip=request.remote_addr)


# ── CORS & Security Headers ──────────────────────────────────

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    origin = request.headers.get('Origin', '')
    if app.config['CORS_ORIGIN'] == '*' or origin == app.config['CORS_ORIGIN']:
        response.headers['Access-Control-Allow-Origin'] = origin if origin else '*'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
    if request.method == 'OPTIONS':
        response.status_code = 204
    return response


# ── Request Logging ──────────────────────────────────────────

@app.before_request
def log_request():
    if request.path.startswith('/api/'):
        log.info(f"{request.method} {request.path}")


# ── Serve frontend files ─────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(ROOT, 'index.html')


@app.route('/<path:filename>')
def serve_frontend(filename):
    if filename.startswith('api/'):
        return jsonify({'error': 'not found'}), 404
    if not filename.endswith(('.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
        return jsonify({'error': 'forbidden'}), 403
    return send_from_directory(ROOT, filename)


# ── API: Auth ────────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
@rate_limit(max_attempts=20, window=300)
def api_register():
    data = request.get_json()
    if not data or 'name' not in data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'name, email and password required'}), 400
    import re
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', data.get('email', '')):
        return jsonify({'error': 'invalid email format'}), 400
    if len(data.get('password', '')) < 6:
        return jsonify({'error': 'password must be at least 6 characters'}), 400
    affiliate = db.create_affiliate(data)
    if not affiliate:
        return jsonify({'error': 'could not create affiliate'}), 500
    user = db.register_user(affiliate['code'], data['email'], data['password'])
    if user is None:
        return jsonify({'error': 'email already registered or invalid data'}), 409
    token = db.create_session(data['email'])
    confirm_token = generate_confirm_token(data['email'])
    send_email(data['email'], 'Confirme seu email - Indique e Ganhe',
        f'Olá {data["name"]},\n\nConfirme seu email clicando no link abaixo:\n\n'
        f'http://localhost:5000/confirm.html?token={confirm_token}\n\n'
        f'Seu código de afiliado: {affiliate["code"]}\n\n'
        f'Após confirmar, acesse: http://localhost:5000/dashboard.html')
    send_email(data['email'], 'Bem-vindo ao Indique e Ganhe!',
        f'Olá {data["name"]},\n\nSeu cadastro foi realizado com sucesso!\n'
        f'Código de afiliado: {affiliate["code"]}\n'
        f'Serviço: {data.get("service", "ambos")}\n\n'
        f'Acesse seu painel: http://localhost:5000/dashboard.html\n\n'
        f'Comece a compartilhar seu link e ganhe comissões!')
    log.info(f"Affiliate {affiliate['code']} registered ({data['email']})")
    audit('affiliate.register', f'{data["name"]} ({data["email"]})')
    add_timeline_event(affiliate['code'], 'register', f'Afiliado cadastrado: {data["name"]}', 0)
    return jsonify({'token': token, 'user': user, 'affiliate': affiliate}), 201


@app.route('/api/auth/login', methods=['POST'])
@rate_limit(max_attempts=app.config['MAX_LOGIN_ATTEMPTS'], window=app.config['RATE_LIMIT_WINDOW'])
def api_login():
    data = request.get_json()
    if not data or 'email' not in data or 'password' not in data:
        return jsonify({'error': 'email and password required'}), 400
    user = db.verify_login(data['email'], data['password'])
    if not user:
        log.warning(f"Failed login attempt for {data.get('email')}")
        return jsonify({'error': 'invalid credentials'}), 401
    token = db.create_session(data['email'])
    affiliate = db.get_affiliate(user['affiliate_code'])
    log.info(f"User {data['email']} logged in")
    return jsonify({'token': token, 'user': user, 'affiliate': affiliate})


@app.route('/api/auth/me', methods=['GET'])
@login_required
def api_me(user):
    affiliate = db.get_affiliate(user['affiliate_code'])
    return jsonify({'user': user, 'affiliate': affiliate})


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout(user):
    token = get_token()
    db.delete_session(token)
    return jsonify({'ok': True})


@app.route('/api/auth/sessions', methods=['GET'])
@login_required
def api_list_sessions(user):
    sessions = db.get_user_sessions(user['email'])
    return jsonify(sessions)


@app.route('/api/auth/sessions', methods=['DELETE'])
@login_required
def api_revoke_session(user):
    data = request.get_json()
    token = data.get('token') if data else None
    if not token:
        return jsonify({'error': 'token required'}), 400
    db.delete_session_by_token(token)
    return jsonify({'ok': True})


@app.route('/api/auth/sessions/current', methods=['DELETE'])
@login_required
def api_logout_all_sessions(user):
    token = get_token()
    db.delete_sessions_except(user['email'], token)
    return jsonify({'ok': True})


@app.route('/api/auth/account', methods=['DELETE'])
@login_required
def api_delete_account(user):
    email = user['email']
    db.delete_user_account(email)
    log.info(f"Account deleted: {email}")
    audit('account.delete', f'{email} deleted own account')
    return jsonify({'ok': True})


@app.route('/api/auth/forgot-password', methods=['POST'])
@rate_limit(max_attempts=5, window=300)
def api_forgot_password():
    data = request.get_json()
    email = data.get('email') if data else None
    if not email:
        return jsonify({'error': 'email required'}), 400
    token = db.generate_reset_token(email)
    if not token:
        return jsonify({'error': 'email not found'}), 404
    send_email(email, 'Recuperação de Senha - Indique e Ganhe',
        f'Olá,\n\nRecebemos uma solicitação de recuperação de senha.\n\n'
        f'Seu token de recuperação: {token}\n\n'
        f'Acesse: http://localhost:5000/reset-password.html\n\n'
        f'Se não foi você quem solicitou, ignore este email.')
    log.info(f"Password reset token generated for {email} ({token[:16]}...)")
    resp = {'message': 'reset link sent'}
    if app.debug:
        resp['token'] = token
    return jsonify(resp)


@app.route('/api/auth/reset-password', methods=['POST'])
def api_reset_password():
    data = request.get_json()
    if not data or 'token' not in data or 'password' not in data:
        return jsonify({'error': 'token and password required'}), 400
    if len(data['password']) < 6:
        return jsonify({'error': 'password must be at least 6 characters'}), 400
    result = db.reset_password(data['token'], data['password'])
    if not result:
        return jsonify({'error': 'invalid or expired token'}), 400
    log.info("Password reset successful")
    return jsonify({'message': 'password updated'})


@app.route('/api/auth/confirm', methods=['POST'])
def api_confirm_email():
    data = request.get_json()
    token = data.get('token') if data else None
    if not token:
        return jsonify({'error': 'token required'}), 400
    user = verify_confirm_token(token)
    if not user:
        return jsonify({'error': 'invalid or expired token'}), 400
    log.info(f"Email confirmed for {user['email']}")
    return jsonify({'message': 'email confirmed'})


@app.route('/api/auth/resend-confirm', methods=['POST'])
@login_required
def api_resend_confirm(user):
    email = user['email']
    token = generate_confirm_token(email)
    send_email(email, 'Confirme seu email - Indique e Ganhe',
        f'Olá,\n\nConfirme seu email clicando no link abaixo:\n\n'
        f'http://localhost:5000/confirm.html?token={token}\n\n'
        f'Se não foi você, ignore este email.')
    log.info(f"Confirmation email resent to {email}")
    return jsonify({'message': 'confirmation email sent'})


# ── API: Affiliates ──────────────────────────────────────────

@app.route('/api/affiliates', methods=['GET'])
def api_get_affiliates():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = max(1, min(per_page, 200))
    offset = (page - 1) * per_page
    affiliates = db.all_affiliates(limit=per_page, offset=offset)
    search = request.args.get('q', '').strip().lower()
    if search:
        affiliates = [a for a in affiliates if
            search in (a.get('name') or '').lower() or
            search in (a.get('email') or '').lower() or
            search in (a.get('code') or '').lower()]
    total = len(affiliates) if search else db.count_affiliates()
    if not app.config['PUBLIC_AFFILIATES']:
        return jsonify({'data': affiliates, 'page': page, 'per_page': per_page, 'total': total, 'pages': (total + per_page - 1) // per_page})
    token = get_token()
    user = db.get_user_by_token(token) if token else None
    if user:
        return jsonify({'data': affiliates, 'page': page, 'per_page': per_page, 'total': total, 'pages': (total + per_page - 1) // per_page})
    public = []
    for a in affiliates:
        public.append({
            'code': a['code'], 'name': a['name'],
            'service': a['service'], 'clicks': a['clicks'],
            'conversions': a['conversions'], 'earnings': a['earnings'],
            'level': a['level']
        })
    return jsonify({'data': public, 'page': page, 'per_page': per_page, 'total': total, 'pages': (total + per_page - 1) // per_page})


@app.route('/api/affiliates', methods=['POST'])
def api_create_affiliate():
    data = request.get_json()
    if not data or 'name' not in data or 'email' not in data:
        return jsonify({'error': 'name and email required'}), 400
    affiliate = db.create_affiliate(data)
    return jsonify(affiliate), 201


@app.route('/api/affiliates/<code>', methods=['GET'])
def api_get_affiliate(code):
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    return jsonify(affiliate)


@app.route('/api/affiliates/<code>', methods=['PUT'])
@login_required
def api_update_affiliate(user, code):
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    if user['role'] != 'admin' and user.get('affiliate_code') != code:
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    affiliate = db.update_affiliate(code, data)
    audit('affiliate.update', f'{code} by {user["email"]}')
    return jsonify(affiliate)


@app.route('/api/affiliates/<code>', methods=['DELETE'])
@admin_required
def api_delete_affiliate(user, code):
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    db.delete_affiliate(code)
    audit('affiliate.delete', f'{code} by {user["email"]}')
    return '', 204


@app.route('/api/admin/affiliates/<code>', methods=['PUT'])
@admin_required
def api_admin_update_affiliate(user, code):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    allowed = {'balance', 'level', 'earnings', 'clicks', 'conversions', 'name', 'email', 'phone', 'service'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'no valid fields'}), 400
    affiliate = db.update_affiliate(code, updates)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    audit('admin.update_affiliate', f'{code}: {json.dumps(updates)}')
    return jsonify(affiliate)


# ── API: Clicks & Conversions ────────────────────────────────

@app.route('/api/click', methods=['POST'])
def api_track_click():
    data = request.get_json()
    code = data.get('code') if data else None
    if not code:
        return jsonify({'error': 'code required'}), 400
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'affiliate not found'}), 404
    db.record_click(code)
    add_timeline_event(code, 'click', 'Clique registrado', 0)
    return jsonify({'status': 'ok'})


@app.route('/api/conversion', methods=['POST'])
def api_track_conversion():
    data = request.get_json()
    code = data.get('code') if data else None
    if not code:
        return jsonify({'error': 'code required'}), 400
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'affiliate not found'}), 404
    ticket = data.get('ticketValue', 50)
    barb_rate = float(get_setting('commission_barbearia', '0.15'))
    lava_rate = float(get_setting('commission_lavarapido', '0.10'))
    rate = get_affiliate_commission(code, barb_rate, lava_rate)
    earnings = ticket * rate
    db.record_conversion(code, earnings)
    add_timeline_event(code, 'conversion', f'Conversão registrada - Ticket: R$ {ticket:.2f}', earnings)
    fire_webhook('conversion', {'affiliate_code': code, 'ticket': ticket, 'earnings': earnings})
    return jsonify({'status': 'ok', 'earnings': earnings})


# ── API: Stats ───────────────────────────────────────────────

@app.route('/api/stats')
def api_stats():
    return jsonify(db.stats())


@app.route('/api/leaderboard')
def api_leaderboard():
    return jsonify(db.top_affiliates(10))


@app.route('/api/public/stats/<code>')
def api_public_stats(code):
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'name': affiliate['name'],
        'code': affiliate['code'],
        'service': affiliate['service'],
        'clicks': affiliate['clicks'],
        'conversions': affiliate['conversions'],
        'earnings': affiliate['earnings'],
        'level': affiliate['level'],
    })


# ── API: Levels ──────────────────────────────────────────────

@app.route('/api/levels/<code>')
def api_level_info(code):
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    return jsonify(db.get_level_info(affiliate['earnings']))


@app.route('/api/levels')
def api_all_levels():
    return jsonify([{
        'level': n,
        'threshold': t,
        'bonus': b
    } for n, t, b in LEVEL_THRESHOLDS])


# ── API: Goals ───────────────────────────────────────────────

@app.route('/api/goals/<code>', methods=['GET'])
def api_get_goals(code):
    now = datetime.now()
    month = request.args.get('month', now.month, type=int)
    year = request.args.get('year', now.year, type=int)
    goals = db.get_goals(code, month, year)
    if not goals:
        return jsonify(None)
    return jsonify(goals)


@app.route('/api/goals/<code>/progress', methods=['GET'])
def api_goal_progress(code):
    now = datetime.now()
    month = request.args.get('month', now.month, type=int)
    year = request.args.get('year', now.year, type=int)
    progress = db.get_goal_progress(code, month, year)
    if not progress:
        return jsonify({'clicks': {'current': 0, 'target': 0, 'progress': 0},
                        'conversions': {'current': 0, 'target': 0, 'progress': 0},
                        'earnings': {'current': 0, 'target': 0, 'progress': 0}})
    return jsonify(progress)


@app.route('/api/goals/<code>', methods=['POST'])
@admin_required
def api_set_goals(user, code):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    now = datetime.now()
    month = data.get('month', now.month)
    year = data.get('year', now.year)
    goals = db.set_goals(code, month, year,
                         clicks=data.get('clicks', 0),
                         conversions=data.get('conversions', 0),
                         earnings=data.get('earnings', 0))
    return jsonify(goals)


# ── API: Timeline ────────────────────────────────────────────

@app.route('/api/timeline/<code>', methods=['GET'])
@login_required
def api_get_timeline(user, code):
    if user['role'] != 'admin' and user.get('affiliate_code') != code:
        return jsonify({'error': 'forbidden'}), 403
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    return jsonify(get_timeline(code, limit=limit, offset=offset))


# ── API: Payouts ─────────────────────────────────────────────

@app.route('/api/payouts', methods=['POST'])
@login_required
def api_request_payout(user):
    if not user['affiliate_code']:
        return jsonify({'error': 'no affiliate code'}), 400
    data = request.get_json()
    amount = data.get('amount', 0) if data else 0
    if amount < app.config['MIN_PAYOUT']:
        return jsonify({'error': f'minimum payout is R${app.config["MIN_PAYOUT"]:.2f}'}), 400
    payout = db.request_payout(user['affiliate_code'], amount)
    if not payout:
        return jsonify({'error': 'insufficient balance or invalid affiliate'}), 400
    log.info(f"Payout requested: {user['affiliate_code']} R${amount:.2f}")
    add_timeline_event(user['affiliate_code'], 'payout', f'Saque solicitado: R$ {amount:.2f}', amount)
    send_push_notification(user['affiliate_code'], 'Pagamento Recebido!', f'Seu pagamento de R$ {amount:,.2f} foi processado com sucesso.', '/dashboard.html')
    return jsonify(payout), 201


@app.route('/api/payouts', methods=['GET'])
@login_required
def api_get_payouts(user):
    code = user['affiliate_code'] if user['role'] != 'admin' else request.args.get('code')
    status = request.args.get('status')
    payouts = db.get_payouts(code=code, status=status)
    return jsonify(payouts)


@app.route('/api/payouts/<int:payout_id>', methods=['PUT'])
@admin_required
def api_update_payout(user, payout_id):
    data = request.get_json()
    status = data.get('status') if data else None
    if status not in ('approved', 'paid', 'rejected'):
        return jsonify({'error': 'invalid status'}), 400
    payout = db.update_payout(payout_id, status, approved_by=user['email'])
    if not payout:
        return jsonify({'error': 'payout not found'}), 404
    aff = db.get_affiliate(payout['affiliate_code'])
    if aff:
        msg_status = {'approved': 'aprovado', 'paid': 'pago', 'rejected': 'rejeitado'}
        send_email(aff['email'], f'Saque #{payout_id} {msg_status.get(status, status)}',
            f'Olá {aff["name"]},\n\nSeu saque de R${payout["amount"]:.2f} '
            f'foi {msg_status.get(status, status)}.\n\n'
            f'Acesse seu painel: http://localhost:5000/dashboard.html')
    log.info(f"Payout #{payout_id} updated to {status} by {user['email']}")
    audit('payout.update', f'#{payout_id} -> {status}')
    return jsonify(payout)


@app.route('/api/payouts/stats')
@admin_required
def api_payout_stats(user):
    return jsonify(db.payout_stats())


# ── API: Export ──────────────────────────────────────────────

@app.route('/api/export/csv')
@admin_required
def api_export_csv(user):
    affiliates = db.all_affiliates()
    search = request.args.get('q', '').strip().lower()
    if search:
        affiliates = [a for a in affiliates if
            search in (a.get('name') or '').lower() or
            search in (a.get('email') or '').lower() or
            search in (a.get('code') or '').lower()]
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Nome', 'Email', 'Codigo', 'Servico', 'Data', 'Cliques', 'Conversoes', 'Ganhos', 'Nivel'])
    for a in affiliates:
        w.writerow([a['name'], a['email'], a['code'], a['service'],
                    a['registered_date'], a['clicks'], a['conversions'],
                    a['earnings'], a.get('level', 'bronze')])
    response = app.response_class(
        out.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=afiliados.csv'}
    )
    return response


@app.route('/api/import/csv', methods=['POST'])
@admin_required
def api_import_csv(user):
    if 'file' not in request.files:
        return jsonify({'error': 'file required'}), 400
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'must be a CSV file'}), 400
    import csv, io
    content = file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    errors = []
    for i, row in enumerate(reader, start=1):
        name = (row.get('nome') or row.get('name') or '').strip()
        email = (row.get('email') or '').strip()
        if not name or not email:
            errors.append(f'Linha {i}: nome e email obrigatórios')
            continue
        aff = db.create_affiliate({
            'name': name,
            'email': email,
            'phone': (row.get('phone') or row.get('telefone') or '').strip(),
            'service': (row.get('service') or row.get('servico') or 'ambos').strip(),
        })
        if aff:
            imported += 1
        else:
            errors.append(f'Linha {i}: erro ao criar afiliado')
    audit('affiliate.import_csv', f'{imported} imported, {len(errors)} errors')
    return jsonify({'imported': imported, 'errors': errors})


@app.route('/api/export/pdf/<code>', methods=['GET'])
@login_required
def api_export_pdf(user, code):
    if user['role'] != 'admin' and user.get('affiliate_code') != code:
        return jsonify({'error': 'forbidden'}), 403
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib import colors
    except ImportError:
        return jsonify({'error': 'PDF generation not available (install reportlab)'}), 501

    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont('Helvetica-Bold', 20)
    c.drawString(50, height - 50, 'Indique e Ganhe')
    c.setFont('Helvetica', 10)
    c.drawString(50, height - 70, 'Relatório de Afiliado')
    c.setStrokeColor(colors.HexColor('#000080'))
    c.line(50, height - 75, width - 50, height - 75)

    y = height - 100
    c.setFont('Helvetica-Bold', 12)
    c.drawString(50, y, f'Afiliado: {affiliate["name"]}')
    y -= 20
    c.setFont('Helvetica', 10)
    c.drawString(50, y, f'Código: {affiliate["code"]}')
    y -= 15
    c.drawString(50, y, f'Email: {affiliate["email"]}')
    y -= 15
    c.drawString(50, y, f'Serviço: {affiliate["service"]}')
    y -= 15
    c.drawString(50, y, f'Data de cadastro: {affiliate["registered_date"]}')

    y -= 30
    c.setFont('Helvetica-Bold', 12)
    c.drawString(50, y, 'Estatísticas')
    y -= 20
    c.setFont('Helvetica', 10)
    c.drawString(50, y, f'Cliques: {affiliate["clicks"]}')
    y -= 15
    c.drawString(50, y, f'Conversões: {affiliate["conversions"]}')
    y -= 15
    c.drawString(50, y, f'Ganhos totais: R$ {affiliate["earnings"]:.2f}')
    y -= 15
    c.drawString(50, y, f'Saldo disponível: R$ {affiliate["balance"]:.2f}')
    y -= 15
    c.drawString(50, y, f'Nível: {affiliate["level"]}')

    c.setFont('Helvetica', 8)
    c.setFillColor(colors.grey)
    c.drawString(50, 30, f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}')

    c.showPage()
    c.save()
    buf.seek(0)

    response = app.response_class(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=afiliado_{code}.pdf'}
    )
    return response


# ── Seed demo data ───────────────────────────────────────────

@app.route('/api/seed', methods=['POST'])
@admin_required
def api_seed(user):
    if app.config['DISABLE_SEED']:
        return jsonify({'error': 'seed disabled'}), 403
    demo = [
        {'name': 'Joao Silva', 'email': 'joao@email.com', 'phone': '11 99999-8888', 'service': 'barbearia'},
        {'name': 'Maria Santos', 'email': 'maria@email.com', 'phone': '11 99999-7777', 'service': 'lava-rapido'},
        {'name': 'Carlos Oliveira', 'email': 'carlos@email.com', 'phone': '11 99999-6666', 'service': 'ambos'},
    ]
    demo_emails = {'joao@email.com', 'maria@email.com', 'carlos@email.com'}
    existing = db.all_affiliates()
    if any(a.get('email') in demo_emails for a in existing):
        return jsonify({'message': 'data already exists'}), 200
    created = []
    for a in demo:
        aff = db.create_affiliate(a)
        created.append(aff)
    return jsonify({'message': 'demo data created', 'count': len(created)}), 201


# ── API: Audit Log ─────────────────────────────────────────

@app.route('/api/admin/audit-log', methods=['GET'])
@admin_required
def api_audit_log(user):
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    return jsonify(get_audit_log(limit=min(limit, 500), offset=offset))


# ── API: Settings ──────────────────────────────────────────

@app.route('/api/admin/settings', methods=['GET'])
@admin_required
def api_get_settings(user):
    return jsonify({
        'commission_barbearia': get_setting('commission_barbearia', '0.15'),
        'commission_lavarapido': get_setting('commission_lavarapido', '0.10'),
    })


@app.route('/api/admin/settings', methods=['PUT'])
@admin_required
def api_update_settings(user):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    allowed = {'commission_barbearia', 'commission_lavarapido'}
    for key, value in data.items():
        if key in allowed:
            try:
                v = float(value)
                if v < 0 or v > 1:
                    return jsonify({'error': f'{key}: value must be between 0 and 1'}), 400
                set_setting(key, str(v))
                audit('settings.update', f'{key} = {v}')
            except (ValueError, TypeError):
                return jsonify({'error': f'{key}: invalid value'}), 400
    return jsonify({'message': 'settings updated'})


@app.route('/api/admin/affiliates/<code>/commission', methods=['PUT'])
@admin_required
def api_set_commission(user, code):
    data = request.get_json()
    if not data or 'rate' not in data:
        return jsonify({'error': 'rate required'}), 400
    try:
        rate = float(data['rate'])
        if rate < 0 or rate > 1:
            return jsonify({'error': 'rate must be between 0 and 1'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid rate'}), 400
    db.update_affiliate(code, {'commission_rate': rate})
    audit('affiliate.commission', f'{code}: rate={rate}')
    return jsonify({'message': 'commission updated'})


@app.route('/api/admin/notify-inactive', methods=['POST'])
@admin_required
def api_notify_inactive(user):
    affiliates = db.all_affiliates()
    sent = 0
    for aff in affiliates:
        if aff['clicks'] == 0 and aff['conversions'] == 0:
            send_email(aff['email'], 'Que tal indicar amigos? - Indique e Ganhe',
                f'Olá {aff["name"]},\n\n'
                f'Notamos que você ainda não fez nenhuma indicação.\n\n'
                f'Compartilhe seu link: http://localhost:5000/click.html?code={aff["code"]}\n\n'
                f'Ganhe comissões por cada cliente que trouxer!')
            sent += 1
    audit('notify.inactive', f'{sent} emails sent')
    return jsonify({'sent': sent})


@app.route('/api/admin/send-reports', methods=['POST'])
@admin_required
def api_send_reports(user):
    affiliates = db.all_affiliates()
    sent = 0
    for aff in affiliates:
        body = (
            f'Olá {aff["name"]},\n\n'
            f'Seu resumo mensal:\n'
            f'├ Cliques: {aff["clicks"]}\n'
            f'├ Conversões: {aff["conversions"]}\n'
            f'├ Ganhos: R$ {aff["earnings"]:.2f}\n'
            f'├ Saldo: R$ {aff["balance"]:.2f}\n'
            f'└ Nível: {aff["level"]}\n\n'
            f'Compartilhe seu link: http://localhost:5000/click.html?code={aff["code"]}\n\n'
            f'Continue indicando e ganhando!'
        )
        send_email(aff['email'], 'Resumo Mensal - Indique e Ganhe', body)
        sent += 1
    audit('report.periodic', f'Monthly report sent to {sent} affiliates')
    return jsonify({'sent': sent})


# ── API: Push Notifications ────────────────────────────────────

@app.route('/api/push/subscribe', methods=['POST'])
@require_auth
def push_subscribe(auth_affiliate):
    try:
        data = request.get_json()
        if not data or 'endpoint' not in data:
            return jsonify({'error': 'endpoint is required'}), 400
        endpoint = data['endpoint']
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth_key = keys.get('auth', '')
        save_push_subscription(auth_affiliate['code'], endpoint, p256dh, auth_key)
        return jsonify({'success': True}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Push Notification Helpers ─────────────────────────────────

def send_push_notification(affiliate_code, title, body, url=None):
    """
    Send a push notification to a specific affiliate using all their subscribed devices.
    Requires pywebpush: pip install pywebpush
    """
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return

    VAPID_PUBLIC_KEY = app.config.get('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = app.config.get('VAPID_PRIVATE_KEY', '')
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return

    subscriptions = get_push_subscriptions(affiliate_code)
    for endpoint, p256dh, auth in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': endpoint,
                    'keys': {'p256dh': p256dh, 'auth': auth}
                },
                data=json.dumps({'title': title, 'body': body, 'url': url or ''}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={
                    'sub': 'mailto:admin@indiqueeganhe.com.br'
                }
            )
        except WebPushException:
            continue
        except Exception:
            continue


def broadcast_push_notification(title, body, url=None):
    """Send a push notification to all subscribed affiliates."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return

    VAPID_PUBLIC_KEY = app.config.get('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = app.config.get('VAPID_PRIVATE_KEY', '')
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return

    subscriptions = get_all_push_subscriptions()
    for endpoint, p256dh, auth in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': endpoint,
                    'keys': {'p256dh': p256dh, 'auth': auth}
                },
                data=json.dumps({'title': title, 'body': body, 'url': url or ''}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={
                    'sub': 'mailto:admin@indiqueeganhe.com.br'
                }
            )
        except WebPushException:
            continue
        except Exception:
            continue


# ── Run ──────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log.info(f'Indique e Ganhe rodando em http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=(os.environ.get('FLASK_DEBUG', '0') == '1'))
