#!/usr/bin/env bash
# Lance une suite de tests Lespass dans le conteneur, avec ou sans Stripe réel.
# / Runs a Lespass test suite in the container, with or without real Stripe.
#
# LOCALISATION : scripts/lancer_tests.sh — appelé par le Makefile (make test, make e2e…).
#
# Usage : scripts/lancer_tests.sh <python|e2e|couverture> <sans-stripe|stripe> [arguments pytest…]
#   Sans argument pytest, toute la suite est lancée (tests/pytest/ et booking/tests/, ou tests/e2e/).
#   / Without pytest arguments, the whole suite runs.
#   `couverture` lance la suite pytest en mesurant la couverture du code (pytest-cov).
#   Variable optionnelle FICHIERS="a.py,b.py" : détail ligne à ligne de ces fichiers.
#   / `couverture` runs the pytest suite while measuring code coverage (pytest-cov).
#   Optional FICHIERS="a.py,b.py": line-by-line detail for these files.
#
# FLUX :
# 1. Vérifie que le serveur live répond (les tests API et E2E l'appellent).
# 2. Récupère une clé API de test (la fixture ne sait pas la créer dans le conteneur).
# 3. Avec Stripe réel : pose STRIPE_REEL=1 ; en E2E, vérifie que `stripe listen` tourne.
# 4. Lance pytest dans le conteneur. poetry ne tourne JAMAIS sur l'hôte : le .venv est partagé.
# 5. En mode couverture : affiche le total, écrit le rapport HTML dans htmlcov/.

set -euo pipefail

SUITE="${1:-}"
MODE="${2:-}"
if [ "$SUITE" != "python" ] && [ "$SUITE" != "e2e" ] && [ "$SUITE" != "couverture" ]; then
    echo "Usage : $0 <python|e2e|couverture> <sans-stripe|stripe> [arguments pytest…]" >&2
    exit 2
fi
if [ "$MODE" != "sans-stripe" ] && [ "$MODE" != "stripe" ]; then
    echo "Usage : $0 <python|e2e|couverture> <sans-stripe|stripe> [arguments pytest…]" >&2
    exit 2
fi
shift 2

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

# 3. Stripe réel : une seule variable pour les deux suites.
# / Real Stripe: a single variable for both suites.
if [ "$MODE" = "stripe" ]; then
    variables_du_conteneur+=(-e "STRIPE_REEL=1")

    # Les parcours E2E à webhook attendent `stripe listen`, qui tourne sur l'hôte (byobu).
    # Le conteneur ne voit pas les processus de l'hôte : on vérifie ici, avant de lancer.
    # On cherche le processus, pas le nom du panneau : installé par npm, le CLI s'affiche « node ».
    # / E2E webhook journeys need `stripe listen`, running on the host (byobu). We look for the
    # process, not the pane name: installed through npm, the CLI shows up as "node".
    if [ "$SUITE" = "e2e" ]; then
        if ! pgrep -f "stripe listen.*/api/webhook_stripe/" > /dev/null; then
            echo "\`stripe listen\` ne tourne pas : le lancer dans byobu avant make e2e-stripe." >&2
            exit 1
        fi
    fi
fi

# 4. Sans argument, toute la suite. booking/tests/ (moteur de créneaux) en fait partie :
# hors de la suite, ses tests ne tournaient plus et avaient cassé sans que personne le voie.
# / Without arguments, the whole suite, booking/tests/ (slot engine) included.
if [ "$#" -eq 0 ]; then
    if [ "$SUITE" = "e2e" ]; then
        set -- tests/e2e/ -q
    else
        set -- tests/pytest/ booking/tests/ -q
    fi
fi

if [ "$SUITE" != "couverture" ]; then
    docker exec "${variables_du_conteneur[@]}" "$CONTENEUR" poetry run pytest "$@"
    exit $?
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
