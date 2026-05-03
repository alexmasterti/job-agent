// Theme toggle — same localStorage key pattern as BookLibrary
// Inline version (no-flash) is embedded in base.html <head>.
// This file handles the interactive toggle button after page load.

(function () {
    const KEY = 'theme';
    const ROOT = document.documentElement;

    function getTheme() {
        return localStorage.getItem(KEY) || 'dark';
    }

    function applyTheme(theme) {
        if (theme === 'light') {
            ROOT.setAttribute('data-theme', 'light');
        } else {
            ROOT.removeAttribute('data-theme');
        }
    }

    function toggleTheme() {
        const current = getTheme();
        const next = current === 'dark' ? 'light' : 'dark';
        localStorage.setItem(KEY, next);
        applyTheme(next);
        document.querySelectorAll('.theme-icon-dark').forEach(el => {
            el.style.display = next === 'dark' ? 'inline' : 'none';
        });
        document.querySelectorAll('.theme-icon-light').forEach(el => {
            el.style.display = next === 'light' ? 'inline' : 'none';
        });
    }

    // Apply saved theme on every navigation (HTMX swaps preserve the <html> tag)
    applyTheme(getTheme());

    // Wire toggle buttons
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
            btn.addEventListener('click', toggleTheme);
        });

        // Update icon state to match current theme
        const current = getTheme();
        document.querySelectorAll('.theme-icon-dark').forEach(el => {
            el.style.display = current === 'dark' ? 'inline' : 'none';
        });
        document.querySelectorAll('.theme-icon-light').forEach(el => {
            el.style.display = current === 'light' ? 'inline' : 'none';
        });
    });

    // Re-wire after HTMX swaps
    document.addEventListener('htmx:afterSwap', function () {
        document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
            btn.removeEventListener('click', toggleTheme);
            btn.addEventListener('click', toggleTheme);
        });
    });

    // Toast trigger from HTMX response headers
    document.addEventListener('htmx:afterRequest', function (evt) {
        const trigger = evt.detail.xhr.getResponseHeader('HX-Trigger');
        if (!trigger) return;
        try {
            const data = JSON.parse(trigger);
            if (data.showToast) {
                showToast(data.showToast.message, data.showToast.type || 'info');
            }
        } catch (_) {}
    });

    function showToast(message, type) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }

    window.showToast = showToast;
})();
