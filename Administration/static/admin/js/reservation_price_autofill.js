/**
 * Auto-remplissage du "Prix par billet" sur le formulaire d'ajout de réservation
 * / Per-ticket price autofill on the reservation add form
 *
 * LOCALISATION : Administration/static/admin/js/reservation_price_autofill.js
 *
 * Chargé par ReservationAddAdmin (class Media) sur /admin/BaseBillet/reservation/add/.
 *
 * Comportement :
 * - À la sélection d'un tarif, le champ "Prix par billet" se pré-remplit avec
 *   le prix du tarif.
 * - Pour un tarif à prix libre, le champ est vidé et rendu OBLIGATOIRE.
 * - Un libellé "prix € × quantité = total €" rappelle que le prix est PAR billet.
 *
 * Données : le <select> du tarif porte un attribut data-prices (JSON) :
 *   { "event_uuid:price_uuid": { "prix": 12.0, "libre": false }, ... }
 */
(function () {
    "use strict";

    function init() {
        // Champs du formulaire (ids Django par défaut).
        // / Form fields (default Django ids).
        var selectTarif = document.getElementById("id_price");
        var champMontant = document.getElementById("id_amount");
        var champQuantite = document.getElementById("id_quantity");

        // Si un champ manque, on n'est pas sur le bon formulaire : on s'arrête.
        // / If a field is missing, we are not on the right form: stop.
        if (!selectTarif || !champMontant) {
            return;
        }

        // Lecture du mapping {valeur: {prix, libre}} injecté par le serveur.
        // / Read the {value: {prix, libre}} mapping injected by the server.
        var prixParTarif = {};
        try {
            prixParTarif = JSON.parse(selectTarif.getAttribute("data-prices") || "{}");
        } catch (e) {
            prixParTarif = {};
        }

        // Libellé "Total" affiché sous le champ montant, pour bien rappeler que
        // le prix saisi est PAR billet.
        // / "Total" label shown below the amount field to stress it is PER ticket.
        var libelleTotal = document.createElement("div");
        libelleTotal.style.marginTop = "4px";
        libelleTotal.style.fontSize = "0.85em";
        libelleTotal.style.opacity = "0.8";
        libelleTotal.setAttribute("data-testid", "reservation-total-hint");
        champMontant.parentNode.appendChild(libelleTotal);

        // Quantité courante (au moins 1).
        // / Current quantity (at least 1).
        function quantiteCourante() {
            var q = parseInt(champQuantite ? champQuantite.value : "1", 10);
            return (isNaN(q) || q < 1) ? 1 : q;
        }

        // Met à jour le libellé "prix € × quantité = total €".
        // / Updates the "price € × quantity = total €" label.
        function mettreAJourTotal() {
            var prixUnitaire = parseFloat(champMontant.value);
            if (isNaN(prixUnitaire)) {
                libelleTotal.textContent = "";
                return;
            }
            var q = quantiteCourante();
            var total = prixUnitaire * q;
            libelleTotal.textContent =
                prixUnitaire.toFixed(2) + " € × " + q + " = " + total.toFixed(2) + " € au total";
        }

        // Applique le tarif sélectionné au champ montant.
        // / Applies the selected rate to the amount field.
        function appliquerTarif() {
            var infos = prixParTarif[selectTarif.value];
            if (infos && infos.libre) {
                // Prix libre : on vide et on rend obligatoire.
                // / Open price: clear and make required.
                champMontant.value = "";
                champMontant.setAttribute("required", "required");
            } else if (infos) {
                // Tarif fixe : on pré-remplit avec le prix du tarif.
                // / Fixed rate: prefill with the rate price.
                champMontant.value = Number(infos.prix).toFixed(2);
                champMontant.removeAttribute("required");
            } else {
                // Aucun tarif (option vide) : pas d'obligation.
                // / No rate (empty option): not required.
                champMontant.removeAttribute("required");
            }
            mettreAJourTotal();
        }

        // Le select est un Select2 : il déclenche un event jQuery "change".
        // On écoute via jQuery si disponible (sinon fallback natif).
        // / The select is a Select2: it fires a jQuery "change" event.
        //   Listen via jQuery if available (native fallback otherwise).
        var jq = (window.django && window.django.jQuery) ? window.django.jQuery : window.jQuery;
        if (jq) {
            jq(selectTarif).on("change", appliquerTarif);
        } else {
            selectTarif.addEventListener("change", appliquerTarif);
        }
        champMontant.addEventListener("input", mettreAJourTotal);
        if (champQuantite) {
            champQuantite.addEventListener("input", mettreAJourTotal);
        }

        // Application initiale (utile si un tarif est déjà sélectionné).
        // / Initial run (useful if a rate is already selected).
        appliquerTarif();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
