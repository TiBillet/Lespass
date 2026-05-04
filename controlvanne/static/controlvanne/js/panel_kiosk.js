/**
 * Logique JS du panneau kiosk controlvanne.
 * / Kiosk JS logic for the controlvanne panel.
 *
 * LOCALISATION : controlvanne/static/controlvanne/js/panel_kiosk.js
 *
 * Ce script gère l'affichage temps réel des tireuses via WebSocket.
 * Il est chargé par kiosk_list.html (toutes les tireuses)
 * et kiosk_detail.html (une seule tireuse).
 * / This script handles real-time tap display via WebSocket.
 * It is loaded by kiosk_list.html (all taps)
 * and kiosk_detail.html (a single tap).
 *
 * COMMUNICATION :
 * Reçoit : messages JSON depuis PanelConsumer (consumers.py) via WebSocket
 * Met à jour : les éléments DOM identifiés par <champ>-<uuid>
 * / Receives: JSON messages from PanelConsumer (consumers.py) via WebSocket
 * Updates: DOM elements identified by <field>-<uuid>
 *
 * Flux WebSocket :
 * 1. Connexion à /ws/rfid/all/ (vue liste) ou /ws/rfid/<uuid>/ (vue detail)
 * 2. Réception du payload initial (état courant de la/les tireuse(s))
 * 3. Réception des mises à jour en temps réel (signaux Django post_save)
 * / WebSocket flow:
 * 1. Connect to /ws/rfid/all/ (list view) or /ws/rfid/<uuid>/ (detail view)
 * 2. Receive initial payload (current state of tap(s))
 * 3. Receive real-time updates (Django post_save signals)
 */
(function () {
  "use strict";

  // Dictionnaire des cartes tireuses, indexé par UUID
  // / Dictionary of tap cards, indexed by UUID
  var cards = {};

  // Constantes SVG pour la jauge
  // / SVG constants for the gauge
  var CX = 50;
  var CY = 54;
  var R_ARC = 44;
  var R_NEEDLE = 38;


  // ──────────────────────────────────────────────────────────────────
  // Fonctions de mise à jour de l'affichage
  // / Display update functions
  // ──────────────────────────────────────────────────────────────────

  /**
   * Met à jour la jauge SVG pour un niveau donné (0 à 1).
   * / Updates the SVG gauge for a given level (0 to 1).
   *
   * @param {Object} c — objet carte (élément dans le dictionnaire cards)
   * @param {number} reservoir_ml — volume actuel dans le fût (millilitres)
   * @param {number} max_ml — volume maximum du fût (millilitres)
   */
  function mettreAJourJauge(c, reservoir_ml, max_ml) {
    var pourcentage = max_ml > 0 ? Math.min(Math.max(reservoir_ml / max_ml, 0), 1) : 0;

    // Angle theta : pi = gauche (0%) → 0 = droite (100%)
    // / Angle theta: pi = left (0%) → 0 = right (100%)
    var theta = (1 - pourcentage) * Math.PI;

    // Arc de remplissage / Fill arc
    var arc_remplissage = c.gaugeFill;
    if (arc_remplissage) {
      if (pourcentage < 0.002) {
        arc_remplissage.setAttribute("d", "");
      } else if (pourcentage > 0.998) {
        arc_remplissage.setAttribute("d", "M 6," + CY + " A " + R_ARC + "," + R_ARC + " 0 0,1 94," + CY);
      } else {
        var ex = (CX + R_ARC * Math.cos(theta)).toFixed(2);
        var ey = (CY - R_ARC * Math.sin(theta)).toFixed(2);
        arc_remplissage.setAttribute("d", "M 6," + CY + " A " + R_ARC + "," + R_ARC + " 0 0,1 " + ex + "," + ey);
      }
      // Couleur selon le niveau : vert > 50%, orange > 25%, rouge sinon
      // / Color by level: green > 50%, orange > 25%, red otherwise
      var couleur = pourcentage > 0.5 ? "#27ae60" : (pourcentage > 0.25 ? "#f39c12" : "#e74c3c");
      arc_remplissage.setAttribute("stroke", couleur);
    }

    // Aiguille / Needle
    var aiguille = c.gaugeNeedle;
    if (aiguille) {
      var nx = (CX + R_NEEDLE * Math.cos(theta)).toFixed(2);
      var ny = (CY - R_NEEDLE * Math.sin(theta)).toFixed(2);
      aiguille.setAttribute("x2", nx);
      aiguille.setAttribute("y2", ny);
    }
  }

  /**
   * Calcule et affiche les prix (25cl, 33cl, 50cl) depuis le prix au litre.
   * / Computes and displays prices (25cl, 33cl, 50cl) from price per liter.
   *
   * @param {Object} c — objet carte
   * @param {string|number} prix_litre — prix au litre en EUR
   */
  function mettreAJourPrix(c, prix_litre) {
    var prix = parseFloat(prix_litre) || 0;
    c.prixL.textContent = prix.toFixed(2);
    c.p25.textContent = (prix * 0.25).toFixed(2) + " \u20ac";
    c.p33.textContent = (prix * 0.33).toFixed(2) + " \u20ac";
    c.p50.textContent = (prix * 0.50).toFixed(2) + " \u20ac";
  }


  // ──────────────────────────────────────────────────────────────────
  // Initialisation des éléments DOM par carte
  // / DOM element initialization per card
  // ──────────────────────────────────────────────────────────────────

  document.querySelectorAll(".card[data-uuid]").forEach(function (element_carte) {
    var uuid = element_carte.dataset.uuid;
    var max_ml = parseFloat(element_carte.dataset.maxreservoir) || 1;
    var bloc_prix = document.getElementById("prix-block-" + uuid);

    cards[uuid] = {
      uuid: uuid,
      maxMl: max_ml,
      uid:         document.getElementById("uid-" + uuid),
      auth:        document.getElementById("auth-" + uuid),
      state:       document.getElementById("state-" + uuid),
      vol:         document.getElementById("vol-" + uuid),
      msg:         document.getElementById("msg-" + uuid),
      nomTireuse:  document.getElementById("nom-tireuse-" + uuid),
      liquid:      document.getElementById("liquid-" + uuid),
      balance:     document.getElementById("balance-" + uuid),
      gaugeFill:   document.getElementById("gauge-fill-" + uuid),
      gaugeNeedle: document.getElementById("gauge-needle-" + uuid),
      prixL:       document.getElementById("prixL-" + uuid),
      p25:         document.getElementById("p25-" + uuid),
      p33:         document.getElementById("p33-" + uuid),
      p50:         document.getElementById("p50-" + uuid),
      lastBalance: null,
      wasPresent: false,
      isMaintenance: false,
      resetTimer: null,
    };

    // Initialiser les prix depuis les données du template (rendu serveur)
    // / Init prices from template data (server-rendered)
    if (bloc_prix) {
      mettreAJourPrix(cards[uuid], bloc_prix.dataset.prixlitre);
    }
  });


  // ──────────────────────────────────────────────────────────────────
  // Popup fin de service
  // / End-of-service popup
  // ──────────────────────────────────────────────────────────────────

  var popup = document.getElementById("global-popup");
  if (!popup) {
    popup = document.createElement("div");
    popup.id = "global-popup";
    popup.style.cssText = "display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#2c3e50;color:white;padding:30px;border-radius:15px;text-align:center;z-index:9999;box-shadow:0 10px 40px rgba(0,0,0,0.3)";
    popup.innerHTML =
      '<div style="font-size:48px;margin-bottom:10px">\uD83C\uDF7A</div>' +
      '<div style="font-size:20px;margin-bottom:10px">Bonne d\u00e9gustation !</div>' +
      '<div style="font-size:16px">Il vous reste <b id="popup-balance">\u2014</b> \u20ac sur votre carte</div>';
    document.body.appendChild(popup);
  }

  var delai_fermeture_popup = null;

  function afficherPopup(solde) {
    var element_solde = document.getElementById("popup-balance");
    if (element_solde) {
      element_solde.textContent = solde;
    }
    popup.style.display = "block";
    if (delai_fermeture_popup) {
      clearTimeout(delai_fermeture_popup);
    }
    delai_fermeture_popup = setTimeout(function () {
      popup.style.display = "none";
    }, 5000);
  }


  // ──────────────────────────────────────────────────────────────────
  // Remise à zéro de l'affichage d'une carte
  // / Reset card display to idle state
  // ──────────────────────────────────────────────────────────────────

  function reinitialiserCarte(c) {
    if (!c) return;
    c.uid.innerHTML = "&mdash;";
    c.vol.textContent = "0 cl";
    c.balance.textContent = "\u2014";
    if (c.isMaintenance) {
      c.auth.className = "badge bg-warning text-dark";
      c.auth.textContent = "Hors service";
      c.state.className = "badge bg-warning text-dark";
      c.state.textContent = "Maintenance";
      c.msg.textContent = "En Maintenance";
    } else {
      c.auth.className = "badge bg-secondary";
      c.auth.textContent = "En attente";
      c.state.className = "badge bg-danger";
      c.state.textContent = "Ferm\u00e9e";
      c.msg.textContent = "Posez votre badge...";
    }
  }

  function mettreAJourBadgeAutorisation(element, est_autorise) {
    element.className = "badge " + (est_autorise ? "bg-success" : "bg-danger");
    element.textContent = est_autorise ? "Autoris\u00e9" : "Refus\u00e9";
  }


  // ──────────────────────────────────────────────────────────────────
  // WebSocket — connexion et traitement des messages
  // / WebSocket — connection and message handling
  // ──────────────────────────────────────────────────────────────────

  // slug_focus est lu depuis l'attribut data du conteneur de cartes
  // "all" pour la vue liste, "<uuid>" pour la vue detail
  // / slug_focus is read from the cards container data attribute
  // "all" for list view, "<uuid>" for detail view
  var slug_focus = document.getElementById("cards-grid").dataset.slugFocus || "all";
  var protocole_ws = location.protocol === "https:" ? "wss" : "ws";

  // Choix du canal WebSocket selon la vue
  // / WebSocket channel choice based on view
  var chemin_ws = (slug_focus === "all")
    ? "/ws/rfid/all/"
    : "/ws/rfid/" + slug_focus + "/";

  var ws = new WebSocket(protocole_ws + "://" + location.host + chemin_ws);

  ws.onopen = function () {
    console.log("WS connect\u00e9 sur " + chemin_ws);
  };

  ws.onmessage = function (evenement) {
    try {
      var donnees = JSON.parse(evenement.data);
      var payload = donnees.payload || donnees;

      // Commandes de navigation du kiosk (utilisées par l'admin)
      // / Kiosk navigation commands (used by admin)
      if (payload.kiosk_url) { window.location.href = payload.kiosk_url; return; }
      if (payload.kiosk_reload) { window.location.reload(); return; }

      // ── Mode maintenance ──
      if (payload.maintenance) {
        var uuid_maintenance = payload.tireuse_bec_uuid || "";
        var carte_maintenance = cards[uuid_maintenance] || Object.values(cards)[0];
        if (!carte_maintenance) return;

        carte_maintenance.isMaintenance = true;
        carte_maintenance.state.className = "badge bg-warning text-dark";
        carte_maintenance.state.textContent = "Maintenance";
        carte_maintenance.uid.textContent = payload.uid || "\u2014";

        if (payload.present && payload.authorized) {
          // Session maintenance active (carte rinçage autorisée)
          // / Active maintenance session (cleaning card authorized)
          carte_maintenance.auth.className = "badge bg-warning text-dark";
          carte_maintenance.auth.textContent = "Rin\u00e7age";
          carte_maintenance.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + " cl";
          carte_maintenance.balance.textContent = "\u2014";
          if (payload.message) carte_maintenance.msg.textContent = payload.message;
        } else if (payload.session_done) {
          // Fin de session maintenance / End of maintenance session
          carte_maintenance.auth.className = "badge bg-info text-dark";
          carte_maintenance.auth.textContent = "Fin rin\u00e7age";
          carte_maintenance.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + " cl";
          if (payload.message) carte_maintenance.msg.textContent = payload.message;
          setTimeout(function () { reinitialiserCarte(carte_maintenance); }, 5000);
        } else {
          // Tireuse en maintenance — état repos
          // / Tap in maintenance — idle state
          carte_maintenance.auth.className = "badge bg-warning text-dark";
          carte_maintenance.auth.textContent = "Hors service";
          carte_maintenance.vol.textContent = "0 cl";
          var solde_maintenance = payload.balance;
          var solde_est_valide = solde_maintenance !== undefined && solde_maintenance !== null && solde_maintenance !== "\u2014" && parseFloat(solde_maintenance) > 0;
          carte_maintenance.balance.textContent = solde_est_valide ? solde_maintenance : "\u2014";
          carte_maintenance.msg.textContent = payload.message || "En Maintenance";
        }
        return;
      }

      // ── Mode normal ──
      var uuid_cible = payload.tireuse_bec_uuid || payload.tireuse_bec || "";
      var cartes_ciblees = [];
      if (uuid_cible === "all") {
        cartes_ciblees = Object.values(cards);
      } else if (cards[uuid_cible]) {
        cartes_ciblees = [cards[uuid_cible]];
      } else {
        console.warn("Event re\u00e7u pour tireuse inconnue :", uuid_cible);
        return;
      }

      cartes_ciblees.forEach(function (c) {
        // Payload normal (pas maintenance) → la tireuse est en service
        // / Normal payload (not maintenance) → tap is in service
        c.isMaintenance = false;

        // Mise à jour jauge (tous les messages) / Update gauge (all messages)
        if (payload.reservoir_ml !== undefined) {
          var max_ml = payload.reservoir_max_ml || c.maxMl;
          c.maxMl = max_ml;
          mettreAJourJauge(c, payload.reservoir_ml, max_ml);
        }

        // Mise à jour nom et boisson / Update name and drink
        if (payload.tireuse_bec !== undefined) c.nomTireuse.textContent = payload.tireuse_bec;
        if (payload.liquid_label !== undefined) c.liquid.textContent = payload.liquid_label;

        // Mise à jour prix / Update prices
        if (payload.prix_litre !== undefined) {
          mettreAJourPrix(c, payload.prix_litre);
        }

        // CAS 1 : Carte présente / CASE 1: Card present
        if (payload.present) {
          c.wasPresent = true;
          // Annuler tout timer de reset en cours
          // / Cancel any pending reset timer
          if (c.resetTimer) { clearTimeout(c.resetTimer); c.resetTimer = null; }
          c.uid.textContent = payload.uid || "Lu...";
          if (typeof payload.authorized !== "undefined") mettreAJourBadgeAutorisation(c.auth, payload.authorized);
          c.state.className = payload.vanne_ouverte ? "badge bg-success" : "badge bg-danger";
          c.state.textContent = payload.vanne_ouverte ? "Ouverte" : "Ferm\u00e9e";
          c.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + " cl";
          if (payload.balance) { c.balance.textContent = payload.balance; c.lastBalance = payload.balance; }
          if (payload.message) c.msg.textContent = payload.message;
          return;
        }

        // Capturer wasPresent AVANT de le réinitialiser
        // / Capture wasPresent BEFORE resetting it
        var etait_present = c.wasPresent;
        c.wasPresent = false;

        // CAS 2 : Fin de session / CASE 2: End of session
        if (payload.session_done) {
          // Si une nouvelle carte est déjà active → ignorer ce session_done tardif
          // / If a new card is already active → ignore this late session_done
          if (etait_present) return;
          c.auth.className = "badge bg-info text-dark";
          c.auth.textContent = "Termin\u00e9";
          c.state.className = "badge bg-danger";
          c.state.textContent = "Ferm\u00e9e";
          c.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + " cl";
          if (payload.balance) { c.balance.textContent = payload.balance; c.lastBalance = payload.balance; }
          if (payload.message) c.msg.textContent = payload.message;
          if (c.lastBalance && parseFloat(payload.volume_ml || 0) > 0) afficherPopup(c.lastBalance);
          c.resetTimer = setTimeout(function () { c.resetTimer = null; reinitialiserCarte(c); }, 5000);
          return;
        }

        // CAS 3 : Retrait / refus / CASE 3: Removal / refusal
        reinitialiserCarte(c);
        c.auth.className = "badge bg-secondary";
        c.msg.textContent = "En attente...";
        c.balance.textContent = "\u2014";
      });

    } catch (erreur) {
      console.error("Erreur traitement message WS :", erreur);
    }
  };


  // ──────────────────────────────────────────────────────────────────
  // Initialisation des jauges depuis les valeurs du template (rendu serveur)
  // / Init gauges from template values (server-rendered)
  // ──────────────────────────────────────────────────────────────────

  document.querySelectorAll(".card[data-uuid]").forEach(function (element_carte) {
    var uuid = element_carte.dataset.uuid;
    var c = cards[uuid];
    if (!c) return;
    var reservoir_initial = parseFloat(element_carte.dataset.reservoir) || 0;
    mettreAJourJauge(c, reservoir_initial, c.maxMl);
  });

})();
