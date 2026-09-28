/**
 * Pilotage de l'ecran de la borne : lecture NFC, saisie du montant, modales.
 * / Kiosk screen driver: NFC reading, amount entry, modals.
 *
 * LOCALISATION : kiosk/static/kiosk/js/main.js
 *
 * Charge par kiosk/templates/kiosk/base.html, APRES nfc.js (qui definit
 * NfcReader) et APRES htmx.
 *
 * CE QUE CE FICHIER NE FAIT PAS / What this file does NOT do :
 * - Aucun calcul metier. Le solde, le nouveau solde, la validite de la carte
 *   et du montant sont decides par le serveur (kiosk/views.py).
 * - Aucun texte visible. Tous les libelles sont dans les templates, traduits.
 * - Aucun style en ligne. On bascule `hidden`, `disabled`, `aria-*` et des
 *   classes ; le reste est dans kiosk.css.
 * / No business logic, no visible text, no inline styles.
 *
 * CONVENTIONS DATA-* LUES ICI / DATA-* CONVENTIONS READ HERE :
 * - form[data-nfc-lecture="auto"]     : lecture NFC lancee des l'affichage
 * - form[data-nfc-lecture="manuelle"] : lecture lancee par un clic (modale admin)
 * - [data-afficher-bloc="x"]          : montre [data-bloc="x"] de la meme etape
 * - [data-modal-open="id"]            : ouvre le <dialog id="id">
 * - [data-modal-close]                : ferme le <dialog> parent
 * - dialog[data-ouvrir-au-chargement] : ouvert des son insertion
 * - [data-afficher-etat-admin="x"]    : etat de la modale admin
 * - form[data-saisie-montant]         : pave numerique + montants rapides
 */

// Lecteur NFC unique de la page (nfc.js).
// / The page's single NFC reader.
const rfid = new NfcReader();

// La lecture en cours : le formulaire qui recevra le tag, et son ecouteur.
// Une seule lecture a la fois : sinon un scan declencherait deux POST.
// / The ongoing read. One at a time, or one scan would fire two POSTs.
let formulaireEnAttenteDeCarte = null;
let ecouteurDeCarte = null;


/* ------------------------------------------------------------------------- */
/* Lecture NFC                                                                */
/* ------------------------------------------------------------------------- */

/**
 * Arrete la lecture NFC en cours, s'il y en a une.
 * / Stops the ongoing NFC read, if any.
 */
function arreterLaLectureNfc() {
    if (ecouteurDeCarte) {
        document.body.removeEventListener("nfcResult", ecouteurDeCarte);
        ecouteurDeCarte = null;
    }
    if (formulaireEnAttenteDeCarte) {
        formulaireEnAttenteDeCarte = null;
        rfid.stopLecture();
    }
}

/**
 * Lance le lecteur NFC pour un formulaire. Quand une carte est posee, son tag
 * est ecrit dans l'input tag_id du formulaire, puis le formulaire est soumis
 * (hx-post).
 * / Starts the NFC reader for a form. On tap, the tag goes into the form's
 * tag_id input and the form is submitted (hx-post).
 *
 * COMMUNICATION :
 * Recoit : 'nfcResult' (detail = tag_id) depuis nfc.js (lecteur ou simulateur DEMO)
 * Declenche : 'submit' HTMX sur le formulaire
 *
 * @param {HTMLFormElement} formulaire - formulaire avec un input name="tag_id"
 */
function lancerLaLectureNfcPour(formulaire) {
    arreterLaLectureNfc();

    formulaireEnAttenteDeCarte = formulaire;

    ecouteurDeCarte = function (evenementNfc) {
        const tagIdLu = evenementNfc.detail;

        // On libere le lecteur AVANT de soumettre : un deuxieme passage de
        // carte ne doit rien declencher. / Release the reader BEFORE submitting.
        arreterLaLectureNfc();

        const champTagId = formulaire.querySelector('input[name="tag_id"]');
        champTagId.value = tagIdLu;
        htmx.trigger(formulaire, "submit");
    };

    // { once: true } : l'ecouteur se retire seul apres le premier scan.
    // / { once: true }: the listener removes itself after the first scan.
    document.body.addEventListener("nfcResult", ecouteurDeCarte, {once: true});
    rfid.startLecture();
}


/* ------------------------------------------------------------------------- */
/* Modales                                                                    */
/* ------------------------------------------------------------------------- */

/**
 * Ouvre un <dialog> et met le focus sur son premier bouton.
 * / Opens a <dialog> and focuses its first button.
 *
 * show() et non showModal() : la modale reste dans la pile z-index normale,
 * donc le simulateur de cartes DEMO de nfc.js reste cliquable au-dessus.
 * / show(), not showModal(): the DEMO card simulator stays clickable on top.
 *
 * @param {HTMLDialogElement} modale
 */
function ouvrirLaModale(modale) {
    if (!modale.open) {
        modale.show();
    }
    const premierBouton = modale.querySelector("button:not([hidden]):not(:disabled)");
    if (premierBouton) {
        premierBouton.focus();
    }
}

/**
 * Montre un seul etat de la modale admin (intro, detection ou erreur).
 * En detection, la lecture NFC demarre sur le formulaire de l'etat.
 * / Shows one admin modal state. In detection, the NFC read starts.
 *
 * @param {string} nomDeLEtat - "intro", "detection" ou "erreur"
 */
function afficherLEtatDeLaModaleAdmin(nomDeLEtat) {
    const contenu = document.getElementById("modale-admin-contenu");
    if (!contenu) {
        return;
    }
    const tousLesEtats = contenu.querySelectorAll("[data-admin-etat]");
    tousLesEtats.forEach(function (etat) {
        etat.hidden = (etat.dataset.adminEtat !== nomDeLEtat);
    });

    if (nomDeLEtat === "detection") {
        const formulaireDeDetection = contenu.querySelector('[data-admin-etat="detection"] form[data-nfc-lecture]');
        lancerLaLectureNfcPour(formulaireDeDetection);
    }
}

/**
 * Appelee quand un <dialog> se ferme. Si c'est la modale admin, on arrete sa
 * lecture et on relance celle de l'ecran (etape 1).
 * / Called when a <dialog> closes. For the admin modal, stop its read and
 * restart the screen's read (step 1).
 */
function quandUneModaleSeFerme(evenement) {
    const modaleFermee = evenement.target;
    if (modaleFermee.id !== "modale-admin") {
        return;
    }
    arreterLaLectureNfc();
    lancerLaLectureAutomatiqueDeLEcran();
}


/* ------------------------------------------------------------------------- */
/* Saisie du montant (etape 3)                                                */
/* ------------------------------------------------------------------------- */

/**
 * Convertit la saisie (« 12,5 ») en centimes (1250). Sert seulement a savoir
 * si Valider doit etre actif : le serveur revalide le montant.
 * / Converts the input into cents. Only used to enable Validate.
 *
 * @param {string} saisie
 * @returns {number}
 */
function saisieEnCentimes(saisie) {
    if (!saisie) {
        return 0;
    }
    const morceaux = saisie.split(",");
    const euros = parseInt(morceaux[0] || "0", 10) || 0;
    let centimes = 0;
    if (morceaux[1]) {
        let decimales = morceaux[1];
        if (decimales.length === 1) {
            decimales = decimales + "0";
        }
        centimes = parseInt(decimales.substring(0, 2), 10) || 0;
    }
    return (euros * 100) + centimes;
}

/**
 * Ecrit la saisie partout : afficheur, bouton Valider, champ cache envoye au
 * serveur (avec un point decimal : « 12.50 »).
 * / Writes the input everywhere: readout, Validate button, hidden field.
 *
 * Regle de la maquette : ce qui est tape s'affiche tel quel, sans « ,00 » force.
 *
 * @param {HTMLFormElement} formulaire - form[data-saisie-montant]
 * @param {string} saisie - par exemple « 12,5 »
 */
function ecrireLaSaisie(formulaire, saisie) {
    formulaire.dataset.saisie = saisie;

    const texteAffiche = (saisie === "") ? "0 €" : saisie + " €";

    const afficheur = formulaire.querySelector("[data-amount]");
    afficheur.textContent = texteAffiche;
    afficheur.classList.toggle("is-empty", saisie === "");

    const montantDuBouton = formulaire.querySelector("[data-validate-amount]");
    montantDuBouton.textContent = texteAffiche;

    const centimes = saisieEnCentimes(saisie);
    const champMontant = formulaire.querySelector("[data-montant-champ]");
    const euros = Math.floor(centimes / 100);
    const resteEnCentimes = centimes % 100;
    champMontant.value = euros + "." + (resteEnCentimes < 10 ? "0" : "") + resteEnCentimes;

    const boutonValider = formulaire.querySelector("[data-validate]");
    boutonValider.disabled = (centimes === 0);
}

/**
 * Retire la selection des montants rapides.
 * / Clears the quick-amount selection.
 */
function deselectionnerLesMontantsRapides(formulaire) {
    formulaire.querySelectorAll("[data-quick]").forEach(function (bouton) {
        bouton.setAttribute("aria-pressed", "false");
    });
}

/**
 * Un montant rapide REMPLACE la saisie, et se marque comme choisi.
 * / A quick amount REPLACES the input and marks itself selected.
 */
function choisirUnMontantRapide(formulaire, bouton) {
    deselectionnerLesMontantsRapides(formulaire);
    bouton.setAttribute("aria-pressed", "true");
    // La prochaine touche du pave repartira de zero.
    // / The next keypad press starts from scratch.
    formulaire.dataset.depuisRapide = "oui";
    ecrireLaSaisie(formulaire, bouton.dataset.quick);
}

/**
 * Touche du pave : chiffre, virgule ou retour arriere.
 * Bornes : 5 chiffres avant la virgule, 2 apres.
 * / Keypad key: digit, comma or backspace. 5 digits before, 2 after.
 */
function appuyerSurUneTouche(formulaire, touche) {
    deselectionnerLesMontantsRapides(formulaire);

    let saisie = formulaire.dataset.saisie || "";
    if (formulaire.dataset.depuisRapide === "oui") {
        saisie = "";
        formulaire.dataset.depuisRapide = "non";
    }

    if (touche === "back") {
        ecrireLaSaisie(formulaire, saisie.slice(0, -1));
        return;
    }

    if (touche === ",") {
        const virguleDejaTapee = saisie.indexOf(",") !== -1;
        if (virguleDejaTapee) {
            return;
        }
        ecrireLaSaisie(formulaire, (saisie === "" ? "0" : saisie) + ",");
        return;
    }

    // Un chiffre. « 0 » seul est remplace par le chiffre suivant.
    // / A digit. A lone "0" is replaced by the next digit.
    if (saisie === "0") {
        saisie = "";
    }
    const aDesDecimales = saisie.indexOf(",") !== -1;
    if (aDesDecimales) {
        const decimales = saisie.split(",")[1] || "";
        if (decimales.length >= 2) {
            return;
        }
    } else if (saisie.length >= 5) {
        return;
    }
    ecrireLaSaisie(formulaire, saisie + touche);
}


/* ------------------------------------------------------------------------- */
/* Clics (delegation sur le document)                                         */
/* ------------------------------------------------------------------------- */

/**
 * Un seul ecouteur de clic pour toute la borne : les ecrans arrivent par
 * HTMX, les boutons n'existent pas encore au chargement.
 * / One click listener for the whole kiosk: screens arrive through HTMX.
 */
function quandOnTouche(evenement) {
    const cible = evenement.target;

    const boutonBloc = cible.closest("[data-afficher-bloc]");
    if (boutonBloc) {
        const etape = boutonBloc.closest("[data-etape]");
        const nomDuBloc = boutonBloc.dataset.afficherBloc;
        etape.querySelectorAll("[data-bloc]").forEach(function (bloc) {
            bloc.hidden = (bloc.dataset.bloc !== nomDuBloc);
        });
        return;
    }

    const boutonOuvrir = cible.closest("[data-modal-open]");
    if (boutonOuvrir) {
        const modale = document.getElementById(boutonOuvrir.dataset.modalOpen);
        if (modale.id === "modale-admin") {
            // La lecture de l'etape 1 s'arrete : la carte posee irait sinon
            // au mauvais formulaire. / Stop step 1's read.
            arreterLaLectureNfc();
            afficherLEtatDeLaModaleAdmin("intro");
        }
        ouvrirLaModale(modale);
        return;
    }

    const boutonFermer = cible.closest("[data-modal-close]");
    if (boutonFermer) {
        boutonFermer.closest("dialog").close();
        return;
    }

    const boutonEtatAdmin = cible.closest("[data-afficher-etat-admin]");
    if (boutonEtatAdmin) {
        afficherLEtatDeLaModaleAdmin(boutonEtatAdmin.dataset.afficherEtatAdmin);
        return;
    }

    const formulaireMontant = cible.closest("form[data-saisie-montant]");
    if (!formulaireMontant) {
        return;
    }

    const boutonRapide = cible.closest("[data-quick]");
    if (boutonRapide) {
        choisirUnMontantRapide(formulaireMontant, boutonRapide);
        return;
    }

    const touche = cible.closest("[data-key]");
    if (touche) {
        appuyerSurUneTouche(formulaireMontant, touche.dataset.key);
        return;
    }

    const boutonEffacer = cible.closest("[data-clear]");
    if (boutonEffacer) {
        deselectionnerLesMontantsRapides(formulaireMontant);
        formulaireMontant.dataset.depuisRapide = "non";
        ecrireLaSaisie(formulaireMontant, "");
    }
}


/* ------------------------------------------------------------------------- */
/* Preparation de chaque ecran                                                */
/* ------------------------------------------------------------------------- */

/**
 * Lance la lecture NFC si l'ecran affiche en attend une (etape 1), sauf si la
 * modale admin est ouverte (elle a sa propre lecture).
 * / Starts the NFC read if the screen expects one, unless the admin modal
 * is open.
 */
function lancerLaLectureAutomatiqueDeLEcran() {
    const modaleAdmin = document.getElementById("modale-admin");
    if (modaleAdmin && modaleAdmin.open) {
        return;
    }

    const formulaireAuto = document.querySelector('#tb-kiosque form[data-nfc-lecture="auto"]');
    if (formulaireAuto) {
        if (formulaireEnAttenteDeCarte !== formulaireAuto) {
            lancerLaLectureNfcPour(formulaireAuto);
        }
        return;
    }

    // L'ecran n'attend plus de carte : on libere le lecteur.
    // / The screen no longer expects a card: release the reader.
    arreterLaLectureNfc();
}

/**
 * Remet l'ecran dans un etat coherent, au chargement et apres chaque swap.
 * / Brings the screen to a coherent state, on load and after every swap.
 */
function preparerLEcran() {
    // L'etape affichee est posee sur <body> : le CSS masque « Recommencer »
    // a l'etape 1. / The shown step goes on <body>.
    const etapeAffichee = document.querySelector("#tb-kiosque [data-etape]");
    if (etapeAffichee) {
        document.body.dataset.etape = etapeAffichee.dataset.etape;
    }

    // Les modales rendues ouvertes par le serveur (carte non enregistree).
    // / Modals the server wants open (unregistered card).
    document.querySelectorAll("dialog[data-ouvrir-au-chargement]").forEach(function (modale) {
        modale.removeAttribute("data-ouvrir-au-chargement");
        ouvrirLaModale(modale);
    });

    // Le formulaire du montant repart d'une saisie vide.
    // / The amount form starts empty.
    document.querySelectorAll("form[data-saisie-montant]:not([data-saisie])").forEach(function (formulaire) {
        ecrireLaSaisie(formulaire, "");
    });

    lancerLaLectureAutomatiqueDeLEcran();
}

// htmx.onLoad est appele au chargement ET pour chaque contenu insere, y compris
// les swaps OOB du websocket. Il peut tirer plusieurs fois pour un meme swap :
// on regroupe les appels en un seul.
// / htmx.onLoad fires on load AND for every inserted content, OOB swaps
// included. It may fire several times per swap: calls are batched.
let preparationPrevue = false;
htmx.onLoad(function () {
    if (preparationPrevue) {
        return;
    }
    preparationPrevue = true;
    setTimeout(function () {
        preparationPrevue = false;
        preparerLEcran();
    }, 0);
});

document.addEventListener("click", quandOnTouche);

// L'evenement 'close' d'un <dialog> ne remonte pas : on l'ecoute en capture.
// / A <dialog>'s 'close' event does not bubble: listen in capture phase.
document.addEventListener("close", quandUneModaleSeFerme, true);
