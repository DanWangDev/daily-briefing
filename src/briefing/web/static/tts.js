(function() {
    'use strict';

    var currentBtn = null;
    var audio = new Audio();

    function extractNewsText(card) {
        var parts = [];
        var h3 = card.querySelector('h3');
        if (h3) parts.push(h3.textContent.replace(/[\u{1F508}\u{1F509}\u{1F50A}\u23F9]/gu, '').trim());
        var summary = card.querySelector('.news-summary');
        if (summary) parts.push(summary.textContent.trim());
        var facts = card.querySelectorAll('.news-facts li');
        if (facts.length) {
            facts.forEach(function(li) { parts.push(li.textContent.trim()); });
        }
        var bias = card.querySelector('.bias-analysis');
        if (bias) parts.push(bias.textContent.trim());
        return parts.join('. ');
    }

    function stopAudio() {
        audio.pause();
        audio.currentTime = 0;
        if (currentBtn) {
            currentBtn.classList.remove('tts-speaking');
            var label = (window.__i18n && window.__i18n.tts_play) || 'Read aloud';
            currentBtn.setAttribute('aria-label', label);
            currentBtn.setAttribute('title', label);
            currentBtn.innerHTML = '\u{1F509}';
        }
        currentBtn = null;
    }

    async function startAudio(btn) {
        var card = btn.closest('.news-card');
        var section = card || btn.closest('.nm-detail');
        if (!section) return;

        var text = card ? extractNewsText(card) : (section.textContent || '').trim();
        if (!text) return;

        // Show loading state
        var label = (window.__i18n && window.__i18n.tts_stop) || 'Stop';
        btn.classList.add('tts-speaking');
        btn.innerHTML = '\u23F3';  // hourglass while loading
        btn.setAttribute('aria-label', label);
        btn.setAttribute('title', label);
        currentBtn = btn;

        try {
            var resp = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
            });

            if (!resp.ok) throw new Error('TTS failed');

            var data = await resp.json();
            audio.src = data.url;
            audio.onended = function() { stopAudio(); };
            audio.onerror = function() { stopAudio(); };
            btn.innerHTML = '\u23F9';  // stop icon
            audio.play();
        } catch (e) {
            console.warn('TTS error:', e);
            stopAudio();
        }
    }

    // Event delegation
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.tts-btn');
        if (!btn) return;
        e.preventDefault();

        if (currentBtn === btn && !audio.paused) {
            stopAudio();
        } else {
            stopAudio();
            startAudio(btn);
        }
    });

    window.addEventListener('beforeunload', stopAudio);
    document.addEventListener('htmx:beforeSwap', function() { stopAudio(); });
})();
