"""
Script local de backfill geoloc via Nominatim, persistance SQLite
/ Local geocoding backfill script via Nominatim, SQLite persistence

LOCALISATION : TECH_DOC/SESSIONS/ONBOARD/scripts/nominatim_backfill.py

But : prend le JSON produit par `export_tenants_addresses --only-incomplete`,
l'importe dans une SQLite, puis appelle Nominatim pour chaque tenant sans
lat/long et stocke le resultat dans la meme base. Crash-safe, reprise auto.
A LANCER DEPUIS LE POSTE DU MAINTENEUR, JAMAIS DEPUIS LA PROD.
/ Goal: take the JSON from `export_tenants_addresses --only-incomplete`,
import it into a SQLite DB, then call Nominatim for each tenant missing
lat/long and store the result in the same DB. Crash-safe, auto-resume.
RUN FROM THE MAINTAINER'S LAPTOP, NEVER FROM PROD.

POURQUOI SQLITE :
- Chaque UPDATE est commit immediatement -> crash-safe sans flag --resume.
- Reprise auto via "SELECT ... WHERE nominatim_status IS NULL".
- Mainteneur peut ouvrir le .sqlite dans DB Browser for SQLite pour
  faire la revue humaine visuellement.
- Filtres SQL plus puissants que jq sur JSON.
- Persistance d'une colonne human_review_status pour tracker la revue.
/ WHY SQLITE:
- Every UPDATE commits immediately -> crash-safe with no --resume flag.
- Auto-resume via "SELECT ... WHERE nominatim_status IS NULL".
- Maintainer can open the .sqlite in DB Browser for visual human review.
- SQL filters more powerful than jq on JSON.
- Persists human_review_status column to track manual review.

PRINCIPE DE SAFETY :
- On ne reecrit JAMAIS l'adresse existante d'un tenant.
- Si le tenant a deja une street_address : on cherche UNIQUEMENT lat/long.
- Si le tenant n'a PAS d'adresse complete : on stocke l'adresse Nominatim
  dans les colonnes proposed_* pour pouvoir la proposer apres revue humaine.
- Chaque resultat est annote d'un niveau de confiance (high/medium/low)
  et d'un flag needs_human_review.
- Le futur script d'import ne prendra QUE les "ok" + needs_review=false
  pour update auto lat/long ; le reste passe par revue manuelle.

CLASSIFICATION DES TENANTS EN 4 BUCKETS :
- full_address    : street + city remplis -> Nominatim full query, confidence high
- partial_address : city seule (sans street) -> city+country, confidence medium
- name_only       : juste un nom -> organisation + countrycodes filter,
                    cross-check fuzzy, confidence low, needs_review forcement true
- no_data         : rien d'exploitable -> skipped, jamais d'appel Nominatim

USAGE :
    # 1. Generer le JSON source depuis le container Lespass :
    docker exec lespass_django poetry run python manage.py \\
        export_tenants_addresses --only-incomplete --output=/tmp/a_relancer.json
    docker cp lespass_django:/tmp/a_relancer.json ./a_relancer.json

    # 2. Lancer le backfill EN LOCAL :
    python nominatim_backfill.py ./a_relancer.json ./geocoded.sqlite

    # Test sur 5 tenants
    python nominatim_backfill.py ./a_relancer.json ./geocoded.sqlite --limit 5

    # Reprise apres crash : automatique (pas de flag, on continue les rows null)
    python nominatim_backfill.py ./a_relancer.json ./geocoded.sqlite

    # Reset complet : drop + recreate la table (si JSON a change)
    python nominatim_backfill.py ./a_relancer.json ./geocoded.sqlite --reset

    # Skip la recherche par nom seul (plus sur, moins de couverture)
    python nominatim_backfill.py ./a_relancer.json ./geocoded.sqlite --no-name-search

DEPENDENCIES : Python 3 (urllib + json + sqlite3 + time natifs).

REQUETES UTILES (apres le run) :
    # Vue d'ensemble
    sqlite3 geocoded.sqlite "SELECT nominatim_status, COUNT(*) FROM tenants_geocode GROUP BY nominatim_status"

    # Imports safe (lat/long uniquement, tenants deja adresses)
    sqlite3 geocoded.sqlite "SELECT schema, organisation, nominatim_latitude, nominatim_longitude \\
        FROM tenants_geocode WHERE nominatim_status='ok'"

    # Propositions d'adresse a revoir
    sqlite3 geocoded.sqlite "SELECT schema, organisation, nominatim_display_name, \\
        proposed_street_address, proposed_address_locality \\
        FROM tenants_geocode WHERE proposed_street_address IS NOT NULL \\
        AND human_review_status='pending'"

    # Approuver manuellement un tenant
    sqlite3 geocoded.sqlite "UPDATE tenants_geocode SET human_review_status='approved', \\
        human_reviewed_at=datetime('now') WHERE schema='nom_du_schema'"
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.error import HTTPError, URLError


# --- Constantes Nominatim ---
# --- Nominatim constants ---

DELAI_ENTRE_REQUETES_SEC = 1.1
USER_AGENT = "TiBillet-Onboard-Backfill/1.0 (contact@tibillet.re)"
URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
TIMEOUT_REQ_SEC = 10

# Pays par defaut : France metropole + DOM-TOM + collectivites.
# / Default countries: mainland France + DOM-TOM + collectivities.
COUNTRY_CODES_DEFAUT = "fr,re,yt,mq,gp,gf,nc,pf,bl,mf,pm,wf"

# Types Nominatim a rejeter pour les recherches par nom seul (homonymes
# probables : un nom de structure qui matche une ville est presque toujours faux).
# / Nominatim types to reject for name-only searches (likely homonyms).
TYPES_REJETES_NAME_ONLY = {
    "city", "village", "town", "hamlet", "administrative", "state", "county",
}

# Codes HTTP qui declenchent un retry avec backoff.
# / HTTP codes that trigger a backoff retry.
CODES_RETRY = {429, 503, 504}
MAX_RETRIES = 2
DELAI_BACKOFF_SEC = 30

# Affichage progression toutes les N requetes.
# / Show progression every N requests.
INTERVALLE_PROGRESSION = 10


# --- Schema SQLite ---
# --- SQLite schema ---

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenants_geocode (
    -- Identite tenant
    schema TEXT PRIMARY KEY,
    tenant_name TEXT,
    categorie TEXT,
    organisation TEXT,
    email TEXT,
    phone TEXT,
    site_web TEXT,

    -- Adresse "legacy" (champs sur Configuration)
    legacy_adress TEXT,
    legacy_postal_code TEXT,
    legacy_city TEXT,

    -- Adresse schema.org (FK PostalAddress du tenant)
    schemaorg_name TEXT,
    schemaorg_street_address TEXT,
    schemaorg_address_locality TEXT,
    schemaorg_postal_code TEXT,
    schemaorg_address_country TEXT,
    schemaorg_latitude TEXT,
    schemaorg_longitude TEXT,

    -- Flags issus du JSON export
    has_address INTEGER,        -- bool
    has_geoloc INTEGER,         -- bool
    configuration_manquante INTEGER,  -- bool

    -- Classification (rempli par ce script)
    nominatim_bucket TEXT,      -- full_address | partial_address | name_only | no_data
    nominatim_query TEXT,

    -- Resultat Nominatim (rempli par ce script)
    nominatim_status TEXT,      -- NULL = pas encore traite ; sinon ok | needs_review | rejected_* | no_match | skipped_no_data | error
    nominatim_confidence TEXT,  -- high | medium | low | NULL
    nominatim_needs_human_review INTEGER,  -- bool
    nominatim_results_count INTEGER,
    nominatim_latitude TEXT,
    nominatim_longitude TEXT,
    nominatim_display_name TEXT,
    nominatim_importance REAL,
    nominatim_type TEXT,
    nominatim_class TEXT,
    nominatim_error TEXT,
    nominatim_processed_at TEXT,  -- ISO datetime

    -- Adresse proposee (uniquement si tenant sans street_address)
    proposed_street_address TEXT,
    proposed_address_locality TEXT,
    proposed_postal_code TEXT,
    proposed_address_country TEXT,
    proposed_country_code TEXT,

    -- JSON brut pour audit complet
    alternatives_json TEXT,
    raw_osm_json TEXT,

    -- Revue humaine (a mettre a jour manuellement apres le run)
    human_review_status TEXT DEFAULT 'pending',  -- pending | approved | rejected | manual_override
    human_review_notes TEXT,
    human_reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_nominatim_status ON tenants_geocode(nominatim_status);
CREATE INDEX IF NOT EXISTS idx_needs_review ON tenants_geocode(nominatim_needs_human_review);
CREATE INDEX IF NOT EXISTS idx_human_status ON tenants_geocode(human_review_status);
CREATE INDEX IF NOT EXISTS idx_bucket ON tenants_geocode(nominatim_bucket);
"""


# --- Helpers ---

def formater_duree(secondes):
    """
    Formate une duree en h/m/s pour l'affichage humain.
    / Formats a duration into h/m/s for human display.
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
    / Loosely normalizes a string for comparison.
    """
    if not texte:
        return ""
    return " ".join(str(texte).lower().split())


def nom_present_dans_display_name(nom_tenant, display_name):
    """
    Cross-check anti-homonymie : le nom du tenant apparait-il dans display_name ?
    / Anti-homonym cross-check.
    """
    nom_norm = normaliser_pour_comparaison(nom_tenant)
    dn_norm = normaliser_pour_comparaison(display_name)
    if not nom_norm or not dn_norm:
        return False
    return nom_norm in dn_norm


def mapper_osm_vers_postal_address(adresse_osm):
    """
    Convertit le dict adresse Nominatim (addressdetails=1) en format compatible
    avec notre modele BaseBillet.PostalAddress (schema.org).
    / Maps Nominatim's address dict into our BaseBillet.PostalAddress format.
    """
    if not adresse_osm:
        return None
    house_number = adresse_osm.get("house_number")
    road = (
        adresse_osm.get("road")
        or adresse_osm.get("pedestrian")
        or adresse_osm.get("path")
    )
    street_address = None
    if house_number and road:
        street_address = f"{house_number} {road}"
    elif road:
        street_address = road
    locality = (
        adresse_osm.get("village")
        or adresse_osm.get("town")
        or adresse_osm.get("city")
        or adresse_osm.get("municipality")
        or adresse_osm.get("hamlet")
    )
    return {
        "street_address": street_address,
        "address_locality": locality,
        "postal_code": adresse_osm.get("postcode"),
        "address_country": adresse_osm.get("country"),
        "country_code": adresse_osm.get("country_code"),
    }


# --- DB helpers ---

def ouvrir_db(chemin):
    """
    Ouvre une connexion SQLite avec WAL et row_factory dict-like.
    / Opens a SQLite connection with WAL and dict-like row_factory.
    """
    connexion = sqlite3.connect(chemin)
    connexion.row_factory = sqlite3.Row
    # WAL : permet a DB Browser de lire pendant qu'on ecrit.
    # / WAL: lets DB Browser read while we write.
    connexion.execute("PRAGMA journal_mode=WAL")
    connexion.executescript(SCHEMA_SQL)
    connexion.commit()
    return connexion


def importer_json_dans_db(connexion, tenants_source):
    """
    Insere les tenants du JSON dans la table SQLite. INSERT OR IGNORE : on ne
    touche pas les rows deja presentes (pour ne pas ecraser le travail de backfill).
    / Inserts JSON tenants into the SQLite table. INSERT OR IGNORE: do not touch
    existing rows (so we don't overwrite backfill progress).

    Renvoie (nombre_inseres, nombre_existants_ignores).
    / Returns (count_inserted, count_already_present_ignored).
    """
    nombre_inseres = 0
    nombre_ignores = 0
    for tenant in tenants_source:
        adresse_legacy = tenant.get("adresse_legacy") or {}
        adresse_schema = tenant.get("adresse_schema_org") or {}
        curseur = connexion.execute(
            """
            INSERT OR IGNORE INTO tenants_geocode (
                schema, tenant_name, categorie, organisation, email, phone, site_web,
                legacy_adress, legacy_postal_code, legacy_city,
                schemaorg_name, schemaorg_street_address, schemaorg_address_locality,
                schemaorg_postal_code, schemaorg_address_country,
                schemaorg_latitude, schemaorg_longitude,
                has_address, has_geoloc, configuration_manquante
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant.get("schema"),
                tenant.get("tenant_name"),
                tenant.get("categorie"),
                tenant.get("organisation"),
                tenant.get("email"),
                tenant.get("phone"),
                tenant.get("site_web"),
                adresse_legacy.get("adress"),
                str(adresse_legacy.get("postal_code")) if adresse_legacy.get("postal_code") else None,
                adresse_legacy.get("city"),
                adresse_schema.get("name"),
                adresse_schema.get("street_address"),
                adresse_schema.get("address_locality"),
                adresse_schema.get("postal_code"),
                adresse_schema.get("address_country"),
                adresse_schema.get("latitude"),
                adresse_schema.get("longitude"),
                1 if tenant.get("has_address") else 0,
                1 if tenant.get("has_geoloc") else 0,
                1 if tenant.get("configuration_manquante") else 0,
            ),
        )
        if curseur.rowcount > 0:
            nombre_inseres += 1
        else:
            nombre_ignores += 1
    connexion.commit()
    return nombre_inseres, nombre_ignores


def selectionner_tenants_a_traiter(connexion, limite):
    """
    Renvoie les tenants jamais traites par Nominatim et n'ayant pas deja une geoloc.
    / Returns tenants never processed by Nominatim and without existing geoloc.
    """
    requete = """
        SELECT * FROM tenants_geocode
        WHERE nominatim_status IS NULL
          AND (has_geoloc IS NULL OR has_geoloc = 0)
        ORDER BY schema
    """
    if limite is not None:
        requete += f" LIMIT {int(limite)}"
    return connexion.execute(requete).fetchall()


def compter_stats(connexion):
    """
    Renvoie un dict {status: count} pour stats finales.
    / Returns a dict {status: count} for final stats.
    """
    rows = connexion.execute(
        "SELECT COALESCE(nominatim_status, 'pending') AS s, COUNT(*) AS n "
        "FROM tenants_geocode GROUP BY s"
    ).fetchall()
    return {row["s"]: row["n"] for row in rows}


# --- Classification tenant -> bucket + query ---

def classer_et_construire_query(row, country_codes, autoriser_name_search):
    """
    Classe la row tenant en bucket et construit la query Nominatim.
    / Classifies the tenant row into a bucket and builds the Nominatim query.

    Renvoie un dict avec bucket, query, params_extra, confidence_attendue,
    needs_review_force.
    / Returns a dict with bucket, query, params_extra, expected_confidence,
    needs_review_force.
    """
    # On accede a la row sqlite3.Row par nom de colonne
    # / We access sqlite3.Row by column name
    street = row["schemaorg_street_address"] or row["legacy_adress"]
    postal_code_value = row["schemaorg_postal_code"] or row["legacy_postal_code"]
    city = row["schemaorg_address_locality"] or row["legacy_city"]
    country = row["schemaorg_address_country"]

    # Bucket 1 : adresse complete
    # / Bucket 1: full address
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

    # Bucket 2 : adresse partielle (ville seule)
    # / Bucket 2: partial address (city only)
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
            "confidence_attendue": "medium",
            "needs_review_force": True,
        }

    # Bucket 3 : juste un nom
    # / Bucket 3: name only
    nom_a_chercher = row["organisation"] or row["tenant_name"]
    if nom_a_chercher and autoriser_name_search:
        return {
            "bucket": "name_only",
            "query": str(nom_a_chercher).strip(),
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


# --- Update SQLite a partir d'un resultat Nominatim ---

def update_tenant_avec_resultat(connexion, schema, classification, reponse_brute):
    """
    Update la row tenant avec le resultat Nominatim. Commit immediat.
    / Updates the tenant row with the Nominatim result. Immediate commit.

    Cette fonction applique les regles de safety :
    - Cross-check homonymie pour name_only
    - Rejet des types geographiques larges
    - Downgrade confidence si ambigu
    - Pas de proposed_address pour les tenants deja adresses
    """
    bucket = classification["bucket"]
    query = classification["query"]
    confidence = classification["confidence_attendue"]
    needs_review = classification["needs_review_force"]
    horodatage = datetime.utcnow().isoformat(timespec="seconds")

    # Erreur reseau / HTTP
    # / Network / HTTP error
    if isinstance(reponse_brute, dict) and "error" in reponse_brute:
        connexion.execute(
            """
            UPDATE tenants_geocode SET
                nominatim_bucket = ?, nominatim_query = ?,
                nominatim_status = 'error',
                nominatim_error = ?,
                nominatim_needs_human_review = 1,
                nominatim_processed_at = ?
            WHERE schema = ?
            """,
            (bucket, query, reponse_brute["error"], horodatage, schema),
        )
        connexion.commit()
        return "error"

    # Aucun resultat
    # / No result
    if not reponse_brute:
        connexion.execute(
            """
            UPDATE tenants_geocode SET
                nominatim_bucket = ?, nominatim_query = ?,
                nominatim_status = 'no_match',
                nominatim_needs_human_review = 1,
                nominatim_processed_at = ?
            WHERE schema = ?
            """,
            (bucket, query, horodatage, schema),
        )
        connexion.commit()
        return "no_match"

    premier = reponse_brute[0]
    type_resultat = premier.get("type", "")
    class_resultat = premier.get("class", "")
    display_name = premier.get("display_name", "")

    # Anti-homonymie pour name_only : reject types geographiques larges
    # / Anti-homonym for name_only: reject broad geographic types
    if bucket == "name_only":
        if type_resultat in TYPES_REJETES_NAME_ONLY:
            connexion.execute(
                """
                UPDATE tenants_geocode SET
                    nominatim_bucket = ?, nominatim_query = ?,
                    nominatim_status = 'rejected_homonym',
                    nominatim_display_name = ?,
                    nominatim_type = ?, nominatim_class = ?,
                    nominatim_error = ?,
                    nominatim_needs_human_review = 1,
                    nominatim_processed_at = ?
                WHERE schema = ?
                """,
                (
                    bucket, query, display_name, type_resultat, class_resultat,
                    f"type={type_resultat} (homonyme probable, ex: ville)",
                    horodatage, schema,
                ),
            )
            connexion.commit()
            return "rejected_homonym"

        # Cross-check : le nom du tenant doit apparaitre dans display_name
        # / Cross-check: tenant name must appear in display_name
        if not nom_present_dans_display_name(query, display_name):
            connexion.execute(
                """
                UPDATE tenants_geocode SET
                    nominatim_bucket = ?, nominatim_query = ?,
                    nominatim_status = 'rejected_name_mismatch',
                    nominatim_display_name = ?,
                    nominatim_type = ?, nominatim_class = ?,
                    nominatim_error = ?,
                    nominatim_needs_human_review = 1,
                    nominatim_processed_at = ?
                WHERE schema = ?
                """,
                (
                    bucket, query, display_name, type_resultat, class_resultat,
                    "nom du tenant absent du display_name",
                    horodatage, schema,
                ),
            )
            connexion.commit()
            return "rejected_name_mismatch"

    # Ambigu : downgrade confidence + force review
    # / Ambiguous: downgrade confidence + force review
    alternatives_pour_audit = []
    if len(reponse_brute) > 1:
        for autre in reponse_brute[1:]:
            alternatives_pour_audit.append({
                "display_name": autre.get("display_name"),
                "lat": autre.get("lat"),
                "lon": autre.get("lon"),
                "type": autre.get("type"),
            })
        if confidence == "high":
            confidence = "medium"
        needs_review = True

    # Adresse proposee : UNIQUEMENT pour partial_address / name_only
    # / Proposed address: ONLY for partial_address / name_only
    proposed = None
    if bucket in ("partial_address", "name_only"):
        proposed = mapper_osm_vers_postal_address(premier.get("address"))

    statut_final = "needs_review" if needs_review else "ok"

    connexion.execute(
        """
        UPDATE tenants_geocode SET
            nominatim_bucket = ?, nominatim_query = ?,
            nominatim_status = ?,
            nominatim_confidence = ?,
            nominatim_needs_human_review = ?,
            nominatim_results_count = ?,
            nominatim_latitude = ?, nominatim_longitude = ?,
            nominatim_display_name = ?,
            nominatim_importance = ?,
            nominatim_type = ?, nominatim_class = ?,
            nominatim_processed_at = ?,
            proposed_street_address = ?,
            proposed_address_locality = ?,
            proposed_postal_code = ?,
            proposed_address_country = ?,
            proposed_country_code = ?,
            alternatives_json = ?,
            raw_osm_json = ?
        WHERE schema = ?
        """,
        (
            bucket, query,
            statut_final,
            confidence,
            1 if needs_review else 0,
            len(reponse_brute),
            premier.get("lat"), premier.get("lon"),
            display_name,
            premier.get("importance"),
            type_resultat, class_resultat,
            horodatage,
            proposed.get("street_address") if proposed else None,
            proposed.get("address_locality") if proposed else None,
            proposed.get("postal_code") if proposed else None,
            proposed.get("address_country") if proposed else None,
            proposed.get("country_code") if proposed else None,
            json.dumps(alternatives_pour_audit, ensure_ascii=False) if alternatives_pour_audit else None,
            json.dumps(premier.get("address"), ensure_ascii=False) if premier.get("address") else None,
            schema,
        ),
    )
    connexion.commit()
    return statut_final


def update_tenant_skip(connexion, schema, classification, raison):
    """
    Update une row pour un tenant skip (no_data, etc.) sans appel Nominatim.
    / Updates a row for a skipped tenant (no_data, etc.) without Nominatim call.
    """
    connexion.execute(
        """
        UPDATE tenants_geocode SET
            nominatim_bucket = ?,
            nominatim_status = 'skipped_no_data',
            nominatim_needs_human_review = 1,
            nominatim_error = ?,
            nominatim_processed_at = ?
        WHERE schema = ?
        """,
        (
            classification["bucket"],
            raison,
            datetime.utcnow().isoformat(timespec="seconds"),
            schema,
        ),
    )
    connexion.commit()


# --- Progression ---

def afficher_progression(numero_courant, total, t0):
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
        file=sys.stderr,
    )


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill geoloc Nominatim pour les tenants Lespass sans coordonnees.\n"
            "Persistance SQLite : crash-safe, reprise auto, revue humaine integree.\n"
            "A LANCER EN LOCAL, JAMAIS DEPUIS LA PROD."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_json",
        help="JSON produit par `manage.py export_tenants_addresses [--only-incomplete]`",
    )
    parser.add_argument(
        "output_sqlite",
        help="Chemin du fichier SQLite de sortie (cree si absent, sinon reprise).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite aux N premiers tenants a traiter (utile pour tester).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop + recree la table avant l'import (utile si JSON a change).",
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

    # --- Reset eventuel ---
    if args.reset and os.path.exists(args.output_sqlite):
        print(f"--reset : suppression de {args.output_sqlite}", file=sys.stderr)
        os.remove(args.output_sqlite)
        # Nettoyer aussi les fichiers WAL et SHM crees par SQLite
        # / Also clean up WAL and SHM files created by SQLite
        for suffixe in ("-wal", "-shm"):
            chemin_aux = args.output_sqlite + suffixe
            if os.path.exists(chemin_aux):
                os.remove(chemin_aux)

    # --- Ouverture DB + import JSON ---
    connexion = ouvrir_db(args.output_sqlite)

    with open(args.input_json, "r", encoding="utf-8") as fichier:
        tenants_source = json.load(fichier)
    nombre_inseres, nombre_ignores = importer_json_dans_db(connexion, tenants_source)

    # --- Selection des tenants a traiter (reprise auto via SQL) ---
    tenants_a_traiter = selectionner_tenants_a_traiter(connexion, args.limit)
    nombre_total = len(tenants_a_traiter)

    print(
        f"\n--- Import JSON -> SQLite ---\n"
        f"DB                       : {args.output_sqlite}\n"
        f"Tenants en entree (JSON) : {len(tenants_source)}\n"
        f"Inseres dans la DB       : {nombre_inseres}\n"
        f"Deja presents (ignored)  : {nombre_ignores}\n"
        f"\n"
        f"--- Selection a traiter ---\n"
        f"A traiter par Nominatim  : {nombre_total}\n"
        f"ETA approximatif         : {formater_duree(nombre_total * DELAI_ENTRE_REQUETES_SEC)}\n",
        file=sys.stderr,
    )

    if nombre_total == 0:
        print("Rien a traiter. Fin.", file=sys.stderr)
        connexion.close()
        return

    # --- Boucle principale ---
    t0 = time.time()
    nombre_requetes_envoyees = 0

    for index_courant, row in enumerate(tenants_a_traiter, start=1):
        classification = classer_et_construire_query(
            row, args.country_codes, not args.no_name_search
        )

        # Tenant no_data : pas d'appel Nominatim
        # / no_data tenant: no Nominatim call
        if classification["query"] is None:
            update_tenant_skip(
                connexion, row["schema"], classification,
                "aucune adresse ni nom exploitable",
            )
            print(
                f"[{index_courant}/{nombre_total}] {row['schema']} "
                f"(no_data) -> skip",
                file=sys.stderr,
            )
            continue

        print(
            f"[{index_courant}/{nombre_total}] {row['schema']} "
            f"({classification['bucket']}) : {classification['query'][:80]}",
            file=sys.stderr,
        )

        reponse = appeler_nominatim(
            classification["query"], classification["params_extra"]
        )
        update_tenant_avec_resultat(
            connexion, row["schema"], classification, reponse
        )
        nombre_requetes_envoyees += 1

        # Progression periodique
        # / Periodic progression
        if nombre_requetes_envoyees % INTERVALLE_PROGRESSION == 0:
            afficher_progression(index_courant, nombre_total, t0)

        # Rate limit strict
        # / Strict rate limit
        time.sleep(DELAI_ENTRE_REQUETES_SEC)

    duree_totale = time.time() - t0

    # --- Stats finales ---
    stats = compter_stats(connexion)
    connexion.close()

    print(
        f"\n--- Stats backfill Nominatim ---\n"
        f"Duree totale             : {formater_duree(duree_totale)}\n"
        f"Requetes envoyees        : {nombre_requetes_envoyees}\n"
        f"\n"
        f"=== Repartition par status (toute la DB) ===\n",
        file=sys.stderr,
    )
    for statut in (
        "ok", "needs_review", "rejected_homonym", "rejected_name_mismatch",
        "no_match", "skipped_no_data", "error", "pending",
    ):
        nombre = stats.get(statut, 0)
        if nombre:
            print(f"  {statut:25} : {nombre}", file=sys.stderr)

    print(
        f"\n=== Requetes SQL utiles ===\n"
        f"  # Vue d'ensemble :\n"
        f"  sqlite3 {args.output_sqlite} \"SELECT nominatim_status, COUNT(*) "
        f"FROM tenants_geocode GROUP BY nominatim_status\"\n"
        f"\n"
        f"  # Imports safe (lat/long uniquement) :\n"
        f"  sqlite3 {args.output_sqlite} \"SELECT schema, organisation, "
        f"nominatim_latitude, nominatim_longitude FROM tenants_geocode "
        f"WHERE nominatim_status='ok'\"\n"
        f"\n"
        f"  # Propositions d'adresse a revoir :\n"
        f"  sqlite3 {args.output_sqlite} \"SELECT schema, organisation, "
        f"nominatim_display_name, proposed_street_address, proposed_address_locality "
        f"FROM tenants_geocode WHERE proposed_street_address IS NOT NULL "
        f"AND human_review_status='pending'\"\n"
        f"\n"
        f"  # Approuver manuellement un tenant :\n"
        f"  sqlite3 {args.output_sqlite} \"UPDATE tenants_geocode SET "
        f"human_review_status='approved', human_reviewed_at=datetime('now') "
        f"WHERE schema='nom_du_schema'\"\n"
        f"\n"
        f"Ouvre {args.output_sqlite} dans DB Browser for SQLite pour la revue visuelle.\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
