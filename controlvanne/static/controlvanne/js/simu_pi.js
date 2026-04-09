/**
 * Simulateur hardware Pi pour le kiosk controlvanne (mode DEMO).
 * / Pi hardware simulator for the controlvanne kiosk (DEMO mode).
 *
 * LOCALISATION : controlvanne/static/controlvanne/js/simu_pi.js
 *
 * Reproduit EXACTEMENT le comportement de tibeer_controller.py :
 *
 * HARDWARE SIMULE :
 * - Lecteur NFC    → boutons cliquables (poser / retirer une carte)
 * - Electrovanne   → s'ouvre automatiquement dès l'autorisation serveur,
 *                    se ferme quand la carte est retirée ou volume max atteint.
 *                    L'utilisateur ne contrôle PAS la vanne.
 * - Robinet        → le slider simule le robinet mécanique que l'utilisateur
 *                    ouvre/ferme physiquement. La bière ne coule que si
 *                    la vanne EST ouverte ET le robinet est ouvert (slider > 0).
 * - Debitmetre     → accumule le volume quand la bière coule (vanne + robinet ouverts).
 *
 * MACHINE A ETATS (identique au Pi) :
 *
 *   IDLE : en attente de badge
 *     ↓ clic bouton carte
 *   AUTHORIZING : POST /authorize/ en cours
 *     ↓ authorized=true
 *   SERVING : vanne ouverte, debitmetre actif, pour_start envoyé
 *     │ slider > 0 : la bière coule, pour_update toutes les 1s
 *     │ slider = 0 : robinet fermé, pas de débit (mais vanne reste ouverte)
 *     │ volume >= allowed_ml : vanne fermée → pour_end → CARD_PRESENT
 *     ↓ clic "Retirer carte"
 *   CARD_REMOVING : grace period 1s, puis pour_end + card_removed → IDLE
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

  // Delai avant de considerer la carte retiree (ms) — meme que CARD_GRACE_PERIOD_S du Pi
  // / Delay before considering card removed (ms) — same as Pi's CARD_GRACE_PERIOD_S
  var CARD_GRACE_PERIOD_MS = 1000;


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

  var etat = "IDLE"; // IDLE | SERVING | CARD_PRESENT (apres volume max)
  var uid_courant = null;
  var session_id = null;
  var volume_autorise_ml = 0;
  var volume_cumule_ml = 0;
  var vanne_ouverte = false; // electrovanne (commandee par le Pi, pas l'utilisateur)
  var timer_boucle = null; // setInterval pour la boucle 100ms (debitmetre)
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

  function maj_affichage_etat() {
    badge_etat.textContent = etat;
    if (etat === "IDLE") {
      badge_etat.className = "ms-auto badge bg-dark";
    } else if (etat === "SERVING") {
      badge_etat.className = "ms-auto badge bg-success";
    } else if (etat === "CARD_PRESENT") {
      badge_etat.className = "ms-auto badge bg-info text-dark";
    }
  }

  function maj_affichage_vanne() {
    if (vanne_ouverte) {
      badge_vanne.className = "badge bg-success";
      badge_vanne.textContent = "Ouverte";
    } else {
      badge_vanne.className = "badge bg-danger";
      badge_vanne.textContent = "Fermée";
    }
  }

  function afficher_message(texte, est_erreur) {
    zone_message.textContent = texte;
    zone_message.style.color = est_erreur ? "#e74c3c" : "#666";
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
   * Remet le simulateur a l'etat initial (IDLE).
   * / Resets the simulator to initial state (IDLE).
   */
  function reinitialiser() {
    etat = "IDLE";
    uid_courant = null;
    session_id = null;
    volume_autorise_ml = 0;
    volume_cumule_ml = 0;
    vanne_ouverte = false;
    dernier_envoi_update = 0;

    if (timer_boucle) {
      clearInterval(timer_boucle);
      timer_boucle = null;
    }

    slider_debit.value = 0;
    label_debit.textContent = "0 ml/s";
    section_debit.style.display = "none";
    maj_affichage_vanne();
    affichage_volume.textContent = "0 ml";
    affichage_autorise.textContent = "\u2014 ml";

    boutons_carte.forEach(function (btn) {
      btn.disabled = false;
    });
    bouton_retirer.disabled = true;

    maj_affichage_etat();
  }


  // ──────────────────────────────────────────────────────────────────
  // Machine a etats — reproduit tibeer_controller.py
  // / State machine — reproduces tibeer_controller.py
  // ──────────────────────────────────────────────────────────────────

  /**
   * ETAPE 1 : Poser une carte NFC.
   * Envoie POST /authorize/ au serveur.
   * Si autorise : ouvre la vanne, envoie pour_start, lance le debitmetre.
   * Comportement identique a _handle_new_session() dans tibeer_controller.py.
   * / STEP 1: Place an NFC card.
   * Sends POST /authorize/ to the server.
   * If authorized: opens valve, sends pour_start, starts flow meter.
   * Same behavior as _handle_new_session() in tibeer_controller.py.
   */
  function poser_carte(tag_id) {
    if (etat !== "IDLE") {
      return;
    }

    uid_courant = tag_id;
    afficher_message("Autorisation en cours...", false);

    // Desactiver les boutons carte, activer retirer
    // / Disable card buttons, enable remove
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
          // --- Autorise : ouvrir la vanne immediatement (comme le Pi) ---
          // / Authorized: open valve immediately (like the Pi)
          session_id = resultat.session_id;
          volume_autorise_ml = parseFloat(resultat.allowed_ml) || 0;
          volume_cumule_ml = 0;

          // Ouvrir la vanne (le Pi fait valve.open() ici)
          // / Open valve (the Pi does valve.open() here)
          vanne_ouverte = true;
          etat = "SERVING";
          maj_affichage_etat();
          maj_affichage_vanne();

          // Afficher le slider (robinet mecanique) et les indicateurs
          // / Show slider (mechanical tap) and indicators
          section_debit.style.display = "block";
          affichage_autorise.textContent = Math.round(volume_autorise_ml) + " ml";

          afficher_message(
            "Vanne ouverte — solde: " +
              (resultat.solde_centimes / 100).toFixed(2) +
              " \u20ac — ouvrez le robinet (slider)",
            false
          );

          // Envoyer pour_start (comme le Pi fait juste apres valve.open())
          // / Send pour_start (like the Pi does right after valve.open())
          envoyer_event("pour_start", 0).catch(function (err) {
            console.warn("pour_start \u00e9chou\u00e9:", err.message);
          });

          // Demarrer la boucle debitmetre (100ms, comme le Pi)
          // Le debit depend du slider (robinet). Si slider=0, debit=0 (robinet ferme).
          // / Start flow meter loop (100ms, like the Pi)
          // Flow depends on slider (tap). If slider=0, flow=0 (tap closed).
          dernier_envoi_update = Date.now();
          timer_boucle = setInterval(tick_debitmetre, TICK_INTERVAL_MS);
        } else {
          // --- Refuse ---
          // La carte est posee mais non autorisee (solde insuffisant, carte inconnue)
          // L'etat reste sur un pseudo-CARD_PRESENT : le user peut retirer la carte
          // / Card is placed but not authorized (insufficient funds, unknown card)
          etat = "CARD_PRESENT";
          maj_affichage_etat();
          afficher_message(
            "Refus\u00e9: " + (resultat.message || "Non autoris\u00e9"),
            true
          );
        }
      })
      .catch(function (erreur) {
        etat = "CARD_PRESENT";
        maj_affichage_etat();
        afficher_message("Erreur: " + erreur.message, true);
      });
  }

  /**
   * BOUCLE DEBITMETRE : appelee toutes les 100ms tant que la vanne est ouverte.
   * Accumule le volume UNIQUEMENT si le slider (robinet) est > 0.
   * La vanne peut etre ouverte sans debit (robinet ferme = slider a 0).
   * Comportement identique a _handle_pouring_loop() dans tibeer_controller.py.
   * / FLOW METER LOOP: called every 100ms while valve is open.
   * Accumulates volume ONLY if slider (tap) is > 0.
   * Valve can be open without flow (tap closed = slider at 0).
   * Same behavior as _handle_pouring_loop() in tibeer_controller.py.
   */
  function tick_debitmetre() {
    if (!vanne_ouverte) {
      return;
    }

    // Lire la position du slider (robinet mecanique)
    // 0 = robinet ferme (pas de debit meme si vanne ouverte)
    // 100 = robinet grand ouvert (debit max)
    // / Read slider position (mechanical tap)
    // 0 = tap closed (no flow even if valve is open)
    // 100 = tap fully open (max flow)
    var pourcentage_slider = parseInt(slider_debit.value, 10);

    if (pourcentage_slider > 0) {
      // Calculer le volume ajoute ce tick / Calculate volume added this tick
      var debit_ml_s = (pourcentage_slider / 100) * MAX_FLOW_ML_S;
      var volume_ce_tick = debit_ml_s * (TICK_INTERVAL_MS / 1000);
      volume_cumule_ml += volume_ce_tick;

      // Mettre a jour l'affichage / Update display
      affichage_volume.textContent = Math.round(volume_cumule_ml) + " ml";
      label_debit.textContent = Math.round(debit_ml_s) + " ml/s";
    }

    // Verifier si le volume max est atteint (comme le Pi)
    // Si oui : fermer la vanne, envoyer pour_end
    // La carte est encore posee — le user doit la retirer
    // / Check if max volume reached (like the Pi)
    // If so: close valve, send pour_end
    // Card is still placed — user must remove it
    if (volume_autorise_ml > 0 && volume_cumule_ml >= volume_autorise_ml) {
      volume_cumule_ml = volume_autorise_ml;
      affichage_volume.textContent = Math.round(volume_cumule_ml) + " ml";
      fermer_vanne_et_terminer("Volume max atteint \u2014 retirez la carte");
      return;
    }

    // Envoyer pour_update toutes les secondes (comme le Pi)
    // Seulement si du volume a ete servi (slider > 0)
    // / Send pour_update every second (like the Pi)
    // Only if volume has been served (slider > 0)
    var maintenant = Date.now();
    if (
      pourcentage_slider > 0 &&
      maintenant - dernier_envoi_update >= UPDATE_INTERVAL_MS
    ) {
      dernier_envoi_update = maintenant;
      envoyer_event("pour_update", volume_cumule_ml).catch(function (err) {
        console.warn("pour_update \u00e9chou\u00e9:", err.message);
      });
    }
  }

  /**
   * Ferme la vanne et envoie pour_end.
   * Appele quand le volume max est atteint.
   * La carte est encore posee — le user doit la retirer pour revenir a IDLE.
   * Comportement identique a _end_session_actions() dans tibeer_controller.py.
   * / Closes valve and sends pour_end.
   * Called when max volume is reached.
   * Card is still placed — user must remove it to return to IDLE.
   * Same behavior as _end_session_actions() in tibeer_controller.py.
   */
  function fermer_vanne_et_terminer(message_info) {
    // Fermer la vanne (le Pi fait valve.close() ici)
    // / Close valve (the Pi does valve.close() here)
    vanne_ouverte = false;
    maj_affichage_vanne();

    // Arreter la boucle debitmetre / Stop flow meter loop
    if (timer_boucle) {
      clearInterval(timer_boucle);
      timer_boucle = null;
    }

    // L'etat passe a CARD_PRESENT : la carte est encore posee, mais la vanne est fermee
    // Le user doit cliquer "Retirer carte" pour revenir a IDLE
    // / State goes to CARD_PRESENT: card is still placed, but valve is closed
    // User must click "Remove card" to return to IDLE
    etat = "CARD_PRESENT";
    maj_affichage_etat();
    slider_debit.value = 0;
    label_debit.textContent = "0 ml/s";

    // Envoyer pour_end avec le volume final / Send pour_end with final volume
    envoyer_event("pour_end", volume_cumule_ml)
      .then(function (resultat) {
        var montant = resultat.montant_centimes || 0;
        afficher_message(
          message_info +
            " \u2014 " +
            Math.round(volume_cumule_ml) +
            " ml \u2014 " +
            (montant / 100).toFixed(2) +
            " \u20ac",
          false
        );
      })
      .catch(function (err) {
        afficher_message("Erreur pour_end: " + err.message, true);
      });
  }

  /**
   * RETIRER LA CARTE : le user retire physiquement sa carte NFC.
   * Comportement identique a _handle_card_removal() dans tibeer_controller.py :
   * 1. Grace period de 1 seconde (anti-rebond)
   * 2. Si la vanne est encore ouverte : fermer + pour_end
   * 3. Envoyer card_removed
   * 4. Retour a IDLE
   * / REMOVE CARD: user physically removes their NFC card.
   * Same behavior as _handle_card_removal() in tibeer_controller.py:
   * 1. Grace period of 1 second (anti-bounce)
   * 2. If valve still open: close + pour_end
   * 3. Send card_removed
   * 4. Return to IDLE
   */
  function retirer_carte() {
    if (etat === "IDLE") {
      return;
    }

    // Desactiver le bouton pour eviter les double-clics / Disable to prevent double-clicks
    bouton_retirer.disabled = true;
    afficher_message("Carte retir\u00e9e \u2014 fermeture en cours...", false);

    // Grace period (1 seconde, comme CARD_GRACE_PERIOD_S du Pi)
    // Sur le vrai Pi, le lecteur RFID fait plusieurs tentatives avant de conclure
    // que la carte est partie. On simule ce delai.
    // / Grace period (1 second, like Pi's CARD_GRACE_PERIOD_S)
    // On the real Pi, the RFID reader makes several attempts before concluding
    // the card is gone. We simulate this delay.
    setTimeout(function () {
      // Si la vanne est encore ouverte (service en cours), fermer et envoyer pour_end
      // / If valve still open (serving), close and send pour_end
      if (vanne_ouverte) {
        vanne_ouverte = false;
        maj_affichage_vanne();

        if (timer_boucle) {
          clearInterval(timer_boucle);
          timer_boucle = null;
        }

        // Envoyer pour_end, puis card_removed apres
        // / Send pour_end, then card_removed after
        envoyer_event("pour_end", volume_cumule_ml)
          .catch(function (err) {
            console.warn("pour_end \u00e9chou\u00e9:", err.message);
          })
          .finally(function () {
            // Envoyer card_removed (declenche le popup kiosk)
            // / Send card_removed (triggers kiosk popup)
            envoyer_event("card_removed", 0)
              .then(function () {
                afficher_message(
                  "Carte retir\u00e9e \u2014 " +
                    Math.round(volume_cumule_ml) +
                    " ml servis",
                  false
                );
              })
              .catch(function (err) {
                afficher_message("card_removed: " + err.message, true);
              })
              .finally(function () {
                reinitialiser();
              });
          });
      } else {
        // Vanne deja fermee (volume max atteint, ou carte refusee)
        // Envoyer seulement card_removed
        // / Valve already closed (max volume reached, or card denied)
        // Send only card_removed
        envoyer_event("card_removed", 0)
          .then(function () {
            afficher_message("Carte retir\u00e9e", false);
          })
          .catch(function (err) {
            afficher_message("card_removed: " + err.message, true);
          })
          .finally(function () {
            reinitialiser();
          });
      }
    }, CARD_GRACE_PERIOD_MS);
  }


  // ──────────────────────────────────────────────────────────────────
  // Branchement des evenements
  // / Event binding
  // ──────────────────────────────────────────────────────────────────

  // Boutons carte NFC : poser une carte / NFC card buttons: place a card
  boutons_carte.forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      poser_carte(bouton.dataset.tagId);
    });
  });

  // Bouton retirer carte / Remove card button
  bouton_retirer.addEventListener("click", retirer_carte);

  // Slider debit : met a jour le label en temps reel
  // Le slider simule le robinet mecanique, pas la vanne.
  // Il ne declenche ni pour_start ni pour_end — seule la carte controle le service.
  // / Flow slider: updates label in real time
  // The slider simulates the mechanical tap, not the valve.
  // It triggers neither pour_start nor pour_end — only the card controls the service.
  slider_debit.addEventListener("input", function () {
    var valeur = parseInt(slider_debit.value, 10);
    var debit_ml_s = (valeur / 100) * MAX_FLOW_ML_S;
    label_debit.textContent = Math.round(debit_ml_s) + " ml/s";
  });


  // --- Init ---
  console.log("Simulateur Pi charg\u00e9 pour tireuse", tireuse_uuid);

})();
