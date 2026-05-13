/**
 * Champs conditionnels generiques pour les inlines Django admin
 * / Generic conditional fields for Django admin inlines
 *
 * LOCALISATION : Administration/static/admin/js/inline_conditional_fields.js
 *
 * Lit les regles depuis un <script id="inline-conditional-rules" type="application/json">
 * injecte par le template inline_conditional_fields.html.
 *
 * Format du JSON :
 * {
 *   "prices": {                                    // prefixe du formset
 *     "iteration": "recurring_payment == true",    // champ_cible: expression
 *     "commitment": "iteration > 0"
 *   }
 * }
 *
 * Expressions supportees (meme syntaxe que Unfold conditional_fields) :
 *   - "champ == true"   : visible si la checkbox est cochee
 *   - "champ > 0"       : visible si la valeur numerique est > 0
 *
 * CASCADE : si le champ source est lui-meme cache par une autre regle,
 * la condition est automatiquement fausse. Exemple :
 *   recurring_payment decoche → iteration cache → commitment cache aussi.
 *
 * STYLE VISUEL : la rangee parente (.form-row.field-row) recoit un fond
 * colore subtil + bordure gauche pour lier visuellement les champs
 * conditionnels a leur source. La rangee entiere se cache/montre avec
 * une animation douce quand tous ses champs conditionnels sont caches.
 *
 * COMMUNICATION :
 * Lit : <script id="inline-conditional-rules"> (injecte par le serveur)
 * Ecoute : change/input sur les champs source de chaque regle
 * Observe : MutationObserver sur les conteneurs inline (nouvelles lignes)
 */
(function () {
    "use strict";

    // Duree de l'animation en millisecondes / Animation duration in ms
    var DUREE_ANIMATION_MS = 200;

    // --- Chargement des regles ---

    function charger_regles() {
        var element_json = document.getElementById("inline-conditional-rules");
        if (!element_json) {
            return null;
        }
        try {
            return JSON.parse(element_json.textContent);
        } catch (erreur) {
            console.warn("inline_conditional_fields: JSON invalide", erreur);
            return null;
        }
    }

    // --- Parsing des expressions ---

    function parser_expression(expression) {
        // "champ == true" → visible si checkbox cochee / visible if checkbox checked
        var match_boolean = expression.match(/^(\w+)\s*==\s*true$/);
        if (match_boolean) {
            return {
                champ_source: match_boolean[1],
                evaluer: function (element_source) {
                    return element_source.checked;
                },
            };
        }

        // "champ == false" → visible si checkbox DECOCHEE / visible if checkbox unchecked
        var match_boolean_false = expression.match(/^(\w+)\s*==\s*false$/);
        if (match_boolean_false) {
            return {
                champ_source: match_boolean_false[1],
                evaluer: function (element_source) {
                    return !element_source.checked;
                },
            };
        }

        // "champ > 0" → valeur numerique superieure au seuil / numeric value above threshold
        var match_numerique = expression.match(/^(\w+)\s*>\s*(\d+)$/);
        if (match_numerique) {
            var seuil = parseInt(match_numerique[2], 10);
            return {
                champ_source: match_numerique[1],
                evaluer: function (element_source) {
                    var valeur = parseInt(element_source.value, 10) || 0;
                    return valeur > seuil;
                },
            };
        }

        console.warn("inline_conditional_fields: expression non reconnue:", expression);
        return null;
    }

    // --- Utilitaires DOM ---

    /**
     * Verifie si un element est visible (pas cache par display:none sur lui ou un parent).
     * / Checks if an element is visible (not hidden by display:none on itself or a parent).
     */
    function est_visible(element) {
        if (!element) {
            return false;
        }
        return element.offsetParent !== null;
    }

    // --- Animations ---

    function animer_apparition(conteneur) {
        conteneur.style.transition = "none";
        conteneur.style.display = "";
        conteneur.style.overflow = "hidden";
        conteneur.style.opacity = "0";
        conteneur.style.height = "auto";

        var hauteur_cible = conteneur.scrollHeight;
        conteneur.style.height = "0px";

        // Forcer le reflow / Force reflow
        conteneur.offsetHeight;

        conteneur.style.transition =
            "height " + DUREE_ANIMATION_MS + "ms ease-out, " +
            "opacity " + DUREE_ANIMATION_MS + "ms ease-out";
        conteneur.style.height = hauteur_cible + "px";
        conteneur.style.opacity = "1";

        setTimeout(function () {
            conteneur.style.height = "";
            conteneur.style.overflow = "";
            conteneur.style.transition = "";
        }, DUREE_ANIMATION_MS + 20);
    }

    function animer_disparition(conteneur) {
        conteneur.style.height = conteneur.scrollHeight + "px";
        conteneur.style.overflow = "hidden";

        // Forcer le reflow / Force reflow
        conteneur.offsetHeight;

        conteneur.style.transition =
            "height " + DUREE_ANIMATION_MS + "ms ease-in, " +
            "opacity " + DUREE_ANIMATION_MS + "ms ease-in";
        conteneur.style.height = "0px";
        conteneur.style.opacity = "0";

        setTimeout(function () {
            conteneur.style.display = "none";
            conteneur.style.height = "";
            conteneur.style.overflow = "";
            conteneur.style.opacity = "";
            conteneur.style.transition = "";
        }, DUREE_ANIMATION_MS + 20);
    }

    // --- Style visuel ---

    /**
     * Applique le style "champ conditionnel" sur la rangee parente (.form-row.field-row).
     * Fond colore subtil + bordure gauche pour lier visuellement au champ source.
     * / Applies "conditional field" style on the parent row (.form-row.field-row).
     * Subtle background + left border to visually link to source field.
     */
    function appliquer_style_rangee(rangee) {
        if (!rangee || rangee.dataset.conditionalStyled) {
            return;
        }
        rangee.style.borderLeft = "3px solid var(--color-primary-600, #6366f1)";
        rangee.style.paddingLeft = "8px";
        rangee.style.marginLeft = "4px";
        rangee.style.borderRadius = "0 6px 6px 0";
        rangee.style.backgroundColor = "rgba(99, 102, 241, 0.04)";
        rangee.dataset.conditionalStyled = "true";
    }

    // --- Logique principale ---

    /**
     * Configure les regles conditionnelles pour une ligne inline.
     *
     * Pattern "recalcul global" : quand N'IMPORTE QUEL champ source change,
     * TOUTES les regles de la ligne sont reevaluees. Cela garantit la cascade.
     *
     * Le style est applique sur la rangee parente (.form-row.field-row) qui
     * contient le(s) champ(s) conditionnel(s). La rangee entiere est animee
     * quand tous ses enfants conditionnels sont caches.
     *
     * / Sets up conditional rules for an inline row.
     * Uses "global recalc": when ANY source changes, ALL rules are re-evaluated.
     * Style is applied on the parent .form-row.field-row container.
     */
    function configurer_regles_pour_ligne(prefixe_formset, numero_ligne, regles) {
        var prefixe_id = "id_" + prefixe_formset + "-" + numero_ligne + "-";

        // Collecter les regles actives et les rangees parentes a styler
        // / Collect active rules and parent rows to style
        var regles_actives = [];
        var elements_source_uniques = {};
        var rangees_conditionnelles = new Set();

        for (var champ_cible in regles) {
            if (!regles.hasOwnProperty(champ_cible)) {
                continue;
            }

            var regle_parsee = parser_expression(regles[champ_cible]);
            if (!regle_parsee) {
                continue;
            }

            var element_cible = document.getElementById(prefixe_id + champ_cible);
            var element_source = document.getElementById(
                prefixe_id + regle_parsee.champ_source
            );

            if (!element_cible || !element_source) {
                continue;
            }

            // Conteneur individuel du champ (div.field-xxx)
            // / Individual field container (div.field-xxx)
            var conteneur_champ = element_cible.closest("[class*='field-']");

            // Rangee parente qui contient le(s) champ(s) du meme tuple
            // Ex: div.form-row.field-row contient iteration + commitment
            // / Parent row containing field(s) from the same tuple
            var rangee_parente = conteneur_champ
                ? conteneur_champ.closest(".form-row.field-row")
                : null;

            if (!conteneur_champ) {
                continue;
            }

            // Styler la rangee parente (ou le champ si pas de rangee)
            // / Style the parent row (or the field if no row)
            var cible_style = rangee_parente || conteneur_champ;
            appliquer_style_rangee(cible_style);

            if (rangee_parente) {
                rangees_conditionnelles.add(rangee_parente);
            }

            regles_actives.push({
                element_source: element_source,
                conteneur_champ: conteneur_champ,
                rangee_parente: rangee_parente,
                evaluer: regle_parsee.evaluer,
            });

            elements_source_uniques[regle_parsee.champ_source] = element_source;
        }

        if (regles_actives.length === 0) {
            return;
        }

        var premiere_evaluation = true;

        /**
         * Reevalue TOUTES les regles de la ligne.
         * CASCADE : si le conteneur du champ source est cache, condition = false.
         * Puis met a jour la visibilite des rangees parentes.
         * / Re-evaluates ALL rules. CASCADE: hidden source = false condition.
         * Then updates parent row visibility.
         */
        function recalculer_toutes_les_regles() {
            // Etape 1 : evaluer chaque regle et cacher/montrer chaque champ
            // / Step 1: evaluate each rule and hide/show each field
            for (var i = 0; i < regles_actives.length; i++) {
                var regle = regles_actives[i];

                // Cascade : source cachee = condition fausse
                // / Cascade: hidden source = false condition
                var source_visible = est_visible(regle.element_source);
                var condition_remplie = source_visible && regle.evaluer(regle.element_source);

                var champ_actuellement_cache =
                    regle.conteneur_champ.style.display === "none";

                if (condition_remplie && champ_actuellement_cache) {
                    regle.conteneur_champ.style.display = "";
                } else if (!condition_remplie && !champ_actuellement_cache) {
                    regle.conteneur_champ.style.display = "none";
                }
            }

            // Etape 2 : pour chaque rangee parente, verifier si tous ses enfants
            // conditionnels sont caches. Si oui, cacher la rangee entiere avec animation.
            // / Step 2: for each parent row, check if all its conditional children
            // are hidden. If so, hide the entire row with animation.
            rangees_conditionnelles.forEach(function (rangee) {
                // Compter les champs conditionnels visibles dans cette rangee
                // / Count visible conditional fields in this row
                var au_moins_un_visible = false;
                for (var j = 0; j < regles_actives.length; j++) {
                    if (regles_actives[j].rangee_parente === rangee) {
                        if (regles_actives[j].conteneur_champ.style.display !== "none") {
                            au_moins_un_visible = true;
                            break;
                        }
                    }
                }

                var rangee_actuellement_cachee =
                    rangee.style.display === "none";

                if (au_moins_un_visible && rangee_actuellement_cachee) {
                    if (premiere_evaluation) {
                        rangee.style.display = "";
                    } else {
                        animer_apparition(rangee);
                    }
                } else if (!au_moins_un_visible && !rangee_actuellement_cachee) {
                    if (premiere_evaluation) {
                        rangee.style.display = "none";
                    } else {
                        animer_disparition(rangee);
                    }
                }
            });
        }

        // Brancher les listeners sur tous les champs source
        // / Attach listeners to all source fields
        for (var nom_source in elements_source_uniques) {
            if (!elements_source_uniques.hasOwnProperty(nom_source)) {
                continue;
            }
            var el = elements_source_uniques[nom_source];
            el.addEventListener("change", recalculer_toutes_les_regles);
            el.addEventListener("input", recalculer_toutes_les_regles);
        }

        // Etat initial (sans animation) / Initial state (no animation)
        recalculer_toutes_les_regles();
        premiere_evaluation = false;
    }

    // --- Initialisation ---

    function initialiser_formset(prefixe_formset, regles) {
        var champ_total = document.getElementById(
            "id_" + prefixe_formset + "-TOTAL_FORMS"
        );
        if (!champ_total) {
            return;
        }
        var nombre_total = parseInt(champ_total.value, 10) || 0;
        for (var i = 0; i < nombre_total; i++) {
            configurer_regles_pour_ligne(prefixe_formset, i, regles);
        }
    }

    function initialiser() {
        var toutes_les_regles = charger_regles();
        if (!toutes_les_regles) {
            return;
        }

        for (var prefixe_formset in toutes_les_regles) {
            if (!toutes_les_regles.hasOwnProperty(prefixe_formset)) {
                continue;
            }
            var regles = toutes_les_regles[prefixe_formset];
            initialiser_formset(prefixe_formset, regles);

            // Observer les nouvelles lignes ajoutees dynamiquement
            // / Observe dynamically added new rows
            (function (prefixe, regles_locales) {
                var conteneur = document.getElementById(prefixe + "-group");
                if (conteneur) {
                    var observateur = new MutationObserver(function () {
                        initialiser_formset(prefixe, regles_locales);
                    });
                    observateur.observe(conteneur, {
                        childList: true,
                        subtree: true,
                    });
                }
            })(prefixe_formset, regles);
        }
    }

    // Si le DOM est deja charge (script injecte par Media dans le body),
    // lancer immediatement. Sinon, attendre DOMContentLoaded.
    // / If DOM is already loaded (script injected by Media in body),
    // run immediately. Otherwise, wait for DOMContentLoaded.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiser);
    } else {
        initialiser();
    }
})();
