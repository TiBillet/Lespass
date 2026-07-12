#!/usr/bin/env python3
"""
Cree une cle API v2 (ExternalApiKey) de test sur un tenant TiBillet/Lespass.
/ Creates a test API v2 key (ExternalApiKey) on a TiBillet/Lespass tenant.

LOCALISATION : api_v2/skills/tibillet-api/scripts/creer_cle_api.py
(lie depuis .claude/skills/tibillet-api par un symlink local, non committe)

Le script tourne depuis le HOTE : il execute du code Django dans le conteneur via
`docker exec <container> ... manage.py shell -c`. Il imprime la cle en clair
(elle n'est visible qu'a la creation, jamais apres).
/ Runs from the HOST: executes Django code inside the container. Prints the key in
clear (only visible at creation time).

Exemple / Example :
    python creer_cle_api.py --tenant lespass --perms page,event,product
    # -> APIKEY=xxxx.yyyy  (a mettre dans le header Authorization: Api-Key xxxx.yyyy)

Puis / Then :
    curl -k -H "Authorization: Api-Key xxxx.yyyy" \\
         https://lespass.tibillet.localhost/api/v2/pages/block-types/
"""
import argparse
import re
import subprocess
import sys

# Permissions granulaires d'ExternalApiKey (cf. BaseBillet/models.py). `page` ouvre
# les pages ET les blocs. / Granular ExternalApiKey permissions; `page` opens pages AND blocs.
PERMISSIONS_VALIDES = {
    "event", "product", "page", "membership",
    "reservation", "ticket", "wallet", "sale", "crowd",
}

# Gabarit du code Django execute dans le conteneur. Les placeholders {..} sont
# remplaces par des valeurs DEJA validees (tenant/name : alphanum simple ; perms :
# liste blanche) -> pas d'injection possible.
# / Django code template run inside the container. Placeholders are filled with
# ALREADY-validated values (whitelist), so no injection is possible.
CODE_DJANGO = """
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import ExternalApiKey
from rest_framework_api_key.models import APIKey
try:
    tenant = Client.objects.get(schema_name="{tenant}")
except Client.DoesNotExist:
    print("ERREUR: tenant introuvable: {tenant}")
    raise SystemExit(1)
with tenant_context(tenant):
    # On repart propre : on retire une eventuelle cle de meme nom (helper de test).
    ExternalApiKey.objects.filter(name="{name}").delete()
    objet_cle, cle_en_clair = APIKey.objects.create_key(name="{name}")
    ExternalApiKey.objects.create(
        name="{name}", key=objet_cle, user=None, {perms_kwargs}
    )
    print("APIKEY=" + cle_en_clair)
"""


def valider_identifiant(valeur, quoi):
    """Autorise seulement [a-zA-Z0-9_-] (anti-injection dans le code genere)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", valeur or ""):
        sys.exit(f"ERREUR: {quoi} invalide (attendu [A-Za-z0-9_-]+): {valeur!r}")
    return valeur


def main():
    analyseur = argparse.ArgumentParser(
        description="Cree une cle API v2 de test sur un tenant TiBillet.",
    )
    analyseur.add_argument("--tenant", default="lespass",
                           help="schema_name du tenant (defaut: lespass)")
    analyseur.add_argument("--perms", default="page",
                           help="permissions separees par virgule parmi: "
                                + ", ".join(sorted(PERMISSIONS_VALIDES)))
    analyseur.add_argument("--name", default=None,
                           help="nom de la cle (defaut: cle-api-<perms>)")
    analyseur.add_argument("--container", default="lespass_django",
                           help="nom du conteneur Django (defaut: lespass_django)")
    args = analyseur.parse_args()

    tenant = valider_identifiant(args.tenant, "tenant")

    # Parse + valide les permissions contre la liste blanche.
    # / Parse + validate permissions against the whitelist.
    demandees = [p.strip() for p in args.perms.split(",") if p.strip()]
    inconnues = [p for p in demandees if p not in PERMISSIONS_VALIDES]
    if inconnues:
        sys.exit(f"ERREUR: permission(s) inconnue(s): {', '.join(inconnues)}\n"
                 f"Valides: {', '.join(sorted(PERMISSIONS_VALIDES))}")
    if not demandees:
        sys.exit("ERREUR: au moins une permission requise (--perms).")

    nom = args.name or ("cle-api-" + "-".join(sorted(demandees)))
    # ExternalApiKey.name = CharField(max_length=30) : on tronque pour eviter un
    # DataError Postgres cryptique quand plusieurs permissions rallongent le nom.
    # / ExternalApiKey.name is max_length=30: truncate to avoid a cryptic DataError.
    nom = nom[:30]
    nom = valider_identifiant(nom, "name")

    # Construit les kwargs de permission (ex: page=True, event=True).
    # / Build the permission kwargs (e.g. page=True, event=True).
    perms_kwargs = ", ".join(f"{p}=True" for p in sorted(demandees))

    code = CODE_DJANGO.format(
        tenant=tenant, name=nom, perms_kwargs=perms_kwargs,
    )

    # docker exec SANS shell=True : la liste d'arguments evite toute interpretation
    # shell (le code Django est passe tel quel a `manage.py shell -c`).
    # / docker exec WITHOUT shell=True: the arg list avoids any shell interpretation.
    commande = [
        "docker", "exec", args.container,
        "poetry", "run", "python", "/DjangoFiles/manage.py", "shell", "-c", code,
    ]
    resultat = subprocess.run(commande, capture_output=True, text=True)

    # On isole la ligne APIKEY= (le shell Django peut logger d'autres lignes).
    # / Extract the APIKEY= line (the Django shell may log other lines).
    cle = None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("APIKEY="):
            cle = ligne[len("APIKEY="):].strip()
    if not cle:
        sys.stderr.write(resultat.stdout + "\n" + resultat.stderr + "\n")
        sys.exit("ERREUR: creation de la cle echouee (voir la sortie ci-dessus).")

    print(f"Tenant      : {tenant}")
    print(f"Permissions : {', '.join(sorted(demandees))}")
    print(f"Nom de cle  : {nom}")
    print(f"APIKEY      : {cle}")
    print()
    print("Exemple d'appel :")
    print(f'  curl -k -H "Authorization: Api-Key {cle}" \\')
    print(f"       https://{tenant}.tibillet.localhost/api/v2/pages/block-types/")


if __name__ == "__main__":
    main()
