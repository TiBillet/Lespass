"""
Tests du script d'anonymisation des copies de production.
/ Tests of the production-copy anonymisation script.

LOCALISATION : tests/pytest/test_anonymiser_dump.py
SCRIPT TESTE : seo/scripts_observatoire/anonymiser_dump.py
SPEC : TECH_DOC/SESSIONS/OBSERVATOIRE/CHANTIER-03-anonymisation-des-dumps.md

Le script n'est pas un module Django : on le charge par son chemin. Les donnees sont
FABRIQUEES dans chaque test (un petit dump texte, une petite base SQLite), dans tmp_path.
Aucun dump de production n'est dans le depot.
/ The script is loaded from its path. Test data is built in tmp_path.
"""

import gzip
import importlib.util
import os
import re
import sqlite3
from pathlib import Path


CHEMIN_DU_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "seo"
    / "scripts_observatoire"
    / "anonymiser_dump.py"
)


def charger_le_script():
    # Charge le script comme un module, sans l'executer comme programme.
    # / Loads the script as a module, without running it as a program.
    specification = importlib.util.spec_from_file_location(
        "anonymiser_dump", CHEMIN_DU_SCRIPT
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


script = charger_le_script()

EXPRESSION_FAUX_EMAIL = re.compile(r"^[0-9a-f]{16}@anonyme\.invalid$")


# ---------------------------------------------------------------------------
# Fabriques de donnees de test
# / Test data builders
# ---------------------------------------------------------------------------

# Un petit dump au format de pg_dumpall. Les valeurs sont separees par de VRAIES
# tabulations (\t dans la chaine Python). « \\n » dans la chaine Python = « \n » dans le
# fichier : c'est un retour a la ligne echappe par COPY.
# / A tiny pg_dumpall-style dump. Real tabs between values.
DUMP_DE_TEST = (
    "--\n"
    "-- PostgreSQL database cluster dump\n"
    "--\n"
    "CREATE ROLE role_de_test;\n"
    "ALTER ROLE role_de_test WITH SUPERUSER LOGIN PASSWORD 'md5motdepassehache';\n"
    "CREATE ROLE autre_role WITH LOGIN PASSWORD 'secret-du-role-2';\n"
    "\\connect tibillet\n"
    'CREATE TABLE public."AuthBillet_tibilletuser" (\n'
    "    id integer NOT NULL,\n"
    "    email character varying(254) NOT NULL,\n"
    "    username character varying(200) NOT NULL,\n"
    "    password character varying(128) NOT NULL,\n"
    "    first_name character varying(200),\n"
    "    phone character varying(20)\n"
    ");\n"
    'CREATE TABLE "lieu-un"."BaseBillet_lignearticle" (\n'
    "    id integer NOT NULL,\n"
    "    metadata jsonb,\n"
    '    "order" character varying(10)\n'
    ");\n"
    'COPY public."AuthBillet_tibilletuser" (id, email, username, password, first_name, phone) FROM stdin;\n'
    "1\tAlice@Exemple.fr\tAlice@Exemple.fr\tpbkdf2_sha256$hache\tAlice\t0601020304\n"
    "2\tbob@exemple.org\tbob@exemple.org\tpbkdf2_sha256$autre\t\\N\t\\N\n"
    "3\tcarl@exemple.org\tjonas\tpbkdf2_sha256$encore\t\\N\t\\N\n"
    "\\.\n"
    'COPY "lieu-un"."BaseBillet_lignearticle" (id, metadata, "order") FROM stdin;\n'
    '1\t{"admin": "bob@exemple.org", "logo": "logo@2x.png", "photo": "avatar_dave@gmail.com.png", '
    '"note": "ligne\\nalice@exemple.fr"}\ta@b.fr\n'
    "2\t{}\tc@d.fr\n"
    "\\.\n"
    'COPY public."BaseBillet_configuration" (id, key_cashless, stripe_api_key) FROM stdin;\n'
    "1\tcle-laboutik-en-clair\t\\N\n"
    "\\.\n"
    "COPY public.rest_framework_api_key_apikey (id, prefix, hashed_key) FROM stdin;\n"
    "abc.hash1\tabc\thash1\n"
    "\\.\n"
    "COPY public.onboard_onboardinvitation (id, code) FROM stdin;\n"
    "1\tinvitation-1\n"
    "2\tinvitation-2\n"
    "\\.\n"
    "COPY public.discovery_pairingdevice (id, pin_code) FROM stdin;\n"
    "1\t123456\n"
    "\\.\n"
    "COPY public.django_session (session_key, session_data, expire_date) FROM stdin;\n"
    "cle1\tdonnees-secretes\t2026-01-01\n"
    "\\.\n"
)


def ecrire_un_dump(dossier, nom="lespass.sql.gz", contenu=DUMP_DE_TEST):
    chemin = dossier / nom
    with gzip.open(chemin, "wt", encoding="utf-8", newline="") as fichier:
        fichier.write(contenu)
    return chemin


def ecrire_une_base_fedow(dossier, nom="fedow.sqlite3"):
    # Une petite base au schema de Fedow, en mode WAL comme la vraie.
    # / A tiny Fedow-like database, in WAL mode like the real one.
    chemin = dossier / nom
    connexion = sqlite3.connect(chemin)
    connexion.execute("PRAGMA journal_mode = WAL")
    connexion.execute(
        "CREATE TABLE fedow_core_fedowuser (id INTEGER, email TEXT UNIQUE, username TEXT UNIQUE, "
        "password TEXT, first_name TEXT)"
    )
    connexion.execute(
        "CREATE TABLE fedow_core_transaction (id INTEGER, comment TEXT, metadata TEXT)"
    )
    connexion.execute(
        "CREATE TABLE fedow_core_wallet (id INTEGER, private_pem TEXT, public_pem TEXT)"
    )
    connexion.execute(
        "CREATE TABLE django_session (session_key TEXT, session_data TEXT)"
    )
    connexion.execute(
        "INSERT INTO fedow_core_fedowuser VALUES (1, 'alice@exemple.fr', 'alice@exemple.fr', 'pbkdf2$x', 'Alice')"
    )
    connexion.execute(
        "INSERT INTO fedow_core_fedowuser VALUES (2, 'carole@exemple.fr', 'carole@exemple.fr', '', NULL)"
    )
    connexion.execute(
        "INSERT INTO fedow_core_transaction VALUES "
        "(1, 'remboursement de alice@exemple.fr', '{\"par\": \"alice@exemple.fr\"}')"
    )
    connexion.execute(
        "INSERT INTO fedow_core_wallet VALUES (1, '-----BEGIN ENCRYPTED PRIVATE KEY-----', '-----BEGIN PUBLIC KEY-----')"
    )
    connexion.execute("INSERT INTO django_session VALUES ('cle1', 'donnees-secretes')")
    connexion.commit()
    connexion.close()
    return chemin


def lignes_d_une_table(chemin_du_dump, nom_de_table):
    """
    Les lignes d'un bloc COPY du dump de sortie, decoupees sur les tabulations.
    / Rows of a COPY block of the output dump, split on tabs.
    """
    lignes_trouvees = []
    dans_le_bon_bloc = False
    with gzip.open(chemin_du_dump, "rt", encoding="utf-8", newline="") as fichier:
        for ligne in fichier:
            if dans_le_bon_bloc:
                if ligne == "\\.\n":
                    return lignes_trouvees
                lignes_trouvees.append(ligne.rstrip("\n").split("\t"))
                continue
            if ligne.startswith("COPY ") and f"{nom_de_table}" in ligne.split(" (")[0]:
                dans_le_bon_bloc = True
    return lignes_trouvees


def texte_du_dump(chemin_du_dump):
    with gzip.open(chemin_du_dump, "rt", encoding="utf-8", newline="") as fichier:
        return fichier.read()


# ---------------------------------------------------------------------------
# Les e-mails
# / E-mails
# ---------------------------------------------------------------------------


def test_un_email_dans_une_colonne_copy_est_remplace_par_un_faux_email(tmp_path):
    chemin = ecrire_un_dump(tmp_path)
    assert script.main([str(chemin)]) == 0

    utilisateurs = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "AuthBillet_tibilletuser"
    )
    assert EXPRESSION_FAUX_EMAIL.match(utilisateurs[0][1])
    assert "exemple" not in texte_du_dump(tmp_path / "lespass.anonyme.sql.gz").replace(
        "@anonyme", ""
    )


def test_le_meme_email_donne_le_meme_faux_email_dans_un_dump_et_une_base_sqlite(
    tmp_path,
):
    # Lespass et Fedow passes DANS LA MEME COMMANDE : meme sel, meme faux e-mail.
    # « bob@exemple.org » n'est que dans le dump ; « alice@exemple.fr » est dans les deux.
    # / Same command, same salt, same fake e-mail.
    chemin_dump = ecrire_un_dump(tmp_path)
    chemin_base = ecrire_une_base_fedow(tmp_path)
    assert script.main([str(chemin_dump), str(chemin_base)]) == 0

    ligne_article = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "BaseBillet_lignearticle"
    )[0]
    connexion = sqlite3.connect(tmp_path / "fedow.anonyme.sqlite3")
    faux_email_d_alice_dans_fedow = connexion.execute(
        "SELECT email FROM fedow_core_fedowuser WHERE id = 1"
    ).fetchone()[0]
    connexion.close()

    assert EXPRESSION_FAUX_EMAIL.match(faux_email_d_alice_dans_fedow)
    assert f"ligne\\n{faux_email_d_alice_dans_fedow}" in ligne_article[1]


def test_un_email_dans_du_json_est_remplace_et_le_meme_email_donne_le_meme_faux(
    tmp_path,
):
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])

    utilisateurs = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "AuthBillet_tibilletuser"
    )
    faux_email_de_bob = utilisateurs[1][1]
    ligne_article = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "BaseBillet_lignearticle"
    )[0]
    assert f'"admin": "{faux_email_de_bob}"' in ligne_article[1]


def test_un_nom_d_image_comme_logo_2x_png_n_est_pas_touche(tmp_path):
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])

    ligne_article = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "BaseBillet_lignearticle"
    )[0]
    assert '"logo": "logo@2x.png"' in ligne_article[1]


def test_un_email_apres_un_retour_a_la_ligne_echappe_ne_garde_pas_la_lettre_n():
    # « ligne\nalice@... » : la correspondance commence a « alice », pas a « nalice ».
    # / The match starts at "alice", not "nalice".
    anonymiseur = script.Anonymiseur(sel=b"sel-de-test")
    texte, nombre = anonymiseur.remplacer_les_emails("ligne\\nalice@exemple.fr")
    assert nombre == 1
    assert texte == "ligne\\n" + anonymiseur.faux_email("alice@exemple.fr")


def test_un_email_avec_un_accent_est_remplace():
    anonymiseur = script.Anonymiseur(sel=b"sel-de-test")
    texte, nombre = anonymiseur.remplacer_les_emails("contact : rené@exemple.fr")
    assert nombre == 1
    assert "rené" not in texte


def test_deux_emails_qui_ne_different_que_par_la_casse_donnent_deux_faux_emails():
    # Le HMAC porte sur le texte exact : une colonne unique ne recoit jamais de doublon.
    # / HMAC on the exact text: a unique column never gets a duplicate.
    anonymiseur = script.Anonymiseur(sel=b"sel-de-test")
    assert anonymiseur.faux_email("Alice@exemple.fr") != anonymiseur.faux_email(
        "alice@exemple.fr"
    )


def section_du_rapport(sortie, titre):
    # Les lignes d'une section du rapport : de son titre jusqu'au titre suivant.
    # / Lines of one report section, from its title to the next title.
    lignes_de_la_section = []
    dans_la_section = False
    for ligne in sortie.splitlines():
        est_un_titre = ligne.startswith("  ") and not ligne.startswith("      ")
        if est_un_titre:
            dans_la_section = ligne.strip().startswith(titre)
            continue
        if dans_la_section:
            lignes_de_la_section.append(ligne.strip())
    return lignes_de_la_section


def test_un_email_court_dans_une_colonne_trop_courte_devient_une_empreinte_distincte(
    tmp_path, capsys
):
    # « a@b.fr » et « c@d.fr » dans un varchar(10) : le faux e-mail (33) ne tient pas.
    # Chacun devient une empreinte de 10 caracteres, differente de l'autre (colonnes
    # uniques), et le rapport compte les deux dans « valeurs trop longues ».
    # / Each becomes a distinct 10-char hash, counted under "valeurs trop longues".
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])

    lignes_article = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "BaseBillet_lignearticle"
    )
    premiere_valeur = lignes_article[0][2]
    deuxieme_valeur = lignes_article[1][2]
    assert re.match(r"^[0-9a-f]{10}$", premiere_valeur)
    assert re.match(r"^[0-9a-f]{10}$", deuxieme_valeur)
    assert premiere_valeur != deuxieme_valeur

    sortie = capsys.readouterr().out
    assert section_du_rapport(sortie, "valeurs trop longues") == [
        "BaseBillet_lignearticle.order : 2"
    ]


def test_un_email_dans_un_nom_de_fichier_d_image_est_remplace(tmp_path):
    # Seul « @<chiffres>x.<extension> » est une image retina. « avatar_dave@gmail.com.png »
    # contient un vrai e-mail.
    # / Only "@<digits>x.<ext>" is a retina image; this one holds a real e-mail.
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])

    ligne_article = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "BaseBillet_lignearticle"
    )[0]
    assert "dave" not in ligne_article[1]
    assert "gmail" not in ligne_article[1]


# ---------------------------------------------------------------------------
# Les regles de colonnes
# / Column rules
# ---------------------------------------------------------------------------


def test_chaque_mode_de_regle_ecrit_la_bonne_valeur_et_un_null_reste_null(tmp_path):
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])
    sortie = tmp_path / "lespass.anonyme.sql.gz"

    utilisateurs = lignes_d_une_table(sortie, "AuthBillet_tibilletuser")
    assert utilisateurs[0][3] == "!anonyme"
    assert re.match(r"^Anonyme-[0-9a-f]{8}$", utilisateurs[0][4])
    assert utilisateurs[0][5] == ""
    assert utilisateurs[1][4] == "\\N"
    assert utilisateurs[1][5] == "\\N"

    configuration = lignes_d_une_table(sortie, "BaseBillet_configuration")[0]
    assert configuration[1] == ""
    assert configuration[2] == "\\N"

    cle_api = lignes_d_une_table(sortie, "rest_framework_api_key_apikey")[0]
    assert cle_api == ["abc.hash1", "abc", "!anonyme"]

    invitations = lignes_d_une_table(sortie, "onboard_onboardinvitation")
    assert invitations[0][1].startswith("anonyme-")
    assert invitations[0][1] != invitations[1][1]

    appairage = lignes_d_une_table(sortie, "discovery_pairingdevice")[0]
    assert appairage[1] == "\\N"


def test_une_table_a_vider_n_a_plus_de_lignes_et_son_bloc_copy_reste_valide(tmp_path):
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])
    texte = texte_du_dump(tmp_path / "lespass.anonyme.sql.gz")

    assert "donnees-secretes" not in texte
    assert (
        "COPY public.django_session (session_key, session_data, expire_date) FROM stdin;\n\\.\n"
        in texte
    )


def test_la_clause_password_d_un_role_disparait(tmp_path):
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])
    texte = texte_du_dump(tmp_path / "lespass.anonyme.sql.gz")

    assert "md5motdepassehache" not in texte
    assert "ALTER ROLE role_de_test WITH SUPERUSER LOGIN;\n" in texte
    assert "secret-du-role-2" not in texte
    assert "CREATE ROLE autre_role WITH LOGIN;\n" in texte


def test_un_username_email_suit_l_email_et_un_username_humain_devient_un_pseudonyme(
    tmp_path,
):
    # Un username qui vaut l'e-mail recoit le meme faux e-mail que la colonne email.
    # Un username humain (« jonas ») devient « Anonyme- » + 16 caracteres (colonne unique).
    # / An e-mail username follows the e-mail; a human login becomes a 16-char pseudonym.
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])

    utilisateurs = lignes_d_une_table(
        tmp_path / "lespass.anonyme.sql.gz", "AuthBillet_tibilletuser"
    )
    assert utilisateurs[0][2] == utilisateurs[0][1]
    assert re.match(r"^Anonyme-[0-9a-f]{16}$", utilisateurs[2][2])


def test_un_en_tete_copy_avec_guillemets_et_schema_de_lieu_est_reconnu():
    schema, table = script.schema_et_table('"lieu-un"."BaseBillet_lignearticle"')
    assert (schema, table) == ("lieu-un", "BaseBillet_lignearticle")
    assert script.decouper_les_identifiants('id, metadata, "order", "ticketZ"') == [
        "id",
        "metadata",
        "order",
        "ticketZ",
    ]


# ---------------------------------------------------------------------------
# SQLite (Fedow)
# ---------------------------------------------------------------------------


def test_fedow_le_commentaire_d_une_transaction_garde_son_email_et_le_rapport_le_compte(
    tmp_path, capsys
):
    # comment et metadata entrent dans le hash chaine de Fedow : on n'y touche pas.
    # / comment and metadata feed Fedow's chained hash: left untouched.
    chemin = ecrire_une_base_fedow(tmp_path)
    assert script.main([str(chemin)]) == 0

    connexion = sqlite3.connect(tmp_path / "fedow.anonyme.sqlite3")
    commentaire, metadonnees = connexion.execute(
        "SELECT comment, metadata FROM fedow_core_transaction"
    ).fetchone()
    connexion.close()
    assert commentaire == "remboursement de alice@exemple.fr"
    assert metadonnees == '{"par": "alice@exemple.fr"}'
    sortie = capsys.readouterr().out
    assert section_du_rapport(sortie, "e-mails laisses (colonnes protegees)") == [
        "fedow_core_transaction.comment : 1",
        "fedow_core_transaction.metadata : 1",
    ]


def test_fedow_les_regles_et_les_tables_videes_sont_appliquees(tmp_path):
    chemin = ecrire_une_base_fedow(tmp_path)
    script.main([str(chemin)])

    connexion = sqlite3.connect(tmp_path / "fedow.anonyme.sqlite3")
    utilisateur = connexion.execute(
        "SELECT email, username, password, first_name FROM fedow_core_fedowuser WHERE id = 1"
    ).fetchone()
    portefeuille = connexion.execute(
        "SELECT private_pem, public_pem FROM fedow_core_wallet"
    ).fetchone()
    nombre_de_sessions = connexion.execute(
        "SELECT count(*) FROM django_session"
    ).fetchone()[0]
    connexion.close()

    assert EXPRESSION_FAUX_EMAIL.match(utilisateur[0])
    assert utilisateur[1] == utilisateur[0]
    assert utilisateur[2] == "!anonyme"
    assert utilisateur[3].startswith("Anonyme-")
    assert portefeuille == ("", "")
    assert nombre_de_sessions == 0


def test_fedow_l_ancien_email_n_est_plus_dans_les_octets_du_fichier(tmp_path):
    # Les anciennes valeurs ne doivent pas rester dans les pages libres du fichier.
    # / Old values must not stay in the file's free pages.
    chemin = ecrire_une_base_fedow(tmp_path)
    script.main([str(chemin)])

    octets_de_la_sortie = (tmp_path / "fedow.anonyme.sqlite3").read_bytes()
    assert b"carole@exemple.fr" not in octets_de_la_sortie
    assert b"donnees-secretes" not in octets_de_la_sortie
    assert b"BEGIN ENCRYPTED PRIVATE KEY" not in octets_de_la_sortie


def test_fedow_le_vacuum_ne_laisse_aucune_page_libre(tmp_path):
    # Preuve du VACUUM : on vide une table de plusieurs pages (django_session). Sans
    # VACUUM, ses pages resteraient dans la liste des pages libres du fichier. Le test des
    # octets ne suffit pas : certaines versions de SQLite mettent deja ces pages a zero.
    # / Proof of VACUUM: emptying a multi-page table leaves free pages without it.
    chemin = ecrire_une_base_fedow(tmp_path)
    connexion = sqlite3.connect(chemin)
    for numero in range(300):
        connexion.execute(
            "INSERT INTO django_session VALUES (?, ?)", (f"cle-{numero}", "x" * 2000)
        )
    connexion.commit()
    connexion.close()

    script.main([str(chemin)])

    connexion = sqlite3.connect(tmp_path / "fedow.anonyme.sqlite3")
    nombre_de_pages_libres = connexion.execute("PRAGMA freelist_count").fetchone()[0]
    mode_du_journal = connexion.execute("PRAGMA journal_mode").fetchone()[0]
    connexion.close()
    assert nombre_de_pages_libres == 0
    assert mode_du_journal == "delete"


def test_fedow_les_ecritures_du_fichier_wal_sont_reprises_et_rien_n_apparait_a_cote_de_l_entree(
    tmp_path,
):
    # Une connexion reste ouverte, sans checkpoint : la derniere ligne n'est QUE dans le
    # fichier « -wal ». Le script doit la reprendre, et ne rien creer a cote de l'entree.
    # / The last row lives only in the -wal file: it must be picked up.
    chemin = ecrire_une_base_fedow(tmp_path)
    connexion_ouverte = sqlite3.connect(chemin)
    connexion_ouverte.execute("PRAGMA wal_autocheckpoint = 0")
    connexion_ouverte.execute(
        "INSERT INTO fedow_core_fedowuser VALUES (3, 'denis@exemple.fr', 'denis@exemple.fr', '', NULL)"
    )
    connexion_ouverte.commit()
    fichiers_avant = sorted(fichier.name for fichier in tmp_path.iterdir())
    assert "fedow.sqlite3-wal" in fichiers_avant

    try:
        assert script.main([str(chemin)]) == 0
        fichiers_apres = sorted(fichier.name for fichier in tmp_path.iterdir())
    finally:
        connexion_ouverte.close()

    assert fichiers_apres == sorted(fichiers_avant + ["fedow.anonyme.sqlite3"])
    connexion = sqlite3.connect(tmp_path / "fedow.anonyme.sqlite3")
    email_de_denis = connexion.execute(
        "SELECT email FROM fedow_core_fedowuser WHERE id = 3"
    ).fetchone()[0]
    connexion.close()
    assert EXPRESSION_FAUX_EMAIL.match(email_de_denis)


def test_fedow_une_base_compressee_en_gz_est_acceptee_et_le_temporaire_supprime(
    tmp_path,
):
    chemin_base = ecrire_une_base_fedow(tmp_path / "")
    chemin_compresse = tmp_path / "fedow.sqlite3.gz"
    with (
        open(chemin_base, "rb") as source,
        gzip.open(chemin_compresse, "wb") as destination,
    ):
        destination.write(source.read())
    os.remove(chemin_base)

    assert script.main([str(chemin_compresse)]) == 0
    assert (tmp_path / "fedow.anonyme.sqlite3").exists()
    fichiers_restants = sorted(fichier.name for fichier in tmp_path.iterdir())
    assert fichiers_restants == ["fedow.anonyme.sqlite3", "fedow.sqlite3.gz"]


# ---------------------------------------------------------------------------
# Refus et controle final
# / Refusals and final check
# ---------------------------------------------------------------------------


def test_un_dump_au_format_custom_est_refuse_et_rien_n_est_ecrit(tmp_path):
    chemin = tmp_path / "lespass.dump"
    chemin.write_bytes(b"PGDMP\x01\x0e\x00" + b"\x00" * 50)

    assert script.main([str(chemin)]) == 2
    assert sorted(fichier.name for fichier in tmp_path.iterdir()) == ["lespass.dump"]


def test_un_dump_avec_des_insert_est_refuse_et_rien_n_est_ecrit(tmp_path):
    contenu = "--\nINSERT INTO public.t VALUES (1, 'alice@exemple.fr');\n"
    chemin = ecrire_un_dump(tmp_path, contenu=contenu)

    assert script.main([str(chemin)]) == 2
    assert sorted(fichier.name for fichier in tmp_path.iterdir()) == ["lespass.sql.gz"]


def test_une_sortie_deja_presente_est_refusee(tmp_path):
    chemin = ecrire_un_dump(tmp_path)
    (tmp_path / "lespass.anonyme.sql.gz").write_bytes(b"deja la")

    assert script.main([str(chemin)]) == 2
    assert (tmp_path / "lespass.anonyme.sql.gz").read_bytes() == b"deja la"


def test_le_controle_final_sort_en_code_1_quand_un_email_encode_en_pourcent_40_reste(
    tmp_path, capsys
):
    # « dave%40exemple.fr » echappe au remplacement, mais pas au controle, plus large.
    # / Escapes the replacement but not the wider final check.
    contenu = DUMP_DE_TEST + (
        "COPY public.pages_bloc (id, texte) FROM stdin;\n"
        "1\thttps://exemple.fr/?courriel=dave%40exemple.fr\n"
        "\\.\n"
    )
    chemin = ecrire_un_dump(tmp_path, contenu=contenu)

    assert script.main([str(chemin)]) == 1
    assert "pages_bloc : 1" in capsys.readouterr().out


def test_le_rapport_ne_contient_aucune_valeur_d_origine(tmp_path, capsys):
    chemin_dump = ecrire_un_dump(tmp_path)
    chemin_base = ecrire_une_base_fedow(tmp_path)
    script.main([str(chemin_dump), str(chemin_base)])

    sortie_complete = capsys.readouterr()
    rapport = sortie_complete.out + sortie_complete.err
    valeurs_d_origine = [
        "Alice@Exemple.fr",
        "bob@exemple.org",
        "alice@exemple.fr",
        "carole@exemple.fr",
        "md5motdepassehache",
        "cle-laboutik-en-clair",
        "invitation-1",
        "0601020304",
        "donnees-secretes",
        "BEGIN",
    ]
    for valeur in valeurs_d_origine:
        assert valeur not in rapport


def test_les_sorties_ne_sont_lisibles_que_par_leur_proprietaire(tmp_path):
    # Les sorties contiennent encore des donnees de prod (dates de naissance, montants).
    # / Outputs still hold production data: mode 600.
    chemin_dump = ecrire_un_dump(tmp_path)
    chemin_base = ecrire_une_base_fedow(tmp_path)
    script.main([str(chemin_dump), str(chemin_base)])

    for nom in ("lespass.anonyme.sql.gz", "fedow.anonyme.sqlite3"):
        mode_du_fichier = (tmp_path / nom).stat().st_mode & 0o777
        assert mode_du_fichier == 0o600, nom


def test_relancer_le_script_sur_une_sortie_ne_change_pas_les_faux_emails(tmp_path):
    # Un faux e-mail deja pose n'est pas remplace a nouveau, meme avec un autre sel.
    # / An existing fake e-mail is not replaced again, even with another salt.
    chemin = ecrire_un_dump(tmp_path)
    script.main([str(chemin)])
    premiere_sortie = tmp_path / "lespass.anonyme.sql.gz"
    script.main([str(premiere_sortie)])
    deuxieme_sortie = tmp_path / "lespass.anonyme.anonyme.sql.gz"

    emails_premiere = [
        ligne[1]
        for ligne in lignes_d_une_table(premiere_sortie, "AuthBillet_tibilletuser")
    ]
    emails_deuxieme = [
        ligne[1]
        for ligne in lignes_d_une_table(deuxieme_sortie, "AuthBillet_tibilletuser")
    ]
    assert emails_premiere == emails_deuxieme


def test_un_dump_tronque_au_milieu_d_un_copy_est_refuse_et_rien_n_est_ecrit(tmp_path):
    contenu = (
        "--\n"
        'COPY public."AuthBillet_tibilletuser" (id, email) FROM stdin;\n'
        "1\talice@exemple.fr\n"
    )
    chemin = ecrire_un_dump(tmp_path, contenu=contenu)

    assert script.main([str(chemin)]) == 2
    assert sorted(fichier.name for fichier in tmp_path.iterdir()) == ["lespass.sql.gz"]


def test_un_fichier_binaire_qui_commence_par_des_lettres_est_refuse(tmp_path):
    # Une archive tar (pg_dump -Ft) commence par un nom de fichier, puis des octets nuls.
    # / A tar archive starts with a file name, then NUL bytes.
    chemin = tmp_path / "lespass.tar"
    chemin.write_bytes(b"toc.dat" + b"\x00" * 200)

    assert script.main([str(chemin)]) == 2
    assert sorted(fichier.name for fichier in tmp_path.iterdir()) == ["lespass.tar"]


def test_le_controle_final_lit_aussi_les_lignes_hors_des_blocs_copy(tmp_path, capsys):
    contenu = (
        DUMP_DE_TEST + "COMMENT ON TABLE public.t IS 'contact : eve@exemple.fr';\n"
    )
    chemin = ecrire_un_dump(tmp_path, contenu=contenu)

    assert script.main([str(chemin)]) == 1
    sortie = capsys.readouterr().out
    assert "(hors des blocs COPY) : 1" in sortie


def test_le_controle_final_sqlite_sort_en_code_1_quand_un_email_reel_reste(tmp_path):
    chemin = ecrire_une_base_fedow(tmp_path)
    connexion = sqlite3.connect(chemin)
    connexion.execute("CREATE TABLE fedow_core_asset (id INTEGER, comment TEXT)")
    connexion.execute(
        "INSERT INTO fedow_core_asset VALUES (1, 'https://x.fr/?m=gaston%40exemple.fr')"
    )
    connexion.commit()
    connexion.close()

    assert script.main([str(chemin)]) == 1


def test_une_erreur_pendant_le_traitement_sqlite_ne_laisse_aucun_fichier(
    tmp_path, monkeypatch
):
    # Le fichier de travail est une copie brute de la prod : il doit disparaitre.
    # / The work file is a raw production copy: it must be removed.
    chemin = ecrire_une_base_fedow(tmp_path)

    def remplacement_qui_plante(self, texte):
        raise RuntimeError("panne simulee")

    monkeypatch.setattr(
        script.Anonymiseur, "remplacer_les_emails", remplacement_qui_plante
    )

    assert script.main([str(chemin)]) == 3
    assert sorted(fichier.name for fichier in tmp_path.iterdir()) == ["fedow.sqlite3"]


def test_les_regles_lespass_visent_des_tables_et_colonnes_qui_existent():
    # Une table ou une colonne renommee dans un modele ferait sauter la regle en silence :
    # elle ne serait plus appliquee. Ce test compare les regles aux modeles de Lespass.
    # Les tables de LaBoutik V1 ne sont pas dans ce depot : elles sont ignorees ici.
    # / A renamed table or column would silently skip its rule. Compares to Lespass models.
    from django.apps import apps

    prefixes_de_laboutik_v1 = ("APIcashless_", "tibiauth_", "epsonprinter_")
    colonnes_par_table = {}
    for modele in apps.get_models(include_auto_created=True):
        noms_des_colonnes = set()
        for champ in modele._meta.get_fields():
            nom_de_colonne = getattr(champ, "column", None)
            if nom_de_colonne:
                noms_des_colonnes.add(nom_de_colonne)
        colonnes_par_table[modele._meta.db_table] = noms_des_colonnes

    regles_manquantes = []
    for nom_de_table, regles_de_la_table in script.REGLES_POSTGRES.items():
        if nom_de_table.startswith(prefixes_de_laboutik_v1):
            continue
        if nom_de_table not in colonnes_par_table:
            regles_manquantes.append(nom_de_table)
            continue
        for nom_de_colonne in regles_de_la_table:
            if nom_de_colonne not in colonnes_par_table[nom_de_table]:
                regles_manquantes.append(f"{nom_de_table}.{nom_de_colonne}")

    for nom_de_table in script.TABLES_A_VIDER_POSTGRES:
        if nom_de_table not in colonnes_par_table:
            regles_manquantes.append(nom_de_table)

    assert regles_manquantes == []
