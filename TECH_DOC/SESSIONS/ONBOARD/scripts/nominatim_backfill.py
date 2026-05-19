"""
Script local de backfill geoloc via Nominatim, persistance SQLite avec FK
/ Local geocoding backfill script via Nominatim, SQLite persistence with FK

LOCALISATION : TECH_DOC/SESSIONS/ONBOARD/scripts/nominatim_backfill.py

But : prend le JSON produit par `export_tenants_addresses`, l'importe dans une
SQLite relationnelle (tenants + postal_addresses avec FK), puis appelle
Nominatim pour chaque PostalAddress sans lat/long.
A LANCER DEPUIS LE POSTE DU MAINTENEUR, JAMAIS DEPUIS LA PROD.
/ Goal: take the JSON from `export_tenants_addresses`, import into a relational
SQLite (tenants + postal_addresses with FK), then call Nominatim for each
PostalAddress missing lat/long.
RUN FROM THE MAINTAINER'S LAPTOP, NEVER FROM PROD.

POURQUOI 2 TABLES AVEC FK :
- Un tenant a 1 + N adresses (Configuration.postal_address + Event.postal_address).
- Plusieurs Event peuvent partager la MEME PostalAddress (meme FK id) -> dedup.
- La SQLite reflete fidelement le modele Lespass : 1 row = 1 PostalAddress reelle.
- Le futur import update PostalAddress.objects.get(pk=postgres_id), un par un.
/ WHY 2 TABLES WITH FK:
- A tenant has 1 + N addresses (Configuration + Events).
- Multiple Events may share the SAME PostalAddress -> deduplication needed.
- The SQLite faithfully reflects the Lespass model: 1 row = 1 real PostalAddress.

POURQUOI SQLITE :
- Chaque UPDATE est commit immediatement -> crash-safe sans flag --resume.
- Reprise auto via "SELECT ... WHERE nominatim_status IS NULL".
- Mainteneur peut ouvrir le .sqlite dans DB Browser for SQLite pour
  faire la revue humaine visuellement.
- Filtres SQL plus puissants que jq sur JSON.

PRINCIPE DE SAFETY :
- On ne reecrit JAMAIS l'adresse existante (street_address, locality, etc.).
- Si la PostalAddress a deja un street_address : on cherche UNIQUEMENT lat/long.
- Si la PostalAddress n'a PAS de street_address (juste locality, ou stub
  legacy) : on stocke l'adresse complete renvoyee par Nominatim dans les
  colonnes proposed_* pour pouvoir la proposer apres revue humaine.
- Chaque resultat est annote d'un niveau de confiance (high/medium/low)
  et d'un flag needs_human_review.
- Le futur script d'import ne prendra QUE les "ok" + needs_review=false
  pour update auto lat/long ; le reste passe par revue manuelle.

CLASSIFICATION EN 4 BUCKETS (par PostalAddress) :
- full_address    : street + locality remplis -> query full, confidence high
- partial_address : locality seule (sans street) -> city+country, confidence medium
- name_only       : juste un name (rare, ex: stub legacy avec organisation seule)
                    -> organisation + countrycodes filter, cross-check fuzzy,
                    confidence low, needs_review force a true
- no_data         : rien d'exploitable -> skipped, jamais d'appel Nominatim

USAGE :
    # 1. Generer le JSON source depuis le container Lespass :
    docker exec lespass_django poetry run python manage.py \\
        export_tenants_addresses > ./tenants.json

    # 2. Lancer le backfill EN LOCAL :
    python nominatim_backfill.py ./tenants.json ./geocoded.sqlite

    # Test sur 5 PostalAddress
    python nominatim_backfill.py ./tenants.json ./geocoded.sqlite --limit 5

    # Reprise apres crash : automatique (relancer la meme commande)
    python nominatim_backfill.py ./tenants.json ./geocoded.sqlite

    # Reset complet : drop + recreate la DB
    python nominatim_backfill.py ./tenants.json ./geocoded.sqlite --reset

    # Skip recherche par nom (plus sur, moins de couverture)
    python nominatim_backfill.py ./tenants.json ./geocoded.sqlite --no-name-search

DEPENDENCIES : Python 3 (urllib + json + sqlite3 + time natifs).

REQUETES SQL UTILES :
    # Vue d'ensemble
    sqlite3 geocoded.sqlite "SELECT nominatim_status, COUNT(*) \\
        FROM postal_addresses GROUP BY nominatim_status"

    # Imports safe (lat/long uniquement, PostalAddress avec adresse complete)
    sqlite3 geocoded.sqlite "SELECT pa.postgres_id, t.organisation, \\
        pa.nominatim_latitude, pa.nominatim_longitude \\
        FROM postal_addresses pa JOIN tenants t ON t.schema = pa.tenant_schema \\
        WHERE pa.nominatim_status='ok'"

    # Adresses partielles a completer (revue humaine)
    sqlite3 geocoded.sqlite "SELECT pa.postgres_id, t.organisation, \\
        pa.address_locality, pa.proposed_street_address, pa.proposed_address_locality \\
        FROM postal_addresses pa JOIN tenants t ON t.schema = pa.tenant_schema \\
        WHERE pa.proposed_street_address IS NOT NULL \\
        AND pa.human_review_status='pending'"

    # Approuver une adresse manuellement
    sqlite3 geocoded.sqlite "UPDATE postal_addresses SET human_review_status='approved', \\
        human_reviewed_at=datetime('now') WHERE id=42"
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
# / Nominatim types to reject for name-only searches.
TYPES_REJETES_NAME_ONLY = {
    "city", "village", "town", "hamlet", "administrative", "state", "county",
}

CODES_RETRY = {429, 503, 504}
MAX_RETRIES = 2
DELAI_BACKOFF_SEC = 30
INTERVALLE_PROGRESSION = 10


# --- Schema SQLite ---
# --- SQLite schema ---

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenants (
    schema TEXT PRIMARY KEY,
    tenant_name TEXT,
    categorie TEXT,
    organisation TEXT,
    email TEXT,
    phone TEXT,
    site_web TEXT,
    -- Adresse legacy (champs sur Configuration directement, sans FK)
    legacy_adress TEXT,
    legacy_postal_code TEXT,
    legacy_city TEXT,
    configuration_manquante INTEGER
);

CREATE TABLE IF NOT EXISTS postal_addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_schema TEXT NOT NULL REFERENCES tenants(schema) ON DELETE CASCADE,
    -- ID de la PostalAddress cote Lespass (NULL = stub legacy a creer)
    postgres_id INTEGER,
    -- True si cette PA est l'adresse principale du tenant
    -- (referencee par Configuration.postal_address ou stub legacy).
    -- Utile pour prioriser la revue humaine.
    -- / True if this PA is the tenant's main address. Useful for review priority.
    is_main_address INTEGER DEFAULT 0,

    -- Champs schema.org actuels (tels qu'ils sont dans Lespass)
    name TEXT,
    street_address TEXT,
    address_locality TEXT,
    postal_code TEXT,
    address_country TEXT,
    latitude TEXT,
    longitude TEXT,

    -- Classification (rempli par ce script)
    nominatim_bucket TEXT,
    nominatim_query TEXT,

    -- Resultat Nominatim (rempli par ce script)
    nominatim_status TEXT,           -- NULL = pas encore traite
    nominatim_confidence TEXT,       -- high | medium | low
    nominatim_needs_human_review INTEGER,
    nominatim_results_count INTEGER,
    nominatim_latitude TEXT,
    nominatim_longitude TEXT,
    nominatim_display_name TEXT,
    nominatim_importance REAL,
    nominatim_type TEXT,
    nominatim_class TEXT,
    nominatim_error TEXT,
    nominatim_processed_at TEXT,

    -- Adresse proposee (uniquement si PostalAddress sans street_address)
    proposed_street_address TEXT,
    proposed_address_locality TEXT,
    proposed_postal_code TEXT,
    proposed_address_country TEXT,
    proposed_country_code TEXT,

    -- JSON brut pour audit complet
    alternatives_json TEXT,
    raw_osm_json TEXT,

    -- Revue humaine (a UPDATE manuellement apres le run)
    human_review_status TEXT DEFAULT 'pending',
    human_review_notes TEXT,
    human_reviewed_at TEXT,

    -- Cle composite : 1 row par (tenant, postgres_id). NULL postgres_id
    -- accepte plusieurs stubs legacy par tenant theoriquement (mais en
    -- pratique il n'y en a qu'un seul par tenant via Configuration_legacy).
    UNIQUE(tenant_schema, postgres_id)
);

CREATE INDEX IF NOT EXISTS idx_pa_tenant ON postal_addresses(tenant_schema);
CREATE INDEX IF NOT EXISTS idx_pa_status ON postal_addresses(nominatim_status);
CREATE INDEX IF NOT EXISTS idx_pa_review ON postal_addresses(human_review_status);
CREATE INDEX IF NOT EXISTS idx_pa_bucket ON postal_addresses(nominatim_bucket);
CREATE INDEX IF NOT EXISTS idx_pa_geoloc ON postal_addresses(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_pa_main ON postal_addresses(is_main_address);

-- UNIQUE(tenant_schema, postgres_id) traite NULL != NULL en SQLite, donc
-- plusieurs stubs legacy (postgres_id=NULL) pourraient s'accumuler a chaque
-- re-import. Cet index partiel garantit 1 seul stub legacy par tenant.
-- / SQLite treats NULL != NULL for UNIQUE, so multiple legacy stubs could
-- accumulate on re-import. This partial index enforces 1 stub per tenant.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pa_unique_stub_legacy
    ON postal_addresses(tenant_schema) WHERE postgres_id IS NULL;
"""


# --- Helpers ---

def formater_duree(secondes):
    """
    Formate une duree en h/m/s.
    / Formats a duration into h/m/s.
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
    Normalise une chaine pour comparaison souple.
    / Loosely normalizes a string for comparison.
    """
    if not texte:
        return ""
    return " ".join(str(texte).lower().split())


def nom_present_dans_display_name(nom_tenant, display_name):
    """
    Cross-check anti-homonymie pour les recherches par nom.
    / Anti-homonym cross-check for name-based searches.
    """
    nom_norm = normaliser_pour_comparaison(nom_tenant)
    dn_norm = normaliser_pour_comparaison(display_name)
    if not nom_norm or not dn_norm:
        return False
    return nom_norm in dn_norm


def mapper_osm_vers_postal_address(adresse_osm):
    """
    Convertit le dict adresse Nominatim (addressdetails=1) en format compatible
    avec notre modele BaseBillet.PostalAddress.
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
    Ouvre une connexion SQLite avec WAL + foreign keys + row_factory dict-like.
    / Opens a SQLite connection with WAL + FK + dict-like row_factory.
    """
    connexion = sqlite3.connect(chemin)
    connexion.row_factory = sqlite3.Row
    connexion.execute("PRAGMA journal_mode=WAL")
    connexion.execute("PRAGMA foreign_keys=ON")
    connexion.executescript(SCHEMA_SQL)
    connexion.commit()
    return connexion


def importer_json_dans_db(connexion, donnees_json):
    """
    Importe le JSON {tenants:[], postal_addresses:[]} dans la SQLite.
    INSERT OR IGNORE pour ne pas ecraser le travail de backfill existant.
    / Imports the JSON into SQLite. INSERT OR IGNORE preserves existing backfill.
    """
    nombre_tenants_inseres = 0
    nombre_tenants_ignores = 0
    nombre_pa_inserees = 0
    nombre_pa_ignorees = 0

    # Import tenants
    for tenant in donnees_json.get("tenants", []):
        curseur = connexion.execute(
            """
            INSERT OR IGNORE INTO tenants (
                schema, tenant_name, categorie, organisation, email, phone, site_web,
                legacy_adress, legacy_postal_code, legacy_city, configuration_manquante
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant.get("schema"),
                tenant.get("tenant_name"),
                tenant.get("categorie"),
                tenant.get("organisation"),
                tenant.get("email"),
                tenant.get("phone"),
                tenant.get("site_web"),
                tenant.get("legacy_adress"),
                tenant.get("legacy_postal_code"),
                tenant.get("legacy_city"),
                1 if tenant.get("configuration_manquante") else 0,
            ),
        )
        if curseur.rowcount > 0:
            nombre_tenants_inseres += 1
        else:
            nombre_tenants_ignores += 1

    # Import postal_addresses
    for pa in donnees_json.get("postal_addresses", []):
        curseur = connexion.execute(
            """
            INSERT OR IGNORE INTO postal_addresses (
                tenant_schema, postgres_id, is_main_address,
                name, street_address, address_locality, postal_code, address_country,
                latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pa.get("tenant_schema"),
                pa.get("postgres_id"),
                1 if pa.get("is_main_address") else 0,
                pa.get("name"),
                pa.get("street_address"),
                pa.get("address_locality"),
                pa.get("postal_code"),
                pa.get("address_country"),
                pa.get("latitude"),
                pa.get("longitude"),
            ),
        )
        if curseur.rowcount > 0:
            nombre_pa_inserees += 1
        else:
            nombre_pa_ignorees += 1

    connexion.commit()
    return (
        nombre_tenants_inseres, nombre_tenants_ignores,
        nombre_pa_inserees, nombre_pa_ignorees,
    )


def selectionner_pa_a_traiter(connexion, limite):
    """
    Renvoie les PostalAddress jamais traitees et sans geoloc existante.
    JOIN avec tenants pour avoir organisation/name dispo pour bucket name_only.
    Tri stable par tenant puis par id. Aucune priorisation : la revue humaine
    se fait sur chaque cas douteux uniformement.
    / Returns PostalAddress never processed and without existing geoloc.
    Stable sort. No prioritization: every uncertain case goes through human review.
    """
    requete = """
        SELECT pa.*, t.organisation AS tenant_organisation,
               t.tenant_name AS t_tenant_name
        FROM postal_addresses pa
        JOIN tenants t ON t.schema = pa.tenant_schema
        WHERE pa.nominatim_status IS NULL
          AND (pa.latitude IS NULL OR pa.longitude IS NULL)
        ORDER BY pa.tenant_schema, pa.id
    """
    if limite is not None:
        requete += f" LIMIT {int(limite)}"
    return connexion.execute(requete).fetchall()


def compter_stats(connexion):
    """
    Renvoie un dict {status: count} pour stats finales (toute la table).
    / Returns a dict {status: count} for final stats (whole table).
    """
    rows = connexion.execute(
        "SELECT COALESCE(nominatim_status, 'pending') AS s, COUNT(*) AS n "
        "FROM postal_addresses GROUP BY s"
    ).fetchall()
    return {row["s"]: row["n"] for row in rows}


# --- Classification PostalAddress -> bucket + query ---

def classer_et_construire_query(row, country_codes, autoriser_name_search):
    """
    Classe la row PostalAddress en bucket et construit la query Nominatim.
    / Classifies the PostalAddress row into a bucket and builds the Nominatim query.

    Renvoie un dict : bucket, query, params_extra, confidence_attendue,
    needs_review_force.
    """
    street = row["street_address"]
    locality = row["address_locality"]
    postal_code_value = row["postal_code"]
    country = row["address_country"]

    # Bucket 1 : adresse complete (street + locality)
    # / Bucket 1: full address (street + locality)
    if street and locality:
        morceaux = [str(street).strip()]
        if postal_code_value:
            morceaux.append(str(postal_code_value).strip())
        morceaux.append(str(locality).strip())
        if country:
            morceaux.append(str(country).strip())
        return {
            "bucket": "full_address",
            "query": ", ".join(morceaux),
            "params_extra": {},
            "confidence_attendue": "high",
            "needs_review_force": False,
        }

    # Bucket 2 : adresse partielle (locality sans street)
    # / Bucket 2: partial address (locality without street)
    if locality:
        morceaux = []
        if postal_code_value:
            morceaux.append(str(postal_code_value).strip())
        morceaux.append(str(locality).strip())
        if country:
            morceaux.append(str(country).strip())
        return {
            "bucket": "partial_address",
            "query": ", ".join(morceaux),
            "params_extra": {},
            "confidence_attendue": "medium",
            "needs_review_force": True,
        }

    # Bucket 3 : juste un nom. On essaie name (PostalAddress.name) puis
    # tenant_organisation en fallback.
    # / Bucket 3: just a name. Try name (PostalAddress.name) then organisation.
    nom_a_chercher = (
        row["name"]
        or row["tenant_organisation"]
        or row["t_tenant_name"]
    )
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


# --- Update SQLite depuis le resultat Nominatim ---

def update_pa_avec_resultat(connexion, pa_id, classification, reponse_brute, row):
    """
    Update la row PostalAddress avec le resultat Nominatim. Commit immediat.
    Applique les regles de safety (cross-check homonymie, downgrade confidence).
    / Updates the PostalAddress row with the Nominatim result. Immediate commit.

    pa_id : id de la row dans la table SQLite postal_addresses.
    row   : la row source (utilisee pour street_address afin de decider si
            on expose ou non proposed_address).
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
            UPDATE postal_addresses SET
                nominatim_bucket = ?, nominatim_query = ?,
                nominatim_status = 'error', nominatim_error = ?,
                nominatim_needs_human_review = 1,
                nominatim_processed_at = ?
            WHERE id = ?
            """,
            (bucket, query, reponse_brute["error"], horodatage, pa_id),
        )
        connexion.commit()
        return "error"

    # Aucun resultat
    # / No result
    if not reponse_brute:
        connexion.execute(
            """
            UPDATE postal_addresses SET
                nominatim_bucket = ?, nominatim_query = ?,
                nominatim_status = 'no_match',
                nominatim_needs_human_review = 1,
                nominatim_processed_at = ?
            WHERE id = ?
            """,
            (bucket, query, horodatage, pa_id),
        )
        connexion.commit()
        return "no_match"

    premier = reponse_brute[0]
    type_resultat = premier.get("type", "")
    class_resultat = premier.get("class", "")
    display_name = premier.get("display_name", "")

    # Anti-homonymie pour name_only
    # / Anti-homonym for name_only
    if bucket == "name_only":
        if type_resultat in TYPES_REJETES_NAME_ONLY:
            connexion.execute(
                """
                UPDATE postal_addresses SET
                    nominatim_bucket = ?, nominatim_query = ?,
                    nominatim_status = 'rejected_homonym',
                    nominatim_display_name = ?,
                    nominatim_type = ?, nominatim_class = ?,
                    nominatim_error = ?,
                    nominatim_needs_human_review = 1,
                    nominatim_processed_at = ?
                WHERE id = ?
                """,
                (
                    bucket, query, display_name, type_resultat, class_resultat,
                    f"type={type_resultat} (homonyme probable, ex: ville)",
                    horodatage, pa_id,
                ),
            )
            connexion.commit()
            return "rejected_homonym"

        if not nom_present_dans_display_name(query, display_name):
            connexion.execute(
                """
                UPDATE postal_addresses SET
                    nominatim_bucket = ?, nominatim_query = ?,
                    nominatim_status = 'rejected_name_mismatch',
                    nominatim_display_name = ?,
                    nominatim_type = ?, nominatim_class = ?,
                    nominatim_error = ?,
                    nominatim_needs_human_review = 1,
                    nominatim_processed_at = ?
                WHERE id = ?
                """,
                (
                    bucket, query, display_name, type_resultat, class_resultat,
                    "nom du tenant absent du display_name",
                    horodatage, pa_id,
                ),
            )
            connexion.commit()
            return "rejected_name_mismatch"

    # Ambigu : downgrade + force review
    # / Ambiguous: downgrade + force review
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

    # Adresse proposee : UNIQUEMENT si la PostalAddress n'a pas deja un street_address.
    # / Proposed address: ONLY if the PostalAddress has no street_address yet.
    proposed = None
    if not row["street_address"]:
        proposed = mapper_osm_vers_postal_address(premier.get("address"))

    statut_final = "needs_review" if needs_review else "ok"

    connexion.execute(
        """
        UPDATE postal_addresses SET
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
        WHERE id = ?
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
            pa_id,
        ),
    )
    connexion.commit()
    return statut_final


def update_pa_skip(connexion, pa_id, classification, raison):
    """
    Update une row pour une PA skip (no_data) sans appel Nominatim.
    / Updates a row for a skipped PA (no_data) without Nominatim call.
    """
    connexion.execute(
        """
        UPDATE postal_addresses SET
            nominatim_bucket = ?,
            nominatim_status = 'skipped_no_data',
            nominatim_needs_human_review = 1,
            nominatim_error = ?,
            nominatim_processed_at = ?
        WHERE id = ?
        """,
        (
            classification["bucket"],
            raison,
            datetime.utcnow().isoformat(timespec="seconds"),
            pa_id,
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
            "Backfill geoloc Nominatim pour les PostalAddress Lespass sans coords.\n"
            "Persistance SQLite avec FK : crash-safe, reprise auto, revue humaine.\n"
            "A LANCER EN LOCAL, JAMAIS DEPUIS LA PROD."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_json",
        help="JSON produit par `manage.py export_tenants_addresses`",
    )
    parser.add_argument(
        "output_sqlite",
        help="Chemin du fichier SQLite (cree si absent, sinon reprise auto).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite aux N premieres PostalAddress a traiter.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop + recree la DB avant l'import (utile si JSON a change).",
    )
    parser.add_argument(
        "--no-name-search",
        action="store_true",
        help="Skip la recherche pour les PA n'ayant qu'un nom (plus sur).",
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
        for suffixe in ("-wal", "-shm"):
            chemin_aux = args.output_sqlite + suffixe
            if os.path.exists(chemin_aux):
                os.remove(chemin_aux)

    # --- Ouverture DB + import JSON ---
    connexion = ouvrir_db(args.output_sqlite)

    with open(args.input_json, "r", encoding="utf-8") as fichier:
        donnees_source = json.load(fichier)

    # Compat : si on recoit l'ancien format (liste plate) au lieu du nouveau
    # {tenants:[], postal_addresses:[]}, on stoppe avec un message clair.
    # / Compat: if we receive the old flat list format, stop with a clear message.
    if isinstance(donnees_source, list):
        print(
            "ERREUR : le JSON source est au format ancien (liste plate).\n"
            "Re-genere le JSON avec la version recente de export_tenants_addresses\n"
            "qui produit {tenants:[], postal_addresses:[]}.",
            file=sys.stderr,
        )
        sys.exit(1)

    (
        nb_t_inseres, nb_t_ignores, nb_pa_inserees, nb_pa_ignorees,
    ) = importer_json_dans_db(connexion, donnees_source)

    # --- Selection des PA a traiter ---
    pa_a_traiter = selectionner_pa_a_traiter(connexion, args.limit)
    nombre_total = len(pa_a_traiter)

    print(
        f"\n--- Import JSON -> SQLite ---\n"
        f"DB                            : {args.output_sqlite}\n"
        f"Tenants inseres / ignores     : {nb_t_inseres} / {nb_t_ignores}\n"
        f"PostalAddress inserees/ignor. : {nb_pa_inserees} / {nb_pa_ignorees}\n"
        f"\n"
        f"--- Selection a traiter ---\n"
        f"PA a geocoder via Nominatim   : {nombre_total}\n"
        f"ETA approximatif              : {formater_duree(nombre_total * DELAI_ENTRE_REQUETES_SEC)}\n",
        file=sys.stderr,
    )

    if nombre_total == 0:
        print("Rien a traiter. Fin.", file=sys.stderr)
        connexion.close()
        return

    # --- Boucle principale ---
    t0 = time.time()
    nombre_requetes_envoyees = 0

    for index_courant, row in enumerate(pa_a_traiter, start=1):
        classification = classer_et_construire_query(
            row, args.country_codes, not args.no_name_search
        )

        if classification["query"] is None:
            update_pa_skip(
                connexion, row["id"], classification,
                "aucune adresse ni nom exploitable",
            )
            print(
                f"[{index_courant}/{nombre_total}] pa#{row['id']} "
                f"({row['tenant_schema']}, no_data) -> skip",
                file=sys.stderr,
            )
            continue

        print(
            f"[{index_courant}/{nombre_total}] pa#{row['id']} "
            f"({row['tenant_schema']}, {classification['bucket']}) : "
            f"{classification['query'][:80]}",
            file=sys.stderr,
        )

        reponse = appeler_nominatim(
            classification["query"], classification["params_extra"]
        )
        update_pa_avec_resultat(
            connexion, row["id"], classification, reponse, row
        )
        nombre_requetes_envoyees += 1

        if nombre_requetes_envoyees % INTERVALLE_PROGRESSION == 0:
            afficher_progression(index_courant, nombre_total, t0)

        time.sleep(DELAI_ENTRE_REQUETES_SEC)

    duree_totale = time.time() - t0
    stats = compter_stats(connexion)
    connexion.close()

    print(
        f"\n--- Stats backfill Nominatim ---\n"
        f"Duree totale             : {formater_duree(duree_totale)}\n"
        f"Requetes envoyees        : {nombre_requetes_envoyees}\n"
        f"\n"
        f"=== Repartition par status (toute la table postal_addresses) ===\n",
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
        f"FROM postal_addresses GROUP BY nominatim_status\"\n"
        f"\n"
        f"  # Imports safe (lat/long uniquement) :\n"
        f"  sqlite3 {args.output_sqlite} \"SELECT pa.postgres_id, t.organisation, "
        f"pa.nominatim_latitude, pa.nominatim_longitude FROM postal_addresses pa "
        f"JOIN tenants t ON t.schema = pa.tenant_schema WHERE pa.nominatim_status='ok'\"\n"
        f"\n"
        f"  # Adresses partielles a completer (revue humaine) :\n"
        f"  sqlite3 {args.output_sqlite} \"SELECT pa.id, pa.postgres_id, t.organisation, "
        f"pa.nominatim_display_name, pa.proposed_street_address, pa.proposed_address_locality "
        f"FROM postal_addresses pa JOIN tenants t ON t.schema = pa.tenant_schema "
        f"WHERE pa.proposed_street_address IS NOT NULL AND pa.human_review_status='pending'\"\n"
        f"\n"
        f"  # Priorite revue : adresses PRINCIPALES (lieu du tenant) a revoir en premier :\n"
        f"  sqlite3 {args.output_sqlite} \"SELECT pa.id, t.organisation, "
        f"pa.nominatim_status, pa.nominatim_display_name FROM postal_addresses pa "
        f"JOIN tenants t ON t.schema = pa.tenant_schema WHERE pa.is_main_address=1 "
        f"AND pa.human_review_status='pending' AND pa.nominatim_status IS NOT NULL\"\n"
        f"\n"
        f"  # Approuver une adresse manuellement (pa.id, pas postgres_id) :\n"
        f"  sqlite3 {args.output_sqlite} \"UPDATE postal_addresses SET "
        f"human_review_status='approved', human_reviewed_at=datetime('now') WHERE id=42\"\n"
        f"\n"
        f"Ouvre {args.output_sqlite} dans DB Browser for SQLite pour la revue visuelle.\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
