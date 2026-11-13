/**
 * OBSERVATOIRE DES INSTANCES — classement des lieux et graphiques
 * / INSTANCE OBSERVATORY — venue classification and charts
 *
 * LOCALISATION : seo/static/seo/observatoire.js
 * CHARGE PAR : seo/templates/seo/observatoire.html (script defer)
 *
 * CE QUE FAIT CE FICHIER
 * Il lit les chiffres calcules la nuit par le serveur, classe chaque lieu
 * (activite : tres actif, actif, peu utilise, sommeil ; usages : agenda,
 * billetterie, caisse... ; rythme : saisonnier, regulier...), puis dessine la
 * synthese, la matrice taille x rythme, l'explorateur, la liste et l'onglet
 * « Sur mesure ».
 * Le classement est fait ICI, dans le navigateur, et pas sur le serveur : le
 * superadmin regle les seuils dans la page et voit le resultat tout de suite.
 * Ce fichier ne lance JAMAIS de calcul sur le serveur : il ne fait aucune requete.
 * / Reads the nightly figures, classifies each venue, draws the page. The
 *   classification runs here so thresholds can be tuned live. No request is made.
 *
 * FLUX :
 * 1. demarrer() lit la balise <script id="observatoire-donnees"> (json_script),
 *    ecrite par seo/views_observatoire.py.
 * 2. charger_les_donnees() range chaque lieu dans liste_des_instances.
 * 3. tout_recalculer() : classer_une_instance() pour chaque lieu, puis rendre_*().
 * 4. Chaque reglage (seuil, filtre, onglet) relance tout_recalculer() ou un rendre_*().
 *
 * COMMUNICATION :
 * Recoit : #observatoire-donnees = { calcul: {cles, mois, inst...}, textes,
 *          indicateurs, libelles } (seo/views_observatoire.py).
 * Depend : window.Chart, charge par Unfold sur toutes les pages de l'admin.
 *
 * TEXTES : aucun texte affiche n'est ecrit ici. Ils arrivent de Python, traduits
 * avec _() (le projet n'a pas de catalogue JavaScript). Les phrases a trous ont des
 * marqueurs {nom}, remplis par texte(cle, valeurs).
 * / No displayed text is written here: they come from Python, translated.
 *
 * SECURITE : un nom de lieu est saisi par un admin de lieu et lu par le
 * superadmin. Il passe TOUJOURS par echapper_html() ou textContent avant d'entrer
 * dans la page.
 * / A venue name always goes through echapper_html() or textContent.
 */
(function () {
    "use strict";

    // ============================================================
    // 0. Outils
    // / 0. Tools
    // ============================================================

    let DONNEES_DE_LA_PAGE = null;
    let TEXTES = {};
    let LIBELLES = {};
    let INDICATEURS = {};

    // La langue de la page, pour formater les nombres et les mois.
    // / The page language, to format numbers and months.
    const LANGUE_DE_LA_PAGE = document.documentElement.lang || "fr";

    function somme(valeurs) {
        let total = 0;
        for (const valeur of valeurs) {
            total += valeur;
        }
        return total;
    }

    // Echappe un texte avant de le mettre dans du HTML.
    // / Escapes a text before putting it into HTML.
    function echapper_html(texte_brut) {
        return String(texte_brut).replace(/[&<>"']/g, function (caractere) {
            return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[caractere];
        });
    }

    // Un texte traduit, avec ses marqueurs {nom} remplis. Les valeurs ne sont PAS
    // echappees ici : l'appelant echappe ce qui vient d'un lieu.
    // / A translated text with its {name} markers filled. Values are not escaped here.
    function texte(cle_du_texte, valeurs) {
        let modele = TEXTES[cle_du_texte];
        if (modele === undefined) {
            modele = cle_du_texte;
        }
        if (!valeurs) {
            return modele;
        }
        return modele.replace(/\{(\w+)\}/g, function (marqueur, nom) {
            return valeurs[nom] !== undefined ? String(valeurs[nom]) : marqueur;
        });
    }

    // Les couleurs sont lues sur le bloc .obs : les variables CSS y sont confinees.
    // / Colours are read on the .obs block, where the CSS variables live.
    function couleur_css(nom_de_variable) {
        const bloc = document.querySelector(".obs") || document.documentElement;
        return getComputedStyle(bloc).getPropertyValue(nom_de_variable).trim();
    }

    // Un nombre lisible : 12 k, 1,2 M, avec l'unite euro si besoin.
    // / A readable number: 12 k, 1.2 M, with the euro unit if needed.
    function formater_nombre(nombre, unite) {
        let texte_du_nombre;
        if (Math.abs(nombre) >= 1e6) {
            texte_du_nombre = (nombre / 1e6).toLocaleString(LANGUE_DE_LA_PAGE, {maximumFractionDigits: 1}) + " M";
        } else if (Math.abs(nombre) >= 1e4) {
            texte_du_nombre = Math.round(nombre / 1e3).toLocaleString(LANGUE_DE_LA_PAGE) + " k";
        } else {
            texte_du_nombre = Math.round(nombre).toLocaleString(LANGUE_DE_LA_PAGE);
        }
        if (unite === "€") {
            return texte_du_nombre + " €";
        }
        return texte_du_nombre;
    }

    function libelle_de(famille, cle) {
        const libelles_de_la_famille = LIBELLES[famille] || {};
        return libelles_de_la_famille[cle] !== undefined ? libelles_de_la_famille[cle] : cle;
    }

    // ============================================================
    // 1. Les donnees
    // / 1. The data
    // ============================================================

    let liste_des_mois = [];
    let libelles_des_mois = [];
    let liste_des_instances = [];
    let nombre_de_mois = 0;

    // Les compteurs d'argent arrivent en CENTIMES (ceux des clotures) : on les passe
    // en euros, l'unite des seuils de classement.
    // / Money counters arrive in cents (closure figures): converted to euros.
    const COMPTEURS_EN_CENTIMES = ["ca_total", "ca_billetterie", "ca_adhesions", "ca_caisse",
        "recharges_ligne", "recharges_place"];

    // Les seuils FIXES (decision du mainteneur : pas dans le panneau des seuils).
    // Un mois est un « mois d'usage » si UNE de ces valeurs est atteinte.
    // / FIXED thresholds. A month is a "month of use" if ONE of these is reached.
    const SEUILS_DU_MOIS_D_USAGE = {
        evenements: 1, billets: 10, chiffre_affaires: 200, adhesions: 5, recharges: 200,
        transactions_cashless: 20, locations: 1,
    };
    // Un lieu a un usage si son total des 12 derniers mois atteint ce seuil.
    // / A venue has a use when its 12-month total reaches this threshold.
    const SEUILS_DES_USAGES = {
        agenda: 3, billetterie_gratuite: 10, billetterie_payante: 10, adhesions: 5,
        caisse_transactions: 20, caisse_chiffre_affaires: 200, location: 1,
    };

    function preparer_une_instance(instance) {
        const compteurs = instance.compteurs_par_mois;
        for (const cle_du_compteur of COMPTEURS_EN_CENTIMES) {
            compteurs[cle_du_compteur] = compteurs[cle_du_compteur].map(function (centimes) {
                return centimes / 100;
            });
        }
        // ca_total est lu tel quel dans la cloture, jamais reconstruit par addition :
        // une adhesion vendue en caisse compte a la fois en « adhesions » et en « caisse ».
        // / ca_total is read as is from the closure, never rebuilt by addition.
        compteurs.recharges = compteurs.recharges_ligne.map(function (valeur, index) {
            return valeur + compteurs.recharges_place[index];
        });
        compteurs.billets = compteurs.billets_gratuits.map(function (valeur, index) {
            return valeur + compteurs.billets_payants[index];
        });
        // Le volume d'activite du mois : les actes des gens (billets, adhesions,
        // paiements cashless), pas l'argent. Le rythme se lit dessus : un festival en
        // caisse V1 ou une fete gratuite a peu de CA dans Lespass, mais du volume.
        // / The month's activity volume: people's acts, not money. Rhythm reads it.
        compteurs.volume = compteurs.billets.map(function (valeur, index) {
            return valeur + compteurs.adhesions[index] + compteurs.transactions_cashless[index];
        });
        // Un « mois d'usage » : au moins un signe que le lieu se sert de TiBillet ce
        // mois-la. Un seul evenement publie suffit (un conseil d'administration, une
        // assemblee de benevoles : le lieu est vivant).
        // / A "month of use": at least one sign the venue uses TiBillet that month.
        compteurs.reel = compteurs.ca_total.map(function (chiffre_affaires, index) {
            const usage_du_mois = compteurs.evenements[index] >= SEUILS_DU_MOIS_D_USAGE.evenements
                || compteurs.billets[index] >= SEUILS_DU_MOIS_D_USAGE.billets
                || chiffre_affaires >= SEUILS_DU_MOIS_D_USAGE.chiffre_affaires
                || compteurs.adhesions[index] >= SEUILS_DU_MOIS_D_USAGE.adhesions
                || compteurs.recharges[index] >= SEUILS_DU_MOIS_D_USAGE.recharges
                || compteurs.transactions_cashless[index] >= SEUILS_DU_MOIS_D_USAGE.transactions_cashless
                || compteurs.locations[index] >= SEUILS_DU_MOIS_D_USAGE.locations;
            return usage_du_mois ? 1 : 0;
        });
        return instance;
    }

    function charger_les_donnees(calcul) {
        liste_des_mois = calcul.mois;
        const cles_des_compteurs = calcul.cles;
        liste_des_instances = calcul.inst.map(function (ligne) {
            // L'ordre des positions est ecrit par seo/observatoire.py
            // (calculer_observatoire_du_reseau, lignes_des_instances).
            // / Position order is written by seo/observatoire.py.
            const instance = {
                id: ligne[0], nom: ligne[1], cree: ligne[2],
                pdv: ligne[3], admins: ligne[4], federe: ligne[5],
                compteurs_par_mois: {},
            };
            cles_des_compteurs.forEach(function (cle_du_compteur, position) {
                instance.compteurs_par_mois[cle_du_compteur] = ligne[6][position];
            });
            return preparer_une_instance(instance);
        });
        nombre_de_mois = liste_des_mois.length;
        const format_du_mois = new Intl.DateTimeFormat(LANGUE_DE_LA_PAGE, {month: "short", year: "2-digit"});
        libelles_des_mois = liste_des_mois.map(function (mois) {
            return format_du_mois.format(new Date(+mois.slice(0, 4), +mois.slice(5, 7) - 1, 1));
        });
    }

    // ============================================================
    // 2. Le classement — NE PAS CHANGER LES REGLES sans le mainteneur
    // / 2. Classification — do not change the rules without the maintainer
    // ============================================================

    const seuils = {
        actifMois: 3, tresActifMois: 9,
        petitMax: 10000, moyenMax: 100000, festivalConcentration: 70, mixtePic: 4,
        abandonSilence: 6, abandonMoisMax: 3, abandonCAMax: 5000, baisse: 50,
    };
    // L'ordre d'affichage des seuils. Leurs libelles viennent de Python (textes « seuil_* »).
    // / Display order of the thresholds. Labels come from Python.
    const ORDRE_DES_SEUILS = ["actifMois", "tresActifMois", "petitMax", "moyenMax",
        "festivalConcentration", "mixtePic", "abandonSilence", "abandonMoisMax", "abandonCAMax",
        "baisse"];

    function classer_une_instance(instance) {
        const compteurs = instance.compteurs_par_mois;
        const N = nombre_de_mois;
        const chiffre_affaires = compteurs.ca_total;
        const mois_reels = compteurs.reel;
        const est_dans_les_12_derniers_mois = function (index) { return index >= N - 12; };
        const total_des_12_derniers_mois = function (cle_du_compteur) {
            return somme(compteurs[cle_du_compteur].slice(N - 12));
        };

        const ca_12_mois = somme(chiffre_affaires.filter(function (v, i) { return est_dans_les_12_derniers_mois(i); }));
        const ca_avant = somme(chiffre_affaires.filter(function (v, i) { return !est_dans_les_12_derniers_mois(i); }));
        const ca_toute_la_periode = ca_12_mois + ca_avant;
        const mois_reels_12_mois = somme(mois_reels.slice(N - 12));
        const mois_reels_avant = somme(mois_reels.slice(0, N - 12));
        const mois_reels_en_tout = somme(mois_reels);
        const dernier_mois_reel = mois_reels.lastIndexOf(1);
        const mois_de_silence = dernier_mois_reel < 0 ? N : N - 1 - dernier_mois_reel;

        // Recurrent : un mois d'usage revient a la meme saison (+/- 1 mois) un an plus tard.
        // / Recurring: a month of use comes back the same season (+/- 1 month) a year later.
        let recurrent = false;
        for (let i = 0; i < N - 11; i++) {
            if (mois_reels[i] && (mois_reels[i + 11] || mois_reels[i + 12] || (i + 13 < N && mois_reels[i + 13]))) {
                recurrent = true;
            }
        }
        const abandon = mois_reels_en_tout > 0 && mois_reels_en_tout <= seuils.abandonMoisMax
            && mois_de_silence >= seuils.abandonSilence && ca_toute_la_periode < seuils.abandonCAMax && !recurrent;

        // L'activite : la regularite, en mois d'usage sur les 12 derniers mois.
        // « Tres actif » demande aussi d'etre « actif » : un seuil tres actif regle plus
        // bas que le seuil actif ne fait pas passer un lieu peu utilise en tres actif.
        // / Activity: regularity, in months of use over the last 12 months.
        let activite;
        if (abandon || mois_reels_12_mois === 0) {
            activite = "sommeil";
        } else if (mois_reels_12_mois >= seuils.actifMois) {
            activite = mois_reels_12_mois >= seuils.tresActifMois ? "tres_actif" : "actif";
        } else {
            activite = "peu_utilise";
        }

        // Les usages : un lieu peut en avoir plusieurs. « reseau » est une valeur fixe
        // (lieu federe) : un lieu en sommeil peut l'avoir.
        // / Uses: a venue can have several. "reseau" is fixed (federated venue).
        const usages = [];
        if (total_des_12_derniers_mois("evenements") >= SEUILS_DES_USAGES.agenda) { usages.push("agenda"); }
        if (total_des_12_derniers_mois("billets_gratuits") >= SEUILS_DES_USAGES.billetterie_gratuite) { usages.push("billetterie_gratuite"); }
        if (total_des_12_derniers_mois("billets_payants") >= SEUILS_DES_USAGES.billetterie_payante) { usages.push("billetterie_payante"); }
        if (total_des_12_derniers_mois("adhesions") >= SEUILS_DES_USAGES.adhesions) { usages.push("adhesions"); }
        if (total_des_12_derniers_mois("transactions_cashless") >= SEUILS_DES_USAGES.caisse_transactions
            || total_des_12_derniers_mois("ca_caisse") >= SEUILS_DES_USAGES.caisse_chiffre_affaires) { usages.push("caisse"); }
        if (total_des_12_derniers_mois("locations") >= SEUILS_DES_USAGES.location) { usages.push("location"); }
        if (instance.federe) { usages.push("reseau"); }
        if (!usages.length) { usages.push("aucun"); }

        // Le rythme, lu sur le VOLUME d'activite (pas sur le CA). Concentration : la
        // part des 2 meilleurs mois consecutifs. Pic : le meilleur mois rapporte au
        // mois median des mois d'usage.
        // / Rhythm, read on activity VOLUME (not revenue).
        const volume_des_12_mois = compteurs.volume.slice(N - 12);
        const volume_total_des_12_mois = somme(volume_des_12_mois);
        let meilleurs_deux_mois = 0;
        for (let i = 0; i < 11; i++) {
            meilleurs_deux_mois = Math.max(meilleurs_deux_mois, volume_des_12_mois[i] + volume_des_12_mois[i + 1]);
        }
        const concentration = volume_total_des_12_mois ? meilleurs_deux_mois / volume_total_des_12_mois : 0;
        const volumes_des_mois_reels = volume_des_12_mois
            .filter(function (v, i) { return mois_reels[N - 12 + i]; })
            .sort(function (a, b) { return a - b; });
        const mois_median = volumes_des_mois_reels.length ? volumes_des_mois_reels[Math.floor(volumes_des_mois_reels.length / 2)] : 0;
        const pic = mois_median ? Math.max.apply(null, volume_des_12_mois) / mois_median : 0;
        const nouveau = mois_reels_avant === 0;

        let rythme = "indetermine";
        if (activite !== "sommeil" && volume_total_des_12_mois > 0) {
            if (concentration * 100 >= seuils.festivalConcentration && mois_reels_12_mois <= 5) {
                rythme = (recurrent || nouveau) ? "saisonnier" : "ponctuel";
            } else if (pic >= seuils.mixtePic) {
                rythme = "temps_forts";
            } else {
                rythme = "regulier";
            }
        }
        const taille = ca_12_mois < seuils.petitMax ? "petit" : ca_12_mois < seuils.moyenMax ? "moyen" : "gros";

        // La tendance : sur le CA si le lieu en avait avant les 12 derniers mois, sinon
        // sur les mois d'usage. Sur les mois d'usage seuls, un lieu deja regulier ne
        // pourrait jamais etre « en hausse ».
        // / Trend: on revenue when there was some before, else on months of use.
        let tendance = "";
        if (activite !== "sommeil") {
            let valeur_actuelle = ca_12_mois;
            let valeur_avant = ca_avant;
            if (ca_avant === 0) {
                valeur_actuelle = mois_reels_12_mois;
                valeur_avant = mois_reels_avant;
            }
            if (valeur_avant === 0) {
                tendance = "nouveau";
            } else if (valeur_actuelle < valeur_avant * seuils.baisse / 100) {
                tendance = "en_baisse";
            } else if (valeur_actuelle > valeur_avant * 1.5) {
                tendance = "en_hausse";
            } else {
                tendance = "stable";
            }
        }
        Object.assign(instance, {
            ca12: ca_12_mois, reels12: mois_reels_12_mois, silence: mois_de_silence, recurrent: recurrent,
            abandon: abandon, activite: activite, usages: usages, rythme: rythme, taille: taille, tendance: tendance,
        });
    }

    // ============================================================
    // 3. Les indicateurs, les rythmes, les usages, les activites
    // / 3. Indicators, rhythms, uses, activity levels
    // ============================================================

    // Comment chaque indicateur se resume sur 12 mois : somme, meilleur mois, ou
    // valeur actuelle (statique). Leurs libelles viennent de Python (INDICATEURS).
    // / How each indicator sums up over 12 months. Labels come from Python.
    const AGREGATION_DES_INDICATEURS = {
        ca_total: "somme", ca_billetterie: "somme", ca_adhesions: "somme", ca_caisse: "somme",
        recharges: "somme", recharges_ligne: "somme", recharges_place: "somme",
        transactions_cashless: "somme", portemonnaies_actifs: "max", evenements: "somme",
        billets: "somme", billets_gratuits: "somme", billets_payants: "somme", billets_scannes: "somme",
        adhesions: "somme", locations: "somme", volume: "somme",
        usagers: "max", reel: "somme", pdv: "statique", admins: "statique",
    };
    const ORDRE_DES_INDICATEURS = Object.keys(AGREGATION_DES_INDICATEURS);

    function indicateur(cle) {
        const definition = INDICATEURS[cle] || {libelle: cle, unite: "", definition: "", source: ""};
        return {
            lib: definition.libelle, u: definition.unite, def: definition.definition,
            src: definition.source, agg: AGREGATION_DES_INDICATEURS[cle],
        };
    }

    const RYTHMES = ["saisonnier", "ponctuel", "temps_forts", "regulier", "indetermine"];
    const VARIABLE_DE_COULEUR_DES_RYTHMES = {
        saisonnier: "--n-festival", ponctuel: "--n-ponct", temps_forts: "--n-mixte",
        regulier: "--n-lieu", indetermine: "--n-indet",
    };
    // Un lieu peut avoir plusieurs usages : ils servent aux filtres, a la liste et aux
    // barres « par usage », jamais la ou il faut une seule valeur par lieu.
    // / A venue may have several uses: filters, list and "per use" bars only.
    const USAGES = ["agenda", "billetterie_gratuite", "billetterie_payante", "adhesions", "caisse",
        "location", "reseau", "aucun"];
    const ACTIVITES = ["tres_actif", "actif", "peu_utilise", "sommeil"];
    const VARIABLE_DE_COULEUR_DES_ACTIVITES = {
        tres_actif: "--a-tres", actif: "--a-actif", peu_utilise: "--a-peu", sommeil: "--a-inactif",
    };
    const TAILLES = ["petit", "moyen", "gros"];
    const VARIABLE_DE_COULEUR_DES_TAILLES = {petit: "--t-petit", moyen: "--t-moyen", gros: "--t-gros"};

    function est_utilisee(activite) {
        return activite === "tres_actif" || activite === "actif" || activite === "peu_utilise";
    }

    // Valeur d'une instance pour un indicateur sur les 12 derniers mois.
    // / An instance's value for an indicator over the last 12 months.
    function valeur_agregee(instance, cle) {
        const agregation = AGREGATION_DES_INDICATEURS[cle];
        if (agregation === "statique") {
            return instance[cle];
        }
        const douze_derniers_mois = instance.compteurs_par_mois[cle].slice(nombre_de_mois - 12);
        return agregation === "max" ? Math.max.apply(null, douze_derniers_mois) : somme(douze_derniers_mois);
    }

    function couleur_du_rythme(rythme, transparence) {
        return couleur_css(VARIABLE_DE_COULEUR_DES_RYTHMES[rythme]) + (transparence || "");
    }

    // ============================================================
    // 4. Vue standard
    // / 4. Standard view
    // ============================================================

    let case_choisie_dans_la_matrice = null;

    function instances_filtrees() {
        const usage_choisi = document.getElementById("c-usage").value;
        const rythme_choisi = document.getElementById("c-rythme").value;
        const activite_choisie = document.getElementById("c-act").value;
        return liste_des_instances.filter(function (instance) {
            if (usage_choisi && !instance.usages.includes(usage_choisi)) { return false; }
            if (rythme_choisi && instance.rythme !== rythme_choisi) { return false; }
            if (activite_choisie && instance.activite !== activite_choisie) { return false; }
            if (case_choisie_dans_la_matrice) {
                return instance.taille === case_choisie_dans_la_matrice.taille
                    && instance.rythme === case_choisie_dans_la_matrice.rythme
                    && est_utilisee(instance.activite);
            }
            return true;
        });
    }

    function nombre_d_instances_avec_l_activite(activite) {
        return liste_des_instances.filter(function (instance) { return instance.activite === activite; }).length;
    }

    function rendre_tuiles() {
        const N = nombre_de_mois;
        const nombre_d_abandons = liste_des_instances.filter(function (instance) { return instance.abandon; }).length;
        const ca_du_reseau = somme(liste_des_instances.map(function (instance) { return instance.ca12; }));
        const recharges_du_reseau = somme(liste_des_instances.map(function (instance) { return valeur_agregee(instance, "recharges"); }));
        const recharges_en_ligne = somme(liste_des_instances.map(function (instance) { return valeur_agregee(instance, "recharges_ligne"); }));
        // Les porte-monnaie distincts ne s'additionnent pas vraiment entre lieux (une
        // personne paie dans deux lieux) : la tuile le dit, c'est un ordre de grandeur.
        // / Distinct wallets do not really add up across venues: an order of magnitude.
        const portemonnaies_par_mois = liste_des_mois.map(function (mois, index) {
            return somme(liste_des_instances.map(function (instance) { return instance.compteurs_par_mois.portemonnaies_actifs[index]; }));
        }).slice(N - 12);
        const meilleur_mois_des_portemonnaies = Math.max.apply(null, portemonnaies_par_mois);
        const annees_de_creation = liste_des_instances.map(function (instance) { return +instance.cree.slice(0, 4) || 9999; });
        const tres_actives = nombre_d_instances_avec_l_activite("tres_actif");

        // Les seuils EN COURS, pour les bulles « ? » : elles suivent les reglages.
        // / The CURRENT thresholds, for the "?" bubbles: they follow the settings.
        const seuils_en_cours = {
            actif_mois: seuils.actifMois,
            tres_actif_mois: seuils.tresActifMois,
            abandon_mois: seuils.abandonMoisMax, abandon_silence: seuils.abandonSilence,
            abandon_ca: formater_nombre(seuils.abandonCAMax),
        };
        const usage_reel = " " + texte("aide_usage_reel");

        // Chaque tuile : [libelle, valeur, detail, methode de calcul].
        // / Each tile: [label, value, detail, computation method].
        const tuiles = [
            [texte("tuile_instances"), formater_nombre(liste_des_instances.length),
                texte("tuile_instances_detail", {annee: Math.min.apply(null, annees_de_creation)}),
                texte("methode_instances")],
            [texte("tuile_actives"), formater_nombre(tres_actives + nombre_d_instances_avec_l_activite("actif")),
                texte("tuile_actives_detail", {nombre: tres_actives}),
                texte("methode_actives", seuils_en_cours) + usage_reel],
            [texte("tuile_peu_utilisees"), formater_nombre(nombre_d_instances_avec_l_activite("peu_utilise")),
                texte("tuile_peu_utilisees_detail"),
                texte("methode_peu_utilisees", seuils_en_cours) + usage_reel],
            [texte("tuile_sommeil"), formater_nombre(nombre_d_instances_avec_l_activite("sommeil")),
                texte("tuile_sommeil_detail"),
                texte("methode_sommeil", seuils_en_cours) + usage_reel],
            [texte("tuile_abandons"), formater_nombre(nombre_d_abandons),
                texte("tuile_abandons_detail", {mois: seuils.abandonSilence}),
                texte("methode_abandons", seuils_en_cours) + usage_reel],
            [texte("tuile_ca"), formater_nombre(ca_du_reseau, "€"), texte("tuile_ca_detail"),
                texte("methode_ca")],
            [texte("tuile_recharges"), formater_nombre(recharges_du_reseau, "€"),
                texte("tuile_recharges_detail", {pourcentage: Math.round(recharges_en_ligne / (recharges_du_reseau || 1) * 100)}),
                texte("methode_recharges")],
            [texte("tuile_portemonnaies"), formater_nombre(meilleur_mois_des_portemonnaies),
                texte("tuile_portemonnaies_detail", {mois: libelles_des_mois[N - 12 + portemonnaies_par_mois.indexOf(meilleur_mois_des_portemonnaies)]}),
                texte("methode_portemonnaies")],
        ];
        // Meme HTML que seo/templates/seo/partials/observatoire_aide.html.
        // / Same HTML as the observatoire_aide.html partial.
        document.getElementById("tuiles").innerHTML = tuiles.map(function (tuile, position) {
            const identifiant_de_la_bulle = "aide-synthese-" + position;
            const bulle = `<span class="aide" role="img" tabindex="0" aria-label="${echapper_html(texte("aide_methode"))}" aria-describedby="${identifiant_de_la_bulle}" data-testid="observatoire-${identifiant_de_la_bulle}">?`
                + `<span class="bulle" role="tooltip" id="${identifiant_de_la_bulle}">${echapper_html(tuile[3])}</span></span>`;
            return `<div class="tuile"><span class="lib">${tuile[0]}${bulle}</span><span class="val">${tuile[1]}</span><span class="det">${tuile[2]}</span></div>`;
        }).join("");
    }

    function rendre_qualification() {
        const instances_utilisees = liste_des_instances.filter(function (instance) { return est_utilisee(instance.activite); });
        // « indetermine » reste affiche : un lieu actif par ses seuls evenements n'a pas
        // de volume, donc pas de rythme, et doit rester visible dans la matrice.
        // / "indetermine" stays: a venue active through events only has no rhythm.
        const rythmes_affiches = RYTHMES;

        // La matrice taille x rythme. Une case non vide est un bouton qui filtre.
        // / The size x rhythm matrix. A non-empty cell is a filtering button.
        let html = `<tr><th></th>${rythmes_affiches.map(function (rythme) {
            return `<th><span class="pastille" style="background:var(${VARIABLE_DE_COULEUR_DES_RYTHMES[rythme]})"></span>${libelle_de("rythmes", rythme)}</th>`;
        }).join("")}<th>${texte("total")}</th></tr>`;
        TAILLES.forEach(function (taille) {
            html += `<tr><th>${libelle_de("tailles", taille)}</th>` + rythmes_affiches.map(function (rythme) {
                const nombre = instances_utilisees.filter(function (instance) { return instance.taille === taille && instance.rythme === rythme; }).length;
                const est_choisie = case_choisie_dans_la_matrice && case_choisie_dans_la_matrice.taille === taille && case_choisie_dans_la_matrice.rythme === rythme;
                if (!nombre) {
                    return `<td class="vide">·</td>`;
                }
                const etiquette = texte("matrice_case", {nombre: nombre, taille: libelle_de("tailles", taille), rythme: libelle_de("rythmes", rythme)});
                return `<td tabindex="0" role="button" data-t="${taille}" data-n="${rythme}" class="${est_choisie ? "choisi" : ""}" aria-label="${echapper_html(etiquette)}">${nombre}</td>`;
            }).join("") + `<td class="vide">${instances_utilisees.filter(function (instance) { return instance.taille === taille; }).length}</td></tr>`;
        });
        html += `<tr><th>${texte("total")}</th>${rythmes_affiches.map(function (rythme) {
            return `<td class="vide">${instances_utilisees.filter(function (instance) { return instance.rythme === rythme; }).length}</td>`;
        }).join("")}<td class="vide">${instances_utilisees.length}</td></tr>`;

        const matrice = document.getElementById("matrice");
        matrice.innerHTML = html;
        matrice.querySelectorAll("td[data-t]").forEach(function (cellule) {
            const choisir_la_case = function () {
                const taille = cellule.dataset.t;
                const rythme = cellule.dataset.n;
                const deja_choisie = case_choisie_dans_la_matrice && case_choisie_dans_la_matrice.taille === taille && case_choisie_dans_la_matrice.rythme === rythme;
                case_choisie_dans_la_matrice = deja_choisie ? null : {taille: taille, rythme: rythme};
                rendre_qualification();
                rendre_graphique();
                rendre_liste();
            };
            cellule.onclick = choisir_la_case;
            cellule.onkeydown = function (evenement) {
                if (evenement.key === "Enter" || evenement.key === " ") {
                    evenement.preventDefault();
                    choisir_la_case();
                }
            };
        });
        document.getElementById("leg-rythme").innerHTML = `<li>${texte("legende_rythme")}</li>`;

        // La barre des niveaux d'activite, avec son equivalent texte (aria-label).
        // / The activity bar, with its text equivalent (aria-label).
        const nombres_par_activite = ACTIVITES.map(nombre_d_instances_avec_l_activite);
        const barre = document.getElementById("barre-act");
        barre.innerHTML = ACTIVITES.map(function (activite, index) {
            return `<span title="${libelle_de("activites", activite)} : ${nombres_par_activite[index]}" style="flex:${nombres_par_activite[index]};background:var(${VARIABLE_DE_COULEUR_DES_ACTIVITES[activite]})"></span>`;
        }).join("");
        barre.setAttribute("aria-label", ACTIVITES.map(function (activite, index) {
            return `${libelle_de("activites", activite)} ${nombres_par_activite[index]}`;
        }).join(", "));
        document.getElementById("leg-act").innerHTML = ACTIVITES.map(function (activite, index) {
            return `<li><span class="pastille" style="background:var(${VARIABLE_DE_COULEUR_DES_ACTIVITES[activite]})"></span>${libelle_de("activites", activite)} <b>${nombres_par_activite[index]}</b></li>`;
        }).join("");

        const abandons = liste_des_instances.filter(function (instance) { return instance.abandon; });
        const saisonniers_recurrents = liste_des_instances.filter(function (instance) { return instance.rythme === "saisonnier" && instance.recurrent; }).length;
        document.getElementById("encart-abandon").innerHTML = texte("encart_abandon", {
            nombre: `<strong>${abandons.length}</strong>`, mois_max: seuils.abandonMoisMax,
            silence: seuils.abandonSilence, saisonniers: saisonniers_recurrents,
        });
    }

    function rendre_seuils() {
        const conteneur = document.getElementById("seuils");
        conteneur.innerHTML = ORDRE_DES_SEUILS.map(function (cle_du_seuil) {
            return `<label for="s-${cle_du_seuil}">${texte("seuil_" + cle_du_seuil)}<input id="s-${cle_du_seuil}" type="number" min="0" value="${seuils[cle_du_seuil]}" data-k="${cle_du_seuil}" data-testid="observatoire-seuil-${cle_du_seuil}"></label>`;
        }).join("");
        conteneur.querySelectorAll("input").forEach(function (champ) {
            champ.oninput = function () {
                const nouvelle_valeur = parseFloat(champ.value);
                if (isNaN(nouvelle_valeur)) {
                    return;
                }
                seuils[champ.dataset.k] = nouvelle_valeur;
                tout_recalculer();
            };
        });
    }

    // ---------- L'explorateur / The explorer ----------

    let graphique_standard = null;

    function rendre_graphique() {
        const cle = document.getElementById("c-ind").value;
        const vue = document.getElementById("c-vue").value;
        const cle_de_l_axe_vertical = document.getElementById("c-ind2").value;
        const echelle_logarithmique = document.getElementById("c-log").checked;
        const definition = indicateur(cle);
        const instances = instances_filtrees();
        const est_statique = definition.agg === "statique";
        const N = nombre_de_mois;

        document.getElementById("l-groupe").hidden = vue !== "groupe";
        document.getElementById("l-ind2").hidden = vue !== "nuage";
        document.getElementById("l-log").hidden = !(vue === "nuage" || vue === "classement");

        const couleur_du_texte = couleur_css("--encre-2");
        const couleur_de_la_grille = couleur_css("--brume");
        const echelle = function (titre, logarithmique) {
            return {type: logarithmique ? "logarithmic" : "linear", beginAtZero: !logarithmique, grid: {color: couleur_de_la_grille}, border: {display: false},
                ticks: {color: couleur_du_texte, callback: function (v) { return formater_nombre(v); }}, title: {display: !!titre, text: titre, color: couleur_du_texte}};
        };
        const options_de_base = {responsive: true, maintainAspectRatio: false, animation: false, interaction: {mode: "index", intersect: false},
            plugins: {legend: {labels: {color: couleur_css("--encre"), boxWidth: 12, boxHeight: 12, usePointStyle: true}},
                tooltip: {callbacks: {label: function (c) { return ` ${c.dataset.label || ""} : ${formater_nombre(c.parsed.y, definition.u)}`; }}}}};
        const axe_des_mois = {grid: {display: false}, ticks: {color: couleur_du_texte, maxRotation: 0, autoSkip: true, autoSkipPadding: 8}, border: {color: couleur_css("--trait")}};
        const graphique_sans_historique = {type: "bar", data: {labels: [], datasets: []}, options: {...options_de_base, plugins: {...options_de_base.plugins,
            title: {display: true, color: couleur_du_texte, text: texte("graphique_sans_historique")}}}};
        const periode_par_instance = definition.agg === "max" ? texte("periode_meilleur_mois") : definition.agg === "statique" ? texte("periode_valeur_actuelle") : texte("periode_12_mois");

        let configuration;
        if (vue === "mois") {
            configuration = est_statique ? graphique_sans_historique : {type: "bar", data: {labels: libelles_des_mois, datasets: [{label: definition.lib,
                data: liste_des_mois.map(function (m, i) { return somme(instances.map(function (instance) { return instance.compteurs_par_mois[cle][i]; })); }),
                backgroundColor: liste_des_mois.map(function (m, i) { return i < N - 12 ? couleur_css("--n-indet") : couleur_css("--n-lieu"); }),
                borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 36}]},
                options: {...options_de_base, plugins: {...options_de_base.plugins, legend: {display: false},
                    title: {display: true, color: couleur_du_texte, text: texte("graphique_annee_precedente")}}, scales: {x: axe_des_mois, y: echelle(definition.u)}}};
        } else if (vue === "moyRythme") {
            configuration = est_statique ? graphique_sans_historique : {type: "line", data: {labels: libelles_des_mois, datasets: RYTHMES.filter(function (r) { return r !== "indetermine"; }).map(function (rythme) {
                const groupe = instances.filter(function (instance) { return instance.rythme === rythme; });
                return {label: `${libelle_de("rythmes", rythme)} (${groupe.length})`,
                    data: liste_des_mois.map(function (m, i) { return groupe.length ? somme(groupe.map(function (instance) { return instance.compteurs_par_mois[cle][i]; })) / groupe.length : null; }),
                    borderColor: couleur_du_rythme(rythme), backgroundColor: couleur_du_rythme(rythme), borderWidth: 2, pointRadius: 2.5, pointHoverRadius: 5, tension: .25};
            }).filter(function (serie) { return serie.data.some(function (v) { return v; }); })},
                options: {...options_de_base, scales: {x: axe_des_mois, y: echelle(texte("unite_par_instance", {unite: definition.u}))}}};
        } else if (vue === "groupe") {
            const regroupement = document.getElementById("c-groupe").value;
            const famille = {rythme: "rythmes", taille: "tailles", activite: "activites", usage: "usages"}[regroupement];
            const groupes = regroupement === "rythme" ? RYTHMES : regroupement === "taille" ? TAILLES : regroupement === "activite" ? ACTIVITES : USAGES;
            // Par usage, un lieu compte dans CHACUN de ses usages (titre du graphique).
            // / Per use, a venue counts in EACH of its uses (chart title says so).
            const est_membre = function (instance, valeur_du_groupe) {
                if (regroupement === "usage") { return instance.usages.includes(valeur_du_groupe); }
                return instance[regroupement] === valeur_du_groupe;
            };
            const lignes = groupes.map(function (valeur_du_groupe) {
                const membres = instances.filter(function (instance) { return est_membre(instance, valeur_du_groupe); });
                return {x: valeur_du_groupe, n: membres.length, v: membres.length ? somme(membres.map(function (instance) { return valeur_agregee(instance, cle); })) / membres.length : 0};
            }).filter(function (ligne) { return ligne.n; });
            configuration = {type: "bar", data: {labels: lignes.map(function (ligne) { return `${libelle_de(famille, ligne.x)} (${ligne.n})`; }),
                datasets: [{label: texte("moyenne_par_instance_de", {indicateur: definition.lib}), data: lignes.map(function (ligne) { return ligne.v; }),
                    backgroundColor: lignes.map(function (ligne) { return regroupement === "rythme" ? couleur_du_rythme(ligne.x) : regroupement === "activite" ? couleur_css(VARIABLE_DE_COULEUR_DES_ACTIVITES[ligne.x]) : couleur_css("--n-lieu"); }),
                    borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 64}]},
                options: {...options_de_base, interaction: {mode: "nearest", intersect: true}, plugins: {...options_de_base.plugins, legend: {display: false},
                    title: {display: regroupement === "usage", color: couleur_du_texte, text: texte("graphique_usages_cumules")}},
                    scales: {x: {...axe_des_mois, ticks: {color: couleur_du_texte, autoSkip: false}}, y: echelle(texte("unite_par_instance_periode", {unite: definition.u, periode: periode_par_instance}))}}};
        } else if (vue === "classement") {
            const classement = instances.map(function (instance) { return {instance: instance, v: valeur_agregee(instance, cle)}; })
                .filter(function (ligne) { return ligne.v > 0; }).sort(function (a, b) { return b.v - a.v; }).slice(0, 120);
            configuration = {type: "bar", data: {labels: classement.map(function (ligne) { return ligne.instance.nom; }), datasets: [{label: definition.lib,
                data: classement.map(function (ligne) { return ligne.v; }), backgroundColor: classement.map(function (ligne) { return couleur_du_rythme(ligne.instance.rythme); }),
                borderRadius: 3, borderSkipped: "bottom", categoryPercentage: .9, barPercentage: .9}]},
                options: {...options_de_base, interaction: {mode: "nearest", intersect: false, axis: "x"}, plugins: {...options_de_base.plugins, legend: {display: false},
                    tooltip: {callbacks: {title: function (c) { return c[0].label; }, label: function (c) {
                        const instance = classement[c.dataIndex].instance;
                        return [` ${formater_nombre(c.parsed.y, definition.u)}`, ` ${libelle_de("rythmes", instance.rythme)} · ${libelle_de("tailles", instance.taille)} · ${libelle_de("activites", instance.activite)}`];
                    }}},
                    title: {display: true, color: couleur_du_texte, text: texte(classement.length === 120 ? "classement_titre_120" : "classement_titre", {nombre: classement.length, periode: periode_par_instance})}},
                    scales: {x: {display: false}, y: echelle(definition.u, echelle_logarithmique)}}};
        } else {
            const definition_verticale = indicateur(cle_de_l_axe_vertical);
            const series = RYTHMES.map(function (rythme) {
                return {label: libelle_de("rythmes", rythme),
                    data: instances.filter(function (instance) { return instance.rythme === rythme; })
                        .map(function (instance) { return {x: valeur_agregee(instance, cle), y: valeur_agregee(instance, cle_de_l_axe_vertical), nom: instance.nom}; })
                        .filter(function (point) { return !echelle_logarithmique || (point.x > 0 && point.y > 0); }),
                    backgroundColor: couleur_du_rythme(rythme, "cc"), borderColor: couleur_css("--papier"), borderWidth: 1.5, pointRadius: 5, pointHoverRadius: 7};
            }).filter(function (serie) { return serie.data.length; });
            configuration = {type: "scatter", data: {datasets: series}, options: {...options_de_base, interaction: {mode: "nearest", intersect: true},
                plugins: {...options_de_base.plugins, tooltip: {callbacks: {label: function (c) { return ` ${c.raw.nom} : ${formater_nombre(c.raw.x, definition.u)} · ${formater_nombre(c.raw.y, definition_verticale.u)}`; }}}},
                scales: {x: echelle(`${definition.lib} (${definition.u})`, echelle_logarithmique), y: echelle(`${definition_verticale.lib} (${definition_verticale.u})`, echelle_logarithmique)}}};
        }
        if (graphique_standard) {
            graphique_standard.destroy();
        }
        graphique_standard = new Chart(document.getElementById("graph"), configuration);

        let phrase_du_filtre = texte("selection_nombre", {nombre: instances.length});
        if (case_choisie_dans_la_matrice) {
            phrase_du_filtre += " · " + texte("selection_case", {taille: libelle_de("tailles", case_choisie_dans_la_matrice.taille), rythme: libelle_de("rythmes", case_choisie_dans_la_matrice.rythme)});
        }
        document.getElementById("filtre-actif").textContent = phrase_du_filtre;

        // La fiche de l'indicateur : sa definition et sa source.
        // / The indicator card: its definition and source.
        const fiche = [[definition.lib, definition.def], [texte("fiche_source"), definition.src]];
        if (vue === "nuage") {
            const definition_verticale = indicateur(cle_de_l_axe_vertical);
            fiche.push([texte("fiche_axe_vertical", {indicateur: definition_verticale.lib}), definition_verticale.def]);
        }
        document.getElementById("fiche").innerHTML = fiche.map(function (ligne) {
            return `<div><dt>${ligne[0]}</dt><dd>${ligne[1]}</dd></div>`;
        }).join("");
        document.getElementById("graph-texte").textContent = texte("graphique_equivalent_texte", {indicateur: definition.lib, nombre: instances.length});
    }

    // ---------- La liste des instances / The instance list ----------

    let tri_de_la_liste = {cle: "ca12", sens: -1};
    const COLONNES_DE_LA_LISTE = [["nom"], ["usages"], ["rythme"], ["taille"], ["activite"], ["tendance"],
        ["reels12", "r"], ["ca12", "r"], ["rech", "r"], ["portemonnaies", "r"]];
    const COLONNES_TRIEES_PAR_ORDRE_ALPHABETIQUE = ["nom", "usages", "rythme", "taille", "activite", "tendance"];

    function rendre_liste() {
        const recherche = document.getElementById("c-cherche").value.trim().toLowerCase();
        const avec_les_inactives = document.getElementById("c-dormants").checked;
        const instances = instances_filtrees().filter(function (instance) {
            const visible = avec_les_inactives || est_utilisee(instance.activite) || instance.abandon;
            return visible && (!recherche || instance.nom.toLowerCase().includes(recherche));
        });
        instances.forEach(function (instance) {
            instance.rech = valeur_agregee(instance, "recharges");
            instance.portemonnaies = valeur_agregee(instance, "portemonnaies_actifs");
        });
        instances.sort(function (a, b) {
            const cle = tri_de_la_liste.cle;
            // Les usages sont une liste : on les compare comme un texte.
            // / Uses are a list: compared as text.
            const valeur_a = cle === "usages" ? a.usages.join(",") : a[cle];
            const valeur_b = cle === "usages" ? b.usages.join(",") : b[cle];
            return (valeur_a > valeur_b ? 1 : valeur_a < valeur_b ? -1 : 0) * tri_de_la_liste.sens;
        });
        document.getElementById("nb-liste").textContent = texte("nombre_d_instances", {nombre: instances.length});

        const en_tete = COLONNES_DE_LA_LISTE.map(function (colonne) {
            const cle = colonne[0];
            const classe = colonne[1] || "";
            const est_triee = tri_de_la_liste.cle === cle;
            const sens_aria = est_triee ? (tri_de_la_liste.sens > 0 ? "ascending" : "descending") : "none";
            const fleche = est_triee ? (tri_de_la_liste.sens > 0 ? " ↑" : " ↓") : "";
            return `<th class="${classe}" aria-sort="${sens_aria}"><button type="button" data-k="${cle}">${texte("colonne_" + cle)}${fleche}</button></th>`;
        }).join("");
        const lignes = instances.slice(0, 300).map(function (instance) {
            const saisonnier_recurrent = instance.recurrent && instance.rythme === "saisonnier" ? " ↻" : "";
            const pastille_abandon = instance.abandon ? ` <span class="pill lourd">${texte("pastille_abandon")}</span>` : "";
            const tendance = instance.tendance === "en_baisse" ? `<span class="pill moyen">${libelle_de("tendances", "en_baisse")}</span>` : (instance.tendance ? libelle_de("tendances", instance.tendance) : "·");
            const pastilles_des_usages = instance.usages.includes("aucun") ? "·" : instance.usages.map(function (usage) {
                return `<span class="pill">${libelle_de("usages", usage)}</span>`;
            }).join(" ");
            return `<tr><td>${echapper_html(instance.nom)}</td>`
                + `<td>${pastilles_des_usages}</td>`
                + `<td><span class="pastille" style="background:var(${VARIABLE_DE_COULEUR_DES_RYTHMES[instance.rythme]})"></span>${libelle_de("rythmes", instance.rythme)}${saisonnier_recurrent}</td>`
                + `<td>${est_utilisee(instance.activite) ? libelle_de("tailles", instance.taille) : "·"}</td>`
                + `<td><span class="pastille" style="background:var(${VARIABLE_DE_COULEUR_DES_ACTIVITES[instance.activite]})"></span>${libelle_de("activites", instance.activite)}${pastille_abandon}</td>`
                + `<td>${tendance}</td>`
                + `<td class="r">${instance.reels12}</td><td class="r">${formater_nombre(instance.ca12, "€")}</td><td class="r">${formater_nombre(instance.rech, "€")}</td>`
                + `<td class="r">${formater_nombre(instance.portemonnaies)}</td></tr>`;
        }).join("");
        document.getElementById("liste").innerHTML = `<thead><tr>${en_tete}</tr></thead><tbody>${lignes}</tbody>`;
        document.querySelectorAll("#liste th button").forEach(function (bouton) {
            bouton.onclick = function () {
                const cle = bouton.dataset.k;
                let sens;
                if (tri_de_la_liste.cle === cle) {
                    sens = -tri_de_la_liste.sens;
                } else {
                    sens = COLONNES_TRIEES_PAR_ORDRE_ALPHABETIQUE.includes(cle) ? 1 : -1;
                }
                tri_de_la_liste = {cle: cle, sens: sens};
                rendre_liste();
            };
        });
    }

    // ============================================================
    // 5. Onglets et demarrage
    // / 5. Tabs and start-up
    // ============================================================

    function tout_recalculer() {
        liste_des_instances.forEach(classer_une_instance);
        rendre_tuiles();
        rendre_qualification();
        rendre_liste();
        if (onglet_actif() === "standard") {
            rendre_graphique();
        } else {
            rendre_mesure();
        }
    }

    function onglet_actif() {
        return document.getElementById("o-mesure").getAttribute("aria-selected") === "true" ? "sur-mesure" : "standard";
    }

    function ouvrir_onglet(nom_de_l_onglet) {
        const sur_mesure = nom_de_l_onglet === "sur-mesure";
        document.getElementById("o-standard").setAttribute("aria-selected", String(!sur_mesure));
        document.getElementById("o-mesure").setAttribute("aria-selected", String(sur_mesure));
        document.getElementById("o-standard").tabIndex = sur_mesure ? -1 : 0;
        document.getElementById("o-mesure").tabIndex = sur_mesure ? 0 : -1;
        document.getElementById("vue-standard").hidden = sur_mesure;
        document.getElementById("vue-mesure").hidden = !sur_mesure;
        history.replaceState(null, "", "#" + nom_de_l_onglet);
        // Un graphique se dessine quand il est visible.
        // / A chart is drawn when it is visible.
        if (sur_mesure) {
            rendre_mesure();
        } else {
            rendre_graphique();
        }
    }

    function remplir_les_listes_de_choix() {
        const options_des_indicateurs = ORDRE_DES_INDICATEURS.map(function (cle) {
            return `<option value="${cle}">${indicateur(cle).lib}</option>`;
        }).join("");
        document.getElementById("c-ind").innerHTML = options_des_indicateurs;
        document.getElementById("c-ind2").innerHTML = options_des_indicateurs;
        document.getElementById("c-ind2").value = "portemonnaies_actifs";
        const options_des_rythmes = RYTHMES.map(function (rythme) { return `<option value="${rythme}">${libelle_de("rythmes", rythme)}</option>`; }).join("");
        const options_des_usages = USAGES.map(function (usage) { return `<option value="${usage}">${libelle_de("usages", usage)}</option>`; }).join("");
        const options_des_activites = ACTIVITES.map(function (activite) { return `<option value="${activite}">${libelle_de("activites", activite)}</option>`; }).join("");
        const options_des_tailles = TAILLES.map(function (taille) { return `<option value="${taille}">${libelle_de("tailles", taille)}</option>`; }).join("");
        document.getElementById("c-usage").insertAdjacentHTML("beforeend", options_des_usages);
        document.getElementById("c-rythme").insertAdjacentHTML("beforeend", options_des_rythmes);
        document.getElementById("c-act").insertAdjacentHTML("beforeend", options_des_activites);
        document.getElementById("m-usage").insertAdjacentHTML("beforeend", options_des_usages);
        document.getElementById("m-rythme").insertAdjacentHTML("beforeend", options_des_rythmes);
        document.getElementById("m-act").insertAdjacentHTML("beforeend", options_des_activites);
        document.getElementById("m-taille").insertAdjacentHTML("beforeend", options_des_tailles);
    }

    function brancher_les_controles() {
        document.getElementById("o-standard").onclick = function () { ouvrir_onglet("standard"); };
        document.getElementById("o-mesure").onclick = function () { ouvrir_onglet("sur-mesure"); };
        document.querySelector(".onglets").onkeydown = function (evenement) {
            if (evenement.key === "ArrowRight" || evenement.key === "ArrowLeft") {
                const onglet_suivant = onglet_actif() === "standard" ? "sur-mesure" : "standard";
                ouvrir_onglet(onglet_suivant);
                document.getElementById(onglet_suivant === "standard" ? "o-standard" : "o-mesure").focus();
            }
        };
        ["c-ind", "c-vue", "c-groupe", "c-ind2", "c-usage", "c-rythme", "c-act", "c-log"].forEach(function (identifiant) {
            document.getElementById(identifiant).onchange = function () {
                rendre_graphique();
                rendre_liste();
            };
        });
        document.getElementById("c-cherche").oninput = rendre_liste;
        document.getElementById("c-dormants").onchange = rendre_liste;
        document.getElementById("c-vue").value = "moyRythme";
    }

    function demarrer() {
        const balise_des_donnees = document.getElementById("observatoire-donnees");
        if (!balise_des_donnees) {
            return;
        }
        DONNEES_DE_LA_PAGE = JSON.parse(balise_des_donnees.textContent);
        TEXTES = DONNEES_DE_LA_PAGE.textes || {};
        LIBELLES = DONNEES_DE_LA_PAGE.libelles || {};
        INDICATEURS = DONNEES_DE_LA_PAGE.indicateurs || {};
        // Sans calcul en cache, le gabarit affiche deja le message « Aucun calcul ».
        // / Without a cached computation, the template already shows the message.
        if (!DONNEES_DE_LA_PAGE.calcul) {
            return;
        }
        Chart.defaults.font.family = couleur_css("--f-texte");
        charger_les_donnees(DONNEES_DE_LA_PAGE.calcul);
        remplir_les_listes_de_choix();
        brancher_les_controles();
        rendre_seuils();
        initialiser_sur_mesure();
        liste_des_instances.forEach(classer_une_instance);
        ouvrir_onglet(location.hash === "#sur-mesure" ? "sur-mesure" : "standard");
        tout_recalculer();

        // Le theme clair / sombre change les couleurs : on redessine.
        // / Light / dark theme changes the colours: redraw.
        const redessiner = function () {
            if (onglet_actif() === "standard") { rendre_graphique(); } else { rendre_mesure(); }
        };
        matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redessiner);
        new MutationObserver(redessiner).observe(document.documentElement, {attributes: true, attributeFilter: ["class", "data-theme"]});
    }

    // ============================================================
    // 6. Onglet « Sur mesure » : l'utilisateur construit UN graphique
    //    en croisant deux parametres.
    // / 6. "Custom" tab: the user builds ONE chart by crossing two parameters.
    //
    // Axe horizontal possible :
    //   - un indicateur   -> nuage de points, une pastille par instance
    //   - le temps (mois) -> courbes, une serie par valeur de « couleur »
    //   - un groupe       -> barres (rythme, taille, activite)
    //   - les instances   -> classement en barres
    //   - une repartition -> anneau
    // ============================================================

    // Des groupes a UNE valeur par lieu (couleurs, anneau, courbes). Les usages n'y
    // sont pas : un lieu en a plusieurs. Ils servent de filtre (m-usage).
    // / Single-valued groups only. Uses (several per venue) are a filter here.
    const GROUPES = {
        rythme: {famille: "rythmes", valeur: function (instance) { return instance.rythme; }, ordre: function () { return RYTHMES; }},
        activite: {famille: "activites", valeur: function (instance) { return instance.activite; }, ordre: function () { return ACTIVITES; }},
        taille: {famille: "tailles", valeur: function (instance) { return instance.taille; }, ordre: function () { return TAILLES; }},
    };

    function nom_du_groupe(dimension) {
        return texte("groupe_" + dimension);
    }

    function couleur_du_groupe(dimension, valeur) {
        if (dimension === "rythme") { return couleur_css(VARIABLE_DE_COULEUR_DES_RYTHMES[valeur] || "--n-indet"); }
        if (dimension === "activite") { return couleur_css(VARIABLE_DE_COULEUR_DES_ACTIVITES[valeur] || "--a-inactif"); }
        if (dimension === "taille") { return couleur_css(VARIABLE_DE_COULEUR_DES_TAILLES[valeur] || "--n-indet"); }
        return couleur_css("--n-lieu");
    }

    function libelle_du_groupe(dimension, valeur) {
        return libelle_de(GROUPES[dimension].famille, valeur);
    }

    // Une seule configuration, modifiee par deux interfaces : « En phrases » et
    // « Mode avance ». Elle est gardee dans le navigateur (localStorage), par confort.
    // / One config, edited by two UIs, kept in localStorage for convenience.
    const TYPES_DE_GRAPHIQUE = ["nuage", "mois", "groupe", "classement", "anneau"];
    const CONFIGURATION_PAR_DEFAUT = {mode: "phrases", type: "nuage", x: "ca_total", y: "portemonnaies_actifs", g: "rythme", calc: "moyenne",
        periode: "12", couleur: "rythme", usage: "", rythme: "", act: "", taille: "", zero: true, log: true};
    // Le suffixe change quand les cles des indicateurs ou des groupes changent : une
    // ancienne configuration gardee (indicateur disparu) ferait planter la page.
    // / The suffix changes with indicator or group keys: an old saved config would crash.
    const CLE_DU_STOCKAGE_LOCAL = "observatoire-sur-mesure-v4";
    let configuration_sur_mesure = {...CONFIGURATION_PAR_DEFAUT};

    const EXEMPLES = [
        {cle: "exemple_portemonnaies_ca", c: {type: "nuage", x: "ca_total", y: "portemonnaies_actifs", periode: "12", couleur: "rythme", log: true, zero: true}},
        {cle: "exemple_volume_rythme", c: {type: "mois", y: "volume", calc: "moyenne", periode: "tout", couleur: "rythme", log: false, zero: true}},
        {cle: "exemple_billets", c: {type: "nuage", x: "billets_payants", y: "billets_gratuits", periode: "12", couleur: "activite", log: true, zero: true}},
        {cle: "exemple_recharges", c: {type: "nuage", x: "recharges_ligne", y: "recharges_place", periode: "12", couleur: "taille", log: true, zero: true}},
        {cle: "exemple_scans", c: {type: "classement", y: "billets_scannes", periode: "12", couleur: "rythme", log: true, zero: true}},
        {cle: "exemple_repartition_rythme", c: {type: "anneau", g: "rythme", y: "volume", periode: "12", log: false, zero: true}},
        {cle: "exemple_composantes", c: {type: "anneau", g: "composantes", y: "ca_total", periode: "12", log: false, zero: true}},
        {cle: "exemple_instances_utilisees", c: {type: "mois", y: "reel", calc: "total", periode: "tout", couleur: "aucune", log: false, zero: false}},
    ];

    // Les choix des phrases a trous : [valeur, cle du texte].
    // / Fill-in sentence choices: [value, text key].
    const PERIODES = [["12", "periode_12"], ["prec", "periode_prec"], ["tout", "periode_tout"]];
    const CALCULS = [["total", "calcul_total"], ["moyenne", "calcul_moyenne"], ["mediane", "calcul_mediane"]];
    const VUES = [["mois", "vue_mois"], ["g:rythme", "vue_rythme"], ["g:activite", "vue_activite"], ["g:taille", "vue_taille"],
        ["classement", "vue_classement"]];
    const DISTINCTIONS = [["aucune", "distinguer_aucune"], ["rythme", "distinguer_rythme"], ["activite", "distinguer_activite"], ["taille", "distinguer_taille"]];
    const COULEURS_DU_NUAGE = [["rythme", "couleur_rythme"], ["activite", "couleur_activite"], ["taille", "couleur_taille"], ["aucune", "couleur_aucune"]];
    const DECOUPES = [["rythme", "decoupe_rythme"], ["activite", "decoupe_activite"], ["taille", "decoupe_taille"],
        ["instances", "decoupe_instances"], ["composantes", "decoupe_composantes"]];

    function forme_choisie() {
        if (configuration_sur_mesure.type === "nuage") { return "croiser"; }
        if (configuration_sur_mesure.type === "anneau") { return "repartir"; }
        return "suivre";
    }

    function vue_choisie() {
        if (configuration_sur_mesure.type === "mois") { return "mois"; }
        if (configuration_sur_mesure.type === "classement") { return "classement"; }
        return "g:" + (GROUPES[configuration_sur_mesure.g] ? configuration_sur_mesure.g : "rythme");
    }

    let graphique_sur_mesure = null;

    // Une liste de choix. Les libelles viennent de Python (cles de texte) ou des
    // indicateurs ; ils sont echappes.
    // / A select. Labels come from Python; they are escaped.
    function options_html(paires_valeur_libelle, valeur_choisie) {
        return paires_valeur_libelle.map(function (paire) {
            return `<option value="${paire[0]}"${paire[0] === valeur_choisie ? " selected" : ""}>${echapper_html(paire[1])}</option>`;
        }).join("");
    }

    function paires_traduites(paires_valeur_cle) {
        return paires_valeur_cle.map(function (paire) { return [paire[0], texte(paire[1])]; });
    }

    function liste_de_choix_html(identifiant, paires, valeur_choisie, nom_accessible) {
        return `<select id="${identifiant}" aria-label="${echapper_html(nom_accessible)}">${options_html(paires, valeur_choisie)}</select>`;
    }

    function rendre_phrase() {
        const indicateurs_avec_article = ORDRE_DES_INDICATEURS.map(function (cle) {
            return [cle, (INDICATEURS[cle] && INDICATEURS[cle].avec_article) || indicateur(cle).lib];
        });
        const choix_de_la_periode = liste_de_choix_html("p-periode", paires_traduites(PERIODES), configuration_sur_mesure.periode, texte("nom_periode"));
        const forme = forme_choisie();
        let phrase;
        if (forme === "suivre") {
            phrase = texte("phrase_suivre", {
                calcul: liste_de_choix_html("p-calc", paires_traduites(CALCULS), configuration_sur_mesure.calc, texte("nom_calcul")),
                indicateur: liste_de_choix_html("p-y", indicateurs_avec_article, configuration_sur_mesure.y, texte("nom_indicateur")),
                vue: liste_de_choix_html("p-vue", paires_traduites(VUES), vue_choisie(), texte("nom_decoupage")),
                periode: choix_de_la_periode,
                distinction: liste_de_choix_html("p-couleur", paires_traduites(DISTINCTIONS), configuration_sur_mesure.couleur, texte("nom_distinction")),
            });
        } else if (forme === "croiser") {
            phrase = texte("phrase_croiser", {
                premier: liste_de_choix_html("p-y", indicateurs_avec_article, configuration_sur_mesure.y, texte("nom_premier_indicateur")),
                second: liste_de_choix_html("p-x", indicateurs_avec_article, configuration_sur_mesure.x, texte("nom_second_indicateur")),
                periode: choix_de_la_periode,
                couleur: liste_de_choix_html("p-couleur", paires_traduites(COULEURS_DU_NUAGE), configuration_sur_mesure.couleur, texte("nom_couleur")),
            });
        } else {
            phrase = texte("phrase_repartir", {
                indicateur: liste_de_choix_html("p-y", indicateurs_avec_article, configuration_sur_mesure.y, texte("nom_indicateur_a_decouper")),
                decoupe: liste_de_choix_html("p-g", paires_traduites(DECOUPES), configuration_sur_mesure.g, texte("nom_decoupage")),
                periode: choix_de_la_periode,
            });
        }
        document.getElementById("phrase").innerHTML = phrase;
        document.getElementById("phrase-aide").textContent = texte("aide_" + forme);
        document.querySelectorAll(".formes button").forEach(function (bouton) {
            bouton.setAttribute("aria-pressed", String(bouton.dataset.forme === forme));
        });
        const choix_du_calcul = document.getElementById("p-calc");
        if (choix_du_calcul) {
            choix_du_calcul.disabled = configuration_sur_mesure.type === "classement";
            choix_du_calcul.title = choix_du_calcul.disabled ? texte("calcul_sans_objet") : "";
        }
        document.querySelectorAll("#phrase select").forEach(function (liste) { liste.onchange = lire_la_phrase; });
    }

    function lire_la_phrase() {
        const valeur_de = function (identifiant) { return (document.getElementById(identifiant) || {}).value; };
        const forme = forme_choisie();
        configuration_sur_mesure.y = valeur_de("p-y");
        configuration_sur_mesure.periode = valeur_de("p-periode");
        if (forme === "suivre") {
            configuration_sur_mesure.calc = valeur_de("p-calc");
            configuration_sur_mesure.couleur = valeur_de("p-couleur");
            const vue = valeur_de("p-vue");
            if (vue === "mois") {
                configuration_sur_mesure.type = "mois";
            } else if (vue === "classement") {
                configuration_sur_mesure.type = "classement";
            } else {
                configuration_sur_mesure.type = "groupe";
                configuration_sur_mesure.g = vue.slice(2);
            }
        } else if (forme === "croiser") {
            configuration_sur_mesure.x = valeur_de("p-x");
            configuration_sur_mesure.couleur = valeur_de("p-couleur");
        } else {
            configuration_sur_mesure.g = valeur_de("p-g");
        }
        rendre_phrase();
        rendre_mesure();
    }

    function choisir_la_forme(forme) {
        if (forme === forme_choisie()) {
            return;
        }
        if (forme === "croiser") {
            configuration_sur_mesure.type = "nuage";
            if (configuration_sur_mesure.couleur === "aucune") { configuration_sur_mesure.couleur = "rythme"; }
            if (configuration_sur_mesure.x === configuration_sur_mesure.y) {
                configuration_sur_mesure.x = configuration_sur_mesure.y === "ca_total" ? "portemonnaies_actifs" : "ca_total";
            }
        } else if (forme === "repartir") {
            configuration_sur_mesure.type = "anneau";
            const decoupe_connue = DECOUPES.some(function (paire) { return paire[0] === configuration_sur_mesure.g; });
            if (!decoupe_connue) { configuration_sur_mesure.g = "rythme"; }
        } else {
            configuration_sur_mesure.type = "mois";
        }
        configuration_sur_mesure.log = configuration_sur_mesure.type === "nuage" ? configuration_sur_mesure.log : false;
        document.getElementById("m-log").checked = configuration_sur_mesure.log;
        rendre_phrase();
        rendre_mesure();
    }

    function rendre_mode_avance() {
        const type = configuration_sur_mesure.type;
        const indicateurs = ORDRE_DES_INDICATEURS.map(function (cle) { return [cle, indicateur(cle).lib]; });
        document.getElementById("a-type").value = type;
        document.getElementById("a-y").innerHTML = options_html(indicateurs, configuration_sur_mesure.y);
        document.getElementById("a-x").innerHTML = options_html(indicateurs, configuration_sur_mesure.x);
        let dimensions;
        if (type === "anneau") {
            dimensions = DECOUPES.map(function (paire) { return [paire[0], texte("groupe_" + paire[0])]; });
        } else {
            dimensions = Object.keys(GROUPES).map(function (dimension) { return [dimension, nom_du_groupe(dimension)]; });
        }
        if (!dimensions.some(function (paire) { return paire[0] === configuration_sur_mesure.g; })) {
            configuration_sur_mesure.g = "rythme";
        }
        document.getElementById("a-g").innerHTML = options_html(dimensions, configuration_sur_mesure.g);
        document.getElementById("a-calc").value = configuration_sur_mesure.calc;
        document.getElementById("a-periode").value = configuration_sur_mesure.periode;
        document.getElementById("a-couleur").value = configuration_sur_mesure.couleur;
        // N'afficher que les champs qui servent pour ce type de graphique.
        // / Only show the fields used by this chart type.
        document.querySelector("#l-a-y span").textContent = type === "nuage" ? texte("champ_axe_vertical") : type === "anneau" ? texte("champ_indicateur_a_repartir") : texte("champ_indicateur");
        document.querySelector("#l-a-g span").textContent = type === "anneau" ? texte("champ_decouper_selon") : texte("champ_regrouper_par");
        document.querySelector("#l-a-couleur span").textContent = type === "mois" ? texte("champ_une_courbe_par") : type === "groupe" ? texte("champ_une_barre_par") : texte("champ_couleur");
        document.getElementById("l-a-x").hidden = type !== "nuage";
        document.getElementById("l-a-g").hidden = !(type === "groupe" || type === "anneau");
        document.getElementById("l-a-calc").hidden = !(type === "mois" || type === "groupe");
        document.getElementById("l-a-couleur").hidden = type === "anneau";
    }

    function lire_le_mode_avance() {
        const ancien_type = configuration_sur_mesure.type;
        configuration_sur_mesure.type = document.getElementById("a-type").value;
        configuration_sur_mesure.y = document.getElementById("a-y").value;
        configuration_sur_mesure.x = document.getElementById("a-x").value;
        configuration_sur_mesure.g = document.getElementById("a-g").value;
        configuration_sur_mesure.calc = document.getElementById("a-calc").value;
        configuration_sur_mesure.periode = document.getElementById("a-periode").value;
        configuration_sur_mesure.couleur = document.getElementById("a-couleur").value;
        if (configuration_sur_mesure.type !== ancien_type && configuration_sur_mesure.type === "anneau") {
            configuration_sur_mesure.log = false;
            document.getElementById("m-log").checked = false;
        }
        rendre_mode_avance();
        rendre_mesure();
    }

    function choisir_le_mode(mode) {
        configuration_sur_mesure.mode = mode;
        document.getElementById("mode-phrases").setAttribute("aria-pressed", String(mode === "phrases"));
        document.getElementById("mode-avance").setAttribute("aria-pressed", String(mode === "avance"));
        document.getElementById("bloc-phrases").hidden = mode !== "phrases";
        document.getElementById("bloc-avance").hidden = mode !== "avance";
        if (mode === "phrases") {
            rendre_phrase();
        } else {
            rendre_mode_avance();
        }
    }

    function appliquer_les_filtres_a_l_ecran() {
        document.getElementById("m-usage").value = configuration_sur_mesure.usage;
        document.getElementById("m-rythme").value = configuration_sur_mesure.rythme;
        document.getElementById("m-act").value = configuration_sur_mesure.act;
        document.getElementById("m-taille").value = configuration_sur_mesure.taille;
        document.getElementById("m-zero").checked = configuration_sur_mesure.zero;
        document.getElementById("m-log").checked = configuration_sur_mesure.log;
    }

    function initialiser_sur_mesure() {
        document.getElementById("exemples").innerHTML = `<span>${texte("exemples")}</span>` + EXEMPLES.map(function (exemple, index) {
            return `<button type="button" data-i="${index}">${texte(exemple.cle)}</button>`;
        }).join("");
        document.querySelectorAll("#exemples button").forEach(function (bouton) {
            bouton.onclick = function () {
                configuration_sur_mesure = {...CONFIGURATION_PAR_DEFAUT, mode: configuration_sur_mesure.mode, ...EXEMPLES[+bouton.dataset.i].c};
                appliquer_les_filtres_a_l_ecran();
                choisir_le_mode(configuration_sur_mesure.mode);
                rendre_mesure();
            };
        });
        // La derniere configuration, gardee dans ce navigateur. Absente ou illisible : le defaut.
        // / The last config, kept in this browser. Missing or unreadable: the default.
        try {
            const configuration_gardee = JSON.parse(localStorage.getItem(CLE_DU_STOCKAGE_LOCAL));
            if (configuration_gardee && TYPES_DE_GRAPHIQUE.includes(configuration_gardee.type)) {
                configuration_sur_mesure = {...CONFIGURATION_PAR_DEFAUT, ...configuration_gardee};
            }
        } catch (erreur) { /* le defaut reste / the default stays */ }
        document.getElementById("mode-phrases").onclick = function () { choisir_le_mode("phrases"); rendre_mesure(); };
        document.getElementById("mode-avance").onclick = function () { choisir_le_mode("avance"); rendre_mesure(); };
        document.querySelectorAll(".formes button").forEach(function (bouton) {
            bouton.onclick = function () { choisir_la_forme(bouton.dataset.forme); };
        });
        ["a-type", "a-y", "a-x", "a-g", "a-calc", "a-periode", "a-couleur"].forEach(function (identifiant) {
            document.getElementById(identifiant).onchange = lire_le_mode_avance;
        });
        ["m-usage", "m-rythme", "m-act", "m-taille", "m-zero", "m-log"].forEach(function (identifiant) {
            document.getElementById(identifiant).onchange = function () {
                configuration_sur_mesure.usage = document.getElementById("m-usage").value;
                configuration_sur_mesure.rythme = document.getElementById("m-rythme").value;
                configuration_sur_mesure.act = document.getElementById("m-act").value;
                configuration_sur_mesure.taille = document.getElementById("m-taille").value;
                configuration_sur_mesure.zero = document.getElementById("m-zero").checked;
                configuration_sur_mesure.log = document.getElementById("m-log").checked;
                rendre_mesure();
            };
        });
        appliquer_les_filtres_a_l_ecran();
        choisir_le_mode(configuration_sur_mesure.mode);
    }

    // ---------- Calculs du sur-mesure / Custom-tab computations ----------

    function fenetre_de_mois(periode) {
        const N = nombre_de_mois;
        if (periode === "prec") { return [Math.max(0, N - 24), N - 12]; }
        if (periode === "tout") { return [0, N]; }
        return [N - 12, N];
    }

    // Valeur d'une instance pour un indicateur, sur une fenetre de mois.
    // / An instance's value for an indicator, over a window of months.
    function valeur_sur_la_fenetre(instance, cle, fenetre) {
        const agregation = AGREGATION_DES_INDICATEURS[cle];
        if (agregation === "statique") {
            return instance[cle] || 0;
        }
        const valeurs = instance.compteurs_par_mois[cle].slice(fenetre[0], fenetre[1]);
        return agregation === "max" ? Math.max.apply(null, [0].concat(valeurs)) : somme(valeurs);
    }

    function combiner(valeurs, calcul) {
        if (!valeurs.length) { return null; }
        if (calcul === "total") { return somme(valeurs); }
        if (calcul === "mediane") {
            const triees = valeurs.slice().sort(function (a, b) { return a - b; });
            const milieu = triees.length >> 1;
            return triees.length % 2 ? triees[milieu] : (triees[milieu - 1] + triees[milieu]) / 2;
        }
        return somme(valeurs) / valeurs.length;
    }

    // Correlation de Spearman : sur les rangs, donc peu sensible aux tres gros lieux.
    // / Spearman correlation: on ranks, so little sensitive to very big venues.
    function rangs(valeurs) {
        const indexees = valeurs.map(function (x, i) { return [x, i]; }).sort(function (a, b) { return a[0] - b[0]; });
        const resultat = new Array(valeurs.length);
        for (let i = 0; i < indexees.length;) {
            let j = i;
            while (j + 1 < indexees.length && indexees[j + 1][0] === indexees[i][0]) { j++; }
            for (let k = i; k <= j; k++) { resultat[indexees[k][1]] = (i + j) / 2; }
            i = j + 1;
        }
        return resultat;
    }

    function spearman(abscisses, ordonnees) {
        if (abscisses.length < 5) { return null; }
        const rangs_x = rangs(abscisses);
        const rangs_y = rangs(ordonnees);
        const moyenne_x = somme(rangs_x) / rangs_x.length;
        const moyenne_y = somme(rangs_y) / rangs_y.length;
        let numerateur = 0;
        let ecart_x = 0;
        let ecart_y = 0;
        for (let i = 0; i < rangs_x.length; i++) {
            numerateur += (rangs_x[i] - moyenne_x) * (rangs_y[i] - moyenne_y);
            ecart_x += (rangs_x[i] - moyenne_x) ** 2;
            ecart_y += (rangs_y[i] - moyenne_y) ** 2;
        }
        return ecart_x && ecart_y ? numerateur / Math.sqrt(ecart_x * ecart_y) : null;
    }

    function phrase_du_lien(correlation) {
        if (correlation === null) { return ""; }
        const force = Math.abs(correlation);
        const cle_de_la_force = force < .2 ? "lien_aucun" : force < .4 ? "lien_faible" : force < .7 ? "lien_modere" : "lien_fort";
        const cle_du_sens = force < .2 ? "" : correlation > 0 ? "lien_meme_sens" : "lien_sens_inverse";
        return " " + texte("lien_phrase", {
            force: `<b>${texte(cle_de_la_force)}</b>`,
            correlation: correlation.toLocaleString(LANGUE_DE_LA_PAGE, {maximumFractionDigits: 2}),
            sens: cle_du_sens ? texte(cle_du_sens) : "",
        });
    }

    // L'anneau : au plus 7 parts. Au-dela, l'oeil ne compare plus les angles ;
    // le reste va dans « Autres ».
    // / The doughnut: 7 parts at most; the rest goes into "Others".
    const COMPOSANTES = {
        ca_total: [["ca_billetterie", "composante_billetterie", "--n-festival"], ["ca_adhesions", "composante_adhesions", "--n-mixte"], ["ca_caisse", "composante_caisse", "--n-lieu"]],
        recharges: [["recharges_ligne", "composante_en_ligne", "--n-lieu"], ["recharges_place", "composante_sur_place", "--n-mixte"]],
    };
    const NOMBRE_MAXIMUM_DE_PARTS = 7;

    function parts_de_l_anneau(dimension, cle, instances, fenetre) {
        let parts;
        if (dimension === "composantes") {
            if (!COMPOSANTES[cle]) { return null; }
            parts = COMPOSANTES[cle].map(function (composante) {
                return {lib: texte(composante[1]), v: somme(instances.map(function (instance) { return valeur_sur_la_fenetre(instance, composante[0], fenetre); })), couleur: couleur_css(composante[2])};
            });
        } else if (dimension === "instances") {
            const triees = instances.map(function (instance) { return {lib: instance.nom, v: valeur_sur_la_fenetre(instance, cle, fenetre)}; })
                .filter(function (part) { return part.v > 0; }).sort(function (a, b) { return b.v - a.v; });
            parts = triees.slice(0, NOMBRE_MAXIMUM_DE_PARTS - 1);
            const reste = somme(triees.slice(NOMBRE_MAXIMUM_DE_PARTS - 1).map(function (part) { return part.v; }));
            if (reste) {
                parts.push({lib: texte("autres_instances", {nombre: triees.length - NOMBRE_MAXIMUM_DE_PARTS + 1}), v: reste, autres: true});
            }
            // Une seule teinte, du plus fonce au plus clair : l'ordre suit la taille de la part.
            // / One hue, dark to light: the order follows the part size.
            const teintes = ["--t-gros", "--t-moyen", "--t-petit"];
            parts.forEach(function (part, index) {
                part.couleur = part.autres ? couleur_css("--n-indet") : couleur_css(teintes[Math.min(2, Math.floor(index / 2))]) + (index % 2 ? "bb" : "");
            });
            return parts;
        } else {
            const groupe = GROUPES[dimension];
            parts = groupe.ordre().map(function (valeur) {
                return {lib: libelle_du_groupe(dimension, valeur),
                    v: somme(instances.filter(function (instance) { return groupe.valeur(instance) === valeur; }).map(function (instance) { return valeur_sur_la_fenetre(instance, cle, fenetre); })),
                    couleur: couleur_du_groupe(dimension, valeur)};
            });
        }
        parts = parts.filter(function (part) { return part.v > 0; }).sort(function (a, b) { return b.v - a.v; });
        if (parts.length > NOMBRE_MAXIMUM_DE_PARTS) {
            const reste = parts.slice(NOMBRE_MAXIMUM_DE_PARTS - 1);
            parts = parts.slice(0, NOMBRE_MAXIMUM_DE_PARTS - 1);
            parts.push({lib: texte("autres", {nombre: reste.length}), v: somme(reste.map(function (part) { return part.v; })), couleur: couleur_css("--n-indet"), autres: true});
        }
        return parts;
    }

    // ---------- Rendu du sur-mesure / Custom-tab rendering ----------

    function est_un_nombre_affiche(valeur) {
        return typeof valeur === "number" || /^[\d\s ,.·]+( [kM])?( €)?$/.test(String(valeur));
    }

    function rendre_mesure() {
        if (!liste_des_instances.length || document.getElementById("vue-mesure").hidden) {
            return;
        }
        const configuration = configuration_sur_mesure;
        try { localStorage.setItem(CLE_DU_STOCKAGE_LOCAL, JSON.stringify(configuration)); } catch (erreur) { /* sans effet / no effect */ }

        const axe_horizontal = {nuage: configuration.x, mois: "mois", groupe: "g:" + configuration.g, classement: "instances", anneau: "r:" + configuration.g}[configuration.type];
        const fenetre = fenetre_de_mois(configuration.periode);
        const definition_y = indicateur(configuration.y);
        const nom_de_la_periode = configuration.periode === "tout" ? texte("periode_n_mois", {nombre: nombre_de_mois}) : texte({"12": "periode_12", prec: "periode_prec"}[configuration.periode]);
        const valeur_par_instance = definition_y.agg === "max" ? texte("par_instance_meilleur_mois") : definition_y.agg === "statique" ? texte("par_instance_valeur_actuelle") : texte("par_instance_total");
        const instances = liste_des_instances.filter(function (instance) {
            return (!configuration.usage || instance.usages.includes(configuration.usage))
                && (!configuration.rythme || instance.rythme === configuration.rythme)
                && (!configuration.act || instance.activite === configuration.act)
                && (!configuration.taille || instance.taille === configuration.taille);
        });
        let type_d_axe;
        if (axe_horizontal === "mois") { type_d_axe = "mois"; }
        else if (axe_horizontal === "instances") { type_d_axe = "instances"; }
        else if (axe_horizontal.startsWith("g:")) { type_d_axe = "groupe"; }
        else if (axe_horizontal.startsWith("r:")) { type_d_axe = "anneau"; }
        else { type_d_axe = "indicateur"; }
        const dimension_de_couleur = configuration.couleur !== "aucune" ? configuration.couleur : null;

        document.getElementById("l-m-log").hidden = type_d_axe === "anneau";

        const couleur_du_texte = couleur_css("--encre-2");
        const couleur_de_la_grille = couleur_css("--brume");
        const axe = function (titre, logarithmique, numerique) {
            if (numerique === undefined) { numerique = true; }
            return {type: logarithmique ? "logarithmic" : numerique ? "linear" : "category", beginAtZero: !logarithmique, grid: {color: numerique ? couleur_de_la_grille : "transparent"},
                border: {display: false}, ticks: {color: couleur_du_texte, callback: numerique ? function (v) { return formater_nombre(v); } : undefined}, title: {display: !!titre, text: titre, color: couleur_du_texte}};
        };
        const options_de_base = {responsive: true, maintainAspectRatio: false, animation: false,
            plugins: {legend: {display: !!dimension_de_couleur, labels: {color: couleur_css("--encre"), boxWidth: 12, boxHeight: 12, usePointStyle: true}}}};
        const libelle_du_calcul = {total: texte("calcul_libelle_total"), moyenne: texte("calcul_libelle_moyenne"), mediane: texte("calcul_libelle_mediane")}[configuration.calc];
        const lib_y = `<b>${echapper_html(definition_y.lib)}</b>`;
        let configuration_du_graphique;
        let lecture;
        let tableau;

        if (type_d_axe === "indicateur") {
            const definition_x = indicateur(configuration.x);
            const points = instances.map(function (instance) { return {x: valeur_sur_la_fenetre(instance, configuration.x, fenetre), y: valeur_sur_la_fenetre(instance, configuration.y, fenetre), instance: instance}; })
                .filter(function (point) { return !(configuration.zero || configuration.log) || (point.x > 0 && point.y > 0); });
            const valeurs_de_couleur = dimension_de_couleur
                ? GROUPES[dimension_de_couleur].ordre().filter(function (v) { return points.some(function (point) { return GROUPES[dimension_de_couleur].valeur(point.instance) === v; }); })
                : [null];
            configuration_du_graphique = {type: "scatter", data: {datasets: valeurs_de_couleur.map(function (v) {
                return {label: v === null ? definition_y.lib : libelle_du_groupe(dimension_de_couleur, v),
                    data: points.filter(function (point) { return v === null || GROUPES[dimension_de_couleur].valeur(point.instance) === v; }).map(function (point) { return {x: point.x, y: point.y, nom: point.instance.nom}; }),
                    backgroundColor: (v === null ? couleur_css("--n-lieu") : couleur_du_groupe(dimension_de_couleur, v)) + "cc",
                    borderColor: couleur_css("--papier"), borderWidth: 1.5, pointRadius: 5, pointHoverRadius: 7};
            })},
                options: {...options_de_base, interaction: {mode: "nearest", intersect: true},
                    plugins: {...options_de_base.plugins, tooltip: {callbacks: {label: function (t) { return ` ${t.raw.nom} : ${formater_nombre(t.raw.x, definition_x.u)} · ${formater_nombre(t.raw.y, definition_y.u)}`; }}}},
                    scales: {x: axe(`${definition_x.lib} (${definition_x.u})`, configuration.log), y: axe(`${definition_y.lib} (${definition_y.u})`, configuration.log)}}};
            lecture = texte("lecture_nuage", {
                vertical: lib_y, horizontal: `<b>${echapper_html(definition_x.lib)}</b>`, periode: nom_de_la_periode, nombre: points.length,
                couleur: dimension_de_couleur ? texte("lecture_couleur", {groupe: nom_du_groupe(dimension_de_couleur).toLowerCase()}) : "",
            }) + phrase_du_lien(spearman(points.map(function (point) { return point.x; }), points.map(function (point) { return point.y; })));
            tableau = {tete: [texte("colonne_nom"), texte("colonne_rythme"), texte("colonne_activite"), `${definition_x.lib} (${definition_x.u})`, `${definition_y.lib} (${definition_y.u})`],
                lignes: points.sort(function (a, b) { return b.y - a.y; }).map(function (point) {
                    return [point.instance.nom, libelle_de("rythmes", point.instance.rythme), libelle_de("activites", point.instance.activite), formater_nombre(point.x, definition_x.u), formater_nombre(point.y, definition_y.u)];
                })};

        } else if (type_d_axe === "mois") {
            const etiquettes = libelles_des_mois.slice(fenetre[0], fenetre[1]);
            const valeurs_de_couleur = dimension_de_couleur ? GROUPES[dimension_de_couleur].ordre() : [null];
            const series = valeurs_de_couleur.map(function (v) {
                const membres = v === null ? instances : instances.filter(function (instance) { return GROUPES[dimension_de_couleur].valeur(instance) === v; });
                const donnees = etiquettes.map(function (etiquette, j) {
                    const i = fenetre[0] + j;
                    let valeurs = membres.map(function (instance) { return instance.compteurs_par_mois[configuration.y] ? instance.compteurs_par_mois[configuration.y][i] : (instance[configuration.y] || 0); });
                    if (configuration.zero && configuration.calc !== "total") {
                        valeurs = valeurs.filter(function (x) { return x > 0; });
                    }
                    return combiner(valeurs, configuration.calc);
                });
                return {v: v, n: membres.length, data: donnees};
            }).filter(function (serie) { return serie.n && serie.data.some(function (x) { return x; }); });
            configuration_du_graphique = {type: "line", data: {labels: etiquettes, datasets: series.map(function (serie) {
                const couleur = serie.v === null ? couleur_css("--n-lieu") : couleur_du_groupe(dimension_de_couleur, serie.v);
                return {label: serie.v === null ? definition_y.lib : `${libelle_du_groupe(dimension_de_couleur, serie.v)} (${serie.n})`, data: serie.data,
                    borderColor: couleur, backgroundColor: couleur, borderWidth: 2, pointRadius: 2.5, pointHoverRadius: 5, tension: .25, spanGaps: true};
            })},
                options: {...options_de_base, interaction: {mode: "index", intersect: false},
                    plugins: {...options_de_base.plugins, legend: {...options_de_base.plugins.legend, display: series.length > 1}, tooltip: {callbacks: {label: function (t) { return ` ${t.dataset.label} : ${formater_nombre(t.parsed.y, definition_y.u)}`; }}}},
                    scales: {x: {grid: {display: false}, ticks: {color: couleur_du_texte, maxRotation: 0, autoSkipPadding: 8}, border: {color: couleur_css("--trait")}}, y: axe(definition_y.u, configuration.log)}}};
            lecture = texte("lecture_mois", {
                indicateur: lib_y, periode: nom_de_la_periode, calcul: libelle_du_calcul,
                zeros: configuration.zero && configuration.calc !== "total" ? texte("lecture_zeros_exclus_du_mois") : "",
                courbes: dimension_de_couleur ? texte("lecture_une_courbe_par", {groupe: nom_du_groupe(dimension_de_couleur).toLowerCase()}) : "",
            });
            tableau = {tete: [texte("colonne_mois")].concat(series.map(function (serie) { return serie.v === null ? definition_y.lib : libelle_du_groupe(dimension_de_couleur, serie.v); })),
                lignes: etiquettes.map(function (etiquette, j) {
                    return [etiquette].concat(series.map(function (serie) { return serie.data[j] === null ? "·" : formater_nombre(serie.data[j], definition_y.u); }));
                })};

        } else if (type_d_axe === "groupe") {
            const dimension = axe_horizontal.slice(2);
            const groupe = GROUPES[dimension];
            const sous_groupes = dimension_de_couleur && dimension_de_couleur !== dimension ? GROUPES[dimension_de_couleur].ordre() : [null];
            const categories = groupe.ordre().filter(function (v) { return instances.some(function (instance) { return groupe.valeur(instance) === v; }); });
            const calculer_le_groupe = function (membres) {
                let valeurs = membres.map(function (instance) { return valeur_sur_la_fenetre(instance, configuration.y, fenetre); });
                if (configuration.zero && configuration.calc !== "total") {
                    valeurs = valeurs.filter(function (x) { return x > 0; });
                }
                return combiner(valeurs, configuration.calc);
            };
            const series = sous_groupes.map(function (sous_groupe) {
                return {s: sous_groupe, data: categories.map(function (v) {
                    const membres = instances.filter(function (instance) { return groupe.valeur(instance) === v && (sous_groupe === null || GROUPES[dimension_de_couleur].valeur(instance) === sous_groupe); });
                    return membres.length ? calculer_le_groupe(membres) : null;
                })};
            }).filter(function (serie) { return serie.data.some(function (v) { return v; }); });
            const effectifs = categories.map(function (v) { return instances.filter(function (instance) { return groupe.valeur(instance) === v; }).length; });
            configuration_du_graphique = {type: "bar", data: {labels: categories.map(function (v, i) { return `${libelle_du_groupe(dimension, v)} (${effectifs[i]})`; }), datasets: series.map(function (serie) {
                return {label: serie.s === null ? definition_y.lib : libelle_du_groupe(dimension_de_couleur, serie.s), data: serie.data,
                    backgroundColor: serie.s === null ? categories.map(function (v) { return couleur_du_groupe(dimension, v); }) : couleur_du_groupe(dimension_de_couleur, serie.s),
                    borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 60};
            })},
                options: {...options_de_base, interaction: {mode: "index", intersect: false},
                    plugins: {...options_de_base.plugins, legend: {...options_de_base.plugins.legend, display: series.length > 1}, tooltip: {callbacks: {label: function (t) { return ` ${t.dataset.label} : ${formater_nombre(t.parsed.y, definition_y.u)}`; }}}},
                    scales: {x: {grid: {display: false}, ticks: {color: couleur_du_texte, autoSkip: false}, border: {color: couleur_css("--trait")}}, y: axe(texte("unite_par_instance_periode", {unite: definition_y.u, periode: valeur_par_instance}), configuration.log)}}};
            lecture = texte("lecture_groupe", {
                indicateur: lib_y, valeur: valeur_par_instance, periode: nom_de_la_periode, groupe: nom_du_groupe(dimension).toLowerCase(), calcul: libelle_du_calcul,
                zeros: configuration.zero && configuration.calc !== "total" ? texte("lecture_zeros_exclus") : "",
                barres: series.length > 1 ? texte("lecture_une_barre_par", {groupe: nom_du_groupe(dimension_de_couleur).toLowerCase()}) : "",
            });
            tableau = {tete: [nom_du_groupe(dimension), texte("colonne_instances")].concat(series.map(function (serie) { return serie.s === null ? definition_y.lib : libelle_du_groupe(dimension_de_couleur, serie.s); })),
                lignes: categories.map(function (v, i) {
                    return [libelle_du_groupe(dimension, v), effectifs[i]].concat(series.map(function (serie) { return serie.data[i] === null ? "·" : formater_nombre(serie.data[i], definition_y.u); }));
                })};

        } else if (type_d_axe === "anneau") {
            const dimension = axe_horizontal.slice(2);
            const parts = parts_de_l_anneau(dimension, configuration.y, instances, fenetre);
            if (!parts) {
                configuration_du_graphique = {type: "doughnut", data: {labels: [], datasets: []}, options: {...options_de_base}};
                lecture = texte("anneau_sans_composantes", {indicateur: lib_y});
                tableau = {tete: [texte("colonne_part")], lignes: []};
            } else if (!parts.length) {
                configuration_du_graphique = {type: "doughnut", data: {labels: [], datasets: []}, options: {...options_de_base}};
                lecture = texte("anneau_vide", {indicateur: lib_y, periode: nom_de_la_periode});
                tableau = {tete: [texte("colonne_part")], lignes: []};
            } else {
                const total = somme(parts.map(function (part) { return part.v; }));
                const pourcentage = function (v) { return total ? Math.round(v / total * 1000) / 10 : 0; };
                configuration_du_graphique = {type: "doughnut",
                    data: {labels: parts.map(function (part) { return `${part.lib} · ${pourcentage(part.v).toLocaleString(LANGUE_DE_LA_PAGE)} %`; }),
                        datasets: [{label: definition_y.lib, data: parts.map(function (part) { return part.v; }), backgroundColor: parts.map(function (part) { return part.couleur; }),
                            borderColor: couleur_css("--papier"), borderWidth: 2, hoverOffset: 6}]},
                    options: {...options_de_base, cutout: "62%",
                        plugins: {...options_de_base.plugins,
                            legend: {display: true, position: window.innerWidth < 640 ? "bottom" : "right", labels: {color: couleur_css("--encre"), boxWidth: 12, boxHeight: 12, usePointStyle: true, padding: 12}},
                            tooltip: {callbacks: {label: function (t) { return ` ${parts[t.dataIndex].lib} : ${formater_nombre(t.parsed, definition_y.u)} (${pourcentage(t.parsed).toLocaleString(LANGUE_DE_LA_PAGE)} %)`; }}}}},
                    plugins: [{id: "centre", afterDraw: function (graphique) {
                        const zone = graphique.chartArea;
                        if (!zone) { return; }
                        const dessin = graphique.ctx;
                        const x = (zone.left + zone.right) / 2;
                        const y = (zone.top + zone.bottom) / 2;
                        dessin.save();
                        dessin.textAlign = "center";
                        dessin.textBaseline = "middle";
                        dessin.fillStyle = couleur_css("--encre");
                        dessin.font = `800 ${Math.max(16, Math.min(28, (zone.right - zone.left) / 9))}px ${couleur_css("--f-titre")}`;
                        dessin.fillText(formater_nombre(total, definition_y.u), x, y - 8);
                        dessin.fillStyle = couleur_css("--encre-2");
                        dessin.font = `12.5px ${couleur_css("--f-texte")}`;
                        dessin.fillText(dimension === "instances" ? texte("nombre_d_instances", {nombre: instances.length}) : texte("au_total"), x, y + 16);
                        dessin.restore();
                    }}]};
                const plus_grande_part = parts.reduce(function (a, b) { return b.v > a.v ? b : a; }, parts[0]);
                lecture = texte("lecture_anneau", {
                    indicateur: lib_y, valeur: valeur_par_instance, periode: nom_de_la_periode,
                    additionne: definition_y.agg === "max" ? texte("lecture_additionne") : "",
                    decoupe: texte(dimension === "composantes" ? "decoupe_composantes" : "decoupe_" + dimension),
                    nombre: parts.length, part: `<b>${echapper_html(plus_grande_part.lib)}</b>`,
                    pourcentage: pourcentage(plus_grande_part.v).toLocaleString(LANGUE_DE_LA_PAGE),
                    autres: parts.some(function (part) { return part.autres; }) ? texte("lecture_autres") : "",
                });
                tableau = {tete: [texte("colonne_part"), `${definition_y.lib} (${definition_y.u})`, texte("colonne_part_du_total")],
                    lignes: parts.map(function (part) { return [part.lib, formater_nombre(part.v, definition_y.u), `${pourcentage(part.v).toLocaleString(LANGUE_DE_LA_PAGE)} %`]; })};
            }

        } else {
            const classement = instances.map(function (instance) { return {instance: instance, v: valeur_sur_la_fenetre(instance, configuration.y, fenetre)}; })
                .filter(function (ligne) { return !(configuration.zero || configuration.log) || ligne.v > 0; }).sort(function (a, b) { return b.v - a.v; });
            const affiches = classement.slice(0, 150);
            configuration_du_graphique = {type: "bar", data: {labels: affiches.map(function (ligne) { return ligne.instance.nom; }), datasets: [{label: definition_y.lib, data: affiches.map(function (ligne) { return ligne.v; }),
                backgroundColor: affiches.map(function (ligne) { return dimension_de_couleur ? couleur_du_groupe(dimension_de_couleur, GROUPES[dimension_de_couleur].valeur(ligne.instance)) : couleur_css("--n-lieu"); }),
                borderRadius: 3, borderSkipped: "bottom", categoryPercentage: .9, barPercentage: .9}]},
                options: {...options_de_base, interaction: {mode: "nearest", intersect: false, axis: "x"},
                    plugins: {...options_de_base.plugins, legend: {display: false}, tooltip: {callbacks: {title: function (t) { return t[0].label; },
                        label: function (t) {
                            const instance = affiches[t.dataIndex].instance;
                            return [` ${formater_nombre(t.parsed.y, definition_y.u)}`, ` ${libelle_de("rythmes", instance.rythme)} · ${libelle_de("tailles", instance.taille)} · ${libelle_de("activites", instance.activite)}`];
                        }}}},
                    scales: {x: {display: false}, y: axe(definition_y.u, configuration.log)}}};
            lecture = texte("lecture_classement", {
                indicateur: lib_y, valeur: valeur_par_instance, periode: nom_de_la_periode, nombre: classement.length,
                limite: classement.length > 150 ? texte("lecture_150_premieres") : "",
                couleur: dimension_de_couleur ? texte("lecture_couleur", {groupe: nom_du_groupe(dimension_de_couleur).toLowerCase()}) : "",
            });
            tableau = {tete: [texte("colonne_rang"), texte("colonne_nom"), texte("colonne_rythme"), texte("colonne_activite"), `${definition_y.lib} (${definition_y.u})`],
                lignes: classement.map(function (ligne, index) {
                    return [index + 1, ligne.instance.nom, libelle_de("rythmes", ligne.instance.rythme), libelle_de("activites", ligne.instance.activite), formater_nombre(ligne.v, definition_y.u)];
                })};
        }

        if (graphique_sur_mesure) {
            graphique_sur_mesure.destroy();
        }
        graphique_sur_mesure = new Chart(document.getElementById("m-graph"), configuration_du_graphique);

        let titre;
        if (type_d_axe === "anneau") { titre = texte("titre_repartition", {indicateur: definition_y.lib}); }
        else if (type_d_axe === "indicateur") { titre = texte("titre_selon", {indicateur: definition_y.lib, autre: indicateur(configuration.x).lib}); }
        else if (type_d_axe === "mois") { titre = texte("titre_mois_par_mois", {indicateur: definition_y.lib}); }
        else if (type_d_axe === "groupe") { titre = texte("titre_par_groupe", {indicateur: definition_y.lib, groupe: nom_du_groupe(axe_horizontal.slice(2)).toLowerCase()}); }
        else { titre = texte("titre_classement", {indicateur: definition_y.lib}); }
        document.getElementById("m-titre").textContent = titre;
        document.getElementById("m-lecture").innerHTML = lecture;

        // Le tableau du graphique : l'equivalent texte, pour les lecteurs d'ecran.
        // Chaque cellule est echappee : elle peut contenir un nom de lieu.
        // / The chart table: the text equivalent. Every cell is escaped.
        const lignes_affichees = tableau.lignes.slice(0, 400);
        document.getElementById("m-resume-tableau").textContent = texte("voir_les_donnees", {nombre: tableau.lignes.length});
        document.getElementById("m-tableau").innerHTML =
            `<thead><tr>${tableau.tete.map(function (titre_de_colonne, i) {
                return `<th class="${lignes_affichees[0] && est_un_nombre_affiche(lignes_affichees[0][i]) ? "r" : ""}">${echapper_html(titre_de_colonne)}</th>`;
            }).join("")}</tr></thead><tbody>`
            + lignes_affichees.map(function (ligne) {
                return `<tr>${ligne.map(function (valeur) { return `<td class="${est_un_nombre_affiche(valeur) ? "r" : ""}">${echapper_html(valeur)}</td>`; }).join("")}</tr>`;
            }).join("") + `</tbody>`;
    }

    document.addEventListener("DOMContentLoaded", demarrer);
})();
