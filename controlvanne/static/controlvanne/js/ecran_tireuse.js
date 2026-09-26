/**
 * Écran des tireuses — mise à jour en direct via WebSocket
 * / Tap screens — live updates via WebSocket
 *
 * LOCALISATION : controlvanne/static/controlvanne/js/ecran_tireuse.js
 *
 * Chargé par kiosk_detail.html (une tireuse) et kiosk_list.html (toutes).
 * Remplace l'ancien panel_kiosk.js.
 * / Loaded by kiosk_detail.html and kiosk_list.html. Replaces panel_kiosk.js.
 *
 * CE SCRIPT FAIT SEULEMENT 3 CHOSES :
 * 1. Il pose l'attribut data-etat sur la racine de la tireuse.
 *    C'est tireuse.css qui montre la bonne étape.
 * 2. Il écrit du texte dans les éléments [data-champ="..."].
 * 3. Il pose 2 variables CSS : --remplissage-verre et --niveau-fut.
 * / Only 3 jobs: set data-etat, write [data-champ] texts, set 2 CSS vars.
 *
 * COMMUNICATION :
 * Reçoit : messages JSON de PanelConsumer (controlvanne/consumers.py).
 *          Format décrit dans controlvanne/ws_payloads.py.
 * Canal  : /ws/rfid/all/ (liste) ou /ws/rfid/<uuid>/ (détail),
 *          lu dans data-slug-focus de #cards-grid.
 * Racine d'une tireuse : [data-tireuse-uuid][data-etat] (tireuse_ecran.html
 *          ou tireuse_vignette.html).
 */
(function () {
  "use strict";

  // Volume d'un verre plein pour le dessin du verre (50 cl = une pinte)
  // / Full glass volume for the glass drawing (50 cl = a pint)
  var VOLUME_VERRE_PLEIN_ML = 500;

  // Volume d'un « verre » pour le calcul « soit N verres » (25 cl)
  // / Glass volume for the "N glasses" count (25 cl)
  var VOLUME_VERRE_REFERENCE_L = 0.25;

  // Temps d'affichage avant le retour en veille (millisecondes)
  // / Display time before going back to idle (milliseconds)
  // Pas de délai pour un refus : l'écran reste affiché tant que la carte
  // est posée. Le Pi envoie card_removed au retrait, même sans session
  // (Pi/controllers/tibeer_controller.py, _handle_card_removal) ; le serveur
  // pousse alors present=false, ce qui ramène en veille.
  // / No delay for a refusal: the screen stays while the card is present.
  // The Pi sends card_removed on removal, even without a session.
  var DELAI_RETOUR_APRES_FIN_MS = 6000;

  var langue_de_la_page = document.documentElement.lang || "fr";


  // ──────────────────────────────────────────────────────────────────
  // Petites fonctions d'affichage
  // / Small display helpers
  // ──────────────────────────────────────────────────────────────────

  // Écrit un texte dans tous les [data-champ="nom"] d'une tireuse
  // / Writes a text into every [data-champ="name"] of a tap
  function ecrireChamp(racine, nom_du_champ, texte) {
    var elements = racine.querySelectorAll('[data-champ="' + nom_du_champ + '"]');
    for (var i = 0; i < elements.length; i++) {
      elements[i].textContent = texte;
    }
  }

  // 12.5 → « 12,50 € » (format de la langue de la page)
  // / 12.5 → "12,50 €" (page locale format)
  function formaterEuros(montant) {
    return Number(montant).toLocaleString(langue_de_la_page, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + " €";
  }

  // 125 ml → « 12,5 » (en centilitres, une décimale)
  // / 125 ml → "12,5" (centiliters, one decimal)
  function formaterCentilitres(volume_ml) {
    return (Number(volume_ml) / 10).toLocaleString(langue_de_la_page, {
      maximumFractionDigits: 1,
    });
  }


  // ──────────────────────────────────────────────────────────────────
  // Choix de l'état à partir du message reçu
  // / Picks the state from the received message
  // ──────────────────────────────────────────────────────────────────

  /**
   * Renvoie le nom de l'état à poser dans data-etat.
   * / Returns the state name to put in data-etat.
   *
   * On regarde le volume et pas vanne_ouverte pour « tirage » :
   * authorize() envoie déjà vanne_ouverte=true au moment du badge.
   * / We check the volume, not vanne_ouverte: authorize() already
   * sends vanne_ouverte=true when the card is badged.
   *
   * @param {Object} payload — message WebSocket
   * @param {Object} tireuse — mémoire de la tireuse (voir plus bas)
   * @return {string} veille | service | tirage | fin | refus | maintenance
   */
  function choisirEtat(payload, tireuse) {
    if (payload.maintenance) return "maintenance";
    if (payload.present && payload.authorized === false) return "refus";
    if (payload.present && Number(payload.volume_ml) > 0) return "tirage";
    if (payload.present) return "service";
    // Bilan dès que la session se termine avec de la bière servie.
    // On ne regarde PAS le message d'avant : au pour_end, le serveur pousse
    // d'abord un « snapshot » de la tireuse (signal post_save, present=false),
    // puis le message session_done. Le snapshot ne doit pas empêcher le bilan.
    // / Summary as soon as the session ends with beer served. We do NOT look
    // at the previous message: at pour_end the server first pushes a tap
    // snapshot (post_save signal, present=false), then session_done.
    if (payload.session_done && Number(payload.volume_ml) > 0) return "fin";
    return tireuse.en_maintenance ? "maintenance" : "veille";
  }


  // ──────────────────────────────────────────────────────────────────
  // Mémoire de chaque tireuse de la page, indexée par UUID
  // / Memory of each tap on the page, indexed by UUID
  // ──────────────────────────────────────────────────────────────────

  // On cherche [data-tireuse-uuid][data-etat] et pas seulement
  // [data-tireuse-uuid] : le panneau du simulateur (mode DEMO) porte
  // aussi data-tireuse-uuid, mais ce n'est pas un écran de tireuse.
  // / We need data-etat too: the DEMO simulator panel also has
  // data-tireuse-uuid, but it is not a tap screen.
  var tireuses_de_la_page = {};
  var racines = document.querySelectorAll("[data-tireuse-uuid][data-etat]");
  for (var i = 0; i < racines.length; i++) {
    var racine = racines[i];
    tireuses_de_la_page[racine.dataset.tireuseUuid] = {
      racine: racine,
      prix_litre: parseFloat(racine.dataset.prixLitre) || 0,
      en_maintenance: racine.dataset.etat === "maintenance",
      minuteur_retour: null,
    };
  }

  // Remet une tireuse en attente et efface les valeurs de la carte
  // / Puts a tap back to idle and clears the card values
  function revenirAuRepos(tireuse) {
    tireuse.minuteur_retour = null;
    tireuse.racine.dataset.etat = tireuse.en_maintenance ? "maintenance" : "veille";
    tireuse.racine.style.setProperty("--remplissage-verre", "0");
    ecrireChamp(tireuse.racine, "prenom", "");
    ecrireChamp(tireuse.racine, "carte", "");
    ecrireChamp(tireuse.racine, "solde", "—");
    ecrireChamp(tireuse.racine, "verres", "—");
    // En maintenance : vide et pas "0", pour cacher la ligne « Volume rincé »
    // / In maintenance: empty, not "0", to hide the "rinsed volume" line
    ecrireChamp(tireuse.racine, "volume-cl", tireuse.en_maintenance ? "" : "0");
    ecrireChamp(tireuse.racine, "prix-servi", "—");
    ecrireChamp(tireuse.racine, "message", "");
  }


  // ──────────────────────────────────────────────────────────────────
  // Application d'un message à une tireuse
  // / Applies a message to one tap
  // ──────────────────────────────────────────────────────────────────

  function appliquerMessage(tireuse, payload) {
    var racine = tireuse.racine;
    var etat = choisirEtat(payload, tireuse);
    var etat_actuel = racine.dataset.etat;

    // Le bilan reste affiché jusqu'à la fin de son minuteur.
    // Le Pi envoie souvent un « carte retirée » juste après : on l'ignore.
    // Une nouvelle carte posée, elle, passe tout de suite.
    // / The summary stays until its timer ends. A new card goes through.
    var bilan_en_cours = etat_actuel === "fin" && tireuse.minuteur_retour;
    if (bilan_en_cours && (etat === "veille" || etat === "maintenance")) {
      tireuse.en_maintenance = Boolean(payload.maintenance);
      return;
    }

    // Mémoire : tireuse en maintenance ? (un refus ne change rien)
    // / Memory: is the tap in maintenance? (a refusal changes nothing)
    if (etat !== "refus") {
      tireuse.en_maintenance = Boolean(payload.maintenance);
    }

    // Un seul minuteur par tireuse / One timer per tap
    if (tireuse.minuteur_retour) {
      clearTimeout(tireuse.minuteur_retour);
      tireuse.minuteur_retour = null;
    }

    // Veille, ou maintenance sans rinçage : on efface les valeurs de la carte
    // / Idle, or maintenance without rinse: clear the card values
    var repos_en_maintenance = etat === "maintenance" && !payload.present && !payload.session_done;
    if (etat === "veille" || repos_en_maintenance) {
      revenirAuRepos(tireuse);
    } else {
      racine.dataset.etat = etat;
    }

    // --- Prix au litre (peut changer si l'admin change le fût) ---
    if (payload.prix_litre !== undefined) {
      tireuse.prix_litre = parseFloat(payload.prix_litre) || 0;
    }

    // --- Carte : prénom et 4 derniers caractères de l'UID ---
    if (payload.prenom !== undefined) {
      ecrireChamp(racine, "prenom", payload.prenom || "");
    }
    if (payload.uid) {
      ecrireChamp(racine, "carte", String(payload.uid).slice(-4).toUpperCase());
    }

    // --- Solde et « soit N verres » ---
    var solde_est_connu = payload.balance !== undefined && payload.balance !== null && payload.balance !== "";
    if (solde_est_connu) {
      var solde = parseFloat(payload.balance) || 0;
      ecrireChamp(racine, "solde", formaterEuros(solde));
      var prix_du_verre = tireuse.prix_litre * VOLUME_VERRE_REFERENCE_L;
      var nombre_de_verres = prix_du_verre > 0 ? Math.floor(solde / prix_du_verre) : "—";
      ecrireChamp(racine, "verres", String(nombre_de_verres));
    }

    // --- Volume servi, verre qui se remplit, prix servi ---
    // En maintenance, le volume n'a de sens que pendant un rinçage (carte posée)
    // / In maintenance, volume only matters during a rinse (card present)
    if (payload.volume_ml !== undefined && etat !== "veille" && !repos_en_maintenance) {
      var volume_ml = Number(payload.volume_ml) || 0;
      ecrireChamp(racine, "volume-cl", formaterCentilitres(volume_ml));
      var remplissage = Math.min(volume_ml / VOLUME_VERRE_PLEIN_ML, 1);
      racine.style.setProperty("--remplissage-verre", String(remplissage));
      ecrireChamp(racine, "prix-servi", formaterEuros(volume_ml / 1000 * tireuse.prix_litre));
    }

    // --- Niveau du fût (vignettes de la liste) ---
    if (payload.reservoir_ml !== undefined && payload.reservoir_max_ml > 0) {
      var pourcentage = Math.max(0, Math.min(payload.reservoir_ml / payload.reservoir_max_ml * 100, 100));
      racine.style.setProperty("--niveau-fut", pourcentage.toFixed(1) + "%");
      ecrireChamp(racine, "niveau-fut", Math.round(pourcentage) + " %");
    }

    // --- Message du serveur (refus, maintenance, liste) ---
    if (payload.message !== undefined && etat !== "veille") {
      ecrireChamp(racine, "message", payload.message);
    }

    // --- Retour automatique en veille (écran non tactile) ---
    if (etat === "fin") {
      tireuse.minuteur_retour = setTimeout(function () { revenirAuRepos(tireuse); }, DELAI_RETOUR_APRES_FIN_MS);
    }
    // Fin de rinçage : on garde le volume rincé à l'écran, puis on l'efface
    // / End of rinse: keep the rinsed volume on screen, then clear it
    if (etat === "maintenance" && payload.session_done) {
      tireuse.minuteur_retour = setTimeout(function () { revenirAuRepos(tireuse); }, DELAI_RETOUR_APRES_FIN_MS);
    }
  }


  // ──────────────────────────────────────────────────────────────────
  // Réception d'un message WebSocket
  // / WebSocket message handling
  // ──────────────────────────────────────────────────────────────────

  function traiterMessageWs(evenement) {
    var donnees;
    try {
      donnees = JSON.parse(evenement.data);
    } catch (erreur) {
      console.error("Message WS illisible :", erreur);
      return;
    }
    var payload = donnees.payload || donnees;

    // Commandes envoyées par l'admin : changer de page ou recharger
    // / Admin commands: change page or reload
    if (payload.kiosk_url) { window.location.href = payload.kiosk_url; return; }
    if (payload.kiosk_reload) { window.location.reload(); return; }

    // Quelles tireuses sont concernées ? / Which taps are concerned?
    var uuid_cible = payload.tireuse_bec_uuid || "";
    if (uuid_cible === "all") {
      for (var uuid in tireuses_de_la_page) {
        appliquerMessage(tireuses_de_la_page[uuid], payload);
      }
      return;
    }
    var tireuse = tireuses_de_la_page[uuid_cible];
    if (!tireuse) {
      // Page détail : un seul écran, le message est pour lui
      // / Detail page: a single screen, the message is for it
      var liste_des_uuid = Object.keys(tireuses_de_la_page);
      if (liste_des_uuid.length !== 1 || uuid_cible) return;
      tireuse = tireuses_de_la_page[liste_des_uuid[0]];
    }
    appliquerMessage(tireuse, payload);
  }


  // ──────────────────────────────────────────────────────────────────
  // Connexion WebSocket avec reconnexion automatique
  // Le kiosk tourne 24h/24 : après une coupure (redémarrage de daphne,
  // réseau), on se reconnecte. Délai 1 s, doublé à chaque échec, 30 s max.
  // Un bandeau est affiché pendant la coupure.
  // / WebSocket with auto-reconnect: 1s backoff doubling up to 30s,
  // banner shown while disconnected.
  // ──────────────────────────────────────────────────────────────────

  var conteneur = document.getElementById("cards-grid");
  var slug_focus = (conteneur && conteneur.dataset.slugFocus) || "all";
  var protocole_ws = location.protocol === "https:" ? "wss" : "ws";
  var chemin_ws = slug_focus === "all" ? "/ws/rfid/all/" : "/ws/rfid/" + slug_focus + "/";
  var bandeau = document.getElementById("ws-status-banner");
  var delai_reconnexion_ms = 1000;

  function connecterWebSocket() {
    var ws = new WebSocket(protocole_ws + "://" + location.host + chemin_ws);

    ws.onopen = function () {
      delai_reconnexion_ms = 1000;
      if (bandeau) bandeau.hidden = true;
    };

    ws.onmessage = traiterMessageWs;

    ws.onclose = function () {
      if (bandeau) bandeau.hidden = false;
      setTimeout(connecterWebSocket, delai_reconnexion_ms);
      delai_reconnexion_ms = Math.min(delai_reconnexion_ms * 2, 30000);
    };

    // onerror est toujours suivi de onclose : on ferme pour reconnecter
    // / onerror is always followed by onclose: close to reconnect
    ws.onerror = function () { ws.close(); };
  }

  connecterWebSocket();
})();
