/**
 * Ajuste la hauteur des iframes d'apercu des blocs a leur contenu
 * / Fits block preview iframes to their content height
 *
 * LOCALISATION : pages/static/pages/admin/apercu.js
 *
 * Charge par :
 * - admin/pages/bloc/apercu_panneau.html (apercu en direct, fiche Bloc) ;
 * - admin/pages/page/blocs_de_la_page.html (toute la page, une iframe).
 *
 * Une iframe ne prend pas la hauteur de son contenu toute seule. Les apercus
 * sont de meme origine que l'admin (srcdoc ou URL de l'admin) : on peut donc
 * lire la hauteur de l'element [data-apercu-contenu] du document.
 * Un ResizeObserver suit ensuite le contenu (images qui se chargent, carte
 * Leaflet, polices).
 *
 * Anti-saut : le conteneur de l'iframe garde sa derniere hauteur (min-height).
 * Quand htmx remplace l'iframe de l'apercu en direct, la page ne « saute » pas
 * pendant que le nouveau document se charge.
 *
 * Aucune logique metier ici : uniquement de l'affichage.
 * / UI only. Same-origin iframes: read [data-apercu-contenu] height, follow it
 * with a ResizeObserver, keep the container's last height to avoid jumps.
 */
(function () {
    // Le script peut etre inclus deux fois (deux gabarits) : un seul
    // branchement. Le drapeau vit dans un data-* du document, pas dans une
    // variable globale window.xxx. / Register only once; the flag is a data-*
    // attribute, not a window global.
    var racine = document.documentElement;
    if (racine.dataset.apercuBlocsBranche === "oui") {
        return;
    }
    racine.dataset.apercuBlocsBranche = "oui";

    function ajusterHauteur(iframe) {
        var documentApercu;
        try {
            documentApercu = iframe.contentDocument;
        } catch (erreur) {
            // Origine differente : on laisse la hauteur minimale.
            // / Different origin: keep the minimum height.
            return;
        }
        if (!documentApercu || !documentApercu.body) {
            return;
        }
        var contenu = documentApercu.querySelector("[data-apercu-contenu]") || documentApercu.body;
        var bas_du_contenu = contenu.getBoundingClientRect().bottom;
        var hauteur = Math.max(Math.ceil(bas_du_contenu), 80);
        iframe.style.height = hauteur + "px";
        if (iframe.parentElement) {
            iframe.parentElement.style.minHeight = hauteur + "px";
        }
    }

    function brancherIframe(iframe) {
        ajusterHauteur(iframe);
        try {
            var fenetreApercu = iframe.contentWindow;
            var contenu = iframe.contentDocument.querySelector("[data-apercu-contenu]");
            if (contenu && fenetreApercu && fenetreApercu.ResizeObserver) {
                var observateur = new fenetreApercu.ResizeObserver(function () {
                    ajusterHauteur(iframe);
                });
                observateur.observe(contenu);
            }
        } catch (erreur) {
            // Rien a observer. / Nothing to observe.
        }
    }

    // L'evenement `load` ne remonte pas : on l'ecoute en phase de capture pour
    // attraper aussi les iframes ajoutees plus tard par htmx.
    // / `load` does not bubble: listen in capture phase to also catch iframes
    // added later by htmx.
    document.addEventListener(
        "load",
        function (evenement) {
            var cible = evenement.target;
            if (cible && cible.tagName === "IFRAME" && cible.hasAttribute("data-apercu-iframe")) {
                brancherIframe(cible);
            }
        },
        true
    );

    // Menu « + Ajouter en tete » (fiche Page) : il se ferme au clic a cote,
    // ou avec Echap (le focus revient sur son bouton). Meme regle que dans
    // l'iframe (apercu_page_outils.js). / The "+ Add at top" menu closes on
    // outside click or Escape.
    document.addEventListener("click", function (evenement) {
        var menus_ouverts = document.querySelectorAll("details[data-menu-modeles][open]");
        for (var n = 0; n < menus_ouverts.length; n++) {
            if (!menus_ouverts[n].contains(evenement.target)) {
                menus_ouverts[n].open = false;
            }
        }
    });
    document.addEventListener("keydown", function (evenement) {
        if (evenement.key !== "Escape") {
            return;
        }
        var menus_ouverts = document.querySelectorAll("details[data-menu-modeles][open]");
        for (var n = 0; n < menus_ouverts.length; n++) {
            menus_ouverts[n].open = false;
            menus_ouverts[n].querySelector("summary").focus();
        }
    });

    // Une iframe peut avoir fini de charger AVANT que ce script s'execute
    // (il est pose apres elle dans la page) : son evenement `load` est alors
    // deja passe. On branche donc aussi celles qui sont deja pretes.
    // / An iframe may finish loading BEFORE this script runs: its `load` event
    // is gone. Also hook the iframes that are already complete.
    var iframes_deja_presentes = document.querySelectorAll("iframe[data-apercu-iframe]");
    for (var i = 0; i < iframes_deja_presentes.length; i++) {
        var iframe_presente = iframes_deja_presentes[i];
        try {
            var document_de_l_iframe = iframe_presente.contentDocument;
            var est_chargee =
                document_de_l_iframe &&
                document_de_l_iframe.readyState === "complete" &&
                document_de_l_iframe.querySelector("[data-apercu-contenu]");
            if (est_chargee) {
                brancherIframe(iframe_presente);
            }
        } catch (erreur) {
            // Pas encore accessible : l'evenement `load` s'en chargera.
            // / Not accessible yet: the `load` event will handle it.
        }
    }
})();
