#!/usr/bin/env bash
# Prepare un serveur de production : le .env, les dossiers montes, et une liste de
# controles. Ne remplace JAMAIS un .env existant.
# / Prepares a production server: the .env, the mounted folders, and a checklist.
# NEVER overwrites an existing .env.
#
# LOCALISATION : scripts/fabriquer_env_prod.sh — appele par le Makefile (make env).
# A lancer sur l'HOTE de production, dans le dossier du depot.
# Spec : TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md.
#
# FLUX :
# 1. Pas de .env : copie de env_prod_example, secrets tires au hasard a la place de
#    A_GENERER, droits 600. Un .env existe deja : on n'y touche pas (regenerer
#    FERNET_KEY rendrait illisibles les donnees chiffrees en base).
# 2. Creation des dossiers montes par docker-compose.prod.yml qui manquent.
# 3. Controles, sans rien modifier : valeurs A_REMPLIR restantes, drapeaux de prod,
#    reseau Docker « frontend », docker compose >= 2, `at`,
#    crontab de sauvegarde.
# Le script peut etre relance autant de fois que voulu : apres le premier passage, il ne
# fait plus que les controles.
# / Can be run again at will: after the first run it only performs the checks.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

FICHIER_ENV=".env"
MODELE_ENV="env_prod_example"
nombre_de_points_a_traiter=0

signaler() {
    echo "  A FAIRE : $1"
    nombre_de_points_a_traiter=$((nombre_de_points_a_traiter + 1))
}


# ---------------------------------------------------------------------------------------
# 1. Le .env
# ---------------------------------------------------------------------------------------
echo "== .env"
if [ -e "$FICHIER_ENV" ]; then
    echo "  $FICHIER_ENV existe deja : il n'est pas modifie."
else
    if ! command -v python3 >/dev/null; then
        echo "python3 est necessaire pour tirer les secrets au hasard." >&2
        exit 1
    fi

    # Secrets tires par le module `secrets` de Python (generateur cryptographique).
    # FERNET_KEY doit etre 32 octets encodes en base64 « urlsafe » : c'est le format exact
    # qu'attend cryptography.fernet.Fernet. Les autres ne contiennent que [A-Za-z0-9_-] :
    # rien a echapper dans le .env ni dans sed.
    # / Secrets from Python's `secrets` module. FERNET_KEY = 32 bytes, urlsafe base64.
    secret_django=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
    cle_fernet=$(python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')
    mot_de_passe_postgres=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

    # Le .env est cree vide avec les droits 600 AVANT d'y ecrire les secrets : ils ne sont
    # jamais lisibles par les autres utilisateurs, meme un instant.
    # / The .env is created with mode 600 BEFORE the secrets are written into it.
    install -m 600 /dev/null "$FICHIER_ENV"
    sed -e "s|^DJANGO_SECRET='A_GENERER'|DJANGO_SECRET='$secret_django'|" \
        -e "s|^FERNET_KEY='A_GENERER'|FERNET_KEY='$cle_fernet'|" \
        -e "s|^POSTGRES_PASSWORD='A_GENERER'|POSTGRES_PASSWORD='$mot_de_passe_postgres'|" \
        "$MODELE_ENV" > "$FICHIER_ENV"

    # Seules les lignes de valeurs comptent : l'en-tete du modele cite « A_GENERER ».
    # En cas d'echec, le .env a moitie ecrit est retire : la relance repartira de zero.
    # / Only value lines count. On failure, the half-written .env is removed.
    if grep -qE "^[^#]*A_GENERER" "$FICHIER_ENV"; then
        rm -f "$FICHIER_ENV"
        echo "Un secret A_GENERER n'a pas ete remplace : $MODELE_ENV a change ?" >&2
        exit 1
    fi
    echo "  $FICHIER_ENV cree depuis $MODELE_ENV, secrets generes (droits 600)."
fi


# ---------------------------------------------------------------------------------------
# 2. Les dossiers montes par docker-compose.prod.yml
# - database/ : la base PostgreSQL (vide : postgres l'initialise au premier demarrage).
# - backup/   : dumps et depot borg de cron/saveDb.sh.
# - ssh/      : cle SSH de la sauvegarde borg distante, lisible par soi seul.
# - logs/, www/ : journaux, fichiers statiques et medias.
# / Folders mounted by the production compose.
# ---------------------------------------------------------------------------------------
echo "== Dossiers"
for dossier in database backup ssh logs www; do
    if [ ! -d "$dossier" ]; then
        mkdir -p "$dossier"
        echo "  $dossier/ cree."
    fi
done
chmod 700 ssh
if [ -z "$(ls -A ssh)" ]; then
    signaler "ssh/ est vide : y deposer la cle de la sauvegarde borg, sinon aucune sauvegarde distante."
fi


# ---------------------------------------------------------------------------------------
# 3. Controles (rien n'est modifie)
# / Checks (nothing is modified)
# ---------------------------------------------------------------------------------------
echo "== Controles"

# Seules les lignes de valeurs comptent, pas les commentaires.
# / Only value lines count, not comments.
valeurs_a_remplir=$(grep -nE "^[^#]*A_REMPLIR" "$FICHIER_ENV" || true)
if [ -n "$valeurs_a_remplir" ]; then
    signaler "valeurs a remplir dans $FICHIER_ENV :"
    echo "$valeurs_a_remplir" | sed 's/^/      ligne /'
fi

# Un drapeau a 1 en production active l'auto-login admin ou les donnees de demonstration.
# / A flag at 1 in production enables admin auto-login or demo data.
for drapeau in TEST DEBUG DEMO STRIPE_TEST; do
    if ! grep -qE "^$drapeau=['\"]?0['\"]?\s*(#.*)?$" "$FICHIER_ENV"; then
        signaler "$drapeau doit valoir 0 en production."
    fi
done

# Traefik est une pile a part : le compose de prod rejoint son reseau, sans le creer.
# / Traefik is a separate stack: the production compose joins its network.
if ! docker network inspect frontend >/dev/null 2>&1; then
    signaler "le reseau Docker « frontend » (Traefik) n'existe pas : lancer la pile Traefik."
fi

if ! docker compose version >/dev/null 2>&1; then
    signaler "docker compose (version 2) est absent."
fi

if ! command -v at >/dev/null; then
    signaler "at est absent (necessaire a make update_nuit) : apt install at."
fi

# La sauvegarde est lancee par la crontab de l'hote (`docker exec lespass_django
# /DjangoFiles/cron/saveDb.sh`). Elle peut etre dans la crontab d'un autre utilisateur :
# ce n'est qu'un avertissement.
# / The backup runs from the host crontab; it may belong to another user.
if ! crontab -l 2>/dev/null | grep -q "saveDb.sh"; then
    signaler "aucune ligne saveDb.sh dans la crontab de $(whoami) (sauvegarde a :00 et :30). A verifier si elle est dans celle de root."
fi

echo ""
if [ "$nombre_de_points_a_traiter" -eq 0 ]; then
    echo "Tout est pret. Verifier le rendu du compose :"
else
    echo "$nombre_de_points_a_traiter point(s) a traiter (relancer make env pour verifier). Ensuite :"
fi
echo "  docker compose -f docker-compose.prod.yml config -q"
