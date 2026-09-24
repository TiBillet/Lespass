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
 * / Loaded INSIDE the Page form iframe. Blocks are direct children of the
 * .tb-flux grid; wrapping them would change the grid, so the bars live in a
 * separate overlay placed at each block's corner. Elements between two
 * <template> markers form one block. htmx.process() activates the buttons.
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

    // Un menu « + Ajouter apres » qui deborderait en bas s'ouvre vers le haut.
    // Verifie a l'ouverture, puis de nouveau quand sa liste arrive du serveur
    // (chargement a la demande, htmx:afterSwap) : elle change sa hauteur.
    // / A menu that would overflow at the bottom opens upwards. Checked on
    // open, then again when its list arrives from the server.
    function orienterLeMenu(details) {
        if (!details || !details.open) {
            return;
        }
        var menu = details.querySelector("[data-menu-liste]");
        if (!menu) {
            return;
        }
        menu.style.top = "calc(100% + 4px)";
        menu.style.bottom = "auto";
        // La fenetre de l'iframe a la hauteur du document (apercu.js) :
        // tout ce qui depasse innerHeight serait coupe.
        // / The iframe viewport is as tall as the content.
        var bas_du_menu = menu.getBoundingClientRect().bottom;
        if (bas_du_menu > window.innerHeight) {
            menu.style.top = "auto";
            menu.style.bottom = "calc(100% + 4px)";
        }
    }
    conteneur.addEventListener(
        "toggle",
        function (evenement) {
            orienterLeMenu(evenement.target);
        },
        true
    );
    // afterSettle et non afterSwap : en outerHTML, la cible d'afterSwap peut
    // etre l'element remplace, deja sorti du DOM. On reoriente donc tous les
    // menus ouverts. / afterSettle, not afterSwap: re-orient every open menu.
    document.body.addEventListener("htmx:afterSettle", function () {
        var menus_ouverts = document.querySelectorAll("details[data-menu-modeles][open]");
        for (var n = 0; n < menus_ouverts.length; n++) {
            orienterLeMenu(menus_ouverts[n]);
        }
    });

    // Fermer un menu « + » au clic a cote, ou avec Echap (le focus revient
    // sur son bouton). / Close a "+" menu on outside click, or with Escape.
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
