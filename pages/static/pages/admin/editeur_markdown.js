/*
 * Éditeur Markdown (EasyMDE, vendorisé) pour le champ texte_markdown du
 * formulaire Bloc (admin Unfold).
 * / Markdown editor (vendored EasyMDE) for the Bloc form's texte_markdown
 * field (Unfold admin).
 *
 * LOCALISATION : pages/static/pages/admin/editeur_markdown.js
 *
 * PIÈGE : le champ est dans un conteneur caché par Alpine (conditional_fields)
 * tant que le type MARKDOWN n'est pas sélectionné. CodeMirror mesuré dans un
 * conteneur caché se dessine à 0px : on rafraîchit l'éditeur quand le type
 * change et une fois après le chargement.
 * / GOTCHA: the field lives in a container hidden by Alpine (conditional_fields)
 * until the MARKDOWN type is selected. CodeMirror measured inside a hidden
 * container renders at 0px: refresh the editor on type change and once after load.
 */
document.addEventListener("DOMContentLoaded", function () {
    var zone_texte = document.querySelector("textarea.editeur-markdown");
    if (!zone_texte || typeof EasyMDE === "undefined") {
        return;
    }

    // Table position -> URL des images de l'inline (posée par le formulaire).
    // / position -> URL table of the inline images (set by the form).
    var urls_galerie = {};
    try {
        urls_galerie = JSON.parse(zone_texte.dataset.galerie || "{}");
    } catch (erreur) {
        urls_galerie = {};
    }

    var editeur = new EasyMDE({
        element: zone_texte,
        // L'aperçu résout ![légende](galerie:N) vers les vraies URLs —
        // même règle que le rendu serveur (rendre_bloc_markdown).
        // / The preview resolves ![caption](galerie:N) to the real URLs —
        // same rule as the server rendering (rendre_bloc_markdown).
        previewRender: function (texte_brut, apercu) {
            var texte_resolu = texte_brut.replace(
                /!\[([^\]]*)\]\(galerie:(\d+)\)/g,
                function (tout, alt, position) {
                    var url = urls_galerie[position];
                    return url ? "![" + alt + "](" + url + ")" : tout;
                }
            );
            return this.parent.markdown(texte_resolu);
        },
        // forceSync : recopie chaque frappe dans le <textarea> (le POST du
        // formulaire lit le textarea). / copy every keystroke back into the
        // <textarea> (the form POST reads the textarea).
        forceSync: true,
        spellChecker: false, // correcteur anglais uniquement / English-only checker
        nativeSpellcheck: true,
        status: false,
        minHeight: "280px",
        // Barre d'outils : l'essentiel, sans upload d'image (les images
        // passent par l'encart « Images » + ![légende](galerie:N)).
        // / Toolbar: the essentials, no image upload (images go through the
        // "Images" inline + the galerie:N reference).
        toolbar: [
            "heading", "bold", "italic", "|",
            "unordered-list", "ordered-list", "quote", "|",
            "link", "code", "|",
            "preview", "side-by-side", "fullscreen", "|",
            "guide",
        ],
    });

    // Rafraîchit CodeMirror quand le conteneur devient visible (choix du type
    // MARKDOWN) — et une fois après le chargement (fiche déjà en MARKDOWN).
    // / Refresh CodeMirror when the container becomes visible (MARKDOWN type
    // picked) — and once after load (form already on MARKDOWN).
    function rafraichir() {
        window.setTimeout(function () {
            editeur.codemirror.refresh();
        }, 100);
    }
    var select_type = document.getElementById("id_type_bloc");
    if (select_type) {
        select_type.addEventListener("change", rafraichir);
    }
    rafraichir();
});
