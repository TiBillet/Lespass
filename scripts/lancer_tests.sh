#!/usr/bin/env bash
# Lance une suite de tests Lespass dans le conteneur, tests Stripe réel compris.
# / Runs a Lespass test suite in the container, real-Stripe tests included.
#
# LOCALISATION : scripts/lancer_tests.sh — appelé par le Makefile (make test, make e2e…).
#
# Usage : scripts/lancer_tests.sh <python|e2e|e2e-visible|couverture> [arguments pytest…]
#   e2e-visible : les E2E dans une fenetre Chromium VISIBLE sur l'hote, ralentie
#   (variable LENTEUR en millisecondes, 800 par defaut), avec un journal lisible.
#   / e2e-visible: E2E in a VISIBLE, slowed-down Chromium window on the host, with a log.
#   Sans argument pytest, toute la suite est lancée (tests/pytest/, booking/tests/ et
#   onboard/tests/, ou tests/e2e/).
#   / Without pytest arguments, the whole suite runs.
#   `couverture` lance la suite pytest en mesurant la couverture du code (pytest-cov).
#   Variable optionnelle FICHIERS="a.py,b.py" : détail ligne à ligne de ces fichiers.
#   / `couverture` runs the pytest suite while measuring code coverage (pytest-cov).
#   Optional FICHIERS="a.py,b.py": line-by-line detail for these files.
#
# FLUX :
# 1. Vérifie que le serveur live répond (les tests API et E2E l'appellent).
# 2. Récupère une clé API de test (la fixture ne sait pas la créer dans le conteneur).
# 3. En E2E : regarde si `stripe listen` tourne et le dit aux tests (STRIPE_LISTEN=1/0).
#    Les tests qui en ont besoin ÉCHOUENT sans lui : aucun n'est ignoré.
# 4. Lance pytest dans le conteneur. poetry ne tourne JAMAIS sur l'hôte : le .venv est partagé.
# 5. En mode couverture : affiche le total, écrit le rapport HTML dans htmlcov/.

set -euo pipefail

SUITE="${1:-}"
if [ "$SUITE" != "python" ] && [ "$SUITE" != "e2e" ] && [ "$SUITE" != "e2e-visible" ] \
    && [ "$SUITE" != "couverture" ]; then
    echo "Usage : $0 <python|e2e|e2e-visible|couverture> [arguments pytest…]" >&2
    exit 2
fi
shift 1

CONTENEUR="lespass_django"
URL_DU_SERVEUR="https://lespass.tibillet.localhost/"

# 1. Le serveur live doit répondre. Un 502 veut dire que runserver est mort dans byobu.
# / The live server must answer. A 502 means runserver died in byobu.
code_http=$(curl -sk -o /dev/null -w "%{http_code}" "$URL_DU_SERVEUR" || true)
if [ "$code_http" != "200" ]; then
    echo "Le serveur live ne répond pas (HTTP $code_http) : relancer runserver dans byobu." >&2
    exit 1
fi

# 2. Clé API de test, passée aux tests par la variable API_KEY.
# / Test API key, passed to the tests through API_KEY.
cle_api=$(docker exec -e TEST=1 "$CONTENEUR" poetry run python /DjangoFiles/manage.py test_api_key 2>/dev/null | tail -1)
variables_du_conteneur=(-e "API_KEY=$cle_api")

# 3. `stripe listen` : les parcours E2E à webhook l'attendent. Il tourne sur l'hôte (byobu),
# et le conteneur ne voit pas les processus de l'hôte : on regarde ici, et on le dit aux
# tests par STRIPE_LISTEN. On ne s'arrête PAS : les autres tests tournent, et ceux qui en
# ont besoin échouent (tests/e2e/conftest.py). On cherche le processus, pas le nom du
# panneau : installé par npm, le CLI s'affiche « node ».
# / 3. `stripe listen`: E2E webhook journeys need it. It runs on the host; the container
# cannot see host processes, so we check here and tell the tests through STRIPE_LISTEN.
# We do NOT stop: the tests that need it fail instead.
if [ "$SUITE" = "e2e" ] || [ "$SUITE" = "e2e-visible" ]; then
    if pgrep -f "stripe listen.*/api/webhook_stripe/" > /dev/null; then
        variables_du_conteneur+=(-e "STRIPE_LISTEN=1")
    else
        variables_du_conteneur+=(-e "STRIPE_LISTEN=0")
        echo "\`stripe listen\` ne tourne pas : les parcours à webhook Stripe vont échouer." >&2
    fi
fi

# 3 bis. Supervision humaine : un serveur de navigateur Playwright tourne sur l'HOTE, et
# les tests du conteneur s'y connectent (tests/e2e/conftest.py, E2E_NAVIGATEUR_DISTANT).
# Meme version que le Playwright du conteneur, sinon la connexion est refusee. Il ecoute
# sur l'adresse Docker de l'hote seulement, pas sur le reseau local. `setsid` le met dans
# son propre groupe de processus : tuer `npx` seul laisserait tourner le `node` qu'il lance.
# / 3 bis. Human supervision: a Playwright browser server runs on the HOST; container
# tests connect to it. Same version as in the container. Own process group via setsid.
if [ "$SUITE" = "e2e-visible" ]; then
    VERSION_DE_PLAYWRIGHT="1.60.0"
    ADRESSE_DU_SERVEUR_DE_NAVIGATEUR="172.17.0.1"
    PORT_DU_SERVEUR_DE_NAVIGATEUR="3999"
    JOURNAL_DU_SERVEUR_DE_NAVIGATEUR="tests/e2e/artefacts/serveur_navigateur.log"

    if ! command -v npx > /dev/null; then
        echo "npx est introuvable sur l'hôte : installer Node.js pour make e2e-visible." >&2
        exit 1
    fi

    # Ubuntu 26.04 n'est pas encore reconnu par Playwright : on lui fait prendre la
    # version Ubuntu 24.04, compatible. / Ubuntu 26.04 is not yet known to Playwright.
    if grep -q 'VERSION_ID="26' /etc/os-release 2>/dev/null; then
        export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE="ubuntu24.04-x64"
    fi

    mkdir -p tests/e2e/artefacts
    setsid npx -y "playwright@${VERSION_DE_PLAYWRIGHT}" run-server \
        --port "$PORT_DU_SERVEUR_DE_NAVIGATEUR" --host "$ADRESSE_DU_SERVEUR_DE_NAVIGATEUR" \
        > "$JOURNAL_DU_SERVEUR_DE_NAVIGATEUR" 2>&1 &
    PID_DU_SERVEUR_DE_NAVIGATEUR=$!
    # Arret du serveur (et de tout son groupe) a la sortie du script, succes ou echec.
    # / Stop the server and its whole group when the script exits, success or failure.
    trap 'kill -- "-$PID_DU_SERVEUR_DE_NAVIGATEUR" 2> /dev/null || true' EXIT

    # Attendre que le serveur ecoute (le premier lancement de npx peut telecharger).
    # / Wait until the server listens (npx may download on first run).
    for _tentative in $(seq 1 60); do
        if (echo > "/dev/tcp/${ADRESSE_DU_SERVEUR_DE_NAVIGATEUR}/${PORT_DU_SERVEUR_DE_NAVIGATEUR}") 2> /dev/null; then
            break
        fi
        sleep 1
    done
    if ! (echo > "/dev/tcp/${ADRESSE_DU_SERVEUR_DE_NAVIGATEUR}/${PORT_DU_SERVEUR_DE_NAVIGATEUR}") 2> /dev/null; then
        echo "Le serveur de navigateur ne démarre pas : voir $JOURNAL_DU_SERVEUR_DE_NAVIGATEUR." >&2
        echo "Premier lancement : npx -y playwright@${VERSION_DE_PLAYWRIGHT} install chromium" >&2
        exit 1
    fi

    variables_du_conteneur+=(
        -e "E2E_NAVIGATEUR_DISTANT=ws://${ADRESSE_DU_SERVEUR_DE_NAVIGATEUR}:${PORT_DU_SERVEUR_DE_NAVIGATEUR}/"
        -e "E2E_LENTEUR=${LENTEUR:-800}"
        -e "E2E_JOURNAL=1"
    )
    echo "Supervision : fenêtre Chromium sur l'écran, ${LENTEUR:-800} ms par action." >&2
    echo "Journal : tests/e2e/artefacts/supervision.log" >&2
fi

# 4. Sans argument, toute la suite. booking/tests/ (moteur de créneaux) et onboard/tests/
# (tunnel de création de lieu) en font partie : hors de la suite, des tests cassent sans que
# personne le voie. onboard/tests/ consomme des lieux du pool « en attente » : lancer la suite
# quand la base de dev est au repos.
# / Without arguments, the whole suite: booking/tests/ (slot engine) and onboard/tests/
# (venue creation funnel) included. onboard/tests/ consumes venues from the waiting pool.
if [ "$#" -eq 0 ]; then
    if [ "$SUITE" = "e2e" ]; then
        set -- tests/e2e/ -q
    elif [ "$SUITE" = "e2e-visible" ]; then
        set -- tests/e2e/
    else
        set -- tests/pytest/ booking/tests/ onboard/tests/ -q
    fi
fi

# En supervision, -v nomme chaque test et -s laisse passer le journal en direct.
# / In supervision, -v names each test and -s lets the log through live.
if [ "$SUITE" = "e2e-visible" ]; then
    set -- -v -s "$@"
fi

if [ "$SUITE" != "couverture" ]; then
    code_de_sortie_pytest=0
    docker exec "${variables_du_conteneur[@]}" "$CONTENEUR" poetry run pytest "$@" \
        || code_de_sortie_pytest=$?
    exit "$code_de_sortie_pytest"
fi

# 5. Couverture. Le fichier de mesure `.coverage` et le rapport `htmlcov/` sont écrits à la
# racine du projet (ignorés par git). La configuration est dans pyproject.toml
# ([tool.coverage.run]). Le rapport est produit même si des tests échouent ; le code de
# sortie reste celui de pytest.
# / 5. Coverage. `.coverage` and `htmlcov/` land at the project root (git-ignored). Config in
# pyproject.toml. The report is produced even when tests fail; the exit code stays pytest's.
code_de_sortie_pytest=0
docker exec "${variables_du_conteneur[@]}" "$CONTENEUR" \
    poetry run pytest --cov --cov-report= "$@" || code_de_sortie_pytest=$?

# Les commandes `coverage` échouent quand il n'y a rien à mesurer. Avec `set -e`, elles
# arrêteraient le script et remplaceraient le code de sortie de pytest : d'où les `||`.
# / `coverage` commands fail when there is no data; `||` keeps pytest's exit code.
pourcentage_total=$(docker exec "$CONTENEUR" poetry run coverage report --format=total) \
    || pourcentage_total="?"
docker exec "$CONTENEUR" poetry run coverage html --quiet \
    || echo "Rapport HTML non produit / HTML report not written" >&2

echo ""
echo "Couverture totale / Total coverage : ${pourcentage_total} %"
echo "Rapport détaillé / Detailed report : htmlcov/index.html"

# Détail ligne à ligne des fichiers demandés (ex. FICHIERS="BaseBillet/services_panier.py").
# / Line-by-line detail of the requested files.
if [ -n "${FICHIERS:-}" ]; then
    echo ""
    docker exec "$CONTENEUR" poetry run coverage report --show-missing --include="$FICHIERS" \
        || echo "Aucune mesure pour FICHIERS=${FICHIERS} / No data for these files" >&2
fi

exit "$code_de_sortie_pytest"
