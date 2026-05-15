/**
 * Wizard onboarding — JS minimal.
 * / Onboarding wizard — minimal JS.
 *
 * LOCALISATION : onboard/static/onboard/wizard.js
 *
 * Roles :
 * 1. Auto-tab entre les 6 inputs OTP de l'etape 2 (si template "6 inputs"
 *    detecte ; sinon no-op, ce qui est le cas actuel avec un seul input OTP).
 * 2. Rotation auto du carrousel d'info a l'etape 6 (5s par card).
 *
 * / Roles:
 * / 1. Auto-tab between the 6 OTP inputs of step 2 (only if a 6-input layout
 * /    is detected; otherwise no-op, which is the current case with a single OTP input).
 * / 2. Auto-rotate info carousel on step 6 (5s per card).
 *
 * FALC : pas de framework, pas de dependance, code lisible par n'importe quel
 * developpeur. Toute la logique tient dans une IIFE et expose rien au global.
 * / FALC: no framework, no dependency, code readable by any developer.
 * / All logic lives in an IIFE and exposes nothing to the global scope.
 */
(function () {
    "use strict";

    // 1. Auto-tab OTP + paste handler + sync hidden (6 inputs successifs)
    //    Comportements gerees :
    //    - Saisie d'un chiffre -> focus sur la case suivante.
    //    - Backspace sur case vide -> focus sur la case precedente.
    //    - Coller un code 6 chiffres dans n'importe quelle case -> repartir
    //      sur les 6 cases. Fix du bug : avant, seule la 1e case etait remplie.
    //    - Apres toute mise a jour, on concatene les 6 chiffres dans
    //      l'input cache `#id_otp_hidden` (l'input reellement envoye).
    //    / Auto-tab OTP + paste handler + hidden sync (6 inputs).
    //    Behaviours:
    //    - Typing a digit -> focus next cell.
    //    - Backspace on empty cell -> focus previous cell.
    //    - Pasting a 6-digit code in any cell -> spread across the 6 cells
    //      (fixes: previously only the first cell was filled).
    //    - After any update, concatenate digits into `#id_otp_hidden`
    //      (the input actually sent to the server).
    function setupOtpAutoTab() {
        const inputs = document.querySelectorAll('input[data-testid^="onboard-verify-otp-"]');
        // Si on n'a pas exactement 6 inputs, on ne fait rien (defense).
        // / If we don't have exactly 6 inputs, do nothing (defensive).
        if (inputs.length !== 6) {
            return;
        }
        const hiddenInput = document.getElementById("id_otp_hidden");

        // Met a jour l'input cache avec la concatenation des 6 chiffres.
        // / Update the hidden input with the concatenation of the 6 digits.
        function syncHidden() {
            if (!hiddenInput) {
                return;
            }
            hiddenInput.value = Array.from(inputs).map((el) => el.value).join("");
        }

        // Distribue une chaine de chiffres a partir de l'index `startIdx`.
        // Renvoie l'index de la derniere case remplie (pour focus).
        // / Spread a digit string across cells starting at `startIdx`.
        // Returns the index of the last filled cell (for focus).
        function spreadDigits(digits, startIdx) {
            let lastFilled = startIdx;
            for (let i = 0; i < digits.length && (startIdx + i) < inputs.length; i++) {
                inputs[startIdx + i].value = digits[i];
                lastFilled = startIdx + i;
            }
            return lastFilled;
        }

        inputs.forEach((input, idx) => {
            // Saisie clavier (1 chiffre) : focus suivant + sync.
            // / Keyboard input (1 digit): focus next + sync.
            input.addEventListener("input", (e) => {
                const value = e.target.value;
                if (value.length === 1 && idx < 5) {
                    inputs[idx + 1].focus();
                }
                syncHidden();
            });

            // Backspace sur case vide -> focus precedent.
            // / Backspace on empty cell -> focus previous.
            input.addEventListener("keydown", (e) => {
                if (e.key === "Backspace" && !e.target.value && idx > 0) {
                    inputs[idx - 1].focus();
                }
            });

            // Collage : on intercepte avant que le browser n'ecrive 6 chiffres
            // dans une seule case. On extrait les chiffres et on les distribue.
            // / Paste: intercept before the browser writes all digits into one
            // cell. Extract digits and spread them across cells.
            input.addEventListener("paste", (e) => {
                const pasted = (e.clipboardData || window.clipboardData).getData("text") || "";
                const digits = pasted.replace(/\D/g, "").slice(0, inputs.length - idx);
                if (digits.length === 0) {
                    return;
                }
                e.preventDefault();
                const last = spreadDigits(digits, idx);
                // Focus sur la case suivant la derniere remplie, ou la
                // derniere case si on a rempli jusqu'au bout.
                // / Focus next cell after the last filled, or last cell.
                const focusTarget = Math.min(last + 1, inputs.length - 1);
                inputs[focusTarget].focus();
                syncHidden();
            });
        });

        // Sync initial (cas : valeurs pre-remplies par le browser autofill).
        // / Initial sync (case: cells prefilled by browser autofill).
        syncHidden();
    }

    // 2. Apercu dynamique du domaine sur l'etape 1 (slug + suffixe DNS)
    //    Slugifie le nom du lieu et met a jour le suffixe quand le select DNS change.
    //    / Live domain preview on step 1 (slug + DNS suffix).
    //    / Slugifies the venue name and updates the suffix when the DNS select changes.
    function slugify(value) {
        // Slug FALC : minuscules, sans accents, espaces/non-alphanum -> "-".
        // / FALC slug: lowercase, accent-stripped, non-alphanum -> "-".
        return value
            .toString()
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "")
            .toLowerCase()
            .trim()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }

    function setupDomainPreview() {
        const nameInput = document.getElementById("onboard-id-name");
        const dnsSelect = document.getElementById("onboard-id-dns");
        const slugEl = document.getElementById("onboard-id-domain-slug");
        const suffixEl = document.getElementById("onboard-id-domain-suffix");
        if (!nameInput || !dnsSelect || !slugEl || !suffixEl) {
            return;
        }
        function update() {
            const s = slugify(nameInput.value);
            slugEl.textContent = s || "…";
            suffixEl.textContent = "." + dnsSelect.value;
        }
        nameInput.addEventListener("input", update);
        dnsSelect.addEventListener("change", update);
        // Initialisation (cas : champs deja remplis au reload, ex. erreurs 422).
        // / Init (case: fields prefilled on reload, e.g. 422 errors).
        update();
    }

    // 3. Rotation du carrousel d'info (etape 6)
    //    On garde une reference au `setInterval` et on le clear sur
    //    `beforeunload` pour ne pas laisser de timer fantome quand la page
    //    se ferme. Aussi : on respecte `prefers-reduced-motion` en stoppant
    //    la rotation pour les utilisateurs qui ont demande peu de motion.
    //    / Info carousel rotation (step 6). Keep the `setInterval` ref to
    //    clear it on `beforeunload`, avoiding ghost timers on page close.
    //    Also respects `prefers-reduced-motion`.
    function setupCarousel() {
        const cards = document.querySelectorAll(".onboard-carousel-card");
        if (cards.length === 0) {
            return;
        }
        let i = 0;
        cards[i].classList.add("is-active");
        // Si l'utilisateur a active "reduce motion", on affiche la 1e card
        // et on laisse l'utilisateur lire — pas de rotation auto.
        // / If the user prefers reduced motion, show the first card and let
        // them read — no auto rotation.
        const reduceMotion = window.matchMedia
            && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (reduceMotion) {
            return;
        }
        const intervalId = setInterval(() => {
            cards[i].classList.remove("is-active");
            i = (i + 1) % cards.length;
            cards[i].classList.add("is-active");
        }, 5000);
        // Cleanup explicite sur unload : evite d'accumuler des timers si
        // l'utilisateur navigue en SPA ou si HTMX swap le contenu.
        // / Explicit cleanup on unload: avoids accumulating timers across
        // SPA-like navigation or HTMX swaps.
        window.addEventListener("beforeunload", () => clearInterval(intervalId), { once: true });
    }

    document.addEventListener("DOMContentLoaded", () => {
        setupOtpAutoTab();
        setupDomainPreview();
        setupCarousel();
    });
})();
