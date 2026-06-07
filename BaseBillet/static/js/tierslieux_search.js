/**
 * Util partagé : recherche Tiers-Lieux avec débounce + spinner.
 * / Shared util: Tiers-Lieux search with debounce + spinner.
 *
 * LOCALISATION : BaseBillet/static/js/tierslieux_search.js
 *
 * Utilisé par le wizard event (_form_lieu.html) ET l'onboard (03_venue.html).
 * Gère le débounce, le basculement loupe <-> spinner pendant l'appel HTMX, et
 * un compteur pour les requêtes qui se chevauchent. Le DÉCLENCHEMENT (condition,
 * valeurs envoyées) reste à la charge de l'appelant : les deux contextes n'ont
 * pas la même règle (le wizard event ne cherche que si 0 adresse locale, etc.).
 *
 * / Used by the event wizard AND onboarding. Handles debounce, the magnifier
 * <-> spinner toggle during the HTMX call, and a counter for overlapping
 * requests. The caller decides WHEN to fire and WHICH values to send (the two
 * contexts have different rules).
 *
 * Usage :
 *   var recherche = creerRechercheTiersLieux({
 *       conteneur: "#id-resultats", url: "/.../search/",
 *       iconeLoupe: elLoupe, spinner: elSpinner, delai: 600
 *   });
 *   champ.addEventListener("input", function () {
 *       if (condition) { recherche.lancer({ q: terme }); }
 *       else { recherche.annuler(); conteneur.innerHTML = ""; }
 *   });
 */
window.creerRechercheTiersLieux = function (options) {
    var minuteur = null;
    var requetes_en_cours = 0;

    function majSpinner() {
        var actif = requetes_en_cours > 0;
        if (options.iconeLoupe) { options.iconeLoupe.style.display = actif ? "none" : "inline-block"; }
        if (options.spinner) { options.spinner.style.display = actif ? "inline-block" : "none"; }
    }

    return {
        // Lance une recherche (débounce). `values` = objet envoyé en query string.
        // / Fire a search (debounced). `values` = query object.
        lancer: function (values) {
            if (minuteur) { clearTimeout(minuteur); }
            minuteur = setTimeout(function () {
                // Spinner ON le temps de l'aller-retour vers l'API.
                // / Spinner ON during the API round-trip.
                requetes_en_cours += 1;
                majSpinner();
                var fin = function () { requetes_en_cours -= 1; majSpinner(); };
                htmx.ajax("GET", options.url, {
                    target: options.conteneur,
                    swap: "innerHTML",
                    values: values,
                }).then(fin, fin);
            }, options.delai || 600);
        },
        // Annule une recherche en attente (terme trop court, conditions non remplies).
        // / Cancel a pending search (term too short, condition not met).
        annuler: function () {
            if (minuteur) { clearTimeout(minuteur); }
        },
    };
};
