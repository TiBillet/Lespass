/**
 * Vider Carte — flow POS Phase 3
 * / Empty Card — POS Phase 3 flow
 *
 * LOCALISATION : laboutik/static/js/vider_carte.js
 *
 * Déclenche un flow dédié quand une tile methode_caisse=VC est cliquée.
 * Court-circuite le panier : scan NFC -> overlay confirm -> POST backend -> success.
 * / Triggers a dedicated flow when a methode_caisse=VC tile is clicked.
 * Bypasses the cart: NFC scan -> confirm overlay -> backend POST -> success.
 *
 * COMMUNICATION :
 *   Ecoute : clic sur [data-methode-caisse="VC"]
 *   Emet : fetch /laboutik/paiement/vider_carte/overlay/
 *   Laisse <c-read-nfc> gerer le reste via event-manage-form="viderCarteManageForm"
 */

(function() {
    /**
     * Intercepte les clics sur les tiles VC avant que addArticle soit appele.
     * / Intercepts clicks on VC tiles before addArticle is called.
     */
    document.addEventListener("click", function(event) {
        const tile = event.target.closest('[data-methode-caisse="VC"]');
        if (!tile) return;

        // Empeche addArticle / handlers du routeur d'articles.
        // / Prevents addArticle / article router handlers.
        event.preventDefault();
        event.stopImmediatePropagation();

        injecterOverlayViderCarte();
    }, true);  // capture phase : on intercepte avant les autres listeners

    /**
     * Injecte l'overlay vider-carte en fetching le HTML depuis le backend.
     * Passe uuid_pv et tag_id_cm en query params (depuis #addition-form).
     * / Injects the vider-carte overlay by fetching HTML from the backend.
     * Passes uuid_pv and tag_id_cm as query params (from #addition-form).
     */
    function injecterOverlayViderCarte() {
        const ancien = document.getElementById("vider-carte-overlay");
        if (ancien) ancien.remove();

        // Recupere uuid_pv et tag_id_cm depuis #addition-form.
        // / Retrieves uuid_pv and tag_id_cm from #addition-form.
        const form = document.getElementById("addition-form");
        const uuidPv = form ? (form.querySelector('[name="uuid_pv"]')?.value || "") : "";
        const tagIdCm = form ? (form.querySelector('[name="tag_id_cm"]')?.value || "") : "";

        const params = new URLSearchParams({uuid_pv: uuidPv, tag_id_cm: tagIdCm});
        fetch("/laboutik/paiement/vider_carte/overlay/?" + params.toString(), {
            method: "GET",
            credentials: "same-origin",
        })
            .then(response => response.text())
            .then(html => {
                const messages = document.getElementById("messages");
                if (messages) {
                    messages.innerHTML = html;
                    // Evalue les scripts injectes (initNfc du component c-read-nfc).
                    // / Evaluate injected scripts (initNfc of c-read-nfc component).
                    messages.querySelectorAll("script").forEach(oldScript => {
                        const newScript = document.createElement("script");
                        newScript.text = oldScript.textContent;
                        oldScript.parentNode.replaceChild(newScript, oldScript);
                    });
                }
            })
            .catch(error => {
                console.error("Erreur chargement overlay vider carte:", error);
            });
    }
})();
