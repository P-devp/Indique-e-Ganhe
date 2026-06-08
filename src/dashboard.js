async function updateStatsDisplay() {
    var affiliates = await getAffiliates();
    var totalClicks = 0, totalConversions = 0, totalEarnings = 0;

    affiliates.forEach(function(a) {
        totalClicks += a.clicks || 0;
        totalConversions += a.conversions || 0;
        totalEarnings += a.earnings || 0;
    });

    var els = {
        'total-affiliates': affiliates.length,
        'total-clicks': totalClicks,
        'total-conversions': totalConversions,
        'total-earnings': formatCurrency(totalEarnings)
    };

    Object.entries(els).forEach(function(e) {
        var el = document.getElementById(e[0]);
        if (el) el.textContent = e[1];
    });

    saveGlobalStats({
        affiliates: affiliates.length,
        clicks: totalClicks,
        conversions: totalConversions,
        earnings: totalEarnings
    });
}

async function updateGlobalStats() {
    return await updateStatsDisplay();
}

async function loadDashboard() {
    showSkeleton('stats-grid', 'cards');
    showSkeleton('goals-grid', 'cards');
    var affiliates = await getAffiliates();
    var totalClicks = 0, totalConversions = 0, totalEarnings = 0;

    affiliates.forEach(function(a) {
        totalClicks += a.clicks || 0;
        totalConversions += a.conversions || 0;
        totalEarnings += a.earnings || 0;
    });

    var statsEl = document.getElementById('stats-grid');
    if (statsEl && statsEl.querySelector('.skeleton')) statsEl.innerHTML = '';
    var goalsEl = document.getElementById('goals-grid');
    if (goalsEl && goalsEl.querySelector('.skeleton')) goalsEl.innerHTML = '';

    setText('dashboard-affiliates', affiliates.length);
    setText('dashboard-clicks', totalClicks);
    setText('dashboard-conversions', totalConversions);
    setText('dashboard-earnings', formatCurrency(totalEarnings));

    loadAffiliatesList(affiliates);
    loadLeaderboard(affiliates);
}

function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
}

function loadAffiliatesList(affiliates) {
    var container = document.getElementById('affiliates-list');
    if (!container) return;

    if (affiliates.length === 0) {
        container.innerHTML = '<p style="text-align:center;padding:20px;color:#666;">Nenhum afiliado cadastrado ainda. <a href="signup.html">Cadastre-se agora</a></p>';
        return;
    }

    var html = '<div class="table-wrapper"><table class="retro-table"><thead><tr><th>Nome</th><th>C\u00f3digo</th><th>Data</th><th>Cliques</th><th>Convers\u00f5es</th><th>A\u00e7\u00f5es</th></tr></thead><tbody>';
    affiliates.forEach(function(a) {
        var safeName = (a.name || '').replace(/[<>&"']/g, function(c) { return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]; });
        html += '<tr><td>' + safeName + '</td><td><strong>' + a.code + '</strong></td><td>' + (a.registeredDate || '') + '</td><td>' + (a.clicks || 0) + '</td><td>' + (a.conversions || 0) + '</td><td><button class="btn btn-tiny" onclick="simulateClick(\'' + a.code + '\')">Simular Clique</button></td></tr>';
    });
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function loadLeaderboard(affiliates) {
    var tbody = document.getElementById('leaderboard-body');
    if (!tbody) return;

    if (affiliates.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;">Nenhum dado dispon\u00edvel</td></tr>';
        return;
    }

    var sorted = affiliates.slice().sort(function(a, b) {
        return (b.earnings || 0) - (a.earnings || 0);
    });

    var html = '';
    sorted.slice(0, 10).forEach(function(a, i) {
        var level = a.level || 'bronze';
        var safeName = (a.name || '').replace(/[<>&"']/g, function(c) { return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]; });
        html += '<tr><td><strong>' + (i + 1) + '</strong></td><td>' + safeName + '</td><td>' + a.code + '</td><td><span class="level-badge level-' + level + '" style="font-size:9px;padding:2px 6px;">' + capitalizeFirst(level) + '</span></td><td>' + (a.clicks || 0) + '</td><td>' + (a.conversions || 0) + '</td><td>' + formatCurrency(a.earnings || 0) + '</td></tr>';
    });
    tbody.innerHTML = html;
}

function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

async function simulateClick(code) {
    var affiliates = await getAffiliates();
    var affiliate = affiliates.find(function(a) { return a.code === code; });
    if (!affiliate) return;

    affiliate.clicks = (affiliate.clicks || 0) + 1;
    var converted = Math.random() < 0.3;

    if (converted) {
        affiliate.conversions = (affiliate.conversions || 0) + 1;
        var rate = affiliate.service === 'barbearia' ? 0.15 : 0.10;
        var ticket = affiliate.service === 'barbearia' ? 80 : 50;
        affiliate.earnings = (affiliate.earnings || 0) + ticket * rate;
    }

    if (await _checkAPI()) {
        await fetch(API_BASE + '/click', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });
        if (converted) {
            await fetch(API_BASE + '/conversion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, ticketValue: ticket })
            });
        }
    } else {
        await saveAffiliates(affiliates);
    }

    await loadDashboard();
}

function showResources(type) {
    if (type === 'mensagens') {
        showToast('Mensagens Prontas:\n\nWhatsApp:\n"Ei! Conhe\u00e7o a melhor barbearia/lava r\u00e1pido da regi\u00e3o! Use meu c\u00f3digo RETRO-XXXX e ganhe 15%/10% de desconto"\n\nEmail:\nVeja nosso programa de afiliados...');
    } else if (type === 'banners') {
        showToast('Banners dispon\u00edveis:\n- Banner 728x90\n- Banner 300x250\n- Banner 1200x400\n\nFun\u00e7\u00e3o em desenvolvimento!');
    }
}

async function copyShareLink() {
    var affiliates = await getAffiliates();
    if (affiliates.length === 0) {
        showToast('Voc\u00ea precisa estar cadastrado para compartilhar um link.');
        return;
    }
    var link = generateReferralLink(affiliates[0].code);
    copyToClipboard(link);
    showToast('Link copiado: ' + link);
}
