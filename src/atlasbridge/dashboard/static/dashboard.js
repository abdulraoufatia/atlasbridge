/* AtlasBridge Dashboard — vanilla JS, no framework */

(function () {
    'use strict';

    // ---- Theme toggle ----
    var THEME_KEY = 'atlasbridge-theme';
    var body = document.body;
    var themeBtn = document.getElementById('theme-toggle');

    function applyTheme(theme) {
        if (theme === 'light') {
            body.classList.add('light');
        } else {
            body.classList.remove('light');
        }
    }

    function toggleTheme() {
        var current = body.classList.contains('light') ? 'light' : 'dark';
        var next = current === 'light' ? 'dark' : 'light';
        applyTheme(next);
        try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* ignore */ }
    }

    // Apply saved theme on load
    try {
        var saved = localStorage.getItem(THEME_KEY);
        if (saved) { applyTheme(saved); }
    } catch (e) { /* ignore */ }

    if (themeBtn) {
        themeBtn.addEventListener('click', toggleTheme);
    }

    // ---- Mobile nav toggle ----
    var navToggle = document.getElementById('nav-toggle');
    var navLinks = document.getElementById('nav-links');
    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function () {
            navLinks.classList.toggle('open');
        });
    }

    // ---- Auto-refresh (home page only) ----
    var REFRESH_KEY = 'atlasbridge-autorefresh';
    var REFRESH_INTERVAL = 5000;
    var refreshTimer = null;

    // Only activate on home page (stat cards present)
    var statSessions = document.getElementById('stat-sessions');
    if (!statSessions) { return; }

    // Create auto-refresh toggle in nav
    var navContainer = document.getElementById('nav-links') || document.querySelector('nav');
    if (navContainer) {
        var refreshBtn = document.createElement('button');
        refreshBtn.className = 'nav-btn';
        refreshBtn.id = 'auto-refresh-toggle';
        refreshBtn.title = 'Toggle auto-refresh';
        refreshBtn.textContent = 'Auto-refresh: OFF';
        navContainer.appendChild(refreshBtn);

        var indicator = document.createElement('span');
        indicator.className = 'auto-refresh-indicator';
        indicator.id = 'refresh-indicator';
        indicator.style.display = 'none';
        indicator.innerHTML = '<span class="pulse"></span> Live';
        navContainer.appendChild(indicator);

        function startRefresh() {
            if (refreshTimer) { return; }
            refreshTimer = setInterval(pollStats, REFRESH_INTERVAL);
            refreshBtn.textContent = 'Auto-refresh: ON';
            indicator.style.display = 'inline-flex';
            try { localStorage.setItem(REFRESH_KEY, 'on'); } catch (e) { /* ignore */ }
        }

        function stopRefresh() {
            if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
            refreshBtn.textContent = 'Auto-refresh: OFF';
            indicator.style.display = 'none';
            try { localStorage.setItem(REFRESH_KEY, 'off'); } catch (e) { /* ignore */ }
        }

        function toggleRefresh() {
            if (refreshTimer) { stopRefresh(); } else { startRefresh(); }
        }

        refreshBtn.addEventListener('click', toggleRefresh);

        // Restore preference
        try {
            if (localStorage.getItem(REFRESH_KEY) === 'on') { startRefresh(); }
        } catch (e) { /* ignore */ }
    }

    function pollStats() {
        fetch('/api/stats')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var el;
                el = document.getElementById('stat-sessions');
                if (el) { el.textContent = data.sessions; }
                el = document.getElementById('stat-active');
                if (el) { el.textContent = data.active_sessions; }
                el = document.getElementById('stat-prompts');
                if (el) { el.textContent = data.prompts; }
                el = document.getElementById('stat-audit');
                if (el) { el.textContent = data.audit_events; }
            })
            .catch(function () { /* silently ignore refresh errors */ });
    }
})();
