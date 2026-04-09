/**
 * Simulateur hardware Pi pour le kiosk controlvanne (mode DEMO).
 * / Pi hardware simulator for the controlvanne kiosk (DEMO mode).
 *
 * LOCALISATION : controlvanne/static/controlvanne/js/simu_pi.js
 *
 * Simule le trio hardware du Raspberry Pi :
 * - Lecteur NFC (boutons cliquables)
 * - Electrovanne (slider > 0 = ouverte)
 * - Debitmetre (accumulation volume selon debit slider)
 *
 * Reproduit la machine a etats de tibeer_controller.py :
 * IDLE → CARD_PRESENT → SERVING → IDLE
 *
 * Les appels fetch() utilisent le cookie de session admin (same-origin).
 * HasTireuseAccess accepte les sessions admin tenant.
 *
 * COMMUNICATION :
 * Envoie : POST /controlvanne/api/tireuse/authorize/
 * Envoie : POST /controlvanne/api/tireuse/event/ (pour_start, pour_update, pour_end, card_removed)
 * Recoit : rien (le kiosk recoit les updates via WebSocket, pas via ce script)
 */
(function () {
  "use strict";

  // --- Constantes (meme comportement que le vrai Pi) ---
  // / Constants (same behavior as the real Pi)

  // Debit max en ml/s : une pinte (500ml) en 10 secondes
  // / Max flow rate in ml/s: a pint (500ml) in 10 seconds
  var MAX_FLOW_ML_S = 50;

  // Intervalle de la boucle interne (ms) — meme frequence que le Pi (100ms)
  // / Internal loop interval (ms) — same frequency as the Pi (100ms)
  var TICK_INTERVAL_MS = 100;

  // Intervalle entre les envois pour_update (ms) — meme que UPDATE_INTERVAL_S du Pi
  // / Interval between pour_update sends (ms) — same as Pi's UPDATE_INTERVAL_S
  var UPDATE_INTERVAL_MS = 1000;


  // --- Elements du DOM ---
  // / DOM elements

  var panneau = document.getElementById("simu-pi-panel");
  if (!panneau) {
    return; // Pas de panneau simu = pas en mode DEMO
  }

  var tireuse_uuid = panneau.dataset.tireuseUuid;
  var csrf_token = panneau.dataset.csrfToken;

  var badge_etat = document.getElementById("simu-state");
  var boutons_carte = document.querySelectorAll(".simu-card-btn");
  var bouton_retirer = document.getElementById("simu-remove-card");
  var section_debit = document.getElementById("simu-flow-section");
  var slider_debit = document.getElementById("simu-flow-slider");
  var label_debit = document.getElementById("simu-flow-label");
  var badge_vanne = document.getElementById("simu-valve-state");
  var affichage_volume = document.getElementById("simu-volume-display");
  var affichage_autorise = document.getElementById("simu-allowed-display");
  var zone_message = document.getElementById("simu-message");


  // --- Etat du simulateur (meme structure que TibeerController) ---
  // / Simulator state (same structure as TibeerController)

  var etat = "IDLE"; // IDLE | CARD_PRESENT | SERVING
  var uid_courant = null;
  var session_id = null;
  var volume_autorise_ml = 0;
  var volume_cumule_ml = 0;
  var pour_start_envoye = false;
  var timer_boucle = null; // setInterval pour la boucle 100ms
  var dernier_envoi_update = 0; // timestamp du dernier pour_update


  // --- Fonctions utilitaires ---
  // / Utility functions

  /**
   * Envoie une requete POST au serveur Django.
   * Utilise le cookie de session admin (same-origin, pas besoin d'API key).
   * / Sends a POST request to the Django server.
   * Uses the admin session cookie (same-origin, no API key needed).
   */
  function poster(url, donnees) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf_token,
      },
      body: JSON.stringify(donnees),
    }).then(function (reponse) {
      return reponse.json().then(function (json) {
        if (!reponse.ok) {
          var message_erreur = json.detail || json.message || reponse.statusText;
          throw new Error(message_erreur);
        }
        return json;
      });
    });
  }

  /**
   * Met a jour l'affichage de l'etat du simulateur.
   * / Updates the simulator state display.
   */
  function maj_affichage_etat() {
    badge_etat.textContent = etat;

    // Couleur du badge selon l'etat / Badge color by state
    if (etat === "IDLE") {
      badge_etat.className = "ms-auto badge bg-dark";
    } else if (etat === "CARD_PRESENT") {
      badge_etat.className = "ms-auto badge bg-info text-dark";
    } else if (etat === "SERVING") {
      badge_etat.className = "ms-auto badge bg-success";
    }
  }

  /**
   * Met a jour l'affichage de la vanne (ouvert/ferme).
   * / Updates the valve display (open/closed).
   */
  function maj_affichage_vanne(est_ouverte) {
    if (est_ouverte) {
      badge_vanne.className = "badge bg-success";
      badge_vanne.textContent = "Ouverte";
    } else {
      badge_vanne.className = "badge bg-danger";
      badge_vanne.textContent = "Fermée";
    }
  }

  /**
   * Affiche un message dans la zone de retour API.
   * / Displays a message in the API feedback zone.
   */
  function afficher_message(texte, est_erreur) {
    zone_message.textContent = texte;
    zone_message.style.color = est_erreur ? "#e74c3c" : "#666";
  }

  /**
   * Remet le simulateur a l'etat initial (IDLE).
   * / Resets the simulator to initial state (IDLE).
   */
  function reinitialiser() {
    etat = "IDLE";
    uid_courant = null;
    session_id = null;
    volume_autorise_ml = 0;
    volume_cumule_ml = 0;
    pour_start_envoye = false;
    dernier_envoi_update = 0;

    // Arreter la boucle de simulation / Stop the simulation loop
    if (timer_boucle) {
      clearInterval(timer_boucle);
      timer_boucle = null;
    }

    // Remettre le slider a zero / Reset slider to zero
    slider_debit.value = 0;
    label_debit.textContent = "0 ml/s";

    // Cacher la section debit / Hide flow section
    section_debit.style.display = "none";

    // Remettre les indicateurs / Reset indicators
    maj_affichage_vanne(false);
    affichage_volume.textContent = "0 ml";
    affichage_autorise.textContent = "— ml";

    // Reactiver les boutons carte, desactiver retirer / Re-enable card buttons, disable remove
    boutons_carte.forEach(function (btn) {
      btn.disabled = false;
    });
    bouton_retirer.disabled = true;

    maj_affichage_etat();
  }


  // --- Actions principales ---
  // / Main actions

  /**
   * Badger une carte NFC (clic sur un bouton carte).
   * Envoie POST authorize au serveur.
   * / Badge an NFC card (click on a card button).
   * Sends POST authorize to the server.
   */
  function badger_carte(tag_id) {
    if (etat !== "IDLE") {
      return;
    }

    uid_courant = tag_id;
    etat = "CARD_PRESENT";
    maj_affichage_etat();
    afficher_message("Autorisation en cours...", false);

    // Desactiver les boutons carte pendant l'appel / Disable card buttons during call
    boutons_carte.forEach(function (btn) {
      btn.disabled = true;
    });
    bouton_retirer.disabled = false;

    poster("/controlvanne/api/tireuse/authorize/", {
      tireuse_uuid: tireuse_uuid,
      uid: tag_id,
    })
      .then(function (resultat) {
        if (resultat.authorized) {
          // Autorise — afficher le slider / Authorized — show slider
          session_id = resultat.session_id;
          volume_autorise_ml = parseFloat(resultat.allowed_ml) || 0;
          volume_cumule_ml = 0;
          pour_start_envoye = false;

          section_debit.style.display = "block";
          affichage_autorise.textContent = Math.round(volume_autorise_ml) + " ml";
          afficher_message(
            "Autorisé — solde: " +
              (resultat.solde_centimes / 100).toFixed(2) +
              " €",
            false
          );
        } else {
          // Refuse / Denied
          afficher_message(
            "Refusé: " + (resultat.message || "Non autorisé"),
            true
          );
          // On reste en CARD_PRESENT — le user peut retirer la carte
        }
      })
      .catch(function (erreur) {
        afficher_message("Erreur: " + erreur.message, true);
      });
  }

  /**
   * Envoie un event au serveur (pour_start, pour_update, pour_end, card_removed).
   * / Sends an event to the server.
   */
  function envoyer_event(type_event, volume_ml) {
    return poster("/controlvanne/api/tireuse/event/", {
      tireuse_uuid: tireuse_uuid,
      uid: uid_courant,
      event_type: type_event,
      volume_ml: volume_ml.toFixed(2),
    });
  }

  /**
   * Boucle de simulation du debitmetre (appelee toutes les 100ms).
   * Accumule le volume selon la position du slider.
   * Envoie pour_update toutes les secondes.
   * / Flow meter simulation loop (called every 100ms).
   * Accumulates volume based on slider position.
   * Sends pour_update every second.
   */
  function tick_debitmetre() {
    if (etat !== "SERVING") {
      return;
    }

    // Lire la position du slider (0 a 100) / Read slider position (0 to 100)
    var pourcentage_slider = parseInt(slider_debit.value, 10);

    if (pourcentage_slider === 0) {
      // Slider a zero = vanne fermee = fin du tirage
      // / Slider at zero = valve closed = end of pour
      arreter_tirage();
      return;
    }

    // Calculer le volume ajoute ce tick / Calculate volume added this tick
    // debit_ml_par_seconde = (pourcentage / 100) * MAX_FLOW_ML_S
    // volume_ce_tick = debit * (TICK_INTERVAL_MS / 1000)
    var debit_ml_s = (pourcentage_slider / 100) * MAX_FLOW_ML_S;
    var volume_ce_tick = debit_ml_s * (TICK_INTERVAL_MS / 1000);
    volume_cumule_ml += volume_ce_tick;

    // Mettre a jour l'affichage / Update display
    affichage_volume.textContent = Math.round(volume_cumule_ml) + " ml";
    label_debit.textContent = Math.round(debit_ml_s) + " ml/s";

    // Verifier si le volume max est atteint / Check if max volume reached
    if (volume_autorise_ml > 0 && volume_cumule_ml >= volume_autorise_ml) {
      volume_cumule_ml = volume_autorise_ml;
      affichage_volume.textContent = Math.round(volume_cumule_ml) + " ml";
      afficher_message("Volume max atteint — vanne fermée", false);
      slider_debit.value = 0;
      label_debit.textContent = "0 ml/s";
      arreter_tirage();
      return;
    }

    // Envoyer pour_update toutes les secondes / Send pour_update every second
    var maintenant = Date.now();
    if (maintenant - dernier_envoi_update >= UPDATE_INTERVAL_MS) {
      dernier_envoi_update = maintenant;
      envoyer_event("pour_update", volume_cumule_ml).catch(function (err) {
        // Non bloquant, comme le vrai Pi / Non-blocking, like the real Pi
        console.warn("pour_update échoué:", err.message);
      });
    }
  }

  /**
   * Demarre le tirage (slider passe de 0 a > 0 pour la premiere fois).
   * Envoie pour_start et lance la boucle debitmetre.
   * / Starts the pour (slider goes from 0 to > 0 for the first time).
   * Sends pour_start and starts the flow meter loop.
   */
  function demarrer_tirage() {
    etat = "SERVING";
    pour_start_envoye = true;
    dernier_envoi_update = Date.now();
    maj_affichage_etat();
    maj_affichage_vanne(true);
    afficher_message("Tirage en cours...", false);

    envoyer_event("pour_start", 0).catch(function (err) {
      console.warn("pour_start échoué:", err.message);
    });

    // Demarrer la boucle 100ms / Start the 100ms loop
    timer_boucle = setInterval(tick_debitmetre, TICK_INTERVAL_MS);
  }

  /**
   * Arrete le tirage (slider revient a 0 ou volume max atteint).
   * Envoie pour_end avec le volume final.
   * / Stops the pour (slider returns to 0 or max volume reached).
   * Sends pour_end with final volume.
   */
  function arreter_tirage() {
    // Arreter la boucle / Stop the loop
    if (timer_boucle) {
      clearInterval(timer_boucle);
      timer_boucle = null;
    }

    maj_affichage_vanne(false);
    etat = "CARD_PRESENT";
    maj_affichage_etat();

    envoyer_event("pour_end", volume_cumule_ml)
      .then(function (resultat) {
        var montant = resultat.montant_centimes || 0;
        afficher_message(
          "Fin tirage — " +
            Math.round(volume_cumule_ml) +
            " ml — " +
            (montant / 100).toFixed(2) +
            " €",
          false
        );
      })
      .catch(function (err) {
        afficher_message("Erreur pour_end: " + err.message, true);
      });
  }

  /**
   * Retirer la carte (bouton "Retirer carte").
   * Si en service : arrete le tirage d'abord, puis envoie card_removed.
   * / Remove the card (button "Remove card").
   * If serving: stops the pour first, then sends card_removed.
   */
  function retirer_carte() {
    if (etat === "IDLE") {
      return;
    }

    // Si en service, fermer la vanne et envoyer pour_end d'abord
    // / If serving, close valve and send pour_end first
    if (etat === "SERVING") {
      if (timer_boucle) {
        clearInterval(timer_boucle);
        timer_boucle = null;
      }
      maj_affichage_vanne(false);

      envoyer_event("pour_end", volume_cumule_ml).catch(function (err) {
        console.warn("pour_end échoué:", err.message);
      });
    }

    // Petit delai puis card_removed (comme le CARD_GRACE_PERIOD du Pi)
    // / Short delay then card_removed (like the Pi's CARD_GRACE_PERIOD)
    setTimeout(function () {
      envoyer_event("card_removed", 0)
        .then(function () {
          afficher_message("Carte retirée", false);
        })
        .catch(function (err) {
          afficher_message("card_removed: " + err.message, true);
        })
        .finally(function () {
          reinitialiser();
        });
    }, 200);
  }


  // --- Branchement des evenements ---
  // / Event binding

  // Boutons carte NFC / NFC card buttons
  boutons_carte.forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      var tag_id = bouton.dataset.tagId;
      badger_carte(tag_id);
    });
  });

  // Bouton retirer carte / Remove card button
  bouton_retirer.addEventListener("click", retirer_carte);

  // Slider debit — detecter le passage de 0 a > 0 et inversement
  // / Flow slider — detect transition from 0 to > 0 and back
  slider_debit.addEventListener("input", function () {
    var valeur = parseInt(slider_debit.value, 10);
    var debit_ml_s = (valeur / 100) * MAX_FLOW_ML_S;
    label_debit.textContent = Math.round(debit_ml_s) + " ml/s";

    // Transition 0 → >0 : demarrer le tirage / Transition 0 → >0: start pour
    if (valeur > 0 && etat === "CARD_PRESENT" && !pour_start_envoye) {
      demarrer_tirage();
    }
  });


  // --- Init ---
  console.log("Simulateur Pi chargé pour tireuse", tireuse_uuid);

})();
