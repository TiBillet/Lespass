/**
 * Pose la barre d'actions de chaque bloc par-dessus l'apercu de la page
 * / Overlays each block's action bar on the page preview
 *
 * LOCALISATION : pages/static/pages/admin/apercu_page_outils.js
 *
 * Charge DANS l'iframe de la fiche Page, par admin/pages/apercu/_blocs.html
 * (seulement quand `avec_outils` est vrai).
 *
 * POURQUOI PAS D'ENVELOPPE : les blocs sont des enfants directs de la grille
 * .tb-flux. Les envelopper dans une <div> changerait la grille (des cartes
 * voisines ne seraient plus cote a cote). Chaque barre est donc inseree
 * juste apres son bloc, en position absolue (elle ne prend aucune case de la
 * grille, et Tab la trouve a cote de son bloc). Les cadres pointilles, eux,
 * vivent dans un calque a part, pose par-dessus.
 *
 * COMMENT ON RETROUVE UN BLOC : apres chaque bloc, le serveur pose un
 * <template data-apercu-outils> qui contient sa barre. Les elements situes
 * entre deux <template> forment un bloc (un gabarit peut produire plusieurs
 * elements : une <section> puis un <script>, par exemple).
 *
 * Les boutons ↑ ↓ Supprimer sont des hx-post (htmx du skin) : on appelle
 * htmx.process() sur le calque apres l'avoir rempli.
 * Aucune logique metier ici : uniquement de l'affichage.
 *
 * COMMUNICATION :
 * Emet : « apercu:ouvrir-menu-ajout » sur le document de l'admin (parent),
 * au clic sur le + d'une barre -> apercu.js ouvre la <dialog> du menu.
 *
 * / Loaded INSIDE the Page form iframe. Blocks are direct children of the
 * .tb-flux grid; wrapping them would change the grid, so the bars live in a
 * separate overlay placed at each block's corner. Elements between two
 * <template> markers form one block. htmx.process() activates the buttons.
 * Emits "apercu:ouvrir-menu-ajout" on the parent document (apercu.js).
 */
(function () {
    var conteneur = document.querySelector("[data-apercu-contenu]");
    if (!conteneur) {
        return;
    }

    // Le calque : pose en haut a gauche du document, sans taille propre.
    // Ses enfants sont places en coordonnees du document.
    // / The overlay: top-left of the document, no size of its own.
    // Place en haut du document pour la barre du premier bloc, qui deborde
    // au-dessus de son bord (voir placerLesBarres).
    // / Room at the top for the first block's bar, which overflows its edge.
    document.body.style.paddingTop = "16px";

    var calque = document.createElement("div");
    calque.setAttribute("data-apercu-calque", "");
    // z-index juste SOUS celui des barres : les cadres passent au-dessus des
    // blocs, mais jamais au-dessus des barres d'actions.
    // / Just BELOW the bars' z-index: frames over blocks, never over bars.
    calque.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;z-index:2147482000;";
    document.body.appendChild(calque);

    // Decoupe les enfants de la grille en blocs, grace aux <template>.
    // / Split the grid children into blocks, using the <template> markers.
    var blocs = [];
    var elements_du_bloc = [];
    var enfants = Array.prototype.slice.call(conteneur.children);
    for (var i = 0; i < enfants.length; i++) {
        var enfant = enfants[i];
        var est_un_repere = enfant.tagName === "TEMPLATE" && enfant.hasAttribute("data-apercu-outils");
        if (!est_un_repere) {
            elements_du_bloc.push(enfant);
            continue;
        }

        // Cadre pointille autour du bloc (ne capte pas les clics).
        // / Dashed frame around the block (does not catch clicks).
        var cadre = document.createElement("div");
        cadre.style.cssText =
            "position:absolute;pointer-events:none;border:2px dashed rgba(5,150,105,.55);border-radius:6px;";
        calque.appendChild(cadre);

        // La barre d'actions, copiee depuis le <template>. Elle est inseree
        // JUSTE APRES son bloc (avant le <template>), et non dans le calque :
        // au clavier, Tab passe ainsi du bloc a sa barre, puis au bloc suivant.
        // En position absolue, elle ne prend aucune case de la grille.
        // / The action bar goes RIGHT AFTER its block (not in the overlay), so
        // Tab reaches it next to its block. Absolutely positioned, it takes no
        // grid cell.
        var barre = document.createElement("div");
        barre.style.cssText = "position:absolute;z-index:2147483000;grid-column:auto;";
        barre.appendChild(enfant.content.cloneNode(true));
        conteneur.insertBefore(barre, enfant);

        blocs.push({ elements: elements_du_bloc, cadre: cadre, barre: barre });
        elements_du_bloc = [];
    }

    // Rectangle qui englobe les elements visibles d'un bloc, en coordonnees
    // du document. / Rectangle around a block's visible elements.
    function rectangleDuBloc(elements) {
        var haut = Infinity, gauche = Infinity, bas = -Infinity, droite = -Infinity;
        for (var j = 0; j < elements.length; j++) {
            var r = elements[j].getBoundingClientRect();
            var est_visible = r.width > 0 && r.height > 0;
            if (!est_visible) {
                continue;
            }
            haut = Math.min(haut, r.top + window.scrollY);
            gauche = Math.min(gauche, r.left + window.scrollX);
            bas = Math.max(bas, r.bottom + window.scrollY);
            droite = Math.max(droite, r.right + window.scrollX);
        }
        if (haut === Infinity) {
            return null;
        }
        return { haut: haut, gauche: gauche, largeur: droite - gauche, hauteur: bas - haut };
    }

    // Point de depart des coordonnees d'un element en position absolue : le
    // coin du premier ancetre positionne, ou le document s'il n'y en a pas.
    // / Origin of an absolutely positioned element's coordinates.
    function origineDuPositionnement(element) {
        var parent = element.offsetParent;
        if (!parent || getComputedStyle(parent).position === "static") {
            return { haut: 0, gauche: 0 };
        }
        var r = parent.getBoundingClientRect();
        return {
            haut: r.top + window.scrollY + parent.clientTop,
            gauche: r.left + window.scrollX + parent.clientLeft,
        };
    }

    function placerLesBarres() {
        for (var k = 0; k < blocs.length; k++) {
            var bloc = blocs[k];
            var rect = rectangleDuBloc(bloc.elements);
            if (!rect) {
                // Bloc sans rendu (liste vide, par ex.) : la barre reste
                // visible, posee sous le bloc precedent.
                // / Block with no rendering: keep the bar, below the previous one.
                var precedent = k > 0 ? rectangleDuBloc(blocs[k - 1].elements) : null;
                rect = {
                    haut: precedent ? precedent.haut + precedent.hauteur : 0,
                    gauche: conteneur.getBoundingClientRect().left + window.scrollX,
                    largeur: conteneur.getBoundingClientRect().width,
                    hauteur: 44,
                };
            }
            bloc.cadre.style.top = rect.haut + "px";
            bloc.cadre.style.left = rect.gauche + "px";
            bloc.cadre.style.width = rect.largeur + "px";
            bloc.cadre.style.height = rect.hauteur + "px";
            // A CHEVAL sur le bord haut : la barre cache moins le contenu.
            // Ses coordonnees sont relatives a son parent positionne (ou au
            // document si aucun ne l'est).
            // / STRADDLING the top edge. Coordinates are relative to its
            // positioned parent (or to the document).
            var origine = origineDuPositionnement(bloc.barre);
            bloc.barre.style.top = Math.max(rect.haut - 13, 0) - origine.haut + "px";
            bloc.barre.style.left = rect.gauche + 8 - origine.gauche + "px";
        }
        reserverLaPlaceSousLaDerniereBarre();
    }

    // Les barres vivent dans le calque, hors du conteneur : une barre qui
    // depasse sous le dernier bloc serait coupee par le bas de l'iframe (qui
    // prend la hauteur du conteneur, cf. apercu.js). On ajoute au conteneur
    // la marge qui manque.
    // / Bars live outside the container: one overflowing below the last block
    // would be cut by the iframe bottom. Add the missing bottom padding.
    function reserverLaPlaceSousLaDerniereBarre() {
        conteneur.style.paddingBottom = "";
        var bas_du_conteneur = conteneur.getBoundingClientRect().bottom + window.scrollY;
        var bas_le_plus_bas = bas_du_conteneur;
        for (var m = 0; m < blocs.length; m++) {
            var bas_de_la_barre = blocs[m].barre.getBoundingClientRect().bottom + window.scrollY;
            bas_le_plus_bas = Math.max(bas_le_plus_bas, bas_de_la_barre + 8);
        }
        if (bas_le_plus_bas > bas_du_conteneur) {
            var marge_actuelle = parseFloat(getComputedStyle(conteneur).paddingBottom) || 0;
            conteneur.style.paddingBottom = marge_actuelle + (bas_le_plus_bas - bas_du_conteneur) + "px";
        }
    }

    // Le + d'une barre ouvre le menu d'ajout dans l'ADMIN, pas dans l'iframe :
    // l'iframe a la hauteur de son contenu, un menu ouvert ici serait coupe.
    // On previent le document parent (meme origine). apercu.js ouvre alors
    // sa <dialog> et y charge la liste des modeles.
    // On passe aussi le bouton : la <dialog> lui rend le focus a la fermeture.
    // / The "+" opens the add menu in the ADMIN document: inside the iframe it
    // would be clipped. The button is passed so focus can return to it.
    conteneur.addEventListener("click", function (evenement) {
        var bouton_ajout = evenement.target.closest("[data-ouvrir-menu-ajout]");
        if (!bouton_ajout) {
            return;
        }
        // Apercu ouvert seul, hors de l'iframe de la fiche Page : pas de
        // document parent pour afficher le menu. / Opened alone: no parent.
        var est_dans_une_iframe = window.parent !== window;
        if (!est_dans_une_iframe) {
            return;
        }
        var evenement_ouverture = new CustomEvent("apercu:ouvrir-menu-ajout", {
            detail: {
                url_du_menu: bouton_ajout.getAttribute("data-ouvrir-menu-ajout"),
                bouton_d_origine: bouton_ajout,
            },
        });
        window.parent.document.dispatchEvent(evenement_ouverture);
    });

    // Les barres sont dans le conteneur : htmx doit activer leurs boutons.
    // / The bars live in the container: htmx must activate their buttons.
    if (window.htmx) {
        window.htmx.process(conteneur);
    }
    placerLesBarres();
    window.addEventListener("load", placerLesBarres);
    window.addEventListener("resize", placerLesBarres);
    if (window.ResizeObserver) {
        new ResizeObserver(placerLesBarres).observe(conteneur);
    }
})();
