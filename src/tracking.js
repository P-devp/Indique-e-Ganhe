async function recordClick(code) {
    if (await _checkAPI()) {
        await fetch(API_BASE + '/click', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });
        return;
    }
    var affiliate = await getAffiliateByCode(code);
    if (affiliate) {
        affiliate.clicks = (affiliate.clicks || 0) + 1;
        await updateAffiliate(code, { clicks: affiliate.clicks });
    }
}

async function recordConversion(code, ticketValue) {
    if (await _checkAPI()) {
        var body = { code: code };
        if (ticketValue) body.ticketValue = ticketValue;
        await fetch(API_BASE + '/conversion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return;
    }
    var affiliate = await getAffiliateByCode(code);
    if (affiliate) {
        affiliate.conversions = (affiliate.conversions || 0) + 1;
        var earnings = affiliate.earnings || 0;
        if (ticketValue) {
            earnings += calculateCommission(affiliate.service, ticketValue);
        } else {
            earnings += getServiceInfo(affiliate.service).averageEarning;
        }
        await updateAffiliate(code, { conversions: affiliate.conversions, earnings: earnings });
    }
}

function generateReferralLink(code) {
    var base = window.location.origin + window.location.pathname.replace(/[^/]*$/, '');
    return base + 'click.html?ref=' + code;
}

function getReferralCode() {
    var params = new URLSearchParams(window.location.search);
    return params.get('ref');
}

async function handleReferralClick(code) {
    await recordClick(code);
    localStorage.setItem('lastReferrer', code);
    return generateReferralLink(code);
}
