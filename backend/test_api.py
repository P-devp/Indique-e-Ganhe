import sys, os, json, tempfile, pytest

sys.path.insert(0, os.path.dirname(__file__))

# Use a temporary file for test database (in-memory doesn't work with SQLite)
import database
database.DB_PATH = os.path.join(tempfile.gettempdir(), 'retro_test.db')

# Clean before import
if os.path.exists(database.DB_PATH):
    os.remove(database.DB_PATH)

from app import app

# Enable debug mode so forgot-password returns tokens in tests
app.debug = True
app.config['TESTING'] = True


def _register_user(client, email='user@t.com', password='123456'):
    """Register a user and return {token, code}."""
    rv = client.post('/api/auth/register',
                     data=json.dumps({'name': 'Test User', 'email': email, 'password': password}),
                     content_type='application/json')
    result = rv.get_json()
    return {'token': result['token'], 'code': result['affiliate']['code']}


def _register_admin(client, email='admin@t.com', password='123456'):
    """Register a user, promote to admin, return token."""
    import sqlite3
    import database as db_mod
    result = _register_user(client, email, password)
    conn = sqlite3.connect(db_mod.DB_PATH)
    conn.execute('UPDATE users SET role = ? WHERE email = ?', ('admin', email))
    conn.commit()
    conn.close()
    return result['token']


@pytest.fixture(autouse=True)
def reset_db():
    """Recreate database before each test."""
    import database as db_mod
    from database import Database
    # Remove the db file so init_db creates a fresh one
    if os.path.exists(db_mod.DB_PATH):
        try:
            os.remove(db_mod.DB_PATH)
        except PermissionError:
            pass
    import app as app_module
    app_module.db = Database()
    yield


# ── Tests ─────────────────────────────────────────────────

class TestAffiliatesAPI:

    def test_list_empty(self, client):
        rv = client.get('/api/affiliates')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['data'] == []
        assert data['total'] == 0
        assert data['page'] == 1

    def test_create_affiliate(self, client):
        data = {'name': 'Joao Silva', 'email': 'joao@email.com', 'service': 'barbearia'}
        rv = client.post('/api/affiliates',
                         data=json.dumps(data),
                         content_type='application/json')
        assert rv.status_code == 201
        result = rv.get_json()
        assert result['name'] == 'Joao Silva'
        assert result['email'] == 'joao@email.com'
        assert result['service'] == 'barbearia'
        assert result['code'].startswith('RETRO-')
        assert result['clicks'] == 0
        assert result['conversions'] == 0
        assert result['earnings'] == 0.0

    def test_create_missing_fields(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Sem Email'}),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_get_affiliate_by_code(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Teste', 'email': 't@t.com'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.get(f'/api/affiliates/{code}')
        assert rv.status_code == 200
        assert rv.get_json()['name'] == 'Teste'

    def test_get_affiliate_not_found(self, client):
        rv = client.get('/api/affiliates/INVALID')
        assert rv.status_code == 404

    def test_update_affiliate(self, client):
        user = _register_user(client, 'update@t.com')
        token = user['token']
        code = user['code']
        rv = client.put(f'/api/affiliates/{code}',
                        data=json.dumps({'name': 'Atualizado', 'clicks': 5}),
                        content_type='application/json',
                        headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200
        result = rv.get_json()
        assert result['name'] == 'Atualizado'
        assert result['clicks'] == 5

    def test_delete_affiliate(self, client):
        token = _register_admin(client, 'deladmin@t.com')
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Delete', 'email': 'del@d.com'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.delete(f'/api/affiliates/{code}',
                           headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 204
        rv = client.get(f'/api/affiliates/{code}')
        assert rv.status_code == 404

    def test_delete_not_found(self, client):
        token = _register_admin(client, 'deladmin2@t.com')
        rv = client.delete('/api/affiliates/INVALID',
                           headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 404


class TestClickTracking:

    def test_record_click(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Click', 'email': 'c@c.com', 'service': 'barbearia'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.post('/api/click',
                         data=json.dumps({'code': code}),
                         content_type='application/json')
        assert rv.status_code == 200
        rv = client.get(f'/api/affiliates/{code}')
        assert rv.get_json()['clicks'] == 1

    def test_click_invalid_code(self, client):
        rv = client.post('/api/click',
                         data=json.dumps({'code': 'INVALID'}),
                         content_type='application/json')
        assert rv.status_code == 404

    def test_click_missing_code(self, client):
        rv = client.post('/api/click',
                         data=json.dumps({}),
                         content_type='application/json')
        assert rv.status_code == 400


class TestConversions:

    def test_record_conversion_barbearia(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Conv', 'email': 'conv@t.com', 'service': 'barbearia'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.post('/api/conversion',
                         data=json.dumps({'code': code, 'ticketValue': 80}),
                         content_type='application/json')
        assert rv.status_code == 200
        assert rv.get_json()['earnings'] == 12.0
        rv = client.get(f'/api/affiliates/{code}')
        data = rv.get_json()
        assert data['conversions'] == 1
        assert data['earnings'] == 12.0

    def test_record_conversion_lava_rapido(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Lava', 'email': 'lava@t.com', 'service': 'lava-rapido'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.post('/api/conversion',
                         data=json.dumps({'code': code, 'ticketValue': 50}),
                         content_type='application/json')
        assert rv.status_code == 200
        assert rv.get_json()['earnings'] == 5.0


class TestStats:

    def test_empty_stats(self, client):
        rv = client.get('/api/stats')
        assert rv.status_code == 200
        stats = rv.get_json()
        assert stats['total'] == 0

    def test_stats_with_data(self, client):
        client.post('/api/affiliates',
                    data=json.dumps({'name': 'A', 'email': 'a@a.com'}),
                    content_type='application/json')
        client.post('/api/affiliates',
                    data=json.dumps({'name': 'B', 'email': 'b@b.com'}),
                    content_type='application/json')
        rv = client.get('/api/stats')
        assert rv.get_json()['total'] == 2

    def test_leaderboard(self, client):
        client.post('/api/affiliates',
                    data=json.dumps({'name': 'A', 'email': 'a@a.com'}),
                    content_type='application/json')
        rv = client.get('/api/leaderboard')
        assert len(rv.get_json()) == 1


class TestSeed:

    def test_seed_creates_data(self, client):
        token = _register_admin(client, 'seedadmin@t.com')
        rv = client.post('/api/seed',
                         headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 201
        assert rv.get_json()['count'] == 3

    def test_seed_idempotent(self, client):
        token = _register_admin(client, 'seedadmin2@t.com')
        client.post('/api/seed', headers={'Authorization': f'Bearer {token}'})
        rv = client.post('/api/seed', headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200
        assert rv.get_json()['message'] == 'data already exists'


class TestFrontendServing:

    def test_index_served(self, client):
        rv = client.get('/')
        assert rv.status_code == 200
        assert b'Retro' in rv.data

    def test_css_served(self, client):
        rv = client.get('/styles.css')
        assert rv.status_code == 200

    def test_js_served(self, client):
        rv = client.get('/src/storage.js')
        assert rv.status_code == 200


class TestAuth:

    def test_register(self, client):
        data = {'name': 'Novo', 'email': 'novo@email.com', 'password': '123456', 'service': 'barbearia'}
        rv = client.post('/api/auth/register',
                         data=json.dumps(data),
                         content_type='application/json')
        assert rv.status_code == 201
        result = rv.get_json()
        assert 'token' in result
        assert result['affiliate']['name'] == 'Novo'

    def test_register_duplicate_email(self, client):
        data = {'name': 'A', 'email': 'a@a.com', 'password': '123456'}
        client.post('/api/auth/register', data=json.dumps(data), content_type='application/json')
        rv = client.post('/api/auth/register', data=json.dumps(data), content_type='application/json')
        assert rv.status_code == 409

    def test_register_missing_fields(self, client):
        rv = client.post('/api/auth/register',
                         data=json.dumps({'name': 'SemSenha'}),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_login(self, client):
        client.post('/api/auth/register',
                    data=json.dumps({'name': 'Log', 'email': 'log@t.com', 'password': '123456'}),
                    content_type='application/json')
        rv = client.post('/api/auth/login',
                         data=json.dumps({'email': 'log@t.com', 'password': '123456'}),
                         content_type='application/json')
        assert rv.status_code == 200
        assert 'token' in rv.get_json()

    def test_login_wrong_password(self, client):
        client.post('/api/auth/register',
                    data=json.dumps({'name': 'Fail', 'email': 'fail@t.com', 'password': '123456'}),
                    content_type='application/json')
        rv = client.post('/api/auth/login',
                         data=json.dumps({'email': 'fail@t.com', 'password': 'wrong'}),
                         content_type='application/json')
        assert rv.status_code == 401

    def test_login_missing_fields(self, client):
        rv = client.post('/api/auth/login',
                         data=json.dumps({'email': 'x@x.com'}),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_me_authenticated(self, client):
        rv = client.post('/api/auth/register',
                         data=json.dumps({'name': 'Me', 'email': 'me@t.com', 'password': '123456'}),
                         content_type='application/json')
        token = rv.get_json()['token']
        rv = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200
        assert rv.get_json()['user']['email'] == 'me@t.com'

    def test_me_no_token(self, client):
        rv = client.get('/api/auth/me')
        assert rv.status_code == 401

    def test_me_invalid_token(self, client):
        rv = client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid'})
        assert rv.status_code == 401

    def test_logout(self, client):
        rv = client.post('/api/auth/register',
                         data=json.dumps({'name': 'Out', 'email': 'out@t.com', 'password': '123456'}),
                         content_type='application/json')
        token = rv.get_json()['token']
        rv = client.post('/api/auth/logout', headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200
        rv = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 401

    def test_admin_create_goals(self, client):
        # Register an affiliate
        rv = client.post('/api/auth/register',
                         data=json.dumps({'name': 'Goal', 'email': 'goal@t.com', 'password': '123456'}),
                         content_type='application/json')
        code = rv.get_json()['affiliate']['code']
        # Only admin can set goals; test with no auth
        rv = client.post(f'/api/goals/{code}',
                         data=json.dumps({'clicks': 100, 'conversions': 10, 'earnings': 500}),
                         content_type='application/json')
        assert rv.status_code == 401


class TestLevels:

    def test_level_info(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Level', 'email': 'level@t.com'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.get(f'/api/levels/{code}')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['current'] == 'bronze'
        assert data['bonus'] == 0.0

    def test_level_not_found(self, client):
        rv = client.get('/api/levels/INVALID')
        assert rv.status_code == 404

    def test_level_progression(self, client):
        user = _register_user(client, 'prog@t.com')
        token = user['token']
        code = user['code']
        # Add earnings to reach prata
        rv = client.put(f'/api/affiliates/{code}',
                        data=json.dumps({'earnings': 150}),
                        content_type='application/json',
                        headers={'Authorization': f'Bearer {token}'})
        rv = client.get(f'/api/levels/{code}')
        data = rv.get_json()
        assert data['current'] == 'prata'
        assert data['bonus'] == 0.02

    def test_level_all(self, client):
        rv = client.get('/api/levels')
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data) >= 4
        assert data[0]['level'] == 'bronze'


class TestGoals:

    def test_goal_progress_empty(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'G', 'email': 'g@t.com'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.get(f'/api/goals/{code}/progress')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['clicks']['current'] == 0

    def test_goal_get_empty(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'G2', 'email': 'g2@t.com'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.get(f'/api/goals/{code}')
        assert rv.status_code == 200
        assert rv.get_json() is None

    def test_create_affiliate_has_level(self, client):
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'LevelTest', 'email': 'lt@t.com'}),
                         content_type='application/json')
        assert rv.status_code == 201
        assert rv.get_json()['level'] == 'bronze'


class TestPayouts:

    def _register(self, client, email):
        rv = client.post('/api/auth/register',
                         data=json.dumps({'name': 'Payout', 'email': email, 'password': '123456', 'service': 'barbearia'}),
                         content_type='application/json')
        return rv.get_json()

    def test_withdraw_no_auth(self, client):
        rv = client.post('/api/payouts',
                         data=json.dumps({'amount': 50}),
                         content_type='application/json')
        assert rv.status_code == 401

    def test_withdraw_insufficient(self, client):
        data = self._register(client, 'low@t.com')
        token = data['token']
        rv = client.post('/api/payouts',
                         data=json.dumps({'amount': 9999}),
                         content_type='application/json',
                         headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 400

    def test_withdraw_below_minimum(self, client):
        data = self._register(client, 'min@t.com')
        token = data['token']
        rv = client.post('/api/payouts',
                         data=json.dumps({'amount': 1}),
                         content_type='application/json',
                         headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 400

    def test_withdraw_success(self, client):
        # Register and add balance
        data = self._register(client, 'bal@t.com')
        token = data['token']
        code = data['affiliate']['code']
        client.put(f'/api/affiliates/{code}',
                   data=json.dumps({'balance': 100}),
                   content_type='application/json',
                   headers={'Authorization': f'Bearer {token}'})
        rv = client.post('/api/payouts',
                         data=json.dumps({'amount': 50}),
                         content_type='application/json',
                         headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 201
        result = rv.get_json()
        assert result['amount'] == 50
        assert result['status'] == 'pending'

    def test_get_payouts_auth(self, client):
        data = self._register(client, 'list@t.com')
        token = data['token']
        code = data['affiliate']['code']
        client.put(f'/api/affiliates/{code}',
                   data=json.dumps({'balance': 100}),
                   content_type='application/json',
                   headers={'Authorization': f'Bearer {token}'})
        client.post('/api/payouts',
                    data=json.dumps({'amount': 30}),
                    content_type='application/json',
                    headers={'Authorization': f'Bearer {token}'})
        rv = client.get('/api/payouts',
                        headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200
        payouts = rv.get_json()
        assert len(payouts) >= 1

    def test_get_payouts_no_auth(self, client):
        rv = client.get('/api/payouts')
        assert rv.status_code == 401


class TestExport:

    def test_export_csv(self, client):
        token = _register_admin(client, 'export@t.com')
        rv = client.get('/api/export/csv',
                        headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 200
        assert 'text/csv' in rv.content_type
        assert 'Nome' in rv.get_data(as_text=True)


class TestRegistrationValidation:

    def test_register_invalid_email(self, client):
        data = {'name': 'Bad', 'email': 'invalido', 'password': '123456'}
        rv = client.post('/api/auth/register',
                         data=json.dumps(data),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_register_short_password(self, client):
        data = {'name': 'Short', 'email': 'short@t.com', 'password': '123'}
        rv = client.post('/api/auth/register',
                         data=json.dumps(data),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_register_user_returned(self, client):
        data = {'name': 'Full', 'email': 'full@t.com', 'password': '123456'}
        rv = client.post('/api/auth/register',
                         data=json.dumps(data),
                         content_type='application/json')
        assert rv.status_code == 201
        result = rv.get_json()
        assert 'user' in result
        assert result['user']['email'] == 'full@t.com'


class TestPasswordReset:

    def test_forgot_password_nonexistent(self, client):
        rv = client.post('/api/auth/forgot-password',
                         data=json.dumps({'email': 'nobody@t.com'}),
                         content_type='application/json')
        assert rv.status_code == 404

    def test_forgot_password_generates_token(self, client):
        client.post('/api/auth/register',
                    data=json.dumps({'name': 'Reset', 'email': 'reset@t.com', 'password': '123456'}),
                    content_type='application/json')
        rv = client.post('/api/auth/forgot-password',
                         data=json.dumps({'email': 'reset@t.com'}),
                         content_type='application/json')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'token' in data
        assert len(data['token']) > 10

    def test_reset_password_full_flow(self, client):
        client.post('/api/auth/register',
                    data=json.dumps({'name': 'Flow', 'email': 'flow@t.com', 'password': '123456'}),
                    content_type='application/json')
        rv = client.post('/api/auth/forgot-password',
                         data=json.dumps({'email': 'flow@t.com'}),
                         content_type='application/json')
        token = rv.get_json()['token']
        rv = client.post('/api/auth/reset-password',
                         data=json.dumps({'token': token, 'password': 'nova456'}),
                         content_type='application/json')
        assert rv.status_code == 200
        rv = client.post('/api/auth/login',
                         data=json.dumps({'email': 'flow@t.com', 'password': 'nova456'}),
                         content_type='application/json')
        assert rv.status_code == 200

    def test_reset_password_invalid_token(self, client):
        rv = client.post('/api/auth/reset-password',
                         data=json.dumps({'token': 'invalid', 'password': 'nova456'}),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_reset_password_short_token(self, client):
        rv = client.post('/api/auth/reset-password',
                         data=json.dumps({'token': 'invalid', 'password': '123'}),
                         content_type='application/json')
        assert rv.status_code == 400


class TestAdminEndpoints:

    def _register_admin(self, client):
        data = {'name': 'Admin', 'email': 'admin@test.com', 'password': '123456'}
        rv = client.post('/api/auth/register',
                         data=json.dumps(data),
                         content_type='application/json')
        result = rv.get_json()
        import sqlite3, database as db_mod
        conn = sqlite3.connect(db_mod.DB_PATH)
        conn.execute('UPDATE users SET role = ? WHERE email = ?', ('admin', 'admin@test.com'))
        conn.commit()
        conn.close()
        return result['token']

    def test_admin_update_affiliate_balance(self, client):
        admin_token = self._register_admin(client)
        rv = client.post('/api/affiliates',
                         data=json.dumps({'name': 'Test', 'email': 'test@t.com'}),
                         content_type='application/json')
        code = rv.get_json()['code']
        rv = client.put(f'/api/admin/affiliates/{code}',
                        data=json.dumps({'balance': 500, 'earnings': 500}),
                        content_type='application/json',
                        headers={'Authorization': f'Bearer {admin_token}'})
        assert rv.status_code == 200
        result = rv.get_json()
        assert result['balance'] == 500
        assert result['level'] == 'ouro'

    def test_admin_update_no_auth(self, client):
        rv = client.put('/api/admin/affiliates/somecode',
                        data=json.dumps({'balance': 100}),
                        content_type='application/json')
        assert rv.status_code == 401

    def test_admin_update_non_admin(self, client):
        rv = client.post('/api/auth/register',
                         data=json.dumps({'name': 'User', 'email': 'user@t.com', 'password': '123456'}),
                         content_type='application/json')
        token = rv.get_json()['token']
        rv = client.put('/api/admin/affiliates/somecode',
                        data=json.dumps({'balance': 100}),
                        content_type='application/json',
                        headers={'Authorization': f'Bearer {token}'})
        assert rv.status_code == 403

    def test_frontend_extension_blocked(self, client):
        rv = client.get('/backend/database.py')
        assert rv.status_code == 403
