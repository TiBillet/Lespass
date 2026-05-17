"""
Script local de backfill geoloc via Nominatim
/ Local geocoding backfill script via Nominatim

LOCALISATION : TECH_DOC/SESSIONS/ONBOARD/scripts/nominatim_backfill.py

But : prend le JSON produit par `export_tenants_addresses --only-incomplete`
et appelle Nominatim pour chaque tenant qui n'a PAS de lat/long.
A LANCER DEPUIS LE POSTE DU MAINTENEUR, JAMAIS DEPUIS LA PROD.
/ Goal: take the JSON from `export_tenants_addresses --only-incomplete` and
call Nominatim for each tenant missing lat/long.
RUN FROM THE MAINTAINER'S LAPTOP, NEVER FROM PROD.

PRINCIPE DE SAFETY :
- On ne reecrit JAMAIS l'adresse existante d'un tenant.
- On cherche UNIQUEMENT les coordonnees GPS (lat/long).
- Chaque resultat est annote d'un niveau de confiance (high/medium/low)
  et d'un flag needs_human_review.
- Le futur script d'import ne prendra QUE les "high" + needs_review=false.
/ SAFETY PRINCIPLE:
- We NEVER overwrite a tenant's existing address.
- We ONLY look up GPS coordinates (lat/long).
- Each result is annotated with a confidence level (high/medium/low)
  and a needs_human_review flag.
- The future import script will ONLY take "high" + needs_review=false.

CLASSIFICATION DES TENANTS EN 3 BUCKETS :
- full_address  : street_address ET city remplis -> Nominatim avec full query, confidence high
- partial_address : city seule (sans street) -> Nominatim avec city+country, confidence medium
                    (Nominatim repondra au centre-ville, ce qui est imprecis)
- name_only     : juste un nom de structure -> Nominatim avec organisation + countrycodes filter,
                  cross-check fuzzy, confidence low, needs_human_review forcement true

POURQUOI EN LOCAL :
- Nominatim public impose 1 req/s strict + User-Agent identifiable obligatoire.
- ~400 tenants -> ~7 minutes de requetes etalees.
- Si Nominatim rate-limite, c'est l'IP du mainteneur, pas celle de la prod.

USAGE :
    # 1. Generer le JSON source depuis le container Lespass :
    docker exec lespass_django poetry run python manage.py \\
        export_tenants_addresses --only-incomplete --output=/tmp/a_relancer.json
    docker cp lespass_django:/tmp/a_relancer.json ./a_relancer.json

    # 2. Lancer le backfill EN LOCAL :
    python nominatim_backfill.py ./a_relancer.json ./geocoded.json

    # Test sur 5 tenants seulement
    python nominatim_backfill.py ./a_relancer.json ./geocoded.json --limit 5

    # Reprise apres crash / Ctrl+C
    python nominatim_backfill.py ./a_relancer.json ./geocoded.json --resume

    # Skip les recherches par nom seul (plus sur, mais moins de couverture)
    python nominatim_backfill.py ./a_relancer.json ./geocoded.json --no-name-search

    # Limiter aux DOM-TOM seulement
    python nominatim_backfill.py ./a_relancer.json ./geocoded.json --country-codes re,yt,mq,gp,gf

DEPENDENCIES : Python 3 (urllib + json + time natifs).
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError


# --- Constantes Nominatim ---
# --- Nominatim constants ---

# Politique d'usage publique : 1 req/s strict. Marge de 100ms.
# / Public usage policy: 1 req/s strict. 100ms margin.
DELAI_ENTRE_REQUETES_SEC = 1.1

# User-Agent obligatoire et identifiable (sinon ban Nominatim).
# / Mandatory identifiable User-Agent (otherwise Nominatim bans).
USER_AGENT = "TiBillet-Onboard-Backfill/1.0 (contact@tibillet.re)"

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"

TIMEOUT_REQ_SEC = 10

# Sauvegarde intermediaire toutes les N requetes (resiste a Ctrl+C / crash).
# / Intermediate save every N requests (survives Ctrl+C / crash).
INTERVALLE_SAUVEGARDE = 10

# Pays par defaut : France metropole + DOM-TOM + collectivites.
# Reduit massivement les faux positifs internationaux pour les recherches par nom.
# / Default countries: mainland France + DOM-TOM + collectivities.
# Massively reduces international false positives for name-based searches.
COUNTRY_CODES_DEFAUT = "fr,re,yt,mq,gp,gf,nc,pf,bl,mf,pm,wf"

# Types Nominatim a rejeter pour les recherches par nom seul.
# Un match "city" ou "village" sur un nom de structure est presque
# toujours un homonyme (le nom de la structure = nom de la ville).
# / Nominatim types to reject for name-only searches.
# A "city" or "village" match on a structure name is almost always a homonym.
TYPES_REJETES_NAME_ONLY = {"city", "village", "town", "hamlet", "administrative", "state", "county"}

# Codes HTTP qui declenchent un retry avec backoff.
# / HTTP codes that trigger a backoff retry.
CODES_RETRY = {429, 503, 504}
MAX_RETRIES = 2
DELAI_BACKOFF_SEC = 30


# --- Helpers ---

def formater_duree(secondes):
    """
    Formate une duree en h/m/s pour l'affichage humain (ETA, temps ecoule).
    / Formats a duration into h/m/s for human display (ETA, elapsed).
    """
    if secondes < 1:
        return "<1s"
    if secondes < 60:
        return f"{int(secondes)}s"
    minutes_totales = int(secondes // 60)
    secondes_restantes = int(secondes % 60)
    if minutes_totales < 60:
        return f"{minutes_totales}m{secondes_restantes:02d}s"
    heures = minutes_totales // 60
    minutes_restantes = minutes_totales % 60
    return f"{heures}h{minutes_restantes:02d}m"


def normaliser_pour_comparaison(texte):
    """
    Normalise une chaine pour comparaison souple : lowercase + espaces compacts.
    / Loosely normalizes a string for comparison: lowercase + compact spaces.
    """
    if not texte:
        return ""
    return " ".join(str(texte).lower().split())


def nom_present_dans_display_name(nom_tenant, display_name):
    """
    Verifie si le nom du tenant apparait dans le display_name renvoye par OSM.
    Cross-check anti-homonymie pour les recherches par nom.
    / Checks if the tenant name appears in OSM's display_name.
    Anti-homonym cross-check for name-based searches.
    """
    nom_norm = normaliser_pour_comparaison(nom_tenant)
    dn_norm = normaliser_pour_comparaison(display_name)
    if not nom_norm or not dn_norm:
        return False
    return nom_norm in dn_norm


# --- Classification tenant -> bucket + query ---

def classer_et_construire_query(tenant, country_codes, autoriser_name_search):
    """
    Classe le tenant en bucket et construit la query Nominatim correspondante.
    / Classifies the tenant into a bucket and builds the matching Nominatim query.

    Renvoie un dict :
      {
        "bucket": "full_address" | "partial_address" | "name_only" | "no_data",
        "query": str | None,
        "params_extra": dict (ex: countrycodes pour name_only),
        "confidence_attendue": "high" | "medium" | "low" | None,
        "needs_review_force": bool,
      }
    """
    schema_org = tenant.get("adresse_schema_org") or {}
    legacy = tenant.get("adresse_legacy") or {}

    # Champs adresse normalises (schema.org prioritaire)
    # / Normalized address fields (schema.org first)
    street = schema_org.get("street_address") or legacy.get("adress")
    postal_code_value = schema_org.get("postal_code") or legacy.get("postal_code")
    city = schema_org.get("address_locality") or legacy.get("city")
    country = schema_org.get("address_country")

    # Bucket 1 : adresse complete (street + ville au minimum)
    # / Bucket 1: full address (street + city at minimum)
    if street and city:
        morceaux = [str(street).strip()]
        if postal_code_value:
            morceaux.append(str(postal_code_value).strip())
        morceaux.append(str(city).strip())
        if country:
            morceaux.append(str(country).strip())
        return {
            "bucket": "full_address",
            "query": ", ".join(morceaux),
            "params_extra": {},
            "confidence_attendue": "high",
            "needs_review_force": False,
        }

    # Bucket 2 : adresse partielle (ville seule, sans rue)
    # / Bucket 2: partial address (city only, no street)
    if city:
        morceaux = []
        if postal_code_value:
            morceaux.append(str(postal_code_value).strip())
        morceaux.append(str(city).strip())
        if country:
            morceaux.append(str(country).strip())
        return {
            "bucket": "partial_address",
            "query": ", ".join(morceaux),
            "params_extra": {},
            # On marque medium parce que Nominatim repondra au centre-ville,
            # ce qui est imprecis pour le lieu reel du tenant.
            # / Marked medium because Nominatim returns city centre, imprecise.
            "confidence_attendue": "medium",
            "needs_review_force": True,
        }

    # Bucket 3 : juste un nom d'organisation (ou tenant_name en fallback)
    # / Bucket 3: just an organisation name (or tenant_name fallback)
    nom_a_chercher = tenant.get("organisation") or tenant.get("tenant_name")
    if nom_a_chercher and autoriser_name_search:
        return {
            "bucket": "name_only",
            "query": str(nom_a_chercher).strip(),
            # Filtre pays : reduit drastiquement les homonymes internationaux
            # / Country filter: drastically reduces international homonyms
            "params_extra": {"countrycodes": country_codes},
            "confidence_attendue": "low",
            "needs_review_force": True,
        }

    # Bucket 4 : rien d'exploitable
    # / Bucket 4: nothing usable
    return {
        "bucket": "no_data",
        "query": None,
        "params_extra": {},
        "confidence_attendue": None,
        "needs_review_force": False,
    }


# --- Appel Nominatim avec retry ---

def appeler_nominatim(query, params_extra):
    """
    Appelle Nominatim avec retry sur 429/503/504.
    / Calls Nominatim with retry on 429/503/504.
    """
    parametres = {
        "q": query,
        "format": "json",
        "limit": 3,
        "addressdetails": 1,
    }
    parametres.update(params_extra)
    url = f"{URL_NOMINATIM}?{urllib.parse.urlencode(parametres)}"
    requete = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for tentative in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(requete, timeout=TIMEOUT_REQ_SEC) as reponse:
                return json.loads(reponse.read().decode("utf-8"))
        except HTTPError as erreur_http:
            if erreur_http.code in CODES_RETRY and tentative < MAX_RETRIES:
                delai_attente = DELAI_BACKOFF_SEC * (tentative + 1)
                print(
                    f"  ! HTTP {erreur_http.code} -> backoff {delai_attente}s "
                    f"(tentative {tentative + 1}/{MAX_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(delai_attente)
                continue
            return {"error": f"HTTP {erreur_http.code}: {erreur_http.reason}"}
        except URLError as erreur_url:
            if tentative < MAX_RETRIES:
                time.sleep(DELAI_BACKOFF_SEC)
                continue
            return {"error": f"URLError: {erreur_url.reason}"}
        except Exception as erreur_inconnue:
            return {"error": f"{type(erreur_inconnue).__name__}: {erreur_inconnue}"}


# --- Validation des resultats Nominatim ---

def construire_entree_nominatim(reponse_brute, classification, tenant):
    """
    Transforme la reponse brute Nominatim + la classification en entree finale.
    Applique les regles de safety : cross-check homonymie, rejet de types
    suspects, downgrade confidence si match douteux.
    / Transforms raw Nominatim response + classification into final entry.
    Applies safety rules: homonym cross-check, suspect type rejection,
    confidence downgrade if dubious match.
    """
    bucket = classification["bucket"]
    confidence = classification["confidence_attendue"]
    needs_review = classification["needs_review_force"]

    # Aucun resultat OSM
    # / No OSM result
    if not reponse_brute:
        return {
            "status": "no_match",
            "bucket": bucket,
            "query": classification["query"],
            "confidence": None,
            "needs_human_review": True,
        }

    # On regarde le premier resultat
    # / Look at the first result
    premier = reponse_brute[0]
    type_resultat = premier.get("type", "")
    class_resultat = premier.get("class", "")
    display_name = premier.get("display_name", "")

    # Regle anti-homonymie : pour bucket name_only, on rejette les types
    # geographiques larges (city/village/town) ET on exige que le nom du
    # tenant apparaisse dans display_name.
    # / Anti-homonym rule: for name_only bucket, reject broad geographic types
    # AND require the tenant name to appear in display_name.
    if bucket == "name_only":
        if type_resultat in TYPES_REJETES_NAME_ONLY:
            return {
                "status": "rejected_homonym",
                "bucket": bucket,
                "query": classification["query"],
                "reason": f"type={type_resultat} (homonyme probable, ex: ville)",
                "confidence": None,
                "needs_human_review": True,
                "raw_first_match": {
                    "display_name": display_name,
                    "type": type_resultat,
                    "class": class_resultat,
                },
            }

        nom_recherche = classification["query"]
        if not nom_present_dans_display_name(nom_recherche, display_name):
            # Le nom ne se retrouve pas dans le display_name -> tres suspect
            # / Name not found in display_name -> very suspicious
            return {
                "status": "rejected_name_mismatch",
                "bucket": bucket,
                "query": classification["query"],
                "reason": "nom du tenant absent du display_name",
                "confidence": None,
                "needs_human_review": True,
                "raw_first_match": {
                    "display_name": display_name,
                    "type": type_resultat,
                    "class": class_resultat,
                },
            }

    # Si on a >= 2 resultats avec des coords proches, on est ambigu mais utilisable.
    # Si tres differents, c'est vraiment ambigu et needs_review.
    # / If >= 2 results with close coords, ambiguous but usable.
    # If very different, truly ambiguous and needs_review.
    alternatives = []
    if len(reponse_brute) > 1:
        for autre in reponse_brute[1:]:
            alternatives.append({
                "display_name": autre.get("display_name"),
                "lat": autre.get("lat"),
                "lon": autre.get("lon"),
                "type": autre.get("type"),
            })
        # Plusieurs matches : downgrade systematique si confidence high.
        # / Multiple matches: systematic downgrade if confidence was high.
        if confidence == "high":
            confidence = "medium"
        needs_review = True

    statut_final = "ok"
    if needs_review:
        statut_final = "needs_review"

    return {
        "status": statut_final,
        "bucket": bucket,
        "query": classification["query"],
        "confidence": confidence,
        "needs_human_review": needs_review,
        "results_count": len(reponse_brute),
        "latitude": premier.get("lat"),
        "longitude": premier.get("lon"),
        "display_name": display_name,
        "importance": premier.get("importance"),
        "type": type_resultat,
        "class": class_resultat,
        "alternatives": alternatives,
    }


# --- IO ---

def sauvegarder_resultats(chemin, resultats):
    """
    Ecrit le JSON de sortie. Helper silencieux.
    / Writes the output JSON. Silent helper.
    """
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(resultats, fichier, indent=2, ensure_ascii=False)


def afficher_progression(numero_courant, total, t0, file=sys.stderr):
    """
    Affiche une ligne de progression avec pourcentage et ETA.
    / Prints a progression line with percentage and ETA.
    """
    pourcentage = (numero_courant / total * 100) if total else 0
    duree_ecoulee = time.time() - t0
    if numero_courant == 0:
        eta_str = "?"
    else:
        cadence = duree_ecoulee / numero_courant
        restantes = total - numero_courant
        eta_str = formater_duree(restantes * cadence)
    print(
        f"  -> progression {numero_courant}/{total} "
        f"({pourcentage:.1f}%) | ecoule {formater_duree(duree_ecoulee)} "
        f"| ETA {eta_str}",
        file=file,
    )


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill geoloc Nominatim pour les tenants Lespass sans coordonnees.\n"
            "A LANCER EN LOCAL, JAMAIS DEPUIS LA PROD.\n"
            "Ne reecrit JAMAIS d'adresse existante. Annotations safety detaillees."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_json",
        help="JSON produit par `manage.py export_tenants_addresses [--only-incomplete]`",
    )
    parser.add_argument(
        "output_json",
        help="JSON de sortie, enrichi avec un champ 'nominatim' par tenant.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite aux N premiers tenants (utile pour tester).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reprend apres un crash : skip les tenants deja dans output_json.",
    )
    parser.add_argument(
        "--no-name-search",
        action="store_true",
        help="Skip la recherche pour les tenants n'ayant qu'un nom (plus sur).",
    )
    parser.add_argument(
        "--country-codes",
        type=str,
        default=COUNTRY_CODES_DEFAUT,
        help=f"Pays autorises pour la recherche par nom (defaut: {COUNTRY_CODES_DEFAUT})",
    )
    args = parser.parse_args()

    # --- Chargement source ---
    with open(args.input_json, "r", encoding="utf-8") as fichier:
        tenants_source = json.load(fichier)

    if args.limit:
        tenants_source = tenants_source[: args.limit]

    # --- Mode reprise ---
    deja_traites_par_schema = {}
    if args.resume and os.path.exists(args.output_json):
        with open(args.output_json, "r", encoding="utf-8") as fichier:
            entrees_existantes = json.load(fichier)
        for entree in entrees_existantes:
            deja_traites_par_schema[entree["schema"]] = entree
        print(
            f"Reprise : {len(deja_traites_par_schema)} tenants deja traites, skip.",
            file=sys.stderr,
        )

    # --- Pre-pass : classification de chaque tenant ---
    # On pre-classe tout pour connaitre le nombre exact de requetes a envoyer
    # et calculer un ETA correct.
    # / Pre-classify all tenants to know the exact number of requests
    # and compute a correct ETA.
    tenants_a_traiter = []
    nombre_skipped_deja_geocode = 0
    nombre_skipped_no_data = 0

    for tenant in tenants_source:
        if tenant["schema"] in deja_traites_par_schema:
            continue
        if tenant.get("has_geoloc"):
            nombre_skipped_deja_geocode += 1
            continue
        classification = classer_et_construire_query(
            tenant, args.country_codes, not args.no_name_search
        )
        if classification["bucket"] == "no_data":
            nombre_skipped_no_data += 1
        tenants_a_traiter.append((tenant, classification))

    # Nombre de requetes Nominatim qui seront vraiment envoyees
    # / Number of Nominatim requests that will actually be sent
    nombre_requetes_prevues = sum(
        1 for _, classif in tenants_a_traiter if classif["query"] is not None
    )

    print(
        f"\n--- Pre-pass classification ---\n"
        f"Tenants en entree         : {len(tenants_source)}\n"
        f"Deja geocodes (skip)      : {nombre_skipped_deja_geocode}\n"
        f"Sans donnee (skip)        : {nombre_skipped_no_data}\n"
        f"Requetes Nominatim prevues: {nombre_requetes_prevues}\n"
        f"ETA approximatif          : {formater_duree(nombre_requetes_prevues * DELAI_ENTRE_REQUETES_SEC)}\n",
        file=sys.stderr,
    )

    # --- Pass principal ---
    resultats = list(deja_traites_par_schema.values())
    compteurs = {
        "ok": 0,
        "needs_review": 0,
        "rejected_homonym": 0,
        "rejected_name_mismatch": 0,
        "no_match": 0,
        "skipped_no_data": 0,
        "error": 0,
    }
    nombre_requetes_envoyees = 0
    t0 = time.time()

    for tenant, classification in tenants_a_traiter:
        # Bucket no_data : on enregistre direct sans appel Nominatim
        # / no_data bucket: record directly without calling Nominatim
        if classification["query"] is None:
            compteurs["skipped_no_data"] += 1
            resultats.append({
                **tenant,
                "nominatim": {
                    "status": "skipped_no_data",
                    "bucket": classification["bucket"],
                    "confidence": None,
                    "needs_human_review": True,
                    "reason": "aucune adresse ni nom exploitable",
                },
            })
            continue

        print(
            f"[{nombre_requetes_envoyees + 1}/{nombre_requetes_prevues}] "
            f"{tenant['schema']} ({classification['bucket']}) : "
            f"{classification['query'][:80]}",
            file=sys.stderr,
        )

        reponse_brute = appeler_nominatim(
            classification["query"], classification["params_extra"]
        )
        nombre_requetes_envoyees += 1

        # Erreur reseau / HTTP
        # / Network / HTTP error
        if isinstance(reponse_brute, dict) and "error" in reponse_brute:
            compteurs["error"] += 1
            resultats.append({
                **tenant,
                "nominatim": {
                    "status": "error",
                    "bucket": classification["bucket"],
                    "query": classification["query"],
                    "error": reponse_brute["error"],
                    "confidence": None,
                    "needs_human_review": True,
                },
            })
        else:
            entree = construire_entree_nominatim(reponse_brute, classification, tenant)
            statut = entree["status"]
            if statut in compteurs:
                compteurs[statut] += 1
            resultats.append({**tenant, "nominatim": entree})

        # Sauvegarde + progression periodiques
        # / Periodic save + progression
        if nombre_requetes_envoyees % INTERVALLE_SAUVEGARDE == 0:
            sauvegarder_resultats(args.output_json, resultats)
            afficher_progression(nombre_requetes_envoyees, nombre_requetes_prevues, t0)

        # Rate limit strict
        # / Strict rate limit
        time.sleep(DELAI_ENTRE_REQUETES_SEC)

    # Sauvegarde finale
    # / Final save
    sauvegarder_resultats(args.output_json, resultats)

    duree_totale = time.time() - t0

    # Stats finales detaillees
    # / Detailed final stats
    print(
        f"\n--- Stats backfill Nominatim ---\n"
        f"Duree totale             : {formater_duree(duree_totale)}\n"
        f"Requetes envoyees        : {nombre_requetes_envoyees}\n"
        f"\n"
        f"=== Resultats SAFE (importables direct) ===\n"
        f"  ok (high confidence)   : {compteurs['ok']}\n"
        f"\n"
        f"=== Resultats a REVOIR humainement ===\n"
        f"  needs_review (medium)  : {compteurs['needs_review']}\n"
        f"  rejected_homonym       : {compteurs['rejected_homonym']}\n"
        f"  rejected_name_mismatch : {compteurs['rejected_name_mismatch']}\n"
        f"  no_match               : {compteurs['no_match']}\n"
        f"  skipped_no_data        : {compteurs['skipped_no_data']}\n"
        f"\n"
        f"=== Problemes techniques ===\n"
        f"  erreurs reseau/HTTP    : {compteurs['error']}\n"
        f"\n"
        f"Sortie : {args.output_json}\n"
        f"\n"
        f"Filtrer les imports safe avec :\n"
        f"  jq '.[] | select(.nominatim.status==\"ok\")' {args.output_json}\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
