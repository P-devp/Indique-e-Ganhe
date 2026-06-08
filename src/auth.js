const AUTH_KEY = 'retro-auth';

function isLoggedIn() {
    var auth = localStorage.getItem(AUTH_KEY);
    if (!auth) return false;
    try {
        var data = JSON.parse(auth);
        return !!data.token;
    } catch (e) {
        return false;
    }
}

function getAuthToken() {
    var auth = localStorage.getItem(AUTH_KEY);
    if (!auth) return null;
    try {
        return JSON.parse(auth).token;
    } catch (e) {
        return null;
    }
}

function getAuthUser() {
    var auth = localStorage.getItem(AUTH_KEY);
    if (!auth) return null;
    try {
        return JSON.parse(auth);
    } catch (e) {
        return null;
    }
}

function saveAuth(token, affiliate, user) {
    localStorage.setItem(AUTH_KEY, JSON.stringify({
        token: token,
        affiliate: affiliate,
        user: user,
        email: user ? user.email : (affiliate ? affiliate.email : null)
    }));
}

function clearAuth() {
    localStorage.removeItem(AUTH_KEY);
}

async function apiLogin(email, password) {
    var res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, password: password })
    });
    if (!res.ok) {
        var err = await res.json();
        throw new Error(err.error || 'Erro ao fazer login');
    }
    var data = await res.json();
    saveAuth(data.token, data.affiliate, data.user);
    subscribePush();
    return data;
}

async function apiRegister(name, email, password, phone, service) {
    var res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: name,
            email: email,
            password: password,
            phone: phone,
            service: service
        })
    });
    if (!res.ok) {
        var err = await res.json();
        throw new Error(err.error || 'Erro ao cadastrar');
    }
    var data = await res.json();
    saveAuth(data.token, data.affiliate, data.user);
    subscribePush();
    return data;
}

async function apiLogout() {
    var token = getAuthToken();
    if (token) {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + token }
            });
        } catch (e) {}
    }
    clearAuth();
}

async function apiGetMe() {
    var token = getAuthToken();
    if (!token) return null;
    var res = await fetch('/api/auth/me', {
        headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!res.ok) {
        clearAuth();
        return null;
    }
    return await res.json();
}

async function checkAuth() {
    var data = await apiGetMe();
    if (!data) return null;
    saveAuth(getAuthToken(), data.affiliate, data.user);
    return data;
}

function updateAuthUI() {
    var loggedIn = isLoggedIn();
    var auth = getAuthUser();
    var authLinks = document.querySelectorAll('.auth-link');
    var guestLinks = document.querySelectorAll('.guest-link');
    var adminLinks = document.querySelectorAll('.admin-link');
    var userNameEl = document.getElementById('auth-user-name');
    var logoutBtn = document.getElementById('auth-logout-btn');

    authLinks.forEach(function(el) { el.style.display = loggedIn ? '' : 'none'; });
    guestLinks.forEach(function(el) { el.style.display = loggedIn ? 'none' : ''; });
    adminLinks.forEach(function(el) {
        el.style.display = (loggedIn && auth && auth.user && auth.user.role === 'admin') ? '' : 'none';
    });

    if (loggedIn && userNameEl) {
        if (auth && auth.affiliate) {
            userNameEl.textContent = auth.affiliate.name;
        } else if (auth && auth.email) {
            userNameEl.textContent = auth.email;
        }
    }

    if (logoutBtn) {
        logoutBtn.onclick = async function() {
            await apiLogout();
            window.location.reload();
        };
    }
}

function subscribePush() {
    if (!('Notification' in window)) return;
    if (!('serviceWorker' in navigator)) return;
    Notification.requestPermission().then(function(permission) {
        if (permission === 'granted') {
            navigator.serviceWorker.ready.then(function(reg) {
                reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array('BCnC0Hx5M0q0GQx7zK2J3R4P5L6M7N8O9P0Q1R2S3T4U5V6W7X8Y9Z0a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6A7B8C9D0E1F2G3H4I5J6K7L8M9N0O1P2Q3R4S5T6U7V8W9X0Y1Z2')
                }).then(function(sub) {
                    var token = localStorage.getItem('token');
                    if (!token) return;
                    fetch('/api/push/subscribe', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                        body: JSON.stringify(sub.toJSON())
                    }).catch(function() {});
                }).catch(function() {});
            });
        }
    });
}

function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - base64String.length % 4) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}
