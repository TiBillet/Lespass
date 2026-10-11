#!/bin/bash
# =============================================================================
# VÉRIFIER TRAEFIK ET LES CERTIFICATS — avant et pendant la nuit de la bascule.
# / CHECK TRAEFIK AND CERTIFICATES — before and during the cutover night.
#
# LOCALISATION : scripts/nuit_de_bascule/verifier_traefik.sh
# PROCÉDURE    : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-nuit-procedure.md
#
# LECTURE SEULE : le script ne fait que des requêtes DNS et HTTPS (GET), il ne
# modifie rien, ni sur le serveur ni dans Traefik.
# / READ ONLY: DNS lookups and HTTPS GET requests only.
#
# POUR CHAQUE DOMAINE, il vérifie :
#   1. le DNS pointe vers l'adresse IP attendue (si elle est donnée) ;
#   2. le certificat présenté est valide (chaîne de confiance), couvre bien le nom,
#      et expire dans plus de 14 jours ;
#   3. pour les sous-domaines : le certificat est bien le WILDCARD (*.tibillet.re,
#      *.tibillet.coop), pas un certificat par sous-domaine ;
#   4. le port 80 redirige vers HTTPS ;
#   5. le code HTTP rendu (200 site ouvert, 503 page de maintenance, autre = à voir).
#
# LANCER (sur le serveur, ou depuis n'importe quel poste) :
#   bash scripts/nuit_de_bascule/verifier_traefik.sh            # sans contrôle d'IP
#   bash scripts/nuit_de_bascule/verifier_traefik.sh 1.2.3.4    # + DNS = cette IP
#
# Code de sortie : 0 si tout est bon, 1 si au moins un contrôle échoue.
# / Exit code 0 if everything passes, 1 otherwise.
# =============================================================================

set -u

ADRESSE_IP_ATTENDUE="${1:-}"

# Les domaines à vérifier. Un sous-domaine « inventé » sert à prouver le wildcard :
# un certificat par hôte ne le couvrirait pas.
# Les domaines personnalisés sont ceux du routeur `custom_dns` du compose de prod.
# / Domains to check. A made-up subdomain proves the wildcard certificate.
DOMAINES_APEX="tibillet.re tibillet.coop"
SOUS_DOMAINES_WILDCARD="verification-wildcard.tibillet.re verification-wildcard.tibillet.coop"
DOMAINES_PERSONNALISES="guichet.latendresse.fr guichet.cafeasso.latendresse.fr fairefestival.fr www.fairefestival.fr tibillet.org"

JOURS_MINIMUM_AVANT_EXPIRATION=14
NOMBRE_D_ECHECS=0

afficher_ok()     { echo "  OK     $1"; }
afficher_echec()  { echo "  ÉCHEC  $1"; NOMBRE_D_ECHECS=$((NOMBRE_D_ECHECS + 1)); }
afficher_info()   { echo "  info   $1"; }

# Vérifie un domaine. Le second argument vaut « wildcard » quand le certificat doit
# être le certificat générique du domaine parent.
# / Checks one domain. Second argument "wildcard" requires the parent's wildcard cert.
verifier_un_domaine() {
    local domaine="$1"
    local attente_du_certificat="${2:-}"
    echo ""
    echo "=== ${domaine}"

    # 1. DNS / DNS lookup
    local adresse_resolue
    adresse_resolue=$(getent ahostsv4 "${domaine}" | awk 'NR==1 {print $1}')
    if [ -z "${adresse_resolue}" ]; then
        afficher_echec "DNS : le nom ne se résout pas"
        return
    fi
    if [ -n "${ADRESSE_IP_ATTENDUE}" ]; then
        if [ "${adresse_resolue}" = "${ADRESSE_IP_ATTENDUE}" ]; then
            afficher_ok "DNS : ${adresse_resolue}"
        else
            afficher_echec "DNS : ${adresse_resolue} (attendu : ${ADRESSE_IP_ATTENDUE})"
        fi
    else
        afficher_info "DNS : ${adresse_resolue}"
    fi

    # 2. Certificat présenté pour ce nom (SNI) / Certificate served for this name
    local certificat
    certificat=$(echo | timeout 15 openssl s_client -connect "${domaine}:443" -servername "${domaine}" 2>/dev/null \
        | openssl x509 2>/dev/null)
    if [ -z "${certificat}" ]; then
        afficher_echec "HTTPS : aucun certificat présenté sur le port 443"
        return
    fi

    local verification_de_la_chaine
    verification_de_la_chaine=$(echo | timeout 15 openssl s_client -connect "${domaine}:443" -servername "${domaine}" \
        -verify_hostname "${domaine}" -verify_return_error 2>&1 | grep -E "Verify return code")
    if echo "${verification_de_la_chaine}" | grep -q "Verify return code: 0 (ok)"; then
        afficher_ok "certificat valide pour ce nom (chaîne de confiance et nom)"
    else
        afficher_echec "certificat refusé : ${verification_de_la_chaine:-pas de réponse}"
    fi

    local secondes_minimum=$((JOURS_MINIMUM_AVANT_EXPIRATION * 24 * 3600))
    local date_d_expiration
    date_d_expiration=$(echo "${certificat}" | openssl x509 -noout -enddate | cut -d= -f2)
    if echo "${certificat}" | openssl x509 -noout -checkend "${secondes_minimum}" > /dev/null; then
        afficher_ok "expire le ${date_d_expiration} (plus de ${JOURS_MINIMUM_AVANT_EXPIRATION} jours)"
    else
        afficher_echec "expire le ${date_d_expiration} (moins de ${JOURS_MINIMUM_AVANT_EXPIRATION} jours)"
    fi

    # 3. Wildcard pour les sous-domaines / Wildcard for subdomains
    if [ "${attente_du_certificat}" = "wildcard" ]; then
        local domaine_parent="${domaine#*.}"
        if echo "${certificat}" | openssl x509 -noout -ext subjectAltName 2>/dev/null | grep -q "DNS:\*\.${domaine_parent}"; then
            afficher_ok "certificat générique *.${domaine_parent}"
        else
            afficher_echec "le certificat n'est PAS le wildcard *.${domaine_parent}"
        fi
    fi

    # 4. Redirection du port 80 / Port 80 redirect
    local reponse_http
    reponse_http=$(curl -s -o /dev/null -w "%{http_code} %{redirect_url}" --max-time 15 "http://${domaine}/")
    case "${reponse_http}" in
        30[1278]\ https://*) afficher_ok "le port 80 redirige vers HTTPS" ;;
        *) afficher_echec "le port 80 ne redirige pas vers HTTPS (${reponse_http})" ;;
    esac

    # 5. Code rendu en HTTPS / HTTPS status
    local code_https
    code_https=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "https://${domaine}/")
    case "${code_https}" in
        200|301|302) afficher_ok "HTTPS répond ${code_https} (site ouvert)" ;;
        503) afficher_info "HTTPS répond 503 (page de maintenance active ?)" ;;
        404) afficher_info "HTTPS répond 404 (normal pour un sous-domaine sans lieu)" ;;
        *) afficher_echec "HTTPS répond ${code_https}" ;;
    esac
}

echo "Vérification de Traefik et des certificats — $(date '+%Y-%m-%d %H:%M:%S')"
[ -n "${ADRESSE_IP_ATTENDUE}" ] && echo "Adresse IP attendue : ${ADRESSE_IP_ATTENDUE}"

for domaine in ${DOMAINES_APEX}; do
    verifier_un_domaine "${domaine}"
done
for domaine in ${SOUS_DOMAINES_WILDCARD}; do
    verifier_un_domaine "${domaine}" wildcard
done
for domaine in ${DOMAINES_PERSONNALISES}; do
    verifier_un_domaine "${domaine}"
done

echo ""
if [ "${NOMBRE_D_ECHECS}" -eq 0 ]; then
    echo "TOUT EST BON."
    exit 0
fi
echo "${NOMBRE_D_ECHECS} CONTRÔLE(S) EN ÉCHEC : ne pas continuer avant d'avoir compris."
exit 1
