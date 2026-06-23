#!/bin/bash
# Script de gestion du mode débogage distant Chromium pour LaBoutik
# Usage: ./debug-chromium.sh [on|off|status]
#   on     : Active le débogage distant (--remote-debugging-port=9222)
#   off    : Désactive le débogage distant
#   status : Affiche l'état actuel du débogage

AUTOSTART_FILE="/etc/xdg/openbox/autostart"
DEBUG_FLAG="--remote-debugging-port=9222"

show_help() {
    echo "Usage: $0 [on|off|status]"
    echo ""
    echo "Commandes:"
    echo "  on     Active le débogage distant Chromium (port 9222)"
    echo "  off    Désactive le débogage distant"
    echo "  status Affiche l'état actuel du débogage"
    echo ""
    echo "Après modification, redémarrez le Pi pour appliquer les changements:"
    echo "  sudo reboot"
    echo ""
    echo "Pour se connecter au débogage distant:"
    echo "  1. Créer un tunnel SSH depuis votre PC:"
    echo "     ssh -L 9222:localhost:9222 sysop@<ip-du-pi>"
    echo "  2. Ouvrir dans le navigateur: http://localhost:9222"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "Erreur: Ce script doit être exécuté avec sudo"
        echo "Usage: sudo $0 [on|off|status]"
        exit 1
    fi
}

get_status() {
    if [ ! -f "$AUTOSTART_FILE" ]; then
        echo "Fichier autostart introuvable: $AUTOSTART_FILE"
        exit 1
    fi
    
    if grep -q -- "$DEBUG_FLAG" "$AUTOSTART_FILE"; then
        echo "Status: DÉBOGAGE ACTIVÉ"
        echo "Le navigateur Chromium démarre avec: $DEBUG_FLAG"
        echo ""
        echo "Pour se connecter:"
        echo "  1. ssh -L 9222:localhost:9222 sysop@<ip-du-pi>"
        echo "  2. http://localhost:9222"
        return 0
    else
        echo "Status: DÉBOGAGE DÉSACTIVÉ"
        echo "Chromium démarre en mode normal (kiosk)"
        return 1
    fi
}

enable_debug() {
    # Vérifier si le flag est déjà présent (une ou plusieurs fois)
    local count=$(grep -o -- "$DEBUG_FLAG" "$AUTOSTART_FILE" | wc -l)
    if [ "$count" -gt 0 ]; then
        echo "Le débogage est déjà activé ($count occurrence(s))"
        return 0
    fi
    
    # Sauvegarde du fichier original
    cp "$AUTOSTART_FILE" "${AUTOSTART_FILE}.bak"
    
    # Ajout du flag de débogage à la ligne chromium
    sed -i "s|chromium |chromium $DEBUG_FLAG |" "$AUTOSTART_FILE"
    
    echo "Débogage activé avec succès"
    echo "Redémarrez le Pi pour appliquer: sudo reboot"
}

disable_debug() {
    # Vérifier si le flag est présent
    local count=$(grep -o -- "$DEBUG_FLAG" "$AUTOSTART_FILE" | wc -l)
    if [ "$count" -eq 0 ]; then
        echo "Le débogage est déjà désactivé"
        return 0
    fi
    
    # Sauvegarde du fichier original
    cp "$AUTOSTART_FILE" "${AUTOSTART_FILE}.bak"
    
    # Suppression de TOUTES les occurrences du flag de débogage
    sed -i "s| $DEBUG_FLAG||g" "$AUTOSTART_FILE"
    
    echo "Débogage désactivé avec succès ($count occurrence(s) supprimée(s))"
    echo "Redémarrez le Pi pour appliquer: sudo reboot"
}

# Vérification des arguments
if [ "$#" -eq 0 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
    exit 0
fi

check_root

case "$1" in
    on)
        enable_debug
        ;;
    off)
        disable_debug
        ;;
    status)
        get_status
        ;;
    *)
        echo "Option invalide: $1"
        show_help
        exit 1
        ;;
esac
