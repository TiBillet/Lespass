/**
 * Pilotage de l'ecran de la borne : montant selectionne et theme jour/nuit.
 * / Kiosk screen driver: selected amount and light/dark theme.
 *
 * LOCALISATION : kiosk/static/kiosk/js/main.js
 *
 * Charge par kiosk/templates/kiosk/base.html, APRES nfc.js (qui definit
 * NfcReader) et APRES htmx.
 *
 * CE QUE CE FICHIER NE FAIT PAS / What this file does NOT do :
 * - Il n'ecrit aucun style en ligne. Le theme est une valeur de `data-theme`
 *   sur <html> ; tout le reste est du CSS (kiosk.css). L'ancienne version
 *   posait des `element.style.backgroundColor = "#3a3a3a"` qui gagnaient
 *   toujours la cascade et ne se nettoyaient jamais completement.
 * - Il n'ecrit aucun texte visible. Les libelles du bouton de theme sont dans
 *   partial/topbar.html, traduits. L'ancienne version faisait
 *   `button.innerHTML = 'Mode Jour'` : l'anglais etait perdu.
 * - Il ne gere plus le compte a rebours des ecrans finaux : il vit dans
 *   partial/state_screen.html. Les deux exemplaires tournaient en meme temps
 *   sur le meme #countdown, et le decompte tombait deux fois par seconde.
 *
 * / It writes no inline styles, no visible text, and no countdown: those three
 * responsibilities moved to CSS, to the templates, and to state_screen.html.
 */

// Lecteur NFC, partage avec sweet_scan_button.html (rfid.startLecture / stopLecture).
// / NFC reader, shared with sweet_scan_button.html.
const rfid = new NfcReader();

// Montant courant, en euros. Globale volontaire : hx-vals la lit directement
// dans sweet_scan_button.html (`js:{"totalAmount": totalAmount}`).
// / Current amount in euros. Deliberately global: hx-vals reads it directly.
let totalAmount = 0;

const CLE_STOCKAGE_THEME = "kiosk-theme";


/* ------------------------------------------------------------------------- */
/* Montant                                                                    */
/* ------------------------------------------------------------------------- */

/**
 * Reporte le montant courant sur tous les afficheurs de la page.
 * / Mirrors the current amount onto every display on the page.
 *
 * Il y en a deux : le grand afficheur a gauche et le rappel dans le bouton
 * Valider. Ils portent tous les deux l'attribut [data-total-display], ce qui
 * evite deux ids identiques dans le DOM.
 * / There are two: the big readout on the left and the reminder inside the
 * Validate button. Both carry [data-total-display], which avoids a duplicate id.
 */
function rafraichirLesAffichagesDuMontant() {
    const afficheurs = document.querySelectorAll("[data-total-display]");
    afficheurs.forEach(function (afficheur) {
        afficheur.textContent = `${totalAmount}`;
    });

    // L'afficheur passe en gris quand rien n'est selectionne : le zero recule
    // au lieu de crier. / The readout greys out when nothing is selected.
    const zoneAfficheur = document.querySelector("[data-total-empty]");
    if (zoneAfficheur) {
        zoneAfficheur.dataset.totalEmpty = (totalAmount === 0) ? "true" : "false";
    }

    // Le bouton reste cliquable (hx-trigger vit dessus) mais s'annonce inerte
    // tant qu'aucun montant n'est choisi. La garde reelle est dans readNfc().
    // / The button stays clickable (hx-trigger lives on it) but announces itself
    // inert while no amount is chosen. The real guard is in readNfc().
    const boutonValider = document.getElementById("scan_button");
    if (boutonValider) {
        boutonValider.setAttribute("aria-disabled", (totalAmount === 0) ? "true" : "false");
    }
}

/**
 * Ajoute un montant au total. Appele par les touches du pave.
 * / Adds an amount to the total. Called by the keypad keys.
 *
 * @param {number} montantEnEuros - 1, 5, 10, 20 ou 50
 */
function selectAmount(montantEnEuros) {
    totalAmount += montantEnEuros;
    rafraichirLesAffichagesDuMontant();
}

/**
 * Remet le total a zero. Appele par la touche Effacer et par
 * sweet_scan_button.html quand le modal de scan est annule ou expire.
 * / Resets the total. Called by the Clear key and by sweet_scan_button.html.
 */
function clearAmount() {
    totalAmount = 0;
    rafraichirLesAffichagesDuMontant();
}


/* ------------------------------------------------------------------------- */
/* Theme jour / nuit                                                          */
/* ------------------------------------------------------------------------- */

/**
 * Applique un theme et met a jour l'etat annonce du bouton.
 * / Applies a theme and updates the button's announced state.
 *
 * Le CSS fait tout le reste (kiosk.css section 6 : il montre le bon libelle et
 * la bonne icone selon :root[data-theme]).
 * / The CSS does everything else.
 *
 * @param {string} nomDuTheme - "light" ou "dark"
 */
function appliquerLeTheme(nomDuTheme) {
    document.documentElement.dataset.theme = nomDuTheme;

    const boutonTheme = document.getElementById("toggleDarkModeBtn");
    if (boutonTheme) {
        boutonTheme.setAttribute("aria-pressed", (nomDuTheme === "dark") ? "true" : "false");
    }
}

/**
 * Bascule entre le jour et la nuit, et memorise le choix.
 * / Toggles between day and night, and remembers the choice.
 *
 * Appele par le onclick du bouton dans partial/topbar.html.
 */
function toggleDarkMode() {
    const themeActuel = document.documentElement.dataset.theme;
    const themeSuivant = (themeActuel === "dark") ? "light" : "dark";

    appliquerLeTheme(themeSuivant);

    try {
        localStorage.setItem(CLE_STOCKAGE_THEME, themeSuivant);
    } catch (erreurStockage) {
        // Navigation privee ou WebView verrouillee : le theme s'applique quand
        // meme, il ne survivra simplement pas au rechargement.
        // / Private browsing or locked-down WebView: the theme still applies, it
        // just will not survive a reload.
        console.warn("Theme non memorise :", erreurStockage);
    }
}


/* ------------------------------------------------------------------------- */
/* Amorcage                                                                   */
/* ------------------------------------------------------------------------- */

/**
 * Remet l'ecran dans un etat coherent.
 * / Brings the screen back to a coherent state.
 *
 * Appele au chargement, et apres chaque swap HTMX qui remplace #tb-kiosque.
 * Le theme est deja pose sur <html> par le script d'amorcage de base.html ; ici
 * on ne fait que resynchroniser aria-pressed sur le bouton fraichement swappe.
 * / Called on load and after every HTMX swap replacing #tb-kiosque. The theme is
 * already set on <html> by base.html's boot script; here we only resync
 * aria-pressed on the freshly swapped button.
 */
function initializePage() {
    const themeCourant = document.documentElement.dataset.theme || "light";
    appliquerLeTheme(themeCourant);

    // L'ecran de choix du montant vient d'etre (re)rendu : le serveur y affiche
    // 0, la variable JS doit repartir de 0 elle aussi. Les autres ecrans (attente,
    // reussite, annulation) n'ont pas d'afficheur : on ne touche a rien.
    // / The amount screen has just been (re)rendered: the server prints 0, so the
    // JS variable must restart at 0 too. Other screens have no display: no-op.
    const ecranDuMontantEstAffiche = document.querySelector("[data-total-display]") !== null;
    if (ecranDuMontantEstAffiche) {
        totalAmount = 0;
        rafraichirLesAffichagesDuMontant();
    }
}

document.addEventListener("DOMContentLoaded", initializePage);

// HTMX remplace #tb-kiosque : on reinitialise l'ecran fraichement injecte.
// / HTMX replaces #tb-kiosque: re-initialise the freshly injected screen.
document.addEventListener("htmx:afterSwap", function (evenementSwap) {
    const cible = evenementSwap.detail.target;
    const swapDansLaBorne = cible.id === "tb-kiosque" || cible.closest("#tb-kiosque") !== null;

    if (swapDansLaBorne) {
        initializePage();
    }
});
