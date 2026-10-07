/* Theme Switcher */
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('news-theme', theme);
    updateThemeButtons();
}

function updateThemeButtons() {
    var current = document.documentElement.getAttribute('data-theme') || 'sepia';
    document.querySelectorAll('.theme-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-theme') === current);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    var saved = localStorage.getItem('news-theme') || 'sepia';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeButtons();
});

/* Status Bar */
async function updateStatus() {
    try {
        var resp = await fetch('/api/stats');
        var data = await resp.json();
        document.getElementById('status-hdd').textContent =
            'HDD ' + (data.hdd_connected ? 'OK' : 'OFF');
        document.getElementById('status-ollama').textContent =
            'Ollama ' + (data.ollama_available ? 'OK' : 'OFF');
        document.getElementById('status-articles').textContent =
            data.total_articles + '건';
    } catch (e) {
        console.error('Status update failed:', e);
    }
}

async function manualCollect() {
    var pw = prompt('수동 수집을 시작합니다. 비밀번호를 입력하세요.');
    if (!pw) return;
    try {
        var resp = await fetch('/api/collect/now', {
            method: 'POST',
            headers: { 'X-Collect-Password': pw }
        });
        var data = await resp.json();
        alert(data.message);
    } catch (e) {
        alert('수집 시작 실패');
    }
}

updateStatus();
setInterval(updateStatus, 60000);

/* Refresh (PWA) */
function reloadPage() {
    var btn = document.querySelector('.header-refresh');
    if (btn) btn.classList.add('spinning');
    var url = window.location.pathname + window.location.search;
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    window.location.href = url + sep + '_=' + Date.now();
}

(function() {
    var lastVisible = Date.now();
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            var elapsed = Date.now() - lastVisible;
            if (elapsed > 5 * 60 * 1000) {
                reloadPage();
            } else {
                updateStatus();
            }
        } else {
            lastVisible = Date.now();
        }
    });
})();

/* Theme Feedback */
async function sendFeedback(themeId, rating, btn) {
    var card = btn.closest('.theme-feedback');
    var title = btn.closest('.theme-card').querySelector('h3').textContent.trim();
    try {
        var resp = await fetch('/api/feedback', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({theme_id: themeId, rating: rating, title: title})
        });
        var data = await resp.json();
        card.querySelectorAll('.fb-btn').forEach(function(b) { b.classList.remove('selected'); });
        btn.classList.add('selected');
        card.querySelector('.fb-status').textContent = data.message || '';
    } catch (e) {
        card.querySelector('.fb-status').textContent = '전송 실패';
    }
}

// 페이지 로드 시 기존 피드백 표시
document.addEventListener('DOMContentLoaded', async function() {
    try {
        var resp = await fetch('/api/feedback/latest');
        var data = await resp.json();
        if (data.feedbacks) {
            data.feedbacks.forEach(function(fb) {
                var card = document.querySelector('[data-theme-id="' + fb.theme_id + '"]');
                if (card) {
                    var btn = card.querySelector('.fb-' + fb.rating);
                    if (btn) btn.classList.add('selected');
                }
            });
        }
    } catch (e) {}
});
