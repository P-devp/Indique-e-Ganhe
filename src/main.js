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
    loadTheme();

    // Seed demo data if database is empty
    var affiliates = await getAffiliates();
    if (affiliates.length === 0) {
        await initializeDemoData();
    }

    await updateStatsDisplay();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}
