/**
 * Widget carte adresse — JS init.
 * / Address map widget — JS init.
 *
 * LOCALISATION : static/widgets/widget_carte_adresse.js
 *
 * Roles :
 * 1. Scanne le DOM au DOMContentLoaded pour trouver les containers
 *    `[data-widget-initialized="false"][data-identifiant]` non encore initialisés.
 * 2. Pour chaque container :
 *    - Crée la map Leaflet (CartoDB Voyager tiles).
 *    - Ajoute le GeoSearchControl (recherche live Nominatim côté navigateur).
 *    - Si lat/lng initiales, place un marqueur draggable centré dessus.
 *    - Bind les events : suggestion click + dragend.
 * 3. À chaque event : remplit les hidden inputs lat/lng/adresse + auto-remplit
 *    les 4 champs adresse séparés depuis `result.raw.address`.
 * 4. Re-scanne au `htmx:afterSettle` pour gérer les ré-injections HTMX.
 *
 * / Roles: scan DOM at DOMContentLoaded, init each widget container,
 * handle search/dragend events, fill hidden inputs + separate address
 * fields. Re-scan on htmx:afterSettle for HTMX re-injections.
 *
 * FALC : pas de framework, pas de bundler. Code lisible top-down.
 */
(function () {
    "use strict";

    // Configuration : Nominatim direct depuis le navigateur. Pas de proxy
    // serveur — leaflet-geosearch fait deja la search forward direct vers
    // Nominatim, on garde la meme approche pour le reverse au drag du
    // marqueur. Avantages : pas de probleme multi-tenant routing, moins
    // de moving parts. Limites : pas de cache mutualise (chaque user
    // hit Nominatim individuellement) — acceptable pour notre volume.
    // Politique Nominatim : 1 req/s/IP. Le drag d'un user reste tres
    // en-dessous de cette limite (un user ne drag pas 10x/s).
    // / Config: Nominatim direct from the browser. No server proxy
    // (leaflet-geosearch already calls Nominatim direct for forward search,
    // we use the same approach for reverse on marker drag). Pros: no
    // multi-tenant routing issue, fewer moving parts. Cons: no shared
    // cache (each user hits Nominatim) — fine for our volume.
    const URL_NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse";
    const URL_NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search";
    const URL_TUILES_CARTODB = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png";
    const ATTRIBUTION_TUILES = "&copy; OpenStreetMap &copy; CARTO";
    const CENTRE_FRANCE = [46.6, 2.5];
    const ZOOM_FRANCE = 5;
    const ZOOM_DETAIL = 15;
    const SOUS_DOMAINES_CARTODB = "abcd";

    /**
     * Initialise un widget pour un container DOM donné.
     * @param {HTMLElement} container - le div [data-identifiant=...].
     */
    function initialiser_widget_carte_adresse(container) {
        const identifiant = container.dataset.identifiant;
        if (!identifiant) {
            return;
        }

        // Marquage idempotent : évite de ré-initialiser un widget existant.
        // / Idempotent flag: avoid re-initializing an existing widget.
        if (container.dataset.widgetInitialized === "true") {
            return;
        }
        container.dataset.widgetInitialized = "true";

        // Récupération des inputs hidden + champs adresse séparés.
        // / Get hidden inputs + separate address fields.
        const input_latitude = document.getElementById(identifiant + "-latitude");
        const input_longitude = document.getElementById(identifiant + "-longitude");
        const input_adresse = document.getElementById(identifiant + "-adresse");
        const input_rue = document.getElementById(identifiant + "-street");
        const input_code_postal = document.getElementById(identifiant + "-postal");
        const input_ville = document.getElementById(identifiant + "-locality");
        const input_pays = document.getElementById(identifiant + "-country");

        if (!input_latitude || !input_longitude || !input_adresse) {
            // Sécurité : sans hidden inputs, le widget n'a aucun sens.
            // / Safety: without hidden inputs, the widget makes no sense.
            console.warn(
                "widget_carte_adresse: hidden inputs manquants pour",
                identifiant,
            );
            return;
        }

        // Lecture des coordonnées initiales depuis les data-* du container.
        // / Read initial coordinates from container data-*.
        const latitude_initiale = parseFloat(container.dataset.latInitiale);
        const longitude_initiale = parseFloat(container.dataset.lngInitiale);
        const a_des_coords_initiales = !isNaN(latitude_initiale)
            && !isNaN(longitude_initiale);

        // Création de la map Leaflet (centre France si pas de coords).
        // / Leaflet map creation (France center if no initial coords).
        const map = L.map(container).setView(
            a_des_coords_initiales
                ? [latitude_initiale, longitude_initiale]
                : CENTRE_FRANCE,
            a_des_coords_initiales ? ZOOM_DETAIL : ZOOM_FRANCE,
        );

        L.tileLayer(URL_TUILES_CARTODB, {
            attribution: ATTRIBUTION_TUILES,
            subdomains: SOUS_DOMAINES_CARTODB,
            maxZoom: 20,
        }).addTo(map);

        // Déplace le zoom control en haut à droite : par défaut Leaflet le
        // pose en `topleft`, où vit aussi la search bar leaflet-geosearch.
        // Sans ce déplacement, le zoom et le placeholder vide
        // `.leaflet-control-geosearch.pending` se chevauchent visuellement
        // (cf. tests/PIEGES.md P8).
        // / Move zoom control to top-right (default is top-left, where the
        // search bar also sits — visual collision with the `.pending`
        // placeholder).
        if (map.zoomControl) {
            map.zoomControl.setPosition("topright");
        }

        // Provider Nominatim (recherche live côté navigateur). Locale auto :
        // leaflet-geosearch lit `<html lang>` ; on force fallback "fr".
        // / Nominatim provider (browser-side live search). Locale auto:
        // leaflet-geosearch reads <html lang>; we fallback to "fr".
        const langue_html = (document.documentElement.lang || "fr").split("-")[0];
        const provider = new GeoSearch.OpenStreetMapProvider({
            params: {
                "accept-language": langue_html,
                "addressdetails": 1,
            },
        });

        const search_control = new GeoSearch.GeoSearchControl({
            provider: provider,
            style: "bar",
            showMarker: false,  // on gère notre propre marqueur draggable.
            showPopup: false,
            autoClose: true,
            keepResult: true,
            // IMPORTANT : `autoComplete: false` désactive la recherche
            // pendant la frappe. La politique d'usage Nominatim INTERDIT
            // explicitement l'autocomplete client-side (cf.
            // https://operations.osmfoundation.org/policies/nominatim/
            // "Auto-complete search ... must not implement such a service
            // on the client side using the API"). Avec `autoComplete: true`
            // (défaut leaflet-geosearch), CHAQUE frappe utilisateur émettait
            // une requête Nominatim après 250ms de debounce. Désormais : 1
            // seule requête, au submit (touche Entrée ou clic sur le bouton
            // search bar). Cohérent avec notre fetch initial au load
            // (pré-fill nom collectif) et le reverse geocode au drag.
            // / IMPORTANT: `autoComplete: false` disables search-while-typing.
            // Nominatim's usage policy EXPLICITLY forbids client-side
            // autocomplete. With the default (true), every keystroke fired
            // a Nominatim request after a 250ms debounce. Now: one request
            // per explicit submit (Enter or search-bar button click).
            autoComplete: false,
            searchLabel: container.dataset.adresseInitiale
                || "Saisissez une adresse ou un lieu",
            notFoundMessage: "Adresse introuvable.",
        });
        map.addControl(search_control);

        // Marqueur draggable (créé seulement quand on a des coords valides).
        // / Draggable marker (created only when valid coords are available).
        let marqueur = null;

        function placer_marqueur_et_remplir_champs(latitude, longitude, adresse_complete, parties_adresse) {
            const lat_lng = L.latLng(latitude, longitude);

            if (marqueur === null) {
                marqueur = L.marker(lat_lng, { draggable: true }).addTo(map);
                marqueur.on("dragend", function (evenement_drag) {
                    recuperer_coordonnees_apres_deplacement_du_marqueur(evenement_drag);
                });
            } else {
                marqueur.setLatLng(lat_lng);
            }

            input_latitude.value = latitude.toFixed(6);
            input_longitude.value = longitude.toFixed(6);
            if (adresse_complete) {
                input_adresse.value = adresse_complete;
            }

            // Auto-remplissage des 4 champs adresse séparés (si présents).
            // Mapping : house_number+road, postcode, city|town|village, country.
            // / Auto-fill the 4 separate address fields if present.
            if (parties_adresse) {
                if (input_rue) {
                    const numero = parties_adresse.house_number || "";
                    const rue = parties_adresse.road || "";
                    input_rue.value = (numero + " " + rue).trim();
                }
                if (input_code_postal && parties_adresse.postcode) {
                    input_code_postal.value = parties_adresse.postcode;
                }
                if (input_ville) {
                    input_ville.value = parties_adresse.city
                        || parties_adresse.town
                        || parties_adresse.village
                        || parties_adresse.municipality
                        || "";
                }
                if (input_pays && parties_adresse.country) {
                    input_pays.value = parties_adresse.country;
                }
            }
        }

        /**
         * Geocodage inverse après drag du marqueur. GET direct vers
         * nominatim.openstreetmap.org/reverse (CORS open) — pas de proxy
         * serveur, meme approche que leaflet-geosearch pour le forward.
         * Met à jour les hidden inputs lat/lng/adresse + les 4 champs
         * adresse séparés.
         * / Reverse geocoding after marker drag. Direct GET to Nominatim
         * (CORS open) — no server proxy, same pattern as leaflet-geosearch
         * uses for forward. Updates hidden inputs + separate address fields.
         */
        async function recuperer_coordonnees_apres_deplacement_du_marqueur(evenement_drag) {
            const nouvelle_position = evenement_drag.target.getLatLng();
            const latitude = nouvelle_position.lat;
            const longitude = nouvelle_position.lng;

            // Mise à jour immédiate des hidden lat/lng (UX réactive,
            // visible meme si le reverse echoue).
            // / Immediate update of hidden lat/lng (responsive UX,
            // visible even if reverse fails).
            input_latitude.value = latitude.toFixed(6);
            input_longitude.value = longitude.toFixed(6);

            // Construction de l'URL Nominatim avec params standards.
            // `addressdetails=1` pour avoir le dict `address` structuré.
            // `accept-language` selon la locale de la page.
            // / Build Nominatim URL with standard params. addressdetails=1
            // to get structured `address` dict. accept-language from page.
            const params = new URLSearchParams({
                lat: latitude.toFixed(6),
                lon: longitude.toFixed(6),
                format: "json",
                addressdetails: "1",
                "accept-language": langue_html,
            });
            const url = URL_NOMINATIM_REVERSE + "?" + params.toString();

            try {
                const reponse = await fetch(url, {
                    method: "GET",
                    headers: { "Accept": "application/json" },
                });

                if (!reponse.ok) {
                    console.warn(
                        "widget_carte_adresse: Nominatim reverse status",
                        reponse.status,
                    );
                    return;
                }

                const donnees = await reponse.json();
                placer_marqueur_et_remplir_champs(
                    latitude,
                    longitude,
                    donnees.display_name || "",
                    donnees.address || {},
                );
            } catch (erreur) {
                // Réseau coupé, CORS, ou erreur fetch : on garde le marqueur
                // placé, les hidden lat/lng à jour, log discret. L'utilisateur
                // peut completer les champs adresse a la main.
                // / Network/CORS/fetch error: keep marker placed, hidden
                // updated, discreet warn. User can fill address fields manually.
                console.warn("widget_carte_adresse: reverse fetch error", erreur);
            }
        }

        // Event leaflet-geosearch : l'utilisateur a cliqué sur une suggestion.
        // / leaflet-geosearch event: user clicked a suggestion.
        map.on("geosearch/showlocation", function (evenement_suggestion) {
            const result = evenement_suggestion.location;
            // result.x = longitude, result.y = latitude (convention GeoJSON).
            // result.raw = payload Nominatim brut (avec address si addressdetails=1).
            // / result.x = lng, result.y = lat (GeoJSON). result.raw = raw Nominatim.
            placer_marqueur_et_remplir_champs(
                result.y,
                result.x,
                result.label || "",
                (result.raw && result.raw.address) || {},
            );
            map.setView([result.y, result.x], ZOOM_DETAIL);
        });

        // Click direct sur la carte (sans search) : place le marqueur + reverse.
        // / Direct map click (no search): place marker + reverse.
        map.on("click", function (evenement_click) {
            const fake_drag_event = { target: { getLatLng: () => evenement_click.latlng } };
            // On crée le marqueur si absent, puis on simule le dragend pour
            // déclencher le reverse geocode (DRY).
            // / Create marker if missing, then simulate dragend to trigger
            // reverse (DRY).
            if (marqueur === null) {
                marqueur = L.marker(evenement_click.latlng, { draggable: true }).addTo(map);
                marqueur.on("dragend", function (evt) {
                    recuperer_coordonnees_apres_deplacement_du_marqueur(evt);
                });
            } else {
                marqueur.setLatLng(evenement_click.latlng);
            }
            recuperer_coordonnees_apres_deplacement_du_marqueur(fake_drag_event);
        });

        /**
         * Lance une recherche Nominatim avec la chaîne donnée et applique
         * le 1er résultat (marqueur + champs adresse + recentrage carte).
         * Utilisé par : (1) la recherche automatique au load avec le nom
         * du collectif ; (2) le keydown Enter sur l'input search ; (3) le
         * clic sur le bouton submit "Rechercher" injecté dans la search bar.
         *
         * Fetch direct vers `/search` avec `addressdetails=1` pour garantir
         * un dict `address` structuré. On évite `provider.search()` de
         * leaflet-geosearch car selon les versions, `result.raw.address`
         * n'est pas toujours peuplé. Même approche que pour le reverse au
         * drag du marqueur.
         *
         * / Run a Nominatim search with the given query and apply the first
         * result (marker + address fields + recentered map). Used by:
         * (1) auto-search at load with the collective name, (2) keydown
         * Enter on the search input, (3) click on the injected "Search"
         * submit button. Direct fetch to /search with addressdetails=1.
         */
        function lancer_recherche_nominatim(query) {
            const requete = (query || "").trim();
            if (!requete) {
                return;
            }
            // Réinitialise la zone d'erreur avant chaque recherche.
            // / Clear the error zone before each search.
            effacer_message_no_result();
            const params_search = new URLSearchParams({
                q: requete,
                format: "json",
                addressdetails: "1",
                limit: "1",
                "accept-language": langue_html,
            });
            fetch(URL_NOMINATIM_SEARCH + "?" + params_search.toString(), {
                method: "GET",
                headers: { "Accept": "application/json" },
            }).then(function (reponse) {
                if (!reponse.ok) {
                    console.warn(
                        "widget_carte_adresse: Nominatim search status",
                        reponse.status,
                    );
                    afficher_message_no_result(
                        "Le service de géolocalisation est indisponible. "
                        + "Cliquez directement sur la carte pour positionner le lieu.",
                    );
                    return null;
                }
                return reponse.json();
            }).then(function (donnees) {
                if (!donnees) {
                    // Cas ok=false plus haut : on a déjà affiché un message
                    // d'indisponibilité. / Already handled above.
                    return;
                }
                if (donnees.length === 0) {
                    // Aucun match Nominatim : message inline pour l'user.
                    // / No Nominatim match: inline message for the user.
                    afficher_message_no_result(
                        "Adresse introuvable. Affinez votre recherche "
                        + "ou cliquez directement sur la carte.",
                    );
                    return;
                }
                const premier_resultat = donnees[0];
                const latitude = parseFloat(premier_resultat.lat);
                const longitude = parseFloat(premier_resultat.lon);
                placer_marqueur_et_remplir_champs(
                    latitude,
                    longitude,
                    premier_resultat.display_name || "",
                    premier_resultat.address || {},
                );
                map.setView([latitude, longitude], ZOOM_DETAIL);
            }).catch(function (erreur) {
                // Réseau coupé / Nominatim down : on log + message inline.
                // / Network down / Nominatim down: log + inline message.
                console.warn(
                    "widget_carte_adresse: recherche échouée",
                    erreur,
                );
                afficher_message_no_result(
                    "Le service de géolocalisation est indisponible. "
                    + "Cliquez directement sur la carte pour positionner le lieu.",
                );
            });
        }

        /**
         * Affiche un message inline sous la search bar (zone `aria-live`).
         * `zone_message_no_result` est créé plus bas dans cette fonction
         * d'init — closure capture la référence au moment de l'appel.
         * Defensive : if absent (e.g. timing), no-op.
         * / Display an inline message under the search bar.
         */
        function afficher_message_no_result(texte) {
            const zone = container.querySelector(".widget-search-no-result");
            if (zone !== null) {
                zone.textContent = texte;
            }
        }

        /**
         * Vide la zone d'erreur (appelé avant chaque nouvelle recherche
         * et au succès). Le CSS `:empty` la cache automatiquement.
         * / Clear the error zone (called before each new search and on success).
         */
        function effacer_message_no_result() {
            const zone = container.querySelector(".widget-search-no-result");
            if (zone !== null) {
                zone.textContent = "";
            }
        }

        // Recherche manuelle : on attache nos propres handlers (keydown Enter
        // sur l'input + clic sur un bouton submit injecté) plutôt que de
        // s'appuyer sur le submit natif du form leaflet-geosearch. Raison :
        // ce <form> est imbriqué dans le <form> onboard parent, ce que
        // HTML5 interdit — les navigateurs gèrent l'ambiguïté de façon
        // imprévisible (cf. boucle infinie constatée 2026-05-16). En
        // appelant `lancer_recherche_nominatim()` directement, on contourne
        // tout le mécanisme de form submit. Un `preventDefault` sur la
        // touche Entrée évite que le browser remonte au form onboard.
        //
        // / Manual search: we wire our own handlers (keydown Enter on the
        // input + click on an injected submit button) instead of relying on
        // the native form submit. Reason: the leaflet-geosearch <form> is
        // nested inside the onboard <form>, which HTML5 forbids — browsers
        // handle the ambiguity unpredictably. We bypass form submit
        // entirely by calling `lancer_recherche_nominatim()` directly.
        const champ_recherche = container.querySelector(
            ".leaflet-control-geosearch form input, .leaflet-control-geosearch input[type='text']",
        );
        if (champ_recherche !== null) {
            // Listener keydown Enter : déclenche la recherche sans
            // soumettre le form (preventDefault bloque la remontée).
            // / Enter keydown listener: triggers search without bubbling
            // to the parent form (preventDefault stops propagation).
            champ_recherche.addEventListener("keydown", function (evt) {
                if (evt.key === "Enter") {
                    evt.preventDefault();
                    evt.stopPropagation();
                    lancer_recherche_nominatim(champ_recherche.value);
                }
            });

            // Injection d'un bouton submit visible (icône loupe). Le mode
            // `style: "bar"` de leaflet-geosearch n'en crée pas, et sans
            // bouton l'utilisateur ne sait pas comment déclencher la
            // recherche (la touche Entrée seule n'est pas découvrable).
            // `type="button"` IMPORTANT : sinon le browser interprète comme
            // submit du form parent (le form onboard) → POST /onboard/place/
            // avec lat/lng vides → 422.
            // / Inject a visible submit button (magnifier icon). `style: "bar"`
            // doesn't provide one and Enter alone isn't discoverable.
            // `type="button"` is CRITICAL — otherwise the browser submits
            // the parent onboard form (lat/lng empty → 422).
            const formulaire_leaflet = champ_recherche.closest("form");
            if (formulaire_leaflet !== null
                && formulaire_leaflet.querySelector(".widget-search-submit") === null) {
                const bouton_recherche = document.createElement("button");
                bouton_recherche.type = "button";
                bouton_recherche.className = "widget-search-submit";
                bouton_recherche.setAttribute("aria-label", "Rechercher");
                bouton_recherche.textContent = "🔍";
                bouton_recherche.addEventListener("click", function (evt) {
                    evt.preventDefault();
                    evt.stopPropagation();
                    lancer_recherche_nominatim(champ_recherche.value);
                });
                formulaire_leaflet.appendChild(bouton_recherche);
            }
        }

        // Bandeau d'erreur "Adresse introuvable" — injecté en JS dans le
        // container Leaflet pour pouvoir être affiché/caché par
        // `lancer_recherche_nominatim()` selon le résultat. `aria-live="polite"`
        // pour annonce screen reader sans interrompre. On le crée vide :
        // le CSS `&:empty { display: none; }` le cache tant qu'il n'a pas
        // de contenu.
        // / "Address not found" banner — injected in the Leaflet container
        // so `lancer_recherche_nominatim()` can show/hide it. aria-live for
        // screen readers. Empty by default, hidden via CSS `:empty`.
        const zone_message_no_result = document.createElement("div");
        zone_message_no_result.className = "widget-search-no-result";
        zone_message_no_result.setAttribute("aria-live", "polite");
        zone_message_no_result.setAttribute("role", "status");
        container.appendChild(zone_message_no_result);

        // Si on a des coords initiales, on place le marqueur tout de suite.
        // / If initial coords exist, place the marker immediately.
        if (a_des_coords_initiales) {
            placer_marqueur_et_remplir_champs(
                latitude_initiale,
                longitude_initiale,
                container.dataset.adresseInitiale || "",
                {},  // pas d'address dict initial — on ne re-geocode pas au load.
            );
        } else if (container.dataset.adresseInitiale) {
            // Pas de coords mais on a une chaîne de recherche initiale (ex:
            // nom du collectif). On pré-remplit l'input search ET on lance
            // la recherche Nominatim auto (via le helper partagé avec
            // l'Enter + le clic bouton).
            // / No initial coords but we have an initial search string.
            // Pre-fill the search input AND auto-trigger the Nominatim
            // search (via the helper shared with Enter + button click).
            if (champ_recherche !== null) {
                champ_recherche.value = container.dataset.adresseInitiale;
            }
            lancer_recherche_nominatim(container.dataset.adresseInitiale);
        }
    }

    /**
     * Scanne le DOM et initialise tous les widgets non encore traités.
     * / Scan DOM and initialize all non-yet-initialized widgets.
     */
    function scanner_et_initialiser_tous_les_widgets() {
        const containers = document.querySelectorAll(
            '[data-widget-initialized="false"][data-identifiant]',
        );
        containers.forEach(initialiser_widget_carte_adresse);
    }

    document.addEventListener("DOMContentLoaded", scanner_et_initialiser_tous_les_widgets);

    // HTMX : si un swap réinjecte un widget (ex: re-render 422 d'un form),
    // on relance le scan pour initialiser les nouveaux containers.
    // / HTMX: re-scan on swap to init new widgets injected by partials.
    document.body.addEventListener("htmx:afterSettle", scanner_et_initialiser_tous_les_widgets);
})();
