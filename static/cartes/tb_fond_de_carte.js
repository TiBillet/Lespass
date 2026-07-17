/**
 * Pose le fond de carte commun a TOUTES les cartes du projet.
 * / Sets the basemap shared by ALL the project's maps.
 *
 * LOCALISATION : static/cartes/tb_fond_de_carte.js
 *
 * UN SEUL endroit decide du style des cartes. Changer de fond de carte pour tout
 * le projet = changer cette fonction, rien d'autre.
 * / A SINGLE place decides the map style. Changing the basemap project-wide means
 * changing this function, nothing else.
 *
 * APPELE PAR / CALLED BY :
 *   - pages/templates/pages/classic/partials/bloc_carte_leaflet.html   (bloc CARTE_LEAFLET)
 *   - pages/templates/pages/faire_festival/partials/bloc_carte_leaflet.html
 *   - pages/templates/pages/classic/partials/evenement_geoloc.html     (geoloc evenement)
 *   - seo/static/seo/explorer.js                                       (explorer du reseau)
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
 * @param {L.Map} carte - la carte Leaflet deja instanciee.
 * @param {string} cleMaptiler - la cle MapTiler ; chaine vide ou absente = repli.
 * @returns {L.TileLayer} la couche de tuiles posee sur la carte.
 */
function tbPoserFondDeCarte(carte, cleMaptiler) {
    var couche_de_tuiles;

    if (cleMaptiler) {
        // Tuiles 512px (HD) : Leaflet a besoin de tileSize 512 + zoomOffset -1.
        // language=fr force les libelles en francais.
        // / 512px (HD) tiles: Leaflet needs tileSize 512 + zoomOffset -1.
        couche_de_tuiles = L.tileLayer(
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
    } else {
        couche_de_tuiles = L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                + ' contributors, style <a href="https://www.hotosm.org/">Humanitarian OSM Team</a>'
                + ' &middot; <a href="https://openstreetmap.fr/">OpenStreetMap France</a>',
            maxZoom: 20,
            subdomains: 'abc',
        });
    }

    couche_de_tuiles.addTo(carte);
    return couche_de_tuiles;
}
