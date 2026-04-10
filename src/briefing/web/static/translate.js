(function() {
    'use strict';

    // Feature detection — Chrome 138+ only
    if (!('Translator' in self)) return;

    var translatorCache = {};  // keyed by "en->zh"
    var translating = new Set();  // track in-flight cards

    async function getTranslator(from, to) {
        var key = from + '->' + to;
        if (translatorCache[key]) return translatorCache[key];

        try {
            var translator = await Translator.create({
                sourceLanguage: from,
                targetLanguage: to,
            });
            translatorCache[key] = translator;
            return translator;
        } catch (e) {
            console.warn('Translator creation failed:', e);
            return null;
        }
    }

    async function translateCard(card, btn) {
        var cardId = card.dataset.storyIndex || Math.random().toString();
        if (translating.has(cardId)) return;
        translating.add(cardId);

        // Determine direction
        var pageLang = document.documentElement.lang || 'en';
        var from = pageLang === 'zh' ? 'zh' : 'en';
        var to = from === 'en' ? 'zh' : 'en';

        // Check if already translated (toggle back)
        if (card.dataset.translated === to) {
            restoreCard(card);
            btn.textContent = '\u{1F310}';
            btn.classList.remove('translate-active');
            translating.delete(cardId);
            return;
        }

        btn.textContent = '\u23F3';  // hourglass
        btn.classList.add('translate-active');

        var translator = await getTranslator(from, to);
        if (!translator) {
            btn.textContent = '\u274C';  // X mark
            setTimeout(function() { btn.textContent = '\u{1F310}'; btn.classList.remove('translate-active'); }, 2000);
            translating.delete(cardId);
            return;
        }

        // Save originals before translating
        saveOriginals(card);

        // Translate each target element
        var targets = [
            { el: card.querySelector('h3'), field: 'headline' },
            { el: card.querySelector('.news-summary'), field: 'summary' },
            { el: card.querySelector('.bias-analysis'), field: 'bias' },
        ];

        // Key facts
        var factEls = card.querySelectorAll('.news-facts li');

        try {
            for (var i = 0; i < targets.length; i++) {
                var t = targets[i];
                if (!t.el) continue;
                var original = t.el.dataset.originalText || t.el.textContent;
                // Skip short strings and ticker badges
                if (original.length < 10) continue;

                // For h3, strip the TTS button text
                var text = original;
                if (t.field === 'headline') {
                    text = text.replace(/[\u{1F508}\u{1F509}\u{1F50A}\u23F9\u{1F310}\u23F3]/gu, '').trim();
                }
                if (t.field === 'bias') {
                    // Keep "Bias check:" prefix, translate the rest
                    var prefix = text.match(/^[^:]+:\s*/);
                    if (prefix) {
                        var rest = text.substring(prefix[0].length);
                        var translated = await translator.translate(rest);
                        t.el.innerHTML = '<strong>' + (to === 'zh' ? '\u504f\u89c1\u68c0\u67e5:' : 'Bias check:') + '</strong> ' + escapeHtml(translated);
                        continue;
                    }
                }

                var translated = await translator.translate(text);
                if (t.field === 'headline') {
                    // Preserve TTS button
                    var ttsBtn = t.el.querySelector('.tts-btn');
                    t.el.textContent = translated + ' ';
                    if (ttsBtn) t.el.appendChild(ttsBtn);
                } else {
                    t.el.textContent = translated;
                }
            }

            // Translate facts
            for (var j = 0; j < factEls.length; j++) {
                var factText = factEls[j].textContent.trim();
                if (factText.length < 5) continue;
                var translatedFact = await translator.translate(factText);
                factEls[j].textContent = translatedFact;
            }

            card.dataset.translated = to;
            btn.textContent = '\u{1F310}';
        } catch (e) {
            console.warn('Translation failed:', e);
            restoreCard(card);
            btn.textContent = '\u274C';
            setTimeout(function() { btn.textContent = '\u{1F310}'; btn.classList.remove('translate-active'); }, 2000);
        }

        translating.delete(cardId);
    }

    function saveOriginals(card) {
        if (card.dataset.originalsStored) return;
        var els = card.querySelectorAll('h3, .news-summary, .bias-analysis, .news-facts li');
        els.forEach(function(el) {
            el.dataset.originalHtml = el.innerHTML;
            el.dataset.originalText = el.textContent;
        });
        card.dataset.originalsStored = '1';
    }

    function restoreCard(card) {
        var els = card.querySelectorAll('[data-original-html]');
        els.forEach(function(el) {
            el.innerHTML = el.dataset.originalHtml;
        });
        delete card.dataset.translated;
    }

    function escapeHtml(text) {
        var d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    // Inject translate buttons into news cards
    function injectButtons() {
        var cards = document.querySelectorAll('.news-card');
        cards.forEach(function(card) {
            if (card.querySelector('.translate-btn')) return;
            var header = card.querySelector('.news-card-header h3');
            if (!header) return;

            var btn = document.createElement('button');
            btn.className = 'translate-btn tts-btn';
            btn.type = 'button';
            btn.textContent = '\u{1F310}';  // globe
            btn.title = 'Translate';
            btn.setAttribute('aria-label', 'Translate');
            header.appendChild(btn);
        });
    }

    // Event delegation
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.translate-btn');
        if (!btn) return;
        e.preventDefault();
        var card = btn.closest('.news-card');
        if (card) translateCard(card, btn);
    });

    // Inject on load and after HTMX swaps
    injectButtons();
    document.addEventListener('htmx:afterSwap', function() {
        setTimeout(injectButtons, 100);
    });
})();
