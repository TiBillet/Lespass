/**
 * Refuse, dans l'admin, un fichier trop lourd pour nginx — AVANT l'envoi du formulaire.
 * / In the admin, rejects a file too heavy for nginx — BEFORE the form is sent.
 *
 * LOCALISATION : static/js/admin_limite_upload.js
 * Charge sur toutes les pages de l'admin par UNFOLD["SCRIPTS"] (TiBillet/settings.py).
 *
 * LE PROBLEME :
 * nginx refuse toute requete plus lourde que `client_max_body_size 12M`
 * (nginx_prod/lespass_prod.conf, nginx_prod/lespass_bascule.conf, nginx/lespass_dev.conf).
 * Il repond par sa propre page « 413 Request Entity Too Large ». Django ne recoit
 * rien : il ne peut ni afficher d'erreur, ni renvoyer le formulaire rempli.
 * La personne perd tout ce qu'elle avait saisi.
 *
 * CE QUE FAIT CE SCRIPT :
 * Des qu'un fichier est choisi, il additionne le poids de tous les fichiers du
 * formulaire. Si le total depasse la limite :
 * - il vide le champ du fichier : ce fichier ne partira pas ;
 * - il remet le libelle du champ comme au chargement de la page ;
 * - il affiche un message rouge sous le champ ;
 * - il ne touche a rien d'autre : le reste du formulaire reste rempli.
 *
 * FLUX :
 * choix d'un fichier -> evenement « change » -> verifier_le_fichier_choisi()
 * Le script ecoute en phase de CAPTURE sur document : il passe AVANT l'ecouteur
 * d'Unfold pose sur le champ (unfold/static/unfold/js/app.js, fileInputUpdatePath),
 * qui recopie le nom du fichier dans le libelle. En cas de refus, le script arrete
 * l'evenement : l'ecouteur d'Unfold ne s'execute pas.
 *
 * COMMUNICATION :
 * Recoit : « change » de n'importe quel <input type="file"> de l'admin.
 * Emet : rien.
 */
(function () {
    "use strict";

    // Limite de nginx : 12M = 12 x 1024 x 1024 octets, pour la requete ENTIERE.
    // Si on change client_max_body_size dans nginx, il faut changer cette valeur.
    // / nginx limit: 12M for the WHOLE request. Keep in sync with client_max_body_size.
    const LIMITE_NGINX_EN_OCTETS = 12 * 1024 * 1024;

    // La requete porte aussi les champs texte et l'enveloppe « multipart ».
    // On leur garde 0,5 Mo de marge.
    // / The request also carries text fields and the multipart envelope: 0.5 MB margin.
    const MARGE_POUR_LES_AUTRES_CHAMPS_EN_OCTETS = 512 * 1024;

    const POIDS_MAXIMAL_DES_FICHIERS_EN_OCTETS =
        LIMITE_NGINX_EN_OCTETS - MARGE_POUR_LES_AUTRES_CHAMPS_EN_OCTETS;

    // Rouge des messages d'erreur. Style en ligne : les classes Tailwind maison
    // ne sont pas dans le paquet CSS d'Unfold.
    // / Error red. Inline style: custom Tailwind classes are not in Unfold's CSS bundle.
    const COULEUR_DU_MESSAGE_D_ERREUR = "#dc2626";

    // Compteur pour donner un id unique a chaque message (lien aria-describedby).
    // / Counter giving each message a unique id (aria-describedby link).
    let nombre_de_messages_crees = 0;

    /**
     * Vrai si l'admin est affiche en francais (attribut lang de <html>).
     * / True if the admin is displayed in French.
     */
    function la_page_est_en_francais() {
        const langue_de_la_page = (document.documentElement.lang || "fr").toLowerCase();
        return langue_de_la_page.startsWith("fr");
    }

    /**
     * Ecrit un poids en Mo, avec une decimale : « 14,2 Mo » ou « 14.2 MB ».
     * / Formats a weight in MB with one decimal.
     */
    function ecrire_le_poids_en_mo(poids_en_octets) {
        const poids_en_mo = poids_en_octets / (1024 * 1024);
        if (la_page_est_en_francais()) {
            return poids_en_mo.toLocaleString("fr-FR", {maximumFractionDigits: 1}) + " Mo";
        }
        return poids_en_mo.toLocaleString("en-GB", {maximumFractionDigits: 1}) + " MB";
    }

    /**
     * Additionne le poids des fichiers choisis dans un champ (un champ peut en porter plusieurs).
     * / Sums the weight of the files chosen in one field.
     */
    function poids_des_fichiers_du_champ(champ_fichier) {
        let poids_total_en_octets = 0;
        for (const fichier of champ_fichier.files) {
            poids_total_en_octets = poids_total_en_octets + fichier.size;
        }
        return poids_total_en_octets;
    }

    /**
     * Additionne le poids de tous les fichiers choisis dans le formulaire.
     * Sans formulaire autour, on ne compte que le champ lui-meme.
     * / Sums the weight of every file chosen in the form.
     */
    function poids_des_fichiers_du_formulaire(champ_fichier) {
        const formulaire = champ_fichier.form;
        if (!formulaire) {
            return poids_des_fichiers_du_champ(champ_fichier);
        }
        let poids_total_en_octets = 0;
        for (const autre_champ of formulaire.querySelectorAll('input[type="file"]')) {
            poids_total_en_octets = poids_total_en_octets + poids_des_fichiers_du_champ(autre_champ);
        }
        return poids_total_en_octets;
    }

    /**
     * Renvoie le cadre visible d'un champ fichier Unfold, ou null pour un champ natif.
     * Dans le gabarit Unfold (unfold/widgets/clearable_file_input.html), le vrai
     * <input type="file"> est cache trois niveaux sous ce cadre. Le cadre contient
     * aussi un <label> avec un <input type="text" disabled> : le libelle du champ.
     * / Returns the visible frame of an Unfold file field, or null for a native field.
     */
    function cadre_unfold_du_champ(champ_fichier) {
        const troisieme_parent = champ_fichier.parentNode
            && champ_fichier.parentNode.parentNode
            && champ_fichier.parentNode.parentNode.parentNode;
        if (!troisieme_parent) {
            return null;
        }
        const libelle = troisieme_parent.querySelector(':scope > label > input[type="text"][disabled]');
        if (!libelle) {
            return null;
        }
        return troisieme_parent;
    }

    /**
     * Renvoie le libelle du champ Unfold (le texte affiche dans le cadre), ou null.
     * / Returns the Unfold field label (text shown in the frame), or null.
     */
    function libelle_unfold_du_champ(champ_fichier) {
        const cadre_unfold = cadre_unfold_du_champ(champ_fichier);
        if (!cadre_unfold) {
            return null;
        }
        return cadre_unfold.querySelector(':scope > label > input[type="text"][disabled]');
    }

    /**
     * Memorise le libelle du champ tel qu'au chargement de la page : l'adresse de
     * l'image deja enregistree, ou « Choisir un fichier ». Appelee avant que l'ecouteur
     * d'Unfold change le libelle : au premier appel, c'est donc le texte d'origine.
     * / Remembers the field label as on page load (called before Unfold changes it).
     */
    function memoriser_le_libelle_d_origine(champ_fichier) {
        const libelle = libelle_unfold_du_champ(champ_fichier);
        const deja_memorise = champ_fichier.dataset.libelleDOrigine !== undefined;
        if (libelle && !deja_memorise) {
            champ_fichier.dataset.libelleDOrigine = libelle.value;
        }
    }

    /**
     * Remet le libelle du champ comme au chargement de la page.
     * Sur une fiche existante, il affiche de nouveau l'adresse de l'image enregistree :
     * la personne voit que son image n'est pas perdue.
     * / Restores the field label as on page load (shows the saved image again).
     */
    function remettre_le_libelle_d_origine(champ_fichier) {
        const libelle = libelle_unfold_du_champ(champ_fichier);
        const texte_d_origine = champ_fichier.dataset.libelleDOrigine;
        if (libelle && texte_d_origine !== undefined) {
            // setAttribute, comme Unfold : c'est l'attribut que le gabarit affiche.
            // / setAttribute, like Unfold: the attribute is what the template shows.
            libelle.setAttribute("value", texte_d_origine);
            libelle.value = texte_d_origine;
        }
    }

    /**
     * Retire le message d'erreur deja affiche pour ce champ, s'il y en a un.
     * On ne retire de aria-describedby QUE l'id de notre message : l'attribut peut
     * aussi pointer vers le texte d'aide du champ.
     * / Removes this field's previous error message, keeping other aria-describedby ids.
     */
    function retirer_le_message_d_erreur(champ_fichier) {
        const message_existant = champ_fichier.message_d_erreur_de_poids;
        if (!message_existant) {
            return;
        }

        const ids_decrivant_le_champ = (champ_fichier.getAttribute("aria-describedby") || "").split(" ");
        const ids_a_garder = [];
        for (const identifiant of ids_decrivant_le_champ) {
            if (identifiant && identifiant !== message_existant.id) {
                ids_a_garder.push(identifiant);
            }
        }
        if (ids_a_garder.length > 0) {
            champ_fichier.setAttribute("aria-describedby", ids_a_garder.join(" "));
        } else {
            champ_fichier.removeAttribute("aria-describedby");
        }

        champ_fichier.removeAttribute("aria-invalid");
        message_existant.remove();
        champ_fichier.message_d_erreur_de_poids = null;
    }

    /**
     * Affiche le message d'erreur sous le champ.
     * role="alert" : le lecteur d'ecran annonce le message tout de suite.
     * / Shows the error message under the field (role="alert").
     */
    function afficher_le_message_d_erreur(champ_fichier, texte_du_message) {
        nombre_de_messages_crees = nombre_de_messages_crees + 1;

        const message = document.createElement("p");
        message.id = "admin-limite-upload-erreur-" + nombre_de_messages_crees;
        message.setAttribute("role", "alert");
        message.setAttribute("data-testid", "admin-upload-erreur-poids");
        message.style.color = COULEUR_DU_MESSAGE_D_ERREUR;
        message.style.fontWeight = "600";
        message.style.marginTop = "6px";
        message.textContent = texte_du_message;

        // Sous le cadre Unfold s'il existe, sinon juste sous le champ natif.
        // / Under the Unfold frame if any, otherwise right under the native field.
        const element_au_dessus_du_message = cadre_unfold_du_champ(champ_fichier) || champ_fichier;
        element_au_dessus_du_message.insertAdjacentElement("afterend", message);

        const ids_existants = champ_fichier.getAttribute("aria-describedby");
        if (ids_existants) {
            champ_fichier.setAttribute("aria-describedby", ids_existants + " " + message.id);
        } else {
            champ_fichier.setAttribute("aria-describedby", message.id);
        }
        champ_fichier.setAttribute("aria-invalid", "true");

        // Reference directe vers le message : sert a le retirer au prochain choix.
        // / Direct reference to the message: used to remove it on the next choice.
        champ_fichier.message_d_erreur_de_poids = message;
    }

    /**
     * Ecrit le message : poids refuse, limite, et poids deja pris par les autres
     * champs du formulaire. « Fichier » ou « Fichiers » selon le nombre choisi.
     * / Builds the message: refused weight, limit, weight used by other fields.
     */
    function ecrire_le_message(nombre_de_fichiers_refuses, poids_refuse, poids_des_autres_champs) {
        const poids_refuse_ecrit = ecrire_le_poids_en_mo(poids_refuse);
        const poids_maximal_ecrit = ecrire_le_poids_en_mo(POIDS_MAXIMAL_DES_FICHIERS_EN_OCTETS);
        const poids_des_autres_ecrit = ecrire_le_poids_en_mo(poids_des_autres_champs);
        const plusieurs_fichiers_refuses = nombre_de_fichiers_refuses > 1;
        const d_autres_fichiers_sont_choisis = poids_des_autres_champs > 0;

        if (la_page_est_en_francais()) {
            let texte = "";
            if (plusieurs_fichiers_refuses) {
                texte = "Fichiers trop lourds (" + poids_refuse_ecrit + " au total). ";
            } else {
                texte = "Fichier trop lourd (" + poids_refuse_ecrit + "). ";
            }
            texte = texte + "Les fichiers d'un formulaire ne peuvent pas dépasser "
                + poids_maximal_ecrit + " au total";
            if (d_autres_fichiers_sont_choisis) {
                texte = texte + " (déjà choisis dans d'autres champs : " + poids_des_autres_ecrit + ")";
            }
            if (plusieurs_fichiers_refuses) {
                return texte + ". Les fichiers ont été retirés, le reste du formulaire est intact.";
            }
            return texte + ". Le fichier a été retiré, le reste du formulaire est intact.";
        }

        let texte = "";
        if (plusieurs_fichiers_refuses) {
            texte = "Files too large (" + poids_refuse_ecrit + " in total). ";
        } else {
            texte = "File too large (" + poids_refuse_ecrit + "). ";
        }
        texte = texte + "The files of a form cannot exceed " + poids_maximal_ecrit + " in total";
        if (d_autres_fichiers_sont_choisis) {
            texte = texte + " (already chosen in other fields: " + poids_des_autres_ecrit + ")";
        }
        if (plusieurs_fichiers_refuses) {
            return texte + ". The files were removed, the rest of the form is unchanged.";
        }
        return texte + ". The file was removed, the rest of the form is unchanged.";
    }

    /**
     * Verifie le ou les fichiers qui viennent d'etre choisis dans un champ.
     * / Checks the file(s) just chosen in a field.
     */
    function verifier_le_fichier_choisi(evenement) {
        const champ_fichier = evenement.target;
        const c_est_un_champ_fichier = champ_fichier instanceof HTMLInputElement
            && champ_fichier.type === "file";
        if (!c_est_un_champ_fichier) {
            return;
        }

        memoriser_le_libelle_d_origine(champ_fichier);
        retirer_le_message_d_erreur(champ_fichier);

        const poids_total_du_formulaire = poids_des_fichiers_du_formulaire(champ_fichier);
        if (poids_total_du_formulaire <= POIDS_MAXIMAL_DES_FICHIERS_EN_OCTETS) {
            return;
        }

        const nombre_de_fichiers_refuses = champ_fichier.files.length;
        const poids_refuse = poids_des_fichiers_du_champ(champ_fichier);
        const poids_des_autres_champs = poids_total_du_formulaire - poids_refuse;

        // Le fichier est refuse : les autres ecouteurs (celui d'Unfold qui recopie
        // le nom du fichier dans le libelle, par exemple) ne doivent pas le voir.
        // / The file is refused: other listeners (e.g. Unfold's label copy) must not see it.
        evenement.stopImmediatePropagation();

        // On vide le champ : le fichier trop lourd ne partira pas avec le formulaire.
        // / Empty the field: the heavy file will not be sent.
        champ_fichier.value = "";
        remettre_le_libelle_d_origine(champ_fichier);

        afficher_le_message_d_erreur(
            champ_fichier,
            ecrire_le_message(nombre_de_fichiers_refuses, poids_refuse, poids_des_autres_champs),
        );
    }

    // Phase de capture (true) : passe AVANT l'ecouteur d'Unfold sur le champ.
    // / Capture phase (true): runs BEFORE Unfold's listener on the field.
    document.addEventListener("change", verifier_le_fichier_choisi, true);
})();
