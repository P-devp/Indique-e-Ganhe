"""Integration test fixtures for Playwright."""
import os
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

@pytest.fixture(scope='session')
def server_url():
    """Start the Flask server in a background thread and return its URL."""
    import logging

    from app import app
    logging.disable(logging.CRITICAL)
    app.config['TESTING'] = True
    app.config['DISABLE_SEED'] = True
    from database import DB_PATH, Database
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = Database()
    app.config['db'] = db
    port = 5199
    url = f'http://localhost:{port}'
    t = threading.Thread(target=app.run, kwargs={'port': port, 'debug': False, 'use_reloader': False}, daemon=True)
    t.start()
    for _ in range(20):
        try:
            urlopen(url, timeout=1)
            break
        except URLError:
            time.sleep(0.5)
    else:
        raise RuntimeError('Server did not start')
    yield url
    import signal
    os.kill(os.getpid(), signal.SIGTERM)


@pytest.fixture(scope='session')
def browser_context(playwright, server_url):
    """Create a browser context."""
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1280, 'height': 720},
        locale='pt-BR'
    )
    yield context
    context.close()
    browser.close()


@pytest.mark.integration
class TestLandingPage:
    """Test the landing page loads correctly."""

    def test_index_loads(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(server_url)
        assert 'Indique' in page.title()
        heading = page.locator('h1').first
        assert heading.is_visible()
        page.close()

    def test_nav_links_visible(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(server_url)
        links = page.locator('nav a')
        count = links.count()
        assert count > 0
        texts = [links.nth(i).inner_text() for i in range(count)]
        assert any('Início' in t for t in texts)
        page.close()

    def test_signup_link_navigates(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(server_url)
        signup_link = page.locator('nav a:has-text("Cadastro")')
        if signup_link.count() > 0:
            signup_link.click()
            page.wait_for_url('**/signup.html')
            assert 'signup' in page.url
        page.close()


@pytest.mark.integration
class TestAuthFlow:
    """Test registration and login flows."""

    def test_registration_form(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(f'{server_url}/signup.html')
        page.wait_for_load_state('networkidle')
        page.fill('input[name="name"]', 'Test User')
        page.fill('input[name="email"]', 'test-integration@example.com')
        page.fill('input[name="password"]', 'test123456')
        page.fill('input[name="phone"]', '11 99999-0000')
        page.select_option('select[name="service"]', 'barbearia')
        page.locator('button[type="submit"]').click()
        page.wait_for_timeout(2000)
        body = page.locator('body').inner_text()
        assert 'sucesso' in body.lower() or 'dashboard' in page.url or 'token' in body.lower()
        page.close()

    def test_login_form(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(f'{server_url}/login.html')
        page.wait_for_load_state('networkidle')
        page.fill('input[name="email"]', 'test-integration@example.com')
        page.fill('input[name="password"]', 'test123456')
        page.locator('button[type="submit"]').click()
        page.wait_for_timeout(2000)
        page.close()

    def test_login_invalid(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(f'{server_url}/login.html')
        page.wait_for_load_state('networkidle')
        page.fill('input[name="email"]', 'wrong@example.com')
        page.fill('input[name="password"]', 'wrongpass')
        page.locator('button[type="submit"]').click()
        page.wait_for_timeout(1000)
        body = page.locator('body').inner_text()
        assert 'inválido' in body.lower() or 'erro' in body.lower() or 'error' in body.lower()
        page.close()


@pytest.mark.integration
class TestAccessibility:
    """Test accessibility features."""

    def test_skip_link_exists(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(server_url)
        skip = page.locator('.skip-link')
        assert skip.count() > 0
        assert skip.get_attribute('href') == '#main-content'
        page.close()

    def test_aria_labels_on_nav(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(server_url)
        nav = page.locator('nav')
        assert nav.get_attribute('role') == 'navigation'
        page.close()

    def test_focus_visible(self, browser_context, server_url):
        page = browser_context.new_page()
        page.goto(server_url)
        page.keyboard.press('Tab')
        focused = page.evaluate('() => document.activeElement')
        assert focused is not None
        page.close()


@pytest.mark.integration
class TestResponsive:
    """Test responsive design."""

    def test_mobile_viewport(self, browser_context, server_url):
        page = browser_context.new_page()
        page.set_viewport_size({'width': 375, 'height': 667})
        page.goto(server_url)
        toggle = page.locator('.nav-toggle')
        assert toggle.is_visible()
        toggle.click()
        nav = page.locator('.nav')
        assert nav.is_visible()
        page.close()

    def test_tablet_viewport(self, browser_context, server_url):
        page = browser_context.new_page()
        page.set_viewport_size({'width': 768, 'height': 1024})
        page.goto(server_url)
        assert page.locator('body').is_visible()
        page.close()
