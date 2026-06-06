const STORAGE_KEY = 'affiliates';
const STATS_KEY = 'globalStats';
const API_BASE = '/api';
let _useAPI = null;

async function _checkAPI() {
    if (_useAPI !== null) return _useAPI;
    try {
        var res = await fetch(API_BASE + '/affiliates', { method: 'HEAD' });
        _useAPI = res.ok;
    } catch (e) {
        _useAPI = false;
    }
    return _useAPI;
}

async function getAffiliates() {
    if (await _checkAPI()) {
        var res = await fetch(API_BASE + '/affiliates');
        var result = await res.json();
        return result.data || result;
    }
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
}

async function saveAffiliates(affiliates) {
    if (await _checkAPI()) {
        // Individual saves are handled by create/update/delete
        return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(affiliates));
}

async function getGlobalStats() {
    if (await _checkAPI()) {
        var res = await fetch(API_BASE + '/stats');
        return await res.json();
    }
    return JSON.parse(localStorage.getItem(STATS_KEY) || '{}');
}

function saveGlobalStats(stats) {
    localStorage.setItem(STATS_KEY, JSON.stringify(stats));
}
