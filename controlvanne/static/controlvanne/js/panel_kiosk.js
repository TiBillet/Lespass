/**
 * panel_kiosk.js — Logique JS du panneau kiosque controlvanne.
 * Kiosk JS logic for the controlvanne panel.
 *
 * Gere : jauges SVG, grille de prix, WebSocket, popup fin de service.
 * Handles: SVG gauges, price grid, WebSocket, end-of-service popup.
 */
(function(){
  const cards = {};
  const CX = 50, CY = 54, R_ARC = 44, R_NEEDLE = 38;

  // Met a jour la jauge SVG pour un niveau donne (0..1)
  // Updates the SVG gauge for a given level (0..1)
  function updateGauge(c, reservoirMl, maxMl) {
    const pct = maxMl > 0 ? Math.min(Math.max(reservoirMl / maxMl, 0), 1) : 0;
    const theta = (1 - pct) * Math.PI; // pi=gauche(0%) -> 0=droite(100%)

    // Arc de remplissage / Fill arc
    const fill = c.gaugeFill;
    if (fill) {
      if (pct < 0.002) {
        fill.setAttribute('d', '');
      } else if (pct > 0.998) {
        fill.setAttribute('d', `M 6,${CY} A ${R_ARC},${R_ARC} 0 0,1 94,${CY}`);
      } else {
        const ex = (CX + R_ARC * Math.cos(theta)).toFixed(2);
        const ey = (CY - R_ARC * Math.sin(theta)).toFixed(2);
        fill.setAttribute('d', `M 6,${CY} A ${R_ARC},${R_ARC} 0 0,1 ${ex},${ey}`);
      }
      const color = pct > 0.5 ? '#27ae60' : (pct > 0.25 ? '#f39c12' : '#e74c3c');
      fill.setAttribute('stroke', color);
    }

    // Aiguille / Needle
    const needle = c.gaugeNeedle;
    if (needle) {
      const nx = (CX + R_NEEDLE * Math.cos(theta)).toFixed(2);
      const ny = (CY - R_NEEDLE * Math.sin(theta)).toFixed(2);
      needle.setAttribute('x2', nx);
      needle.setAttribute('y2', ny);
    }
  }

  // Calcule et affiche les prix / Compute and display prices
  function updatePrix(c, prixLitre) {
    const pL = parseFloat(prixLitre) || 0;
    c.prixL.textContent = pL.toFixed(2);
    c.p25.textContent = (pL * 0.25).toFixed(2) + ' \u20ac';
    c.p33.textContent = (pL * 0.33).toFixed(2) + ' \u20ac';
    c.p50.textContent = (pL * 0.50).toFixed(2) + ' \u20ac';
  }

  // Initialisation des elements HTML par carte / Init HTML elements per card
  document.querySelectorAll('.card[data-uuid]').forEach(card => {
    const uuid = card.dataset.uuid;
    const maxMl = parseFloat(card.dataset.maxreservoir) || 1;
    const prixBlock = document.getElementById('prix-block-' + uuid);
    cards[uuid] = {
      uuid, maxMl,
      uid:         document.getElementById('uid-'    + uuid),
      auth:        document.getElementById('auth-'   + uuid),
      state:       document.getElementById('state-'  + uuid),
      vol:         document.getElementById('vol-'    + uuid),
      msg:         document.getElementById('msg-'    + uuid),
      nomTireuse:  document.getElementById('nom-tireuse-' + uuid),
      liquid:      document.getElementById('liquid-' + uuid),
      balance:     document.getElementById('balance-'+ uuid),
      gaugeFill:   document.getElementById('gauge-fill-'  + uuid),
      gaugeNeedle: document.getElementById('gauge-needle-'+ uuid),
      prixL:       document.getElementById('prixL-'  + uuid),
      p25:         document.getElementById('p25-'    + uuid),
      p33:         document.getElementById('p33-'    + uuid),
      p50:         document.getElementById('p50-'    + uuid),
      lastBalance: null,
      wasPresent: false,
      isMaintenance: false,
      resetTimer: null,
    };
    // Init prix depuis template / Init prices from template
    if (prixBlock) {
      updatePrix(cards[uuid], prixBlock.dataset.prixlitre);
    }
    // Init jauge avec reservoir_ml courant (template ne donne pas le % directement)
    // Gauge starts at 0% until first WS message
  });

  // Popup fin de service / End-of-service popup
  let popup = document.getElementById('global-popup');
  if (!popup) {
    popup = document.createElement('div');
    popup.id = 'global-popup';
    popup.style.cssText = 'display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#2c3e50;color:white;padding:30px;border-radius:15px;text-align:center;z-index:9999;box-shadow:0 10px 40px rgba(0,0,0,0.3)';
    popup.innerHTML = `
      <div style="font-size:48px;margin-bottom:10px">\uD83C\uDF7A</div>
      <div style="font-size:20px;margin-bottom:10px">Bonne d\u00e9gustation !</div>
      <div style="font-size:16px">Il vous reste <b id="popup-balance">\u2014</b> \u20ac sur votre carte</div>
    `;
    document.body.appendChild(popup);
  }
  let popupTimeout = null;
  function showPopup(balance) {
    const el = document.getElementById('popup-balance');
    if (el) el.textContent = balance;
    popup.style.display = 'block';
    if (popupTimeout) clearTimeout(popupTimeout);
    popupTimeout = setTimeout(() => { popup.style.display = 'none'; }, 5000);
  }

  // Remise a zero de la carte (mode attente ou maintenance selon etat)
  // Reset card UI (waiting mode or maintenance depending on state)
  function resetCardUI(c) {
    if (!c) return;
    c.uid.innerHTML = '&mdash;';
    c.vol.textContent = '0 cl';
    c.balance.textContent = '\u2014';
    if (c.isMaintenance) {
      c.auth.className = 'badge bg-warning text-dark';
      c.auth.textContent = 'Hors service';
      c.state.className = 'badge bg-warning text-dark';
      c.state.textContent = 'Maintenance';
      c.msg.textContent = 'En Maintenance';
    } else {
      c.auth.className = 'badge bg-secondary';
      c.auth.textContent = 'En attente';
      c.state.className = 'badge bg-danger';
      c.state.textContent = 'Ferm\u00e9e';
      c.msg.textContent = 'Posez votre badge...';
    }
  }

  function setBadge(el, ok) {
    el.className = 'badge ' + (ok ? 'bg-success' : 'bg-danger');
    el.textContent = ok ? 'Autoris\u00e9' : 'Refus\u00e9';
  }

  // WebSocket — slug_focus lu depuis l'attribut data du conteneur
  // WebSocket — slug_focus read from the container's data attribute
  const slugFocus = document.getElementById('cards-grid').dataset.slugFocus || "all";
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const wsPath = (!slugFocus || slugFocus === 'all') ? '/ws/rfid/all/' : `/ws/rfid/${slugFocus}/`;
  const ws = new WebSocket(`${proto}://${location.host}${wsPath}`);

  ws.onopen = () => console.log("WS Connect\u00e9 sur", wsPath);

  ws.onmessage = ev => {
    try {
      const data = JSON.parse(ev.data);
      const payload = data.payload || data;

      if (payload.kiosk_url)    { window.location.href = payload.kiosk_url; return; }
      if (payload.kiosk_reload) { window.location.reload(); return; }

      // Maintenance
      if (payload.maintenance) {
        const uuid = payload.tireuse_bec_uuid || '';
        const c = cards[uuid] || Object.values(cards)[0];
        if (!c) return;
        c.isMaintenance = true;
        c.state.className = 'badge bg-warning text-dark';
        c.state.textContent = 'Maintenance';
        c.uid.textContent = payload.uid || '\u2014';

        if (payload.present && payload.authorized) {
          // Session maintenance active (carte rincage autorisee, liquide en cours)
          c.auth.className = 'badge bg-warning text-dark';
          c.auth.textContent = 'Rin\u00e7age';
          c.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + ' cl';
          c.balance.textContent = '\u2014';
          if (payload.message) c.msg.textContent = payload.message;
        } else if (payload.session_done) {
          // Fin de session maintenance / End of maintenance session
          c.auth.className = 'badge bg-info text-dark';
          c.auth.textContent = 'Fin rin\u00e7age';
          c.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + ' cl';
          if (payload.message) c.msg.textContent = payload.message;
          setTimeout(() => resetCardUI(c), 5000);
        } else {
          // Tireuse en maintenance — carte normale refusee ou etat repos
          c.auth.className = 'badge bg-warning text-dark';
          c.auth.textContent = 'Hors service';
          c.vol.textContent = '0 cl';
          const bal = payload.balance;
          c.balance.textContent = (bal !== undefined && bal !== null && bal !== '\u2014' && parseFloat(bal) > 0) ? bal : '\u2014';
          c.msg.textContent = payload.message || 'En Maintenance';
        }
        return;
      }

      const targetUuid = payload.tireuse_bec_uuid || payload.tireuse_bec || '';
      let targets = [];
      if (targetUuid === 'all') {
        targets = Object.values(cards);
      } else if (cards[targetUuid]) {
        targets = [cards[targetUuid]];
      } else if (slugFocus === 'all') {
        console.warn("Re\u00e7u event pour", targetUuid, "mais pas de carte trouv\u00e9e.");
        return;
      }

      targets.forEach(c => {
        // Le serveur envoie un payload normal (pas maintenance) -> la tireuse est en service
        c.isMaintenance = false;

        // Mise a jour jauge (tous les messages) / Update gauge (all messages)
        if (payload.reservoir_ml !== undefined) {
          const maxMl = payload.reservoir_max_ml || c.maxMl;
          c.maxMl = maxMl;
          updateGauge(c, payload.reservoir_ml, maxMl);
        }

        // Mise a jour nom tireuse et nom boisson / Update tap name and drink name
        if (payload.tireuse_bec !== undefined) c.nomTireuse.textContent = payload.tireuse_bec;
        if (payload.liquid_label !== undefined) c.liquid.textContent = payload.liquid_label;

        // Mise a jour prix si envoyes / Update prices if sent
        if (payload.prix_litre !== undefined) {
          updatePrix(c, payload.prix_litre);
        }

        // CAS 1 : Carte presente / CASE 1: Card present
        if (payload.present) {
          c.wasPresent = true;
          // Annuler tout timer de reset en cours (nouvelle carte arrivee avant la fin du delai)
          if (c.resetTimer) { clearTimeout(c.resetTimer); c.resetTimer = null; }
          c.uid.textContent = payload.uid || 'Lu...';
          if (typeof payload.authorized !== 'undefined') setBadge(c.auth, payload.authorized);
          c.state.className = payload.vanne_ouverte ? 'badge bg-success' : 'badge bg-danger';
          c.state.textContent = payload.vanne_ouverte ? 'Ouverte' : 'Ferm\u00e9e';
          c.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + ' cl';
          if (payload.balance) { c.balance.textContent = payload.balance; c.lastBalance = payload.balance; }
          if (payload.message) c.msg.textContent = payload.message;
          return;
        }

        // Pour les messages sans carte presente, capturer wasPresent AVANT de le reinitialiser.
        const wasCurrentlyPresent = c.wasPresent;
        c.wasPresent = false;

        // CAS 2 : Fin de session / CASE 2: End of session
        if (payload.session_done) {
          // Session_done tardif : une nouvelle carte est deja active -> ignorer
          if (wasCurrentlyPresent) return;
          c.auth.className = 'badge bg-info text-dark';
          c.auth.textContent = 'Termin\u00e9';
          c.state.className = 'badge bg-danger';
          c.state.textContent = 'Ferm\u00e9e';
          c.vol.textContent = Math.round((payload.volume_ml || 0) / 10) + ' cl';
          if (payload.balance) { c.balance.textContent = payload.balance; c.lastBalance = payload.balance; }
          if (payload.message) c.msg.textContent = payload.message;
          if (c.lastBalance && parseFloat(payload.volume_ml || 0) > 0) showPopup(c.lastBalance);
          c.resetTimer = setTimeout(() => { c.resetTimer = null; resetCardUI(c); }, 5000);
          return;
        }

        // CAS 3 : Retrait / refus / CASE 3: Removal / refusal
        resetCardUI(c);
        c.auth.className = 'badge bg-secondary';
        c.msg.textContent = 'En attente...';
        c.balance.textContent = '\u2014';
      });

    } catch(e) { console.error("Erreur WS JS:", e); }
  };

  // Init jauges depuis les valeurs du template (rendu serveur)
  // Init gauges from template values (server-rendered)
  document.querySelectorAll('.card[data-uuid]').forEach(card => {
    const uuid = card.dataset.uuid;
    const c = cards[uuid];
    if (!c) return;
    const initReservoir = parseFloat(card.dataset.reservoir) || 0;
    updateGauge(c, initReservoir, c.maxMl);
  });

})();
