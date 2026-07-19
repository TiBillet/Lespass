/*
 * Sommaire : souligne l'entree de la section en cours de lecture.
 * / Table of contents: highlights the entry of the section being read.
 *
 * LOCALISATION : pages/static/pages/js/sommaire_actif.js
 *
 * Le sommaire de la colonne de droite liste les titres de la page. Sans ce
 * script il reste une liste de liens inerte : le lecteur ne sait pas ou il en
 * est dans un article long. Le script marque l'entree correspondant au titre
 * actuellement lu.
 * / The right-hand table of contents lists the page headings. Without this
 * script it stays an inert list of links: the reader cannot tell where they
 * are in a long article. This script marks the entry matching the heading
 * currently being read.
 *
 * POURQUOI IntersectionObserver ET NON UN ECOUTEUR DE DEFILEMENT : un
 * `scroll` se declenche des dizaines de fois par seconde et impose de mesurer
 * la position de chaque titre a chaque appel, ce qui fait ramer la page sur un
 * article long. L'observateur, lui, ne parle au script que lorsqu'un titre
 * franchit la zone surveillee.
 * / WHY IntersectionObserver AND NOT A SCROLL LISTENER: `scroll` fires dozens
 * of times per second and forces measuring every heading each time, which
 * janks long articles. The observer only speaks when a heading crosses the
 * watched band.
 *
 * DEGRADATION : sans JavaScript, le sommaire reste une liste de liens qui
 * fonctionne. Rien n'est casse, seule la mise en valeur manque.
 * / DEGRADATION: without JavaScript the ToC stays a working list of links.
 */

(function () {
    "use strict";

    function activerLeSommaire() {
        var sommaire = document.querySelector(".tb-sommaire");
        if (!sommaire) {
            return;  // Page sans sommaire : rien a faire. / No ToC: nothing to do.
        }

        // Chaque entree du sommaire pointe vers l'ancre d'un titre : on relie
        // l'identifiant du titre a son entree, une fois pour toutes.
        // / Each ToC entry points at a heading's anchor: map heading id to entry.
        var entreeParAncre = {};
        var titresSurveilles = [];

        sommaire.querySelectorAll(".tb-sommaire__entree a").forEach(function (lien) {
            var ancre = decodeURIComponent((lien.getAttribute("href") || "").replace("#", ""));
            if (!ancre) {
                return;
            }
            var titre = document.getElementById(ancre);
            if (!titre) {
                return;  // Ancre orpheline : on l'ignore. / Orphan anchor: skip.
            }
            entreeParAncre[ancre] = lien.parentElement;
            titresSurveilles.push(titre);
        });

        if (titresSurveilles.length === 0) {
            return;
        }

        var CLASSE_ACTIVE = "tb-sommaire__entree--active";

        function marquerSeul(entreeActive) {
            Object.keys(entreeParAncre).forEach(function (ancre) {
                var entree = entreeParAncre[ancre];
                var estActive = entree === entreeActive;
                entree.classList.toggle(CLASSE_ACTIVE, estActive);
                // `aria-current` dit la meme chose aux lecteurs d'ecran que la
                // couleur dit a l'oeil. / `aria-current` tells screen readers
                // what the colour tells the eye.
                var lien = entree.querySelector("a");
                if (lien) {
                    if (estActive) {
                        lien.setAttribute("aria-current", "true");
                    } else {
                        lien.removeAttribute("aria-current");
                    }
                }
            });
        }

        // On surveille une BANDE etroite en haut de l'ecran plutot que tout le
        // viewport : le titre actif est celui qui vient de passer sous l'entete,
        // pas celui qui est visible quelque part. Sans cette marge negative en
        // bas, tous les titres d'un ecran seraient « visibles » a la fois et
        // l'entree active sauterait.
        // / We watch a narrow BAND at the top rather than the whole viewport:
        // the active heading is the one that just passed under the header. The
        // negative bottom margin keeps several headings from matching at once.
        var observateur = new IntersectionObserver(
            function (entrees) {
                // Parmi les titres ayant franchi la bande, le dernier dans
                // l'ordre du document est celui qu'on lit.
                // / Among headings crossing the band, the last one in document
                // order is the one being read.
                var visibles = titresSurveilles.filter(function (titre) {
                    var rect = titre.getBoundingClientRect();
                    return rect.top <= 120;
                });
                var courant = visibles.length ? visibles[visibles.length - 1] : titresSurveilles[0];
                marquerSeul(entreeParAncre[courant.id]);
            },
            { rootMargin: "-100px 0px -70% 0px", threshold: 0 }
        );

        titresSurveilles.forEach(function (titre) {
            observateur.observe(titre);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", activerLeSommaire);
    } else {
        activerLeSommaire();
    }

    // Le site navigue aussi par HTMX : apres un echange, le sommaire et les
    // titres de la nouvelle page remplacent les anciens, et les observateurs
    // poses sur les elements disparus ne servent plus.
    // / The site also navigates via HTMX: after a swap the ToC and headings are
    // replaced, and observers on the removed elements are useless.
    document.body.addEventListener("htmx:afterSwap", activerLeSommaire);
})();
