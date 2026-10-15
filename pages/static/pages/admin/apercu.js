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
 * Fiche Page : ouvre aussi la <dialog> du menu « + Ajouter un bloc »
 * (#dialog-menu-ajout, dans blocs_de_la_page.html), pour le bouton de
 * l'en-tete et pour le + de chaque barre. Le menu vit dans l'admin, pas dans
 * l'iframe, ou il serait coupe.
 *
 * COMMUNICATION :
 * Recoit : clic sur [data-ouvrir-menu-ajout] dans ce document (en-tete) ;
 * « apercu:ouvrir-menu-ajout » depuis apercu_page_outils.js (iframe), avec
 * detail.url_du_menu et detail.bouton_d_origine.
 *
 * Aucune logique metier ici : uniquement de l'affichage.
 * / UI only. Same-origin iframes: read [data-apercu-contenu] height, follow it
 * with a ResizeObserver, keep the container's last height to avoid jumps.
 * Also opens the Page form's "add a block" <dialog>.
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

    // Menu « + Ajouter un bloc » de la fiche Page : une seule <dialog>.
    // FLUX : deux boutons [data-ouvrir-menu-ajout] l'ouvrent.
    // - « + Ajouter un bloc en premier » (en-tete, dans ce document) : son
    //   clic est vu directement ici.
    // - le + de la barre d'un bloc (dans l'iframe) : apercu_page_outils.js
    //   emet « apercu:ouvrir-menu-ajout » sur ce document.
    // Les deux appellent ouvrirLeMenuDAjout : la <dialog> s'ouvre tout de
    // suite (texte « Chargement… »), puis htmx y charge la liste
    // (pages/admin_apercu.py:vue_menu_ajout).
    // / Two "+" buttons open the same <dialog>: the header one (clicked here)
    // and each block bar's one (event from the iframe). htmx loads the list.
    var dialog_menu_ajout = document.getElementById("dialog-menu-ajout");
    if (dialog_menu_ajout) {
        var liste_du_menu = document.getElementById("dialog-menu-ajout-liste");

        // Le + qui a ouvert la <dialog> : il recupere le focus a la fermeture.
        // Il peut vivre dans l'iframe, rechargee entre-temps : on verifie
        // qu'il est encore dans un document (isConnected).
        // / The "+" that opened the dialog gets focus back on close.
        var bouton_qui_a_ouvert_le_menu = null;

        function afficherLeTexte(texte) {
            var paragraphe = document.createElement("p");
            paragraphe.setAttribute("role", "status");
            paragraphe.style.cssText = "margin: 0; font-size: 13px; color: #71717a;";
            paragraphe.textContent = texte;
            liste_du_menu.replaceChildren(paragraphe);
        }

        function ouvrirLeMenuDAjout(url_du_menu, bouton_d_origine) {
            bouton_qui_a_ouvert_le_menu = bouton_d_origine;
            afficherLeTexte(liste_du_menu.dataset.texteChargement);
            if (!dialog_menu_ajout.open) {
                dialog_menu_ajout.showModal();
            }
            if (!window.htmx) {
                afficherLeTexte(liste_du_menu.dataset.texteErreur);
                return;
            }
            window.htmx.ajax("GET", url_du_menu, {
                target: "#dialog-menu-ajout-liste",
                swap: "innerHTML",
            });
        }

        // Bouton + de l'en-tete (dans ce document).
        // / Header "+" button (in this document).
        document.addEventListener("click", function (evenement) {
            var bouton_ajout = evenement.target.closest("[data-ouvrir-menu-ajout]");
            if (!bouton_ajout) {
                return;
            }
            ouvrirLeMenuDAjout(bouton_ajout.getAttribute("data-ouvrir-menu-ajout"), bouton_ajout);
        });

        // Bouton + d'une barre (dans l'iframe, via apercu_page_outils.js).
        // / A bar's "+" button (in the iframe, via apercu_page_outils.js).
        document.addEventListener("apercu:ouvrir-menu-ajout", function (evenement) {
            ouvrirLeMenuDAjout(evenement.detail.url_du_menu, evenement.detail.bouton_d_origine);
        });

        // htmx ne remplace rien sur une reponse en erreur (403, 404, 500) ni
        // sans reseau : on le dit au lieu de laisser « Chargement… ».
        // / htmx does not swap on errors: say so instead of "Loading…".
        liste_du_menu.addEventListener("htmx:responseError", function () {
            afficherLeTexte(liste_du_menu.dataset.texteErreur);
        });
        liste_du_menu.addEventListener("htmx:sendError", function () {
            afficherLeTexte(liste_du_menu.dataset.texteErreur);
        });

        // Bouton Fermer, et clic sur le fond. Un clic sur le fond a pour
        // cible la <dialog> elle-meme. Echap est gere par le navigateur.
        // / Close button, and backdrop click (its target is the dialog itself).
        dialog_menu_ajout.addEventListener("click", function (evenement) {
            var clic_sur_le_fond = evenement.target === dialog_menu_ajout;
            var clic_sur_fermer = evenement.target.closest("[data-fermer-dialog-menu-ajout]");
            if (clic_sur_le_fond || clic_sur_fermer) {
                dialog_menu_ajout.close();
            }
        });

        dialog_menu_ajout.addEventListener("close", function () {
            if (bouton_qui_a_ouvert_le_menu && bouton_qui_a_ouvert_le_menu.isConnected) {
                bouton_qui_a_ouvert_le_menu.focus();
            }
            bouton_qui_a_ouvert_le_menu = null;
        });
    }

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
