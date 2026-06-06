function formatCurrency(value) {
    var v = (value || 0);
    return 'R$ ' + v.toFixed(2).replace('.', ',');
}

function formatDate(date) {
    if (typeof date === 'string') return date;
    return new Date(date).toLocaleDateString('pt-BR');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).catch(function() {
        fallbackCopy(text);
    });
}

function fallbackCopy(text) {
    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
}

function getConversionRate(clicks, conversions) {
    if (clicks === 0) return 0;
    return ((conversions / clicks) * 100).toFixed(2);
}
