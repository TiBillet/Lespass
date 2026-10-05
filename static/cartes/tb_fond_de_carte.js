/**
 * Fond de carte commun a TOUTES les cartes Leaflet du projet.
 * / Basemap shared by ALL the project's Leaflet maps.
 *
 * LOCALISATION : static/cartes/tb_fond_de_carte.js
 *
 * Fonction publique : tbPoserFondDeCarte(carte, cleMaptiler).
 * / Public function: tbPoserFondDeCarte(carte, cleMaptiler).
 */

/**
 * Cree la couche OSM France "Humanitarian" (HOT), sans cle.
 * / Creates the keyless OSM France "Humanitarian" (HOT) layer.
 *
 * @returns {L.TileLayer} la couche, pas encore posee sur la carte.
 */
function tbCreerCoucheOsmHot() {
    return L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            + ' contributors, style <a href="https://www.hotosm.org/">Humanitarian OSM Team</a>'
            + ' &middot; <a href="https://openstreetmap.fr/">OpenStreetMap France</a>',
        maxZoom: 20,
        subdomains: 'abc',
    });
}

/**
 * Pose le fond de carte commun a TOUTES les cartes du projet.
 * / Sets the basemap shared by ALL the project's maps.
 *
 * UN SEUL endroit decide du style des cartes. Changer de fond de carte pour tout
 * le projet = changer cette fonction, rien d'autre.
 * / A SINGLE place decides the map style. Changing the basemap project-wide means
 * changing this function, nothing else.
 *
 * APPELE PAR / CALLED BY :
 *   - pages/templates/pages/classic/partials/bloc_lieu.html           (bloc lieu)
 *   - pages/templates/pages/faire_festival/partials/bloc_lieu.html
 *   - pages/templates/pages/V2/partials/bloc_lieu.html
 *   - pages/templates/pages/V2/partials/bloc_lieu_horizontal.html
 *   - pages/templates/pages/V2/vues/accueil.html
 *   - pages/templates/pages/classic/partials/evenement_geoloc.html     (geoloc evenement)
 *   - pages/templates/pages/V2/partials/evenement_geoloc.html
 *   - seo/static/seo/explorer.js                                       (explorer du reseau)
 *     charge par seo/templates/seo/explorer.html,
 *     pages/templates/pages/classic/vues/reseau.html et pages/templates/pages/V2/vues/reseau.html
 *   - static/widgets/widget_carte_adresse.js                           (saisie d'adresse)
 *
 * La cle vient de settings.MAPTILER_KEY, exposee a tous les gabarits par le
 * context processor TiBillet.maptiler.maptiler_context. Chaque appelant la lit
 * dans un data-* de son conteneur, puis la passe ici.
 * / The key comes from settings.MAPTILER_KEY, exposed to every template by the
 * TiBillet.maptiler.maptiler_context context processor.
 *
 * AVEC cle : MapTiler "dataviz-v4" — style epure, labels en francais, tuiles HD.
 * SANS cle : repli sur les tuiles "Humanitarian" d'OpenStreetMap France — labels
 * en francais, aucune cle, fonctionne en localhost et sur une installation tierce
 * qui n'a pas de compte MapTiler. Le repli est INDISPENSABLE : sans lui, une
 * install sans MAPTILER_KEY n'afficherait plus aucune carte.
 * / WITH a key: MapTiler "dataviz-v4". WITHOUT: fall back to OpenStreetMap France
 * "Humanitarian" tiles. The fallback is MANDATORY: without it, an install with no
 * MAPTILER_KEY would show no map at all.
 *
 * REPLI DYNAMIQUE : avec une cle, MapTiler peut quand meme refuser les tuiles
 * (quota epuise, cle ou origine refusee). La carte bascule alors UNE SEULE FOIS
 * sur OSM France HOT, dans deux cas :
 *   - aucune tuile MapTiler n'a reussi au premier affichage (evenement `load`) ;
 *   - le total d'erreurs de tuiles atteint SEUIL_ERREURS_TUILES.
 * Spec : TECH_DOC/SESSIONS/WIDGET_GEO/04-fonds-de-carte-maptiler-repli-osm.md
 * / DYNAMIC FALLBACK: with a key, MapTiler may still refuse tiles (quota, key or
 * origin). The map then switches ONCE to OSM France HOT.
 *
 * La valeur retournee reste la couche MapTiler, meme apres une bascule : les
 * ecouteurs poses par l'appelant (`load`, `tileerror`) restent sur cette couche.
 * / The returned layer stays the MapTiler one, even after a switch.
 *
 * @param {L.Map} carte - la carte Leaflet deja instanciee.
 * @param {string} cleMaptiler - la cle MapTiler ; chaine vide ou absente = repli.
 * @returns {L.TileLayer} la couche de tuiles posee sur la carte.
 */
function tbPoserFondDeCarte(carte, cleMaptiler) {
    // Sans cle : OSM France HOT directement.
    // / No key: OSM France HOT right away.
    if (!cleMaptiler) {
        var couche_osm_hot = tbCreerCoucheOsmHot();
        couche_osm_hot.addTo(carte);
        return couche_osm_hot;
    }

    // Tuiles 512px (HD) : Leaflet a besoin de tileSize 512 + zoomOffset -1.
    // language=fr force les libelles en francais.
    // / 512px (HD) tiles: Leaflet needs tileSize 512 + zoomOffset -1.
    var couche_maptiler = L.tileLayer(
        'https://api.maptiler.com/maps/dataviz-v4/{z}/{x}/{y}.png?key='
            + cleMaptiler + '&language=fr',
        {
            attribution: '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a>'
                + ' &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            tileSize: 512,
            zoomOffset: -1,
            minZoom: 1,
            maxZoom: 20,
            crossOrigin: true,
        }
    );

    // Compteurs du repli MapTiler -> OSM France HOT.
    // / MapTiler -> OSM France HOT fallback counters.
    var SEUIL_ERREURS_TUILES = 5;
    var bascule_osm_faite = false;
    var tuiles_maptiler_ok = 0;
    var tuiles_maptiler_en_erreur = 0;

    function basculer_vers_osm_hot() {
        // Une seule bascule par carte.
        // / Only one switch per map.
        if (bascule_osm_faite) {
            return;
        }
        bascule_osm_faite = true;
        console.warn('tb_fond_de_carte : MapTiler indisponible, bascule sur OSM France HOT');

        // Retrait DIFFERE (setTimeout 0) : INDISPENSABLE. Leaflet 1.9.4 lit
        // this._map juste apres avoir emis `load`. Un removeLayer direct dans
        // le handler `load` fait lever un TypeError (piege P.WIDGET.5).
        // / DEFERRED removal is REQUIRED: Leaflet 1.9.4 reads this._map right
        // after firing `load` (trap P.WIDGET.5).
        setTimeout(function () {
            carte.removeLayer(couche_maptiler);
            tbCreerCoucheOsmHot().addTo(carte);
        }, 0);
    }

    couche_maptiler.on('tileload', function () {
        tuiles_maptiler_ok = tuiles_maptiler_ok + 1;
    });

    couche_maptiler.on('tileerror', function () {
        tuiles_maptiler_en_erreur = tuiles_maptiler_en_erreur + 1;
        if (tuiles_maptiler_en_erreur >= SEUIL_ERREURS_TUILES) {
            basculer_vers_osm_hot();
        }
    });

    // `load` est emis quand toutes les tuiles visibles ont fini, en succes ou
    // en erreur. Aucune reussite + au moins une erreur = MapTiler refuse tout.
    // / `load` fires once all visible tiles are done, success or error.
    couche_maptiler.on('load', function () {
        var aucune_tuile_n_a_jamais_reussi = tuiles_maptiler_ok === 0;
        if (aucune_tuile_n_a_jamais_reussi && tuiles_maptiler_en_erreur > 0) {
            basculer_vers_osm_hot();
        }
    });

    couche_maptiler.addTo(carte);
    return couche_maptiler;
}
