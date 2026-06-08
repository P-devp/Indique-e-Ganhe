var COMMISSION_RATES = {
    'barbearia': 0.15,
    'lava-rapido': 0.10,
    'ambos': 0.125
};

var SERVICES = {
    'barbearia': { name: '\u2702 Barbearia', commission: 0.15, averageTicket: 80, averageEarning: 12 },
    'lava-rapido': { name: '\uD83D\uDE97 Lava R\u00e1pido', commission: 0.10, averageTicket: 50, averageEarning: 5 },
    'ambos': { name: 'Ambos', commission: 0.125, averageTicket: 65, averageEarning: 8.125 }
};

function generateCode() {
    var year = new Date().getFullYear();
    var random = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
    return 'RETRO-' + year + '-' + random;
}

function generateAffiliateCode() {
    return generateCode();
}

function calculateCommission(service, ticketValue) {
    return (COMMISSION_RATES[service] || 0.10) * ticketValue;
}

function getServiceInfo(service) {
    return SERVICES[service] || SERVICES['ambos'];
}

function getServiceName(service) {
    var info = getServiceInfo(service);
    return info ? info.name : service;
}

async function getAffiliateByCode(code) {
    if (await _checkAPI()) {
        var res = await fetch(API_BASE + '/affiliates/' + encodeURIComponent(code));
        if (!res.ok) return null;
        return await res.json();
    }
    var affiliates = await getAffiliates();
    return affiliates.find(function(a) { return a.code === code; });
}

async function getTopAffiliates(limit) {
    if (limit === undefined) limit = 10;
    if (await _checkAPI()) {
        var res = await fetch(API_BASE + '/leaderboard');
        var data = await res.json();
        return data.slice(0, limit);
    }
    var affiliates = await getAffiliates();
    return affiliates
        .sort(function(a, b) { return (b.earnings || 0) - (a.earnings || 0); })
        .slice(0, limit);
}

async function createAffiliate(data) {
    if (await _checkAPI()) {
        var res = await fetch(API_BASE + '/affiliates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        var affiliate = await res.json();
        await updateStatsDisplay();
        return affiliate;
    }
    var affiliate = {
        name: data.name,
        email: data.email,
        phone: data.phone || '',
        service: data.service || 'ambos',
        code: data.code || generateCode(),
        registeredDate: new Date().toLocaleDateString('pt-BR'),
        clicks: 0, conversions: 0, earnings: 0
    };
    var affiliates = await getAffiliates();
    affiliates.push(affiliate);
    await saveAffiliates(affiliates);
    await updateStatsDisplay();
    return affiliate;
}

async function updateAffiliate(code, updates) {
    if (await _checkAPI()) {
        var headers = { 'Content-Type': 'application/json' };
        var token = getAuthToken();
        if (token) headers['Authorization'] = 'Bearer ' + token;
        var res = await fetch(API_BASE + '/affiliates/' + encodeURIComponent(code), {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify(updates)
        });
        if (!res.ok) return null;
        var affiliate = await res.json();
        await updateStatsDisplay();
        return affiliate;
    }
    var affiliates = await getAffiliates();
    var index = affiliates.findIndex(function(a) { return a.code === code; });
    if (index !== -1) {
        for (var key in updates) {
            if (updates.hasOwnProperty(key)) affiliates[index][key] = updates[key];
        }
        await saveAffiliates(affiliates);
        await updateStatsDisplay();
        return affiliates[index];
    }
    return null;
}

async function deleteAffiliate(code) {
    if (await _checkAPI()) {
        var headers = {};
        var token = getAuthToken();
        if (token) headers['Authorization'] = 'Bearer ' + token;
        await fetch(API_BASE + '/affiliates/' + encodeURIComponent(code), { method: 'DELETE', headers: headers });
        await updateStatsDisplay();
        return;
    }
    var affiliates = await getAffiliates();
    affiliates = affiliates.filter(function(a) { return a.code !== code; });
    await saveAffiliates(affiliates);
    await updateStatsDisplay();
}

async function searchAffiliates(query) {
    var affiliates = await getAffiliates();
    var lowerQuery = query.toLowerCase();
    return affiliates.filter(function(a) {
        return a.name.toLowerCase().includes(lowerQuery) ||
               a.email.toLowerCase().includes(lowerQuery) ||
               a.code.toLowerCase().includes(lowerQuery);
    });
}

async function filterAffiliatesByService(service) {
    var affiliates = await getAffiliates();
    return affiliates.filter(function(a) {
        return a.service === service || a.service === 'ambos';
    });
}

// ── Search / Filter ──────────────────────────────────────────
function setupSearch(inputId, tableId) {
    var input = document.getElementById(inputId);
    var table = document.getElementById(tableId);
    if (!input || !table) return;
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    input.addEventListener('input', function() {
        var q = input.value.toLowerCase();
        var rows = tbody.querySelectorAll('tr');
        rows.forEach(function(row) {
            var match = false;
            row.querySelectorAll('td').forEach(function(td) {
                if (td.textContent.toLowerCase().includes(q)) match = true;
            });
            row.style.display = match ? '' : 'none';
        });
    });
}
