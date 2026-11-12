"""
Anonymise une copie de base de production : Lespass, Fedow ou LaBoutik V1.
/ Anonymises a production database copy: Lespass, Fedow or LaBoutik V1.

LOCALISATION : seo/scripts_observatoire/anonymiser_dump.py
SPEC : TECH_DOC/SESSIONS/OBSERVATOIRE/CHANTIER-03-anonymisation-des-dumps.md

CE N'EST PAS UNE COMMANDE DJANGO
Ce script ne s'importe pas dans Django et `manage.py` ne le voit pas : il n'est pas dans
`management/commands/`, et son dossier n'a pas de `__init__.py`. Il n'utilise que la
bibliotheque standard de Python. On le lance avec n'importe quel `python3` (3.9 ou plus).
/ Not a Django command: standard library only, run with any python3 >= 3.9.

UTILISATION
    python3 seo/scripts_observatoire/anonymiser_dump.py lespass.sql.gz fedow.sqlite3 laboutik.sql.gz

On passe les trois bases DANS LA MEME COMMANDE : le faux e-mail d'une personne est alors
le meme dans les trois. C'est indispensable, car Fedow retrouve un utilisateur Lespass
par son e-mail exact.
/ Pass all databases in ONE command so a person gets the same fake e-mail everywhere.

CE QUE LE SCRIPT FAIT
- Il ne charge JAMAIS la production dans un serveur de base de donnees.
- Il lit le fichier d'entree, sans jamais le modifier, et ecrit un nouveau fichier a cote :
    lespass.sql.gz  -> lespass.anonyme.sql.gz
    fedow.sqlite3   -> fedow.anonyme.sqlite3
- Il remplace les e-mails PARTOUT (toutes les valeurs texte de toutes les tables).
- Il remplace les cles, mots de passe, cles RSA, noms, prenoms, pseudos et telephones
  dans une liste de colonnes ecrite plus bas (REGLES_POSTGRES, REGLES_SQLITE).
- Il vide quelques tables (sessions, jetons, journal de l'admin).
- Il relit sa sortie pour verifier qu'il ne reste aucun vrai e-mail.
- Il affiche un rapport : des NOMBRES et des noms de colonnes, JAMAIS une valeur.
/ Never loads production into a database server. Writes a new file next to the input.

FORMATS ACCEPTES
- Dump PostgreSQL en texte (pg_dump ou pg_dumpall), compresse en .gz ou non.
- Base SQLite (Fedow), compressee en .gz ou non.
Le format est reconnu par les premiers octets du fichier, pas par son extension.
Un dump au format custom (pg_dump -Fc) est refuse : il faut d'abord le convertir en texte.
/ Format detected from the first bytes, not the extension. Custom-format dumps are refused.

CODES DE SORTIE
    0 : tout est anonymise, controle OK
    1 : sortie ecrite, mais le controle final a trouve de vrais e-mails
    2 : entree refusee, rien n'est ecrit
    3 : erreur pendant le traitement (seul le type de l'erreur est affiche)
"""

import argparse
import gzip
import hashlib
import hmac
import os
import re
import secrets
import shutil
import signal
import sqlite3
import sys
from collections import Counter


# ---------------------------------------------------------------------------
# LES E-MAILS
# / E-MAILS
# ---------------------------------------------------------------------------

# Le domaine des faux e-mails. « .invalid » est reserve (RFC 2606) : aucun mail ne peut
# partir vers lui.
# / Fake e-mail domain. ".invalid" is reserved: no mail can be sent there.
DOMAINE_DES_FAUX_EMAILS = "anonyme.invalid"

# L'expression qui trouve un e-mail dans un texte.
# - \w est Unicode en Python : « rené@exemple.fr » est trouve.
# - (?<!\\) : dans le texte d'un COPY, un retour a la ligne s'ecrit « \n ». Sans cette
#   regle, « ...\nalice@x.fr » donnerait l'adresse « nalice@x.fr », donc un autre faux
#   e-mail que dans Fedow. Avec elle, la correspondance ne peut pas commencer juste apres
#   une barre oblique inverse : elle commence a « alice ».
# - L'etoile est acceptee avant l'arobase : une adresse masquee comme « j***@gmail.com »
#   ou « ****@exemple.fr » est remplacee aussi. Le controle final la trouve sinon.
# / Finds an e-mail. The lookbehind skips the letter of a "\n" or "\t" escape.
# / The star is accepted before the @, so masked addresses are replaced too.
EXPRESSION_EMAIL = re.compile(r"(?<!\\)[\w.%+*-]+@[\w.-]+\.\w{2,}")

# L'expression du CONTROLE FINAL. Elle est volontairement plus large que celle du
# remplacement : sinon le controle ne prouverait que l'accord du script avec lui-meme.
# Elle attrape aussi l'arobase encodee dans une URL (%40).
# / Final check pattern: deliberately WIDER than the replacement one (also catches %40).
# La fin du domaine doit etre faite de lettres : « django@4.2 » n'est pas un e-mail.
# / The top-level domain must be letters: "django@4.2" is not an e-mail.
EXPRESSION_DE_CONTROLE = re.compile(
    r"[^\s@\\\"'`<>()\[\]{},;:/=&?]+(?:@|%40)[^\s@\\\"'`<>()\[\]{},;:/=&?%]+\.[^\W\d_]{2,}"
)

# Un texte comme « logo@2x.png » ressemble a un e-mail, mais c'est le nom d'une image
# « retina ». On ne le remplace pas, et le controle final ne le compte pas.
# L'exception est etroite : seulement « @<chiffres>x.<extension> ». Un nom de fichier
# comme « avatar_alice@gmail.com.png » contient un vrai e-mail : il est remplace.
# / "logo@2x.png" is a retina image name, left alone. Only "@<digits>x.<ext>" is skipped.
EXPRESSION_SUFFIXE_IMAGE_RETINA = re.compile(
    r"^\d+(?:\.\d+)?x\.(?:png|jpe?g|gif|svg|webp)$", re.IGNORECASE
)


def est_un_nom_d_image_retina(adresse_trouvee):
    # Vrai pour « logo@2x.png » ou « icone@1.5x.webp », faux pour un vrai e-mail.
    # / True for "logo@2x.png", false for a real e-mail.
    partie_apres_l_arobase = adresse_trouvee.rsplit("@", 1)[-1]
    return EXPRESSION_SUFFIXE_IMAGE_RETINA.match(partie_apres_l_arobase) is not None


# ---------------------------------------------------------------------------
# LES MODES DE REMPLACEMENT
# Chaque colonne d'une regle recoit un de ces modes. Une valeur NULL reste NULL.
# / Replacement modes. A NULL value always stays NULL.
# ---------------------------------------------------------------------------

# vide              : texte vide. Une cle en clair ou chiffree : « pas de cle configuree ».
# null              : NULL. Une colonne qui accepte NULL (un PIN entier, par exemple).
# hash_inutilisable : « !anonyme ». Le hash d'une cle API : plus aucune cle ne correspond.
# mot_de_passe      : « !anonyme ». Pour Django, un mot de passe qui commence par « ! »
#                     est inutilisable.
# jeton_unique      : « anonyme- » + 16 caracteres aleatoires. Un jeton dans une colonne
#                     unique (le mode « vide » y creerait des doublons).
# nom               : « Anonyme- » + 8 caracteres tires du HMAC de la valeur. Le meme nom
#                     donne le meme pseudonyme. Une valeur vide reste vide. Deux noms
#                     differents peuvent, rarement, donner le meme pseudonyme (32 bits) :
#                     ne pas l'utiliser sur une colonne unique.
# identifiant       : pour un « username » ou l'« email » d'un compte. Si c'est un e-mail
#                     seul, il prend le meme faux e-mail que partout. Sinon (nom de connexion
#                     humain, adresse mal formee comme « jean@gmail » ou « jean=x@gmail.com »),
#                     la valeur entiere devient « Anonyme- » + 16 caracteres tires du HMAC
#                     (colonne unique, meme valeur dans Fedow pour le meme texte).
# / Modes: empty text, NULL, unusable hash, unusable password, unique token, pseudonym,
#   login (e-mail replaced, or 16-char pseudonym).
MODES_CONNUS = (
    "vide",
    "null",
    "hash_inutilisable",
    "mot_de_passe",
    "jeton_unique",
    "nom",
    "identifiant",
)

VALEUR_HASH_OU_MOT_DE_PASSE_INUTILISABLE = "!anonyme"

# Le pseudonyme que le mode « identifiant » ecrit. Une relance le reconnait et le garde.
# / The pseudonym written by the "identifiant" mode; a new run keeps it.
EXPRESSION_PSEUDONYME_D_IDENTIFIANT = re.compile(r"Anonyme-[0-9a-f]{16}")


# ---------------------------------------------------------------------------
# LES REGLES POUR POSTGRESQL (Lespass et LaBoutik V1)
# Une regle s'applique a une table QUEL QUE SOIT SON SCHEMA : les tables des lieux de
# Lespass existent dans chaque schema. Une regle dont la colonne n'existe pas dans le
# dump est ignoree (un vieux dump n'a pas les colonnes recentes).
# / PostgreSQL rules (Lespass + LaBoutik V1), applied whatever the schema.
# ---------------------------------------------------------------------------

REGLES_POSTGRES = {
    # --- Lespass, schema public ---
    "AuthBillet_tibilletuser": {
        "password": "mot_de_passe",
        "email": "identifiant",
        "username": "identifiant",
        "first_name": "nom",
        "last_name": "nom",
        "phone": "vide",
    },
    "AuthBillet_rsakey": {
        "private_pem": "vide",
        "public_pem": "vide",
    },
    "AuthBillet_wallet": {
        "public_pem": "vide",
    },
    "root_billet_rootconfiguration": {
        "stripe_api_key": "vide",
        "stripe_test_api_key": "vide",
        "fedow_create_place_apikey": "vide",
        "fedow_primary_pub_pem": "vide",
    },
    "onboard_onboardinvitation": {
        # Colonne unique : un lien d'invitation valide sur la prod.
        # / Unique column: a valid invitation link on production.
        "code": "jeton_unique",
    },
    "discovery_pairingdevice": {
        # Un PIN non reclame cree une cle LaBoutikAPIKey sur la prod.
        # / An unclaimed PIN mints an API key on production.
        "pin_code": "null",
    },
    "MetaBillet_waitingconfiguration": {
        "first_name": "nom",
        "last_name": "nom",
        "phone": "vide",
        # Hash d'un code a 6 chiffres : on le retrouve en essayant le million de codes.
        # / Hash of a 6-digit code: brute-forceable.
        "otp_hash": "vide",
    },
    # --- Lespass, schemas des lieux ---
    "BaseBillet_configuration": {
        "key_cashless": "vide",
        "key_fedow": "vide",
        "stripe_api_key": "vide",
        "stripe_test_api_key": "vide",
        "laboutik_public_pem": "vide",
        "phone": "vide",
        # Colonne retiree du modele (migration 0062), encore presente dans de vieux schemas.
        # / Column removed from the model (migration 0062), still present in old schemas.
        "mollie_api_key": "vide",
    },
    "BaseBillet_ghostconfig": {"ghost_key": "vide"},
    "BaseBillet_formbricksconfig": {"api_key": "vide"},
    "BaseBillet_brevoconfig": {"api_key": "vide"},
    "BaseBillet_webhook": {
        # Une URL de webhook porte souvent un jeton secret.
        # / A webhook URL often carries a secret token.
        "url": "vide",
    },
    "fedow_connect_fedowconfig": {"fedow_place_admin_apikey": "vide"},
    "laboutik_laboutikconfiguration": {
        "sunmi_app_id": "vide",
        "sunmi_app_key": "vide",
        "hmac_key": "vide",
    },
    "laboutik_tpebancaire": {"registration_code": "vide"},
    "BaseBillet_scannerapikey": {"hashed_key": "hash_inutilisable"},
    "BaseBillet_laboutikapikey": {"hashed_key": "hash_inutilisable"},
    "controlvanne_tireuseapikey": {"hashed_key": "hash_inutilisable"},
    "rest_framework_api_key_apikey": {"hashed_key": "hash_inutilisable"},
    "BaseBillet_membership": {
        "first_name": "nom",
        "last_name": "nom",
        "pseudo": "nom",
        "phone": "vide",
    },
    "BaseBillet_commande": {"first_name": "nom", "last_name": "nom"},
    "BaseBillet_ticket": {"first_name": "nom", "last_name": "nom"},
    "booking_booking": {"first_name": "nom", "last_name": "nom"},
    "crowds_contribution": {"contributor_name": "nom"},
    "crowds_globalfunding": {"contributor_name": "nom"},
    # --- LaBoutik V1 ---
    "tibiauth_tibiuser": {
        "password": "mot_de_passe",
        "email": "identifiant",
        "username": "identifiant",
        "first_name": "nom",
        "last_name": "nom",
        "public_pem": "vide",
    },
    "APIcashless_configuration": {
        "odoo_api_key": "vide",
        "dokos_key": "vide",
        # Identifiant de connexion a Odoo, souvent un e-mail.
        # / Odoo login, often an e-mail.
        "odoo_login": "vide",
        "lespass_api_key": "vide",
        "fedow_place_admin_apikey": "vide",
        # Base64 qui contient une cle temporaire Fedow.
        # / Base64 holding a temporary Fedow key.
        "string_connect": "vide",
        # Lien Stripe qui porte un jeton.
        # / Stripe link carrying a token.
        "onboard_url": "vide",
        "stripe_api_key": "vide",
        "sunmi_app_id": "vide",
        "sunmi_app_key": "vide",
        "discovery_key": "vide",
        # NOT NULL : le code regenere la paire quand elle est vide.
        # / NOT NULL: the code regenerates the pair when empty.
        "private_pem": "vide",
        "public_pem": "vide",
        "telephone": "vide",
    },
    "APIcashless_configurationstripe": {"stripe_api_key": "vide"},
    "APIcashless_terminal": {"registration_code": "vide"},
    "APIcashless_appareil": {"pin_code": "null"},
    "APIcashless_membre": {
        "email": "identifiant",
        "name": "nom",
        "prenom": "nom",
        "pseudo": "nom",
        "tel": "vide",
    },
    "epsonprinter_printer": {"api_serveur_impression": "vide"},
}

# Les tables dont toutes les lignes sont retirees. La structure de la table reste.
# / Tables whose rows are all removed. The table itself stays.
TABLES_A_VIDER_POSTGRES = {
    "django_session",
    "authtoken_token",
    "token_blacklist_outstandingtoken",
    "token_blacklist_blacklistedtoken",
    # La colonne « token » est un entier NOT NULL : on ne peut pas la mettre a NULL.
    # / "token" is a NOT NULL integer: it cannot be set to NULL.
    "AuthBillet_terminalpairingtoken",
    "django_admin_log",
}


# ---------------------------------------------------------------------------
# LES REGLES POUR SQLITE (Fedow, la seule des trois bases en SQLite)
# / SQLite rules (Fedow)
# ---------------------------------------------------------------------------

REGLES_SQLITE = {
    "fedow_core_fedowuser": {
        "password": "mot_de_passe",
        "email": "identifiant",
        "username": "identifiant",
        "first_name": "nom",
        "last_name": "nom",
    },
    "fedow_core_configuration": {
        # Si la colonne est NULL, le code de Fedow relit la cle dans l'environnement.
        # / When NULL, Fedow reads the key from the environment.
        "stripe_api_key": "null",
        "stripe_endpoint_secret_enc": "null",
    },
    "fedow_core_place": {
        "cashless_admin_apikey": "vide",
        "cashless_rsa_pub_key": "vide",
    },
    "fedow_core_wallet": {
        "private_pem": "vide",
        "public_pem": "vide",
    },
    "fedow_core_createplaceapikey": {"hashed_key": "hash_inutilisable"},
    "fedow_core_organizationapikey": {"hashed_key": "hash_inutilisable"},
    "rest_framework_api_key_apikey": {"hashed_key": "hash_inutilisable"},
}

TABLES_A_VIDER_SQLITE = {
    "django_session",
    "django_admin_log",
}

# Les colonnes ou l'on ne remplace PAS les e-mails.
# INDISPENSABLE : comment et metadata entrent dans le hash chaine des transactions de
# Fedow (dict_for_hash, Fedow/fedow_core/models.py). Les changer casse verify_hash(), et
# chaque nouvelle transaction verifie la precedente : plus aucune ecriture sur l'asset.
# Les e-mails qu'elles contiennent sont comptes dans le rapport, jamais affiches.
# / Columns left untouched: they feed Fedow's chained transaction hash.
COLONNES_PROTEGEES_SQLITE = {
    ("fedow_core_transaction", "comment"),
    ("fedow_core_transaction", "metadata"),
}


# ---------------------------------------------------------------------------
# LES COLONNES SUSPECTES
# Une colonne dont le nom contient un de ces mots, et qui n'a pas de regle, est NOMMEE
# dans le rapport. Le script NE LA TOUCHE PAS : une recherche par le nom toucherait des
# colonnes qui ne sont pas des secrets (la table fedow_core_token contient les soldes).
# C'est ce qui tient les regles a jour quand un modele gagne un champ.
# / Columns whose name looks secret but have no rule are listed, never modified.
# ---------------------------------------------------------------------------

MOTS_SUSPECTS = {
    "key",
    "secret",
    "token",
    "password",
    "pem",
    "pin",
    "api",
    "apikey",
    "otp",
}

# Les colonnes vues et laissees expres : ce ne sont pas des secrets.
# / Columns reviewed and deliberately left alone.
COLONNES_VUES_ET_LAISSEES = {
    # Cles etrangeres vers une cle API (la cle elle-meme est un hash rendu inutilisable).
    # / Foreign keys to an API key row.
    ("APIcashless_configuration", "key_id"),
    ("APIcashless_configuration", "key_billetterie_id"),
    ("APIcashless_configuration", "self_fed_apikey_id"),
    ("BaseBillet_externalapikey", "key_id"),
    ("BaseBillet_scanapp", "key_id"),
    # Cles etrangeres vers une cle RSA (la cle elle-meme est videe).
    # / Foreign keys to an RSA key row (the key itself is emptied).
    ("AuthBillet_tibilletuser", "rsa_key_id"),
    ("BaseBillet_event", "rsa_key_id"),
    # Adresse du serveur Formbricks, pas un secret.
    # / Formbricks server address, not a secret.
    ("BaseBillet_formbricksconfig", "api_host"),
    # Cle d'idempotence d'une vente : un identifiant, pas un secret.
    # / Sale idempotency key: an identifier, not a secret.
    ("BaseBillet_lignearticle", "idempotency_key"),
    ("BaseBillet_vente", "idempotency_key"),
    # Compteurs et dates de l'OTP d'inscription (le hash, lui, est vide).
    # / Onboarding OTP counters and dates (the hash itself is emptied).
    ("MetaBillet_waitingconfiguration", "otp_attempts"),
    ("MetaBillet_waitingconfiguration", "otp_expires_at"),
    ("MetaBillet_waitingconfiguration", "otp_resend_count"),
    ("MetaBillet_waitingconfiguration", "otp_sent_at"),
    ("fedow_core_configuration", "create_place_apikey_id"),
    # Cases a cocher « revoquer la cle » de LaBoutik : des booleens.
    # / LaBoutik "revoke the key" checkboxes: booleans.
    ("APIcashless_configuration", "revoquer_key_billetterie"),
    ("APIcashless_configuration", "revoquer_odoo_api_key"),
    ("epsonprinter_printer", "revoquer_api_serveur_impression"),
    # Le numero d'un jeton Fedow (solde d'un wallet), pas un secret.
    # / A Fedow token row (a wallet balance), not a secret.
    ("fedow_core_transaction", "token_id"),
}


# ---------------------------------------------------------------------------
# LE RAPPORT D'UN FICHIER
# / One file's report
# ---------------------------------------------------------------------------


class RapportDUnFichier:
    """
    Les compteurs d'un fichier traite. Que des nombres et des noms de colonnes.
    / Counters of one processed file. Numbers and column names only.
    """

    def __init__(self, chemin_entree, chemin_sortie):
        self.chemin_entree = chemin_entree
        self.chemin_sortie = chemin_sortie
        # Cle : « table.colonne ». Valeur : nombre.
        # / Key: "table.column". Value: count.
        self.emails_remplaces_par_colonne = Counter()
        self.valeurs_remplacees_par_colonne = Counter()
        self.valeurs_trop_longues_par_colonne = Counter()
        self.emails_laisses_dans_colonnes_protegees = Counter()
        self.lignes_retirees_par_table = Counter()
        self.colonnes_suspectes_non_traitees = set()
        self.clauses_password_retirees = 0
        self.emails_reels_restants_par_table = Counter()
        self.controle_fait = False


# ---------------------------------------------------------------------------
# L'ANONYMISEUR : le sel et les remplacements
# / The anonymiser: the salt and the replacements
# ---------------------------------------------------------------------------


class Anonymiseur:
    """
    Porte le sel secret et fabrique les valeurs de remplacement.
    / Holds the secret salt and builds replacement values.

    Un seul Anonymiseur sert a tous les fichiers d'un lancement : c'est ce qui donne le
    meme faux e-mail a une personne dans Lespass, Fedow et LaBoutik.
    / One instance for all files of a run: same fake e-mail everywhere.

    Le sel est tire au hasard, garde en memoire, jamais affiche ni ecrit. Sans lui, on ne
    peut pas retrouver une adresse en essayant des adresses connues.
    / Random salt, kept in memory only, never printed or written.
    """

    def __init__(self, sel=None):
        if sel is None:
            sel = secrets.token_bytes(32)
        self.sel = sel

    def _empreinte_hexadecimale(self, prefixe, texte):
        # HMAC-SHA256 du texte avec le sel. Le prefixe separe les usages (un nom et un
        # e-mail identiques ne donnent pas la meme empreinte).
        # / HMAC-SHA256 of the text; the prefix separates uses.
        message = f"{prefixe}:{texte}".encode("utf-8")
        return hmac.new(self.sel, message, hashlib.sha256).hexdigest()

    def faux_email(self, adresse_trouvee):
        """
        Le faux e-mail d'une adresse : 16 caracteres hexadecimaux @anonyme.invalid.
        Le HMAC porte sur le texte EXACT, sans passer en minuscules : deux adresses
        differentes donnent toujours deux faux e-mails differents, donc une colonne
        unique ne recoit jamais de doublon. Les trois systemes enregistrent deja les
        e-mails en minuscules : le texte exact suffit a garder les jointures.
        / Fake e-mail from the EXACT text (no lowercasing): never a duplicate.
        """
        empreinte = self._empreinte_hexadecimale("email", adresse_trouvee)
        return f"{empreinte[:16]}@{DOMAINE_DES_FAUX_EMAILS}"

    def pseudonyme(self, valeur, nombre_de_caracteres=8):
        """
        Le pseudonyme d'un nom, d'un prenom ou d'un pseudo : « Anonyme-xxxxxxxx ».
        / Pseudonym of a name: "Anonyme-xxxxxxxx".
        """
        empreinte = self._empreinte_hexadecimale("nom", valeur)
        return f"Anonyme-{empreinte[:nombre_de_caracteres]}"

    def valeur_pour_colonne_trop_courte(self, valeur_d_origine, longueur_maximale):
        """
        Une valeur qui tient dans une colonne trop courte pour le faux e-mail : l'empreinte
        de la valeur d'origine, coupee a la longueur de la colonne.
        Deux valeurs differentes donnent deux resultats differents : une colonne unique
        (ex. BaseBillet_externalapikey.name, varchar(30)) ne recoit pas de doublon.
        / Fits a short column: the original value's hash cut to the column length, distinct.
        """
        empreinte = self._empreinte_hexadecimale("trop-long", valeur_d_origine)
        return empreinte[:longueur_maximale]

    def remplacer_les_emails(self, texte):
        """
        Remplace chaque e-mail du texte par son faux e-mail.
        Renvoie le texte modifie et le nombre d'e-mails remplaces.
        / Replaces every e-mail in the text. Returns (text, count).
        """
        nombre_de_remplacements = 0
        morceaux_du_resultat = []
        position_courante = 0

        for correspondance in EXPRESSION_EMAIL.finditer(texte):
            adresse_trouvee = correspondance.group(0)

            # Un faux e-mail deja pose, ou un nom d'image : on n'y touche pas.
            # / An already-fake e-mail, or an image name: left alone.
            deja_anonyme = adresse_trouvee.endswith("@" + DOMAINE_DES_FAUX_EMAILS)
            if deja_anonyme or est_un_nom_d_image_retina(adresse_trouvee):
                continue

            morceaux_du_resultat.append(
                texte[position_courante : correspondance.start()]
            )
            morceaux_du_resultat.append(self.faux_email(adresse_trouvee))
            position_courante = correspondance.end()
            nombre_de_remplacements = nombre_de_remplacements + 1

        if nombre_de_remplacements == 0:
            return texte, 0

        morceaux_du_resultat.append(texte[position_courante:])
        return "".join(morceaux_du_resultat), nombre_de_remplacements

    def valeur_de_remplacement(self, mode, valeur):
        """
        La valeur a ecrire pour une colonne qui a une regle.
        La valeur recue n'est jamais None : un NULL est garde tel quel par l'appelant.
        Renvoie None pour ecrire NULL.
        / Value to write for a ruled column. Returns None to write NULL.
        """
        if mode == "vide":
            return ""
        if mode == "null":
            return None
        if mode == "hash_inutilisable" or mode == "mot_de_passe":
            return VALEUR_HASH_OU_MOT_DE_PASSE_INUTILISABLE
        if mode == "jeton_unique":
            return "anonyme-" + secrets.token_hex(8)
        if mode == "nom":
            if valeur == "":
                return ""
            return self.pseudonyme(valeur)
        if mode == "identifiant":
            if valeur == "":
                return ""
            valeur_sans_espaces = valeur.strip()

            # Deja anonymisee (relance du script) : on la garde telle quelle.
            # / Already anonymised (script run again): kept as is.
            deja_un_faux_email = valeur_sans_espaces.endswith("@" + DOMAINE_DES_FAUX_EMAILS)
            deja_un_pseudonyme = EXPRESSION_PSEUDONYME_D_IDENTIFIANT.fullmatch(
                valeur_sans_espaces
            )
            if deja_un_faux_email or deja_un_pseudonyme:
                return valeur

            # Un e-mail seul (des espaces autour au plus) : le meme faux e-mail que partout.
            # / A lone e-mail (spaces around at most): the same fake e-mail as everywhere.
            if EXPRESSION_EMAIL.fullmatch(valeur_sans_espaces):
                valeur_sans_email, _nombre_d_emails = self.remplacer_les_emails(valeur)
                return valeur_sans_email

            # Tout le reste devient un pseudonyme, valeur ENTIERE : « jonas », « jean@gmail »,
            # « jean=x@gmail.com ». Dans ce dernier cas, l'expression ne verrait que
            # « x@gmail.com » et « jean= » resterait en clair.
            # / Anything else: the WHOLE value becomes a pseudonym (no clear-text leftover).
            return self.pseudonyme(valeur, nombre_de_caracteres=16)
        raise ValueError(f"Mode inconnu : {mode}")


# ---------------------------------------------------------------------------
# LES PETITS OUTILS COMMUNS
# / Shared helpers
# ---------------------------------------------------------------------------


class EntreeRefusee(Exception):
    """
    L'entree ne peut pas etre traitee. Le message dit pourquoi. Rien n'est ecrit.
    / The input cannot be processed. Nothing is written.
    """


def colonne_est_suspecte(nom_de_table, nom_de_colonne, regles_de_la_table):
    """
    Vrai si le nom de la colonne ressemble a un secret et qu'elle n'a pas de regle.
    On coupe le nom sur « _ » : « stripe_api_key » donne « stripe », « api », « key ».
    / True if the column name looks secret and the column has no rule.
    """
    if nom_de_colonne in regles_de_la_table:
        return False
    if (nom_de_table, nom_de_colonne) in COLONNES_VUES_ET_LAISSEES:
        return False
    mots_du_nom = nom_de_colonne.lower().split("_")
    for mot in mots_du_nom:
        if mot in MOTS_SUSPECTS:
            return True
    return False


def compter_les_emails_reels(texte):
    """
    Compte, avec l'expression LARGE du controle, les e-mails qui ne sont ni faux ni des
    noms d'image.
    / Counts, with the WIDE check pattern, e-mails that are neither fake nor images.
    """
    nombre_d_emails_reels = 0
    for correspondance in EXPRESSION_DE_CONTROLE.finditer(texte):
        adresse_trouvee = correspondance.group(0)
        if adresse_trouvee.endswith("@" + DOMAINE_DES_FAUX_EMAILS):
            continue
        if est_un_nom_d_image_retina(adresse_trouvee):
            continue
        nombre_d_emails_reels = nombre_d_emails_reels + 1
    return nombre_d_emails_reels


def lire_les_premiers_octets(chemin):
    """
    Lit les premiers octets du fichier, decompresses s'il est en gzip.
    Renvoie (est_compresse, premiers_octets).
    / Reads the first bytes (decompressed if gzip). Returns (is_gzip, bytes).
    """
    with open(chemin, "rb") as fichier:
        debut_brut = fichier.read(2)

    est_compresse = debut_brut == b"\x1f\x8b"
    if est_compresse:
        with gzip.open(chemin, "rb") as fichier_compresse:
            return True, fichier_compresse.read(16)

    with open(chemin, "rb") as fichier:
        return False, fichier.read(16)


def chemin_de_sortie(chemin_entree, extension_de_sortie):
    """
    Le nom du fichier de sortie, a cote de l'entree.
    « lespass.sql.gz » -> « lespass.anonyme.sql.gz » ; « db.sqlite3 » -> « db.anonyme.sqlite3 ».
    / Output path next to the input.
    """
    dossier = os.path.dirname(os.path.abspath(chemin_entree))
    nom = os.path.basename(chemin_entree)

    extensions_a_retirer = (".gz", ".sql", ".sqlite3", ".sqlite", ".db")
    nom_raccourci = True
    while nom_raccourci:
        nom_raccourci = False
        for extension in extensions_a_retirer:
            if nom.endswith(extension) and len(nom) > len(extension):
                nom = nom[: -len(extension)]
                nom_raccourci = True

    return os.path.join(dossier, f"{nom}.anonyme{extension_de_sortie}")


# ---------------------------------------------------------------------------
# POSTGRESQL : lecture du dump texte, en flux
# / PostgreSQL: streaming the text dump
# ---------------------------------------------------------------------------

# Un nom SQL, entre guillemets ou non. Les guillemets doubles s'echappent en "".
# / A SQL identifier, quoted or not.
EXPRESSION_IDENTIFIANT_SQL = re.compile(r'"((?:[^"]|"")+)"|([^\s,."()]+)')

# « COPY public."APIcashless_membre" (id, name, "order") FROM stdin; »
# La liste des colonnes manque pour une table sans colonne.
# / The column list is missing for a table without columns.
EXPRESSION_LIGNE_COPY = re.compile(r"^COPY (.+?) (?:\((.*)\) )?FROM stdin;$")

# « CREATE TABLE public."APIcashless_membre" ( »
EXPRESSION_DEBUT_CREATE_TABLE = re.compile(r"^CREATE (?:UNLOGGED )?TABLE (.+?) \($")

# «     "name" character varying(50) NOT NULL, » (on ignore les tableaux « [] »)
# / A varchar column line inside CREATE TABLE (arrays are ignored).
EXPRESSION_COLONNE_A_LONGUEUR = re.compile(
    r'^\s+("(?:[^"]|"")+"|\S+) (?:character varying|varchar|character|char)\((\d+)\)(?!\[)'
)

# La clause « PASSWORD '...' » d'un CREATE ROLE ou d'un ALTER ROLE.
# / The PASSWORD clause of a role line.
EXPRESSION_CLAUSE_PASSWORD = re.compile(r" PASSWORD '(?:[^']|'')*'")

# Le suffixe du fichier de travail. Le nom dit clairement ce qu'il contient : tant que
# le traitement n'est pas fini, c'est encore une copie de la prod.
# / Work file suffix: until processing ends, it is still a production copy.
SUFFIXE_DU_FICHIER_DE_TRAVAIL = ".travail-PAS-ENCORE-ANONYME"

MARQUEUR_NULL_DE_COPY = "\\N"
MARQUEUR_FIN_DE_COPY = "\\."


def decouper_les_identifiants(texte):
    """
    Decoupe « public."APIcashless_membre" » en ["public", "APIcashless_membre"],
    ou « id, name, "order" » en ["id", "name", "order"]. Retire les guillemets.
    / Splits SQL identifiers and removes the quotes.
    """
    identifiants = []
    for correspondance in EXPRESSION_IDENTIFIANT_SQL.finditer(texte):
        nom_entre_guillemets = correspondance.group(1)
        if nom_entre_guillemets is not None:
            identifiants.append(nom_entre_guillemets.replace('""', '"'))
        else:
            identifiants.append(correspondance.group(2))
    return identifiants


def schema_et_table(nom_qualifie):
    """
    « public."APIcashless_membre" » -> ("public", "APIcashless_membre").
    Sans schema -> ("", "table").
    / Splits a qualified table name.
    """
    morceaux = decouper_les_identifiants(nom_qualifie)
    if len(morceaux) == 1:
        return "", morceaux[0]
    return morceaux[-2], morceaux[-1]


def anonymiser_une_ligne_de_copy(
    ligne, nom_de_table, noms_des_colonnes, longueurs_des_colonnes, anonymiseur, rapport
):
    """
    Anonymise une ligne de donnees d'un bloc COPY (format texte de PostgreSQL).
    / Anonymises one data row of a COPY block.

    Dans ce format, une tabulation ou un retour a la ligne A L'INTERIEUR d'une valeur est
    echappe (\\t, \\n). Couper sur les vraies tabulations est donc sur. NULL s'ecrit \\N.
    / Inside values, tabs and newlines are escaped: splitting on real tabs is safe.

    La longueur comparee a varchar(N) est celle du texte echappe, un peu plus longue que
    la valeur reelle quand elle contient des echappements : le test est prudent.
    / The escaped length is compared to varchar(N): a cautious test.
    """
    fin_de_ligne = ""
    if ligne.endswith("\n"):
        fin_de_ligne = "\n"
        ligne = ligne[:-1]

    valeurs = ligne.split("\t")
    regles_de_la_table = REGLES_POSTGRES.get(nom_de_table, {})

    for position, valeur in enumerate(valeurs):
        if valeur == MARQUEUR_NULL_DE_COPY:
            continue
        if position >= len(noms_des_colonnes):
            continue

        nom_de_colonne = noms_des_colonnes[position]
        cle_du_rapport = f"{nom_de_table}.{nom_de_colonne}"
        mode = regles_de_la_table.get(nom_de_colonne)

        if mode is not None:
            nouvelle_valeur = anonymiseur.valeur_de_remplacement(mode, valeur)
            if nouvelle_valeur is None:
                nouvelle_valeur = MARQUEUR_NULL_DE_COPY
            if nouvelle_valeur != valeur:
                rapport.valeurs_remplacees_par_colonne[cle_du_rapport] += 1
        elif "@" in valeur:
            nouvelle_valeur, nombre_d_emails = anonymiseur.remplacer_les_emails(valeur)
            if nombre_d_emails:
                rapport.emails_remplaces_par_colonne[cle_du_rapport] += nombre_d_emails
        else:
            continue

        # Valeur trop longue pour sa colonne : PostgreSQL refuserait la ligne, et TOUT le
        # COPY de la table serait annule au chargement. On met l'empreinte de la valeur
        # d'origine, coupee a N : rien ne fuit, le chargement passe, et deux valeurs
        # differentes restent differentes (colonnes uniques).
        # / Too long for varchar(N): write the original value's hash cut to N (distinct).
        longueur_maximale = longueurs_des_colonnes.get(nom_de_colonne)
        valeur_a_change = nouvelle_valeur != valeur
        if (
            valeur_a_change
            and longueur_maximale is not None
            and nouvelle_valeur != MARQUEUR_NULL_DE_COPY
            and len(nouvelle_valeur) > longueur_maximale
        ):
            nouvelle_valeur = anonymiseur.valeur_pour_colonne_trop_courte(
                valeur, longueur_maximale
            )
            rapport.valeurs_trop_longues_par_colonne[cle_du_rapport] += 1

        valeurs[position] = nouvelle_valeur

    return "\t".join(valeurs) + fin_de_ligne


def anonymiser_un_dump_postgres(
    chemin_entree, est_compresse, chemin_sortie_final, anonymiseur, rapport
):
    """
    Lit le dump texte ligne par ligne et ecrit le dump anonymise, compresse en gzip.
    La memoire reste constante, quelle que soit la taille du dump.
    / Streams the text dump line by line and writes the anonymised gzip dump.

    FLUX :
    1. Hors d'un bloc COPY :
       - CREATE TABLE : on retient la longueur des colonnes varchar(N) ;
       - CREATE ROLE / ALTER ROLE : on retire la clause PASSWORD ;
       - INSERT INTO : refus (seul le format COPY est gere) ;
       - COPY ... FROM stdin; : on entre dans le bloc.
       Dans un pg_dumpall, chaque base redeclare ses tables (CREATE TABLE) avant leurs
       COPY : les longueurs retenues sont toujours celles de la bonne base.
    2. Dans un bloc COPY : chaque ligne est anonymisee, ou retiree si la table est a
       vider. La ligne « \\. » ferme le bloc.
    / Flow: CREATE TABLE lengths, role passwords, COPY blocks.
    """
    if est_compresse:
        fichier_entree = gzip.open(chemin_entree, "rt", encoding="utf-8", newline="")
    else:
        fichier_entree = open(chemin_entree, "r", encoding="utf-8", newline="")

    # On ecrit d'abord dans un fichier de travail. Il n'est renomme qu'a la fin : un
    # arret au milieu ne laisse jamais un fichier qui ressemble a une sortie finie.
    # / Write to a work file, renamed only at the end.
    chemin_en_cours = chemin_sortie_final + SUFFIXE_DU_FICHIER_DE_TRAVAIL
    fichier_sortie = gzip.open(
        chemin_en_cours, "wt", encoding="utf-8", newline="", compresslevel=6
    )

    # Longueurs des colonnes varchar(N), par (schema, table), puis par colonne.
    # / varchar(N) lengths by (schema, table), then by column.
    longueurs_par_table = {}
    table_en_cours_de_creation = None

    dans_un_bloc_copy = False
    nom_de_table_du_copy = ""
    colonnes_du_copy = []
    longueurs_du_copy = {}
    table_du_copy_a_vider = False

    try:
        for ligne in fichier_entree:
            # --- Dans un bloc COPY ---
            if dans_un_bloc_copy:
                if ligne.rstrip("\n") == MARQUEUR_FIN_DE_COPY:
                    dans_un_bloc_copy = False
                    fichier_sortie.write(ligne)
                    continue
                if table_du_copy_a_vider:
                    rapport.lignes_retirees_par_table[nom_de_table_du_copy] += 1
                    continue
                # Chemin rapide : une ligne sans arobase, d'une table sans regle, ne change pas.
                # La plupart des 37 000 tables de Lespass sont dans ce cas.
                # / Fast path: no "@" and no rule for the table, the row is unchanged.
                if "@" not in ligne and nom_de_table_du_copy not in REGLES_POSTGRES:
                    fichier_sortie.write(ligne)
                    continue
                ligne_anonymisee = anonymiser_une_ligne_de_copy(
                    ligne,
                    nom_de_table_du_copy,
                    colonnes_du_copy,
                    longueurs_du_copy,
                    anonymiseur,
                    rapport,
                )
                fichier_sortie.write(ligne_anonymisee)
                continue

            # --- Dans un CREATE TABLE : on lit les longueurs ---
            if table_en_cours_de_creation is not None:
                if ligne.startswith(")"):
                    table_en_cours_de_creation = None
                else:
                    correspondance = EXPRESSION_COLONNE_A_LONGUEUR.match(ligne)
                    if correspondance:
                        nom_de_colonne = decouper_les_identifiants(
                            correspondance.group(1)
                        )[0]
                        longueurs_par_table[table_en_cours_de_creation][
                            nom_de_colonne
                        ] = int(correspondance.group(2))
                fichier_sortie.write(ligne)
                continue

            # --- Hors bloc ---
            if ligne.startswith("COPY "):
                correspondance = EXPRESSION_LIGNE_COPY.match(ligne.rstrip("\n"))
                if correspondance is None:
                    raise EntreeRefusee(
                        "Une ligne COPY n'a pas la forme attendue « COPY table (colonnes) FROM stdin; »."
                    )
                schema, nom_de_table = schema_et_table(correspondance.group(1))
                colonnes_du_copy = decouper_les_identifiants(
                    correspondance.group(2) or ""
                )
                nom_de_table_du_copy = nom_de_table
                longueurs_du_copy = longueurs_par_table.get((schema, nom_de_table), {})
                table_du_copy_a_vider = nom_de_table in TABLES_A_VIDER_POSTGRES
                dans_un_bloc_copy = True

                # Une table videe n'a plus de valeur : ses colonnes ne sont pas suspectes.
                # / An emptied table holds no value: its columns are not suspicious.
                regles_de_la_table = REGLES_POSTGRES.get(nom_de_table, {})
                for nom_de_colonne in colonnes_du_copy:
                    if table_du_copy_a_vider:
                        break
                    if colonne_est_suspecte(
                        nom_de_table, nom_de_colonne, regles_de_la_table
                    ):
                        rapport.colonnes_suspectes_non_traitees.add(
                            f"{nom_de_table}.{nom_de_colonne}"
                        )

                fichier_sortie.write(ligne)
                continue

            correspondance = EXPRESSION_DEBUT_CREATE_TABLE.match(ligne.rstrip("\n"))
            if correspondance:
                schema, nom_de_table = schema_et_table(correspondance.group(1))
                table_en_cours_de_creation = (schema, nom_de_table)
                longueurs_par_table[table_en_cours_de_creation] = {}
                fichier_sortie.write(ligne)
                continue

            if ligne.startswith("CREATE ROLE ") or ligne.startswith("ALTER ROLE "):
                ligne_sans_mot_de_passe, nombre = EXPRESSION_CLAUSE_PASSWORD.subn(
                    "", ligne
                )
                rapport.clauses_password_retirees += nombre
                fichier_sortie.write(ligne_sans_mot_de_passe)
                continue

            if ligne.startswith("INSERT INTO "):
                # On s'arrete plutot que de laisser passer des donnees non anonymisees.
                # / Stop rather than let non-anonymised data through.
                raise EntreeRefusee(
                    "Le dump contient des INSERT (pg_dump --inserts). Seul le format COPY est gere : "
                    "refaire le dump sans --inserts."
                )

            fichier_sortie.write(ligne)

        if dans_un_bloc_copy:
            raise EntreeRefusee(
                "Le dump se termine au milieu d'un bloc COPY : il est tronque."
            )

    except BaseException:
        fichier_entree.close()
        fichier_sortie.close()
        os.remove(chemin_en_cours)
        raise

    fichier_entree.close()
    fichier_sortie.close()
    os.rename(chemin_en_cours, chemin_sortie_final)


def controler_un_dump_postgres(chemin_sortie, rapport):
    """
    Relit TOUT le dump anonymise et compte les e-mails reels restants.
    Ceux des blocs COPY sont comptes par table. Ceux des autres lignes (un COMMENT ON,
    une valeur par defaut, un nom de role) sont comptes sous « (hors des blocs COPY) ».
    / Re-reads the WHOLE dump and counts real e-mails left, per table or outside COPY.
    """
    dans_un_bloc_copy = False
    nom_de_table_du_copy = ""

    with gzip.open(chemin_sortie, "rt", encoding="utf-8", newline="") as fichier:
        for ligne in fichier:
            if dans_un_bloc_copy:
                if ligne.rstrip("\n") == MARQUEUR_FIN_DE_COPY:
                    dans_un_bloc_copy = False
                    continue
                endroit_du_rapport = nom_de_table_du_copy
            else:
                if ligne.startswith("COPY "):
                    correspondance = EXPRESSION_LIGNE_COPY.match(ligne.rstrip("\n"))
                    if correspondance:
                        _schema, nom_de_table_du_copy = schema_et_table(
                            correspondance.group(1)
                        )
                        dans_un_bloc_copy = True
                        continue
                endroit_du_rapport = "(hors des blocs COPY)"

            if "@" in ligne or "%40" in ligne:
                nombre = compter_les_emails_reels(ligne)
                if nombre:
                    rapport.emails_reels_restants_par_table[endroit_du_rapport] += (
                        nombre
                    )

    rapport.controle_fait = True


# ---------------------------------------------------------------------------
# SQLITE : copie, UPDATE, VACUUM
# / SQLite: copy, UPDATE, VACUUM
# ---------------------------------------------------------------------------


def citer_identifiant_sqlite(nom):
    # Met un nom de table ou de colonne entre guillemets pour SQLite.
    # / Quotes a table or column name for SQLite.
    return '"' + nom.replace('"', '""') + '"'


def anonymiser_une_base_sqlite(
    chemin_entree, est_compresse, chemin_sortie_final, anonymiseur, rapport
):
    """
    Copie la base, l'anonymise par UPDATE, puis la compacte par VACUUM.
    / Copies the database, anonymises it with UPDATE, then compacts it with VACUUM.

    FLUX :
    1. Copie de l'entree vers le fichier de travail (decompressee si elle est en .gz).
       Si l'entree a un fichier « -wal » a cote, il est copie aussi : SQLite y lit les
       dernieres ecritures. L'entree n'est JAMAIS ouverte par SQLite : ouvrir une base WAL,
       meme en lecture seule, cree des fichiers « -wal » et « -shm » a cote d'elle.
    2. Dans une transaction : regles de colonnes, tables a vider, e-mails partout (sauf
       colonnes protegees, ou ils sont seulement comptes).
    3. journal_mode = DELETE (le -wal est reverse dans la base puis supprime), puis VACUUM.

    LE VACUUM EST OBLIGATOIRE : sans lui, les anciennes valeurs (vrais e-mails, cles)
    restent lisibles dans les pages libres du fichier, meme apres les UPDATE.
    / VACUUM is mandatory: without it, old values stay readable in free pages.

    L'entree doit etre une copie au repos (le snapshot de Fedow/backup/save.sh, ou une
    archive borg extraite), pas la base vivante de Fedow.
    / The input must be a copy at rest, not Fedow's live database.
    """
    chemin_en_cours = chemin_sortie_final + SUFFIXE_DU_FICHIER_DE_TRAVAIL
    fichiers_annexes_en_cours = [
        chemin_en_cours + "-wal",
        chemin_en_cours + "-shm",
        chemin_en_cours + "-journal",
    ]

    try:
        if est_compresse:
            with gzip.open(chemin_entree, "rb") as fichier_compresse:
                with open(chemin_en_cours, "wb") as fichier_copie:
                    shutil.copyfileobj(fichier_compresse, fichier_copie)
        else:
            shutil.copyfile(chemin_entree, chemin_en_cours)
            if os.path.exists(chemin_entree + "-wal"):
                shutil.copyfile(chemin_entree + "-wal", chemin_en_cours + "-wal")

        connexion_sortie = sqlite3.connect(chemin_en_cours)

        # Mode « autocommit » de Python : c'est NOUS qui ouvrons et fermons la transaction
        # (BEGIN / COMMIT ci-dessous). VACUUM ne peut pas tourner dans une transaction.
        # / Python autocommit mode: we drive BEGIN/COMMIT ourselves. VACUUM needs it.
        connexion_sortie.isolation_level = None

        # Les pages liberees par UPDATE et DELETE sont mises a zero tout de suite. Le
        # VACUUM final reecrit le fichier de toute facon : c'est une seconde protection,
        # qui ne depend pas de la facon dont SQLite a ete compile.
        # / Freed pages are zeroed at once: a second protection besides VACUUM.
        connexion_sortie.execute("PRAGMA secure_delete = ON")

        # La table et la colonne en cours de traitement, pour que les fonctions SQL
        # ci-dessous comptent au bon endroit.
        # / Current table and column, so the SQL functions count in the right place.
        position_courante = {"cle_du_rapport": ""}

        def fonction_sql_anonymiser_emails(valeur):
            if not isinstance(valeur, str):
                return valeur
            nouvelle_valeur, nombre_d_emails = anonymiseur.remplacer_les_emails(valeur)
            if nombre_d_emails:
                rapport.emails_remplaces_par_colonne[
                    position_courante["cle_du_rapport"]
                ] += nombre_d_emails
            return nouvelle_valeur

        def fonction_sql_appliquer_le_mode(mode, valeur):
            if valeur is None:
                return None
            # Le mode « nom » travaille sur du texte : un entier est converti.
            # / The "nom" mode works on text: an integer is converted.
            valeur_en_texte = valeur if isinstance(valeur, str) else str(valeur)
            nouvelle_valeur = anonymiseur.valeur_de_remplacement(mode, valeur_en_texte)
            if nouvelle_valeur != valeur:
                rapport.valeurs_remplacees_par_colonne[
                    position_courante["cle_du_rapport"]
                ] += 1
            return nouvelle_valeur

        connexion_sortie.create_function(
            "anonymiser_emails", 1, fonction_sql_anonymiser_emails
        )
        # Pas « deterministic » : le mode jeton_unique tire une valeur au hasard.
        # / Not deterministic: jeton_unique draws a random value.
        connexion_sortie.create_function(
            "appliquer_le_mode", 2, fonction_sql_appliquer_le_mode
        )

        curseur = connexion_sortie.cursor()
        curseur.execute("BEGIN")

        lignes_des_tables = curseur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        noms_des_tables = [ligne_de_table[0] for ligne_de_table in lignes_des_tables]

        for nom_de_table in noms_des_tables:
            table_citee = citer_identifiant_sqlite(nom_de_table)

            if nom_de_table in TABLES_A_VIDER_SQLITE:
                curseur.execute(f"DELETE FROM {table_citee}")
                rapport.lignes_retirees_par_table[nom_de_table] += curseur.rowcount
                continue

            infos_des_colonnes = curseur.execute(
                f"PRAGMA table_info({table_citee})"
            ).fetchall()
            noms_des_colonnes = [
                info_de_colonne[1] for info_de_colonne in infos_des_colonnes
            ]
            regles_de_la_table = REGLES_SQLITE.get(nom_de_table, {})

            for nom_de_colonne in noms_des_colonnes:
                colonne_citee = citer_identifiant_sqlite(nom_de_colonne)
                cle_du_rapport = f"{nom_de_table}.{nom_de_colonne}"
                position_courante["cle_du_rapport"] = cle_du_rapport

                if colonne_est_suspecte(
                    nom_de_table, nom_de_colonne, regles_de_la_table
                ):
                    rapport.colonnes_suspectes_non_traitees.add(cle_du_rapport)

                mode = regles_de_la_table.get(nom_de_colonne)
                if mode is not None:
                    curseur.execute(
                        f"UPDATE {table_citee} SET {colonne_citee} = appliquer_le_mode(?, {colonne_citee}) "
                        f"WHERE {colonne_citee} IS NOT NULL",
                        (mode,),
                    )
                    continue

                if (nom_de_table, nom_de_colonne) in COLONNES_PROTEGEES_SQLITE:
                    # On compte sans remplacer (hash chaine de Fedow).
                    # / Count without replacing (Fedow's chained hash).
                    valeurs_avec_arobase = curseur.execute(
                        f"SELECT {colonne_citee} FROM {table_citee} "
                        f"WHERE typeof({colonne_citee}) = 'text' AND instr({colonne_citee}, '@') > 0"
                    ).fetchall()
                    for (valeur,) in valeurs_avec_arobase:
                        _texte, nombre_d_emails = anonymiseur.remplacer_les_emails(
                            valeur
                        )
                        rapport.emails_laisses_dans_colonnes_protegees[
                            cle_du_rapport
                        ] += nombre_d_emails
                    continue

                curseur.execute(
                    f"UPDATE {table_citee} SET {colonne_citee} = anonymiser_emails({colonne_citee}) "
                    f"WHERE typeof({colonne_citee}) = 'text' AND instr({colonne_citee}, '@') > 0"
                )

        curseur.execute("COMMIT")

        # Sortie du mode WAL : le -wal est reverse dans la base puis supprime. La PRAGMA
        # renvoie le nouveau mode : on le lit pour etre sur qu'elle a bien agi.
        # / Leave WAL mode; read the result to be sure it worked.
        nouveau_mode_du_journal = curseur.execute(
            "PRAGMA journal_mode = DELETE"
        ).fetchone()[0]
        if nouveau_mode_du_journal.lower() != "delete":
            raise RuntimeError("SQLite n'a pas quitte le mode WAL.")

        curseur.execute("VACUUM")
        connexion_sortie.close()

    except BaseException:
        # Le fichier en cours contient encore des donnees de prod : il est supprime.
        # / The in-progress file still holds production data: removed.
        for chemin_a_supprimer in [chemin_en_cours] + fichiers_annexes_en_cours:
            if os.path.exists(chemin_a_supprimer):
                os.remove(chemin_a_supprimer)
        raise

    # Apres journal_mode = DELETE et la fermeture, aucun fichier annexe ne doit rester.
    # S'il en reste un, il peut contenir d'anciennes pages : on s'arrete.
    # / No side file may remain: it could hold old pages.
    for chemin_annexe in fichiers_annexes_en_cours:
        if os.path.exists(chemin_annexe):
            os.remove(chemin_en_cours)
            os.remove(chemin_annexe)
            raise EntreeRefusee(
                f"SQLite a laisse un fichier annexe ({os.path.basename(chemin_annexe)})."
            )

    os.rename(chemin_en_cours, chemin_sortie_final)


def controler_une_base_sqlite(chemin_sortie, rapport):
    """
    Relit la base anonymisee et compte les e-mails reels restants (hors colonnes protegees).
    / Re-reads the anonymised database and counts real e-mails left.
    """
    connexion = sqlite3.connect(f"file:{chemin_sortie}?mode=ro", uri=True)
    curseur = connexion.cursor()

    lignes_des_tables = curseur.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    for (nom_de_table,) in lignes_des_tables:
        table_citee = citer_identifiant_sqlite(nom_de_table)
        infos_des_colonnes = curseur.execute(
            f"PRAGMA table_info({table_citee})"
        ).fetchall()
        for info_de_colonne in infos_des_colonnes:
            nom_de_colonne = info_de_colonne[1]
            if (nom_de_table, nom_de_colonne) in COLONNES_PROTEGEES_SQLITE:
                continue
            colonne_citee = citer_identifiant_sqlite(nom_de_colonne)
            valeurs_suspectes = curseur.execute(
                f"SELECT {colonne_citee} FROM {table_citee} WHERE typeof({colonne_citee}) = 'text' "
                f"AND (instr({colonne_citee}, '@') > 0 OR instr({colonne_citee}, '%40') > 0)"
            ).fetchall()
            for (valeur,) in valeurs_suspectes:
                nombre = compter_les_emails_reels(valeur)
                if nombre:
                    rapport.emails_reels_restants_par_table[nom_de_table] += nombre

    connexion.close()
    rapport.controle_fait = True


# ---------------------------------------------------------------------------
# UN FICHIER, DU DEBUT A LA FIN
# / One file, start to finish
# ---------------------------------------------------------------------------


def traiter_un_fichier(chemin_entree, anonymiseur):
    """
    Reconnait le format, anonymise, controle. Renvoie le rapport.
    Leve EntreeRefusee si le fichier ne peut pas etre traite.
    / Detects the format, anonymises, checks. Returns the report.
    """
    if not os.path.isfile(chemin_entree):
        raise EntreeRefusee(f"Fichier absent : {chemin_entree}")

    est_compresse, premiers_octets = lire_les_premiers_octets(chemin_entree)

    if premiers_octets.startswith(b"PGDMP"):
        raise EntreeRefusee(
            "Dump PostgreSQL au format custom (pg_dump -Fc). Le convertir d'abord en texte : "
            "pg_restore -f - fichier.dump | gzip > fichier.sql.gz"
        )

    est_une_base_sqlite = premiers_octets.startswith(b"SQLite format 3\x00")
    if est_une_base_sqlite:
        chemin_sortie = chemin_de_sortie(chemin_entree, ".sqlite3")
    else:
        chemin_sortie = chemin_de_sortie(chemin_entree, ".sql.gz")

    if os.path.exists(chemin_sortie):
        raise EntreeRefusee(
            f"La sortie existe deja, elle n'est pas ecrasee : {chemin_sortie}"
        )

    rapport = RapportDUnFichier(chemin_entree, chemin_sortie)

    if est_une_base_sqlite:
        anonymiser_une_base_sqlite(
            chemin_entree, est_compresse, chemin_sortie, anonymiseur, rapport
        )
        controler_une_base_sqlite(chemin_sortie, rapport)
        return rapport

    # Un dump texte commence par « -- » (commentaire) ou par une commande SQL.
    # / A text dump starts with a "--" comment or an SQL statement.
    try:
        debut_en_texte = premiers_octets.decode("utf-8")
    except UnicodeDecodeError:
        debut_en_texte = ""
    # Un octet nul n'existe pas dans du texte SQL : c'est un fichier binaire (par exemple
    # une archive tar de pg_dump -Ft, dont le debut est un nom de fichier).
    # / A NUL byte never appears in SQL text: binary file (e.g. a pg_dump -Ft tar).
    contient_un_octet_nul = b"\x00" in premiers_octets
    ressemble_a_du_sql = not contient_un_octet_nul and (
        debut_en_texte.startswith("--")
        or debut_en_texte[:1].isalpha()
        or debut_en_texte[:1] == "\n"
    )
    if not ressemble_a_du_sql:
        raise EntreeRefusee(
            "Format inconnu : ni dump PostgreSQL en texte, ni base SQLite."
        )

    anonymiser_un_dump_postgres(
        chemin_entree, est_compresse, chemin_sortie, anonymiseur, rapport
    )
    controler_un_dump_postgres(chemin_sortie, rapport)
    return rapport


# ---------------------------------------------------------------------------
# L'AFFICHAGE DU RAPPORT : des nombres et des noms de colonnes, JAMAIS une valeur
# / Printing the report: numbers and column names, NEVER a value
# ---------------------------------------------------------------------------


def afficher_un_detail(titre, compteur):
    total = sum(compteur.values())
    print(f"  {titre:<34}: {total}")
    for cle in sorted(compteur):
        print(f"      {cle} : {compteur[cle]}")


def afficher_le_rapport(rapport):
    """
    Affiche le rapport d'un fichier. Renvoie True si le controle final est OK.
    / Prints one file's report. Returns True when the final check is OK.
    """
    print()
    print(f"{rapport.chemin_entree} -> {rapport.chemin_sortie}")
    afficher_un_detail("e-mails remplaces", rapport.emails_remplaces_par_colonne)
    afficher_un_detail(
        "valeurs remplacees (regles)", rapport.valeurs_remplacees_par_colonne
    )
    afficher_un_detail("valeurs trop longues", rapport.valeurs_trop_longues_par_colonne)
    afficher_un_detail(
        "lignes retirees (tables videes)", rapport.lignes_retirees_par_table
    )
    afficher_un_detail(
        "e-mails laisses (colonnes protegees)",
        rapport.emails_laisses_dans_colonnes_protegees,
    )
    print(f"  {'clauses PASSWORD retirees':<34}: {rapport.clauses_password_retirees}")

    print(
        f"  {'colonnes suspectes NON traitees':<34}: {len(rapport.colonnes_suspectes_non_traitees)}"
    )
    for cle in sorted(rapport.colonnes_suspectes_non_traitees):
        print(f"      {cle}")

    controle_ok = rapport.controle_fait and not rapport.emails_reels_restants_par_table
    if controle_ok:
        print(f"  {'controle final':<34}: OK")
    else:
        afficher_un_detail(
            "controle final : E-MAILS REELS RESTANTS",
            rapport.emails_reels_restants_par_table,
        )
    return controle_ok


# ---------------------------------------------------------------------------
# POINT D'ENTREE
# / Entry point
# ---------------------------------------------------------------------------


def main(arguments=None):
    """
    Traite chaque fichier passe en argument, avec le meme sel. Renvoie le code de sortie.
    / Processes each file with the same salt. Returns the exit code.
    """
    analyseur = argparse.ArgumentParser(
        description=(
            "Anonymise des copies de bases de production (dump PostgreSQL texte ou base SQLite). "
            "Passer toutes les bases dans la meme commande pour garder les memes faux e-mails."
        )
    )
    analyseur.add_argument(
        "fichiers", nargs="+", help="Dumps .sql / .sql.gz ou bases .sqlite3 / .gz"
    )
    arguments_lus = analyseur.parse_args(arguments)

    verifier_les_modes_des_regles()

    # Les sorties contiennent encore des donnees de production : lisibles par nous seuls.
    # L'ancien reglage est remis a la fin (les tests appellent main() dans pytest).
    # / Outputs still hold production data: owner-only. Previous umask restored at the end.
    ancien_umask = os.umask(0o077)

    # Un « kill », un terminal ferme ou un « docker stop » envoient SIGTERM ou SIGHUP. Par
    # defaut, Python s'arrete alors SANS executer les blocs « except » : le fichier de
    # travail, copie brute de la prod, resterait sur le disque. On transforme ces signaux
    # en sortie normale (SystemExit) pour que le menage se fasse. « kill -9 » ne peut pas
    # etre intercepte.
    # / SIGTERM/SIGHUP become SystemExit so cleanup runs. kill -9 cannot be caught.
    anciens_gestionnaires = {}
    for nom_du_signal in ("SIGTERM", "SIGHUP"):
        numero_du_signal = getattr(signal, nom_du_signal, None)
        if numero_du_signal is not None:
            anciens_gestionnaires[numero_du_signal] = signal.signal(
                numero_du_signal, sortir_proprement_sur_un_signal
            )

    anonymiseur = Anonymiseur()
    code_de_sortie = 0

    try:
        for chemin_entree in arguments_lus.fichiers:
            try:
                rapport = traiter_un_fichier(chemin_entree, anonymiseur)
            except EntreeRefusee as refus:
                print(f"\n{chemin_entree} : REFUSE. {refus}", file=sys.stderr)
                code_de_sortie = max(code_de_sortie, 2)
                continue
            except Exception as erreur:
                # On n'affiche QUE le type de l'erreur : son message peut contenir un
                # morceau de donnee de prod (ex. UnicodeDecodeError montre des octets).
                # Le fichier de travail est deja supprime par la fonction qui a plante.
                # / Only the error TYPE is shown: its message may hold production data.
                print(
                    f"\n{chemin_entree} : ERREUR {type(erreur).__name__}. "
                    "Le fichier de travail est supprime. Si une sortie existe, elle "
                    "n'est pas controlee : la supprimer.",
                    file=sys.stderr,
                )
                code_de_sortie = max(code_de_sortie, 3)
                continue

            controle_ok = afficher_le_rapport(rapport)
            if not controle_ok:
                code_de_sortie = max(code_de_sortie, 1)
    finally:
        os.umask(ancien_umask)
        for numero_du_signal, ancien_gestionnaire in anciens_gestionnaires.items():
            signal.signal(numero_du_signal, ancien_gestionnaire)

    return code_de_sortie


def sortir_proprement_sur_un_signal(numero_du_signal, _cadre):
    # Leve SystemExit : les blocs « except BaseException » font le menage.
    # Code 128 + numero du signal, comme le shell.
    # / Raises SystemExit so cleanup blocks run. Exit code 128 + signal number.
    raise SystemExit(128 + numero_du_signal)


def verifier_les_modes_des_regles():
    """
    Verifie, avant de lire le moindre fichier, que chaque regle utilise un mode connu.
    Sans ce controle, une faute de frappe dans un mode planterait au milieu d'un dump de
    prod, sur la premiere table concernee.
    / Checks every rule uses a known mode, before reading any file.
    """
    toutes_les_regles = list(REGLES_POSTGRES.items()) + list(REGLES_SQLITE.items())
    for nom_de_table, regles_de_la_table in toutes_les_regles:
        for nom_de_colonne, mode in regles_de_la_table.items():
            if mode not in MODES_CONNUS:
                raise ValueError(
                    f"Mode inconnu « {mode} » pour {nom_de_table}.{nom_de_colonne}"
                )


if __name__ == "__main__":
    sys.exit(main())
