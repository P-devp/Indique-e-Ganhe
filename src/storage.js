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
    showSkeleton('affiliates-table', 'table');
    if (await _checkAPI()) {
        var res = await fetch(API_BASE + '/affiliates');
        var result = await res.json();
        var data = result.data || result;
        var skeletonContainer = document.getElementById('affiliates-table');
        if (skeletonContainer) skeletonContainer.innerHTML = '';
        return data;
    }
    var skeletonContainer = document.getElementById('affiliates-table');
    if (skeletonContainer) skeletonContainer.innerHTML = '';
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

// ── Sortable tables ──────────────────────────────────────────
function makeSortable(tableId) {
    var table = document.getElementById(tableId);
    if (!table) return;
    var headers = table.querySelectorAll('th');
    headers.forEach(function(th, colIndex) {
        if (!th.getAttribute('data-sortable')) return;
        th.style.cursor = 'pointer';
        th.setAttribute('role', 'columnheader');
        th.setAttribute('aria-sort', 'none');
        var arrow = document.createElement('span');
        arrow.className = 'sort-arrow';
        arrow.textContent = ' ↕';
        arrow.style.fontSize = '10px';
        th.appendChild(arrow);
        th.addEventListener('click', function() {
            sortTable(table, colIndex, th);
        });
    });
}

function sortTable(table, colIndex, th) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr'));
    var isAsc = th.getAttribute('aria-sort') !== 'ascending';
    rows.sort(function(a, b) {
        var aVal = a.cells[colIndex] ? a.cells[colIndex].textContent.trim() : '';
        var bVal = b.cells[colIndex] ? b.cells[colIndex].textContent.trim() : '';
        var aNum = parseFloat(aVal.replace(/[R$\s]/g, '').replace(',', '.'));
        var bNum = parseFloat(bVal.replace(/[R$\s]/g, '').replace(',', '.'));
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAsc ? aNum - bNum : bNum - aNum;
        }
        return isAsc ? aVal.localeCompare(bVal, 'pt-BR') : bVal.localeCompare(aVal, 'pt-BR');
    });
    rows.forEach(function(row) { tbody.appendChild(row); });
    var allHeaders = table.querySelectorAll('th');
    allHeaders.forEach(function(h) { h.setAttribute('aria-sort', 'none'); });
    th.setAttribute('aria-sort', isAsc ? 'ascending' : 'descending');
    var arrow = th.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = isAsc ? ' ▲' : ' ▼';
}
