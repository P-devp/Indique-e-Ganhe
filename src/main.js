function toggleNav(btn) {
    var nav = document.querySelector('.nav');
    if (!nav) return;
    var isOpen = nav.classList.toggle('open');
    btn.setAttribute('aria-expanded', isOpen);
    btn.textContent = isOpen ? '✕' : '☰';
    btn.setAttribute('aria-label', isOpen ? 'Fechar menu' : 'Abrir menu');
}

function showToast(message) {
    var toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function() { toast.classList.add('toast-show'); }, 10);
    setTimeout(function() {
        toast.classList.remove('toast-show');
        setTimeout(function() { document.body.removeChild(toast); }, 300);
    }, 4000);
}

function toggleTheme() {
    var html = document.documentElement;
    var isDark = html.getAttribute('data-theme') === 'dark';
    var newTheme = isDark ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme === 'dark' ? 'dark' : '');
    localStorage.setItem('retro-theme', newTheme);
    updateThemeButton();
}

function updateThemeButton() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.textContent = isDark ? '\u25C9 Tema' : '\u25D0 Tema';
    btn.title = isDark ? 'Modo claro' : 'Modo escuro';
}

function loadTheme() {
    var saved = localStorage.getItem('retro-theme');
    if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
    updateThemeButton();
}

async function exportAffiliatesData() {
    var affiliates = await getAffiliates();
    var dataStr = JSON.stringify(affiliates, null, 2);
    var blob = new Blob([dataStr], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = 'affiliates-backup-' + new Date().toISOString().split('T')[0] + '.json';
    link.click();
    URL.revokeObjectURL(url);
}

function importAffiliatesData(jsonString) {
    try {
        var data = JSON.parse(jsonString);
        if (Array.isArray(data)) {
            saveAffiliates(data);
            updateStatsDisplay();
            return true;
        }
    } catch (e) {
        console.error('Erro ao importar:', e);
    }
    return false;
}

async function clearAllData() {
    if (!confirm('Deseja realmente limpar todos os dados?')) return false;
    if (await _checkAPI()) {
        var affiliates = await getAffiliates();
        for (var i = 0; i < affiliates.length; i++) {
            try {
                await deleteAffiliate(affiliates[i].code);
            } catch (e) {}
        }
    } else {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(STATS_KEY);
    }
    await updateStatsDisplay();
    return true;
}

async function resetAffiliateStats(code) {
    return await updateAffiliate(code, { clicks: 0, conversions: 0, earnings: 0 });
}

async function initializeMockData() {
    if (await _checkAPI()) {
        await fetch(API_BASE + '/seed', { method: 'POST' });
    } else {
        var mock = [
            { name: 'Jo\u00e3o Silva', email: 'joao@email.com', phone: '11 99999-8888', service: 'barbearia', code: 'RETRO-2026-0001', registeredDate: '15/03/2026', clicks: 45, conversions: 15, earnings: 180 },
            { name: 'Maria Santos', email: 'maria@email.com', phone: '11 99999-7777', service: 'lava-rapido', code: 'RETRO-2026-0002', registeredDate: '14/03/2026', clicks: 32, conversions: 10, earnings: 50 },
            { name: 'Carlos Oliveira', email: 'carlos@email.com', phone: '11 99999-6666', service: 'ambos', code: 'RETRO-2026-0003', registeredDate: '13/03/2026', clicks: 28, conversions: 8, earnings: 120 },
            { name: 'Ana Costa', email: 'ana@email.com', phone: '11 99999-5555', service: 'barbearia', code: 'RETRO-2026-0004', registeredDate: '12/03/2026', clicks: 55, conversions: 18, earnings: 216 },
            { name: 'Pedro Ferreira', email: 'pedro@email.com', phone: '11 99999-4444', service: 'lava-rapido', code: 'RETRO-2026-0005', registeredDate: '11/03/2026', clicks: 20, conversions: 6, earnings: 30 }
        ];
        localStorage.setItem(STORAGE_KEY, JSON.stringify(mock));
    }
    await updateStatsDisplay();
}

async function initializeDemoData() {
    var existing = await getAffiliates();
    if (existing.length === 0) {
        await initializeMockData();
    }
}

/* ============ INIT ============ */

async function initApp() {
    // Auto-detect dark mode via prefers-color-scheme
    var storedTheme = localStorage.getItem('retro-theme');
    if (!storedTheme) {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
    }

    loadTheme();

    // Seed demo data if database is empty
    var affiliates = await getAffiliates();
    if (affiliates.length === 0) {
        await initializeDemoData();
    }

    await updateStatsDisplay();
}

    // Dark mode manual toggle
    var darkToggle = document.getElementById('dark-toggle');
    if (darkToggle) {
        darkToggle.addEventListener('click', function() {
            var current = document.documentElement.getAttribute('data-theme');
            var next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            darkToggle.textContent = next === 'dark' ? '☀️' : '🌙';
            darkToggle.setAttribute('aria-label', next === 'dark' ? 'Modo claro' : 'Modo escuro');
        });
        // Set initial button text
        var theme = document.documentElement.getAttribute('data-theme') || 'light';
        darkToggle.textContent = theme === 'dark' ? '☀️' : '🌙';
        darkToggle.setAttribute('aria-label', theme === 'dark' ? 'Modo claro' : 'Modo escuro');
    }

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

function showSkeleton(containerId, type) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    if (type === 'cards') {
        for (var i = 0; i < 4; i++) {
            var card = document.createElement('div');
            card.className = 'skeleton skeleton-card';
            container.appendChild(card);
        }
    } else if (type === 'table') {
        for (var i = 0; i < 5; i++) {
            var row = document.createElement('div');
            row.className = 'skeleton-table-row';
            for (var j = 0; j < 5; j++) {
                var cell = document.createElement('div');
                cell.className = 'skeleton skeleton-text';
                if (j === 4) cell.classList.add('tiny');
                row.appendChild(cell);
            }
            container.appendChild(row);
        }
    }
}

// ── Real-time form validation ────────────────────────────────
document.addEventListener('input', function(e) {
    var el = e.target;
    if (el.tagName !== 'INPUT' && el.tagName !== 'SELECT') return;
    var wrapper = el.closest('.form-input-wrapper');
    if (!wrapper) return;
    var errorEl = wrapper.querySelector('.field-error');
    if (!errorEl) {
        errorEl = document.createElement('span');
        errorEl.className = 'field-error';
        wrapper.appendChild(errorEl);
    }
    if (el.hasAttribute('required') && !el.value.trim()) {
        errorEl.textContent = 'Campo obrigatório';
        errorEl.style.display = 'block';
        el.style.borderColor = 'red';
        return;
    }
    if (el.type === 'email' && el.value) {
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(el.value)) {
            errorEl.textContent = 'Email inválido';
            errorEl.style.display = 'block';
            el.style.borderColor = 'red';
            return;
        }
    }
    if (el.type === 'password' && el.value && el.value.length < 6) {
        errorEl.textContent = 'Mínimo 6 caracteres';
        errorEl.style.display = 'block';
        el.style.borderColor = 'red';
        return;
    }
    errorEl.style.display = 'none';
    el.style.borderColor = '';
});

// ── Toast notifications ──────────────────────────────────────
function showToast(message, type) {
    type = type || 'info';
    var container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function() {
        toast.style.animation = 'toast-out 0.3s ease-in forwards';
        setTimeout(function() { toast.remove(); }, 300);
    }, 4000);
}

// ── Confirm modal ────────────────────────────────────────────
function showConfirm(title, message) {
    return new Promise(function(resolve) {
        var overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = '<div class="modal-box" role="alertdialog" aria-modal="true">' +
            '<div class="modal-title">' + title + '</div>' +
            '<div class="modal-message">' + message + '</div>' +
            '<div class="modal-actions">' +
            '<button class="btn btn-cancel" data-action="cancel">Cancelar</button>' +
            '<button class="btn btn-danger" data-action="confirm">Confirmar</button>' +
            '</div></div>';
        document.body.appendChild(overlay);
        setTimeout(function() { overlay.classList.add('active'); }, 10);
        overlay.addEventListener('click', function(e) {
            var action = e.target.getAttribute('data-action');
            if (action === 'confirm') { overlay.remove(); resolve(true); }
            if (action === 'cancel') { overlay.remove(); resolve(false); }
        });
    });
}

// ── Copy affiliate link ──────────────────────────────────────
function copyLink(link) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function() {
            showToast('Link copiado!', 'success');
        }).catch(function() {
            fallbackCopy(link);
        });
    } else {
        fallbackCopy(link);
    }
}

function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    showToast('Link copiado!', 'success');
}

// ── QR Code ──────────────────────────────────────────────────
function showQRCode(elementId, data) {
    var el = document.getElementById(elementId);
    if (!el) return;
    var url = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(data);
    el.innerHTML = '<img src="' + url + '" alt="QR Code" style="width:200px;height:200px;image-render:pixelated;border:2px inset var(--color-silver);">';
}

// ── Pagination UI ────────────────────────────────────────────
function renderPagination(containerId, current, total, baseUrl) {
    var container = document.getElementById(containerId);
    if (!container) return;
    if (total <= 1) { container.innerHTML = ''; return; }
    var html = '<div class="pagination" role="navigation" aria-label="Paginação">';
    if (current > 1) {
        html += '<a href="' + baseUrl + 'page=' + (current - 1) + '" class="page-link" data-page="' + (current - 1) + '">« Anterior</a>';
    }
    for (var i = 1; i <= total; i++) {
        if (i === current) {
            html += '<span class="page-link active" aria-current="page">' + i + '</span>';
        } else if (i === 1 || i === total || Math.abs(i - current) <= 2) {
            html += '<a href="' + baseUrl + 'page=' + i + '" class="page-link" data-page="' + i + '">' + i + '</a>';
        } else if (Math.abs(i - current) === 3) {
            html += '<span class="page-dots">...</span>';
        }
    }
    if (current < total) {
        html += '<a href="' + baseUrl + 'page=' + (current + 1) + '" class="page-link" data-page="' + (current + 1) + '">Próximo »</a>';
    }
    html += '</div>';
    container.innerHTML = html;
}

// ── Session management ───────────────────────────────────────
function loadSessions(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return;
    fetch('/api/auth/sessions', {
        headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.error) { container.innerHTML = '<p class="empty-state-message">' + data.error + '</p>'; return; }
        if (!data.length) { container.innerHTML = '<p class="empty-state-message">Nenhuma sessão ativa.</p>'; return; }
        var html = '<div class="retro-table"><table><thead><tr><th>Dispositivo</th><th>Data</th><th></th></tr></thead><tbody>';
        data.forEach(function(s) {
            html += '<tr><td>' + (s.user_agent || 'Desconhecido') + '</td><td>' + (s.created_at || '') + '</td>';
            html += '<td><button class="btn btn-danger" onclick="revokeSession(\'' + s.token + '\')" style="padding:4px 8px;font-size:9px;">Revogar</button></td></tr>';
        });
        html += '</tbody></table></div>';
        container.innerHTML = html;
    }).catch(function() {
        container.innerHTML = '<p class="empty-state-message">Erro ao carregar sessões.</p>';
    });
}

function revokeSession(token) {
    fetch('/api/auth/sessions', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('token') },
        body: JSON.stringify({ token: token })
    }).then(function(r) { return r.json(); }).then(function(data) {
        if (data.ok) { showToast('Sessão revogada!', 'success'); loadSessions('sessions-list'); }
        else { showToast(data.error || 'Erro', 'error'); }
    }).catch(function() {
        showToast('Erro de conexão', 'error');
    });
}

// ── Delete own account ───────────────────────────────────────
function deleteOwnAccount() {
    showConfirm('Excluir conta', 'Tem certeza? Esta ação é irreversível e todos os seus dados serão excluídos conforme a LGPD.').then(function(confirmed) {
        if (!confirmed) return;
        fetch('/api/auth/account', {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (data.ok) {
                localStorage.removeItem('token');
                showToast('Conta excluída com sucesso.', 'success');
                setTimeout(function() { window.location.href = '/'; }, 1500);
            } else {
                showToast(data.error || 'Erro ao excluir conta', 'error');
            }
        }).catch(function() {
            showToast('Erro de conexão', 'error');
        });
    });
}
