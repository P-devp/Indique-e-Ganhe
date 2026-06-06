import os
import sys
import time
import json
import smtplib
import logging
from datetime import datetime
from functools import wraps
from urllib.request import Request, urlopen
from email.mime.text import MIMEText
from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.dirname(__file__))
from database import Database, LEVEL_THRESHOLDS

ROOT = os.path.dirname(os.path.dirname(__file__))
app = Flask(__name__)

# ── Configuration ────────────────────────────────────────────

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'retro-dev-key-change-in-production')
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
app.config['SMTP_FROM'] = os.environ.get('SMTP_FROM', 'noreply@retroafiliados.com')
app.config['CONVERSION_WEBHOOK'] = os.environ.get('CONVERSION_WEBHOOK', '')

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

if app.config['SECRET_KEY'] in ('retro-dev-key-change-in-production', 'change-this-to-a-random-secret-key', ''):
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
    send_email(data['email'], 'Bem-vindo ao Indique e Ganhe!',
        f'Olá {data["name"]},\n\nSeu cadastro foi realizado com sucesso!\n'
        f'Código de afiliado: {affiliate["code"]}\n'
        f'Serviço: {data.get("service", "ambos")}\n\n'
        f'Acesse seu painel: http://localhost:5000/dashboard.html\n\n'
        f'Comece a compartilhar seu link e ganhe comissões!')
    log.info(f"Affiliate {affiliate['code']} registered ({data['email']})")
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
    log.info(f"Password reset successful")
    return jsonify({'message': 'password updated'})


# ── API: Affiliates ──────────────────────────────────────────

@app.route('/api/affiliates', methods=['GET'])
def api_get_affiliates():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = max(1, min(per_page, 200))
    offset = (page - 1) * per_page
    affiliates = db.all_affiliates(limit=per_page, offset=offset)
    total = db.count_affiliates()
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
    return jsonify(affiliate)


@app.route('/api/affiliates/<code>', methods=['DELETE'])
@admin_required
def api_delete_affiliate(user, code):
    affiliate = db.get_affiliate(code)
    if not affiliate:
        return jsonify({'error': 'not found'}), 404
    db.delete_affiliate(code)
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
    rate = 0.15 if affiliate['service'] in ('barbearia', 'ambos') else 0.10
    earnings = ticket * rate
    db.record_conversion(code, earnings)
    fire_webhook('conversion', {'affiliate_code': code, 'ticket': ticket, 'earnings': earnings})
    return jsonify({'status': 'ok', 'earnings': earnings})


# ── API: Stats ───────────────────────────────────────────────

@app.route('/api/stats')
def api_stats():
    return jsonify(db.stats())


@app.route('/api/leaderboard')
def api_leaderboard():
    return jsonify(db.top_affiliates(10))


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
    import csv, io
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


# ── Run ──────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log.info(f'Indique e Ganhe rodando em http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=(os.environ.get('FLASK_DEBUG', '0') == '1'))
