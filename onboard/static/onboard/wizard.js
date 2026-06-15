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

    // Exposition globale du slugify pour reutilisation par le JS inline de
    // 03_venue.html (etape « Votre lieu ») — evite de dupliquer la fonction.
    // L'ancien apercu de domaine de l'etape 1 (`setupDomainPreview`) a ete
    // retire : le nom et le domaine ne sont plus saisis sur l'identite.
    // / Global slugify export for reuse by 03_venue.html (avoids duplication).
    // The old step-1 domain preview (`setupDomainPreview`) was removed: the
    // name and domain are no longer on the identity step.
    window.tibilletSlugify = slugify;

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

    // 4. Cooldown visuel sur le bouton "Renvoyer le code" (etape 2)
    //    Quand l'utilisateur clique le bouton, le serveur applique un
    //    cooldown de 60s (cf. OTP_RESEND_COOLDOWN_SECONDS dans
    //    onboard/views.py). On miroite ce cooldown cote UI : le bouton
    //    est desactive et son label affiche un decompte "Renvoyer le code
    //    (Xs)". L'utilisateur sait qu'il doit patienter au lieu de
    //    recliquer en boucle et se prendre des 429.
    //
    //    Logique 100% cote JS (pas de modif serveur) : on demarre le
    //    timer apres la reponse HTMX (200 envoi reussi OU 429 cooldown
    //    deja actif sur le serveur — dans les deux cas, l'utilisateur
    //    doit attendre 60s avant de pouvoir recliquer).
    //
    //    / Visual cooldown on the "Resend code" button (step 2). Mirrors
    //    the server-side 60s cooldown (cf. OTP_RESEND_COOLDOWN_SECONDS in
    //    onboard/views.py). Button gets disabled with a "Resend code (Xs)"
    //    countdown label. Triggers on both 200 (sent) and 429 (server
    //    cooldown already active) — both cases require a 60s wait.
    function setupResendCooldown() {
        const resendBtn = document.querySelector('[data-testid="onboard-verify-resend"]');
        if (!resendBtn) {
            return;
        }

        // Doit rester aligne sur OTP_RESEND_COOLDOWN_SECONDS cote serveur.
        // / Must stay aligned with OTP_RESEND_COOLDOWN_SECONDS server-side.
        const cooldownSeconds = 60;

        // On sauvegarde le HTML original du bouton (icone + texte traduit
        // par Django). On extrait aussi le texte brut pour le reinjecter
        // dans le label avec le decompte. textContent ne contient pas
        // l'icone (les icones bi-* sont des pseudo-elements), donc trim()
        // donne directement "Renvoyer le code" / "Resend the code" selon
        // la langue active.
        // / Save original HTML (icon + Django-translated text). Also
        // extract the raw text to reuse in the countdown label. textContent
        // does not include the icon (bi-* icons are pseudo-elements), so
        // trim() yields "Renvoyer le code" / "Resend the code" depending
        // on the active language.
        const originalHtml = resendBtn.innerHTML;
        const baseText = resendBtn.textContent.trim();

        // Reference de l'interval pour permettre un cleanup propre si la
        // page se ferme avant la fin du decompte.
        // / Interval ref for clean teardown on page unload.
        let intervalId = null;

        function startCooldown() {
            // Defense : si un decompte est deja en cours, on ne le redemarre
            // pas (cas : double `htmx:afterRequest` sur la meme reponse).
            // / Defensive: don't restart an in-flight countdown.
            if (intervalId !== null) {
                return;
            }
            let remaining = cooldownSeconds;
            resendBtn.disabled = true;
            // `disabled` natif suffit pour l'a11y (le screen reader annonce
            // "button, dimmed"). On ajoute la classe Bootstrap pour le
            // visuel grise. / `disabled` is enough for a11y; we add the
            // Bootstrap class for visual feedback.
            resendBtn.classList.add("disabled");

            // Construit le label avec icone hourglass + texte original +
            // decompte. L'icone hourglass remplace l'icone arrow-clockwise
            // pour signaler visuellement "attente". / Build label with
            // hourglass icon + original text + countdown. Hourglass icon
            // replaces the arrow-clockwise to signal "waiting".
            function renderLabel() {
                resendBtn.innerHTML =
                    '<i class="bi bi-hourglass-split me-1" aria-hidden="true"></i>'
                    + baseText + ' (' + remaining + 's)';
            }
            renderLabel();

            intervalId = setInterval(function () {
                remaining -= 1;
                if (remaining <= 0) {
                    // Fin du cooldown : restaure l'etat initial du bouton.
                    // / End of cooldown: restore the original button state.
                    clearInterval(intervalId);
                    intervalId = null;
                    resendBtn.disabled = false;
                    resendBtn.classList.remove("disabled");
                    resendBtn.innerHTML = originalHtml;
                } else {
                    renderLabel();
                }
            }, 1000);
        }

        // On ecoute `htmx:afterRequest` plutot que `click` : on attend la
        // reponse serveur avant de demarrer le timer. Si la requete echoue
        // (reseau coupe, status 5xx), on ne demarre pas — l'utilisateur
        // peut reessayer immediatement.
        // / Listen on `htmx:afterRequest` (not `click`): start the timer
        // only after the server responds. Don't start on network error
        // or 5xx — the user should be able to retry immediately.
        resendBtn.addEventListener("htmx:afterRequest", function (event) {
            const status = event.detail.xhr.status;
            // 200 = envoi reussi, 429 = cooldown deja actif cote serveur
            // (autre tab, ou refresh apres clic recent). Dans les 2 cas
            // on miroite le cooldown 60s cote UI.
            // / 200 = sent; 429 = server cooldown already active (other
            // tab, refresh after recent click). Both mirror the 60s wait.
            if (status === 200 || status === 429) {
                startCooldown();
            }
        });

        // Cleanup : si l'utilisateur ferme la page pendant le decompte,
        // on libere le setInterval pour ne pas laisser de timer fantome.
        // / Cleanup: clear the interval on page unload to avoid ghost timers.
        window.addEventListener("beforeunload", function () {
            if (intervalId !== null) {
                clearInterval(intervalId);
                intervalId = null;
            }
        }, { once: true });
    }

    document.addEventListener("DOMContentLoaded", () => {
        setupOtpAutoTab();
        setupCarousel();
        setupResendCooldown();
    });
})();
