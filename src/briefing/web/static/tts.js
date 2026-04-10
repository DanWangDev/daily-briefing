(function() {
    'use strict';

    if (!('speechSynthesis' in window)) return;

    var synth = window.speechSynthesis;
    var currentBtn = null;
    var utterance = null;

    function getVoice(lang) {
        var voices = synth.getVoices();
        var prefix = lang === 'zh' ? 'zh' : 'en';
        for (var i = 0; i < voices.length; i++) {
            if (voices[i].lang.indexOf(prefix) === 0) return voices[i];
        }
        return null;
    }

    function stopSpeech() {
        synth.cancel();
        if (currentBtn) {
            currentBtn.classList.remove('tts-speaking');
            var label = (window.__i18n && window.__i18n.tts_play) || 'Read aloud';
            currentBtn.setAttribute('aria-label', label);
            currentBtn.setAttribute('title', label);
            currentBtn.innerHTML = '\u{1F509}';
        }
        currentBtn = null;
        utterance = null;
    }

    function extractNewsText(card) {
        var parts = [];
        // Headline
        var h3 = card.querySelector('h3');
        if (h3) parts.push(h3.textContent.replace(/[\u{1F508}\u{1F509}\u{1F50A}\u23F9]/gu, '').trim());
        // Summary
        var summary = card.querySelector('.news-summary');
        if (summary) parts.push(summary.textContent.trim());
        // Key facts
        var facts = card.querySelectorAll('.news-facts li');
        if (facts.length) {
            facts.forEach(function(li) { parts.push(li.textContent.trim()); });
        }
        // Bias check
        var bias = card.querySelector('.bias-analysis');
        if (bias) parts.push(bias.textContent.trim());
        return parts.join('. ');
    }

    function startSpeech(btn) {
        var card = btn.closest('.news-card');
        var section = card || btn.closest('.nm-detail');
        if (!section) return;

        var text = card ? extractNewsText(card) : (section.textContent || '').trim();
        if (!text) return;
        if (text.length > 5000) text = text.substring(0, 5000);

        var lang = document.documentElement.getAttribute('lang') || 'en';
        utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang === 'zh' ? 'zh-CN' : 'en-US';
        utterance.rate = lang === 'zh' ? 0.9 : 1.0;

        var voice = getVoice(lang);
        if (voice) utterance.voice = voice;

        utterance.onend = function() { stopSpeech(); };
        utterance.onerror = function() { stopSpeech(); };

        var label = (window.__i18n && window.__i18n.tts_stop) || 'Stop reading';
        btn.classList.add('tts-speaking');
        btn.setAttribute('aria-label', label);
        btn.setAttribute('title', label);
        btn.innerHTML = '\u23F9';
        currentBtn = btn;

        synth.speak(utterance);
    }

    // Event delegation — works with HTMX-swapped content
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.tts-btn');
        if (!btn) return;
        e.preventDefault();

        if (currentBtn === btn && synth.speaking) {
            stopSpeech();
        } else {
            stopSpeech();
            startSpeech(btn);
        }
    });

    // Stop on navigation
    window.addEventListener('beforeunload', stopSpeech);
    document.addEventListener('htmx:beforeSwap', function() { stopSpeech(); });

    // Chrome: load voices async
    if (synth.onvoiceschanged !== undefined) {
        synth.onvoiceschanged = function() {};
    }
})();
