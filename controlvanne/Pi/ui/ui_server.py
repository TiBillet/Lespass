# Fichier: ui_server.py
from flask import Flask, render_template, jsonify
import threading

app = Flask(__name__)

# Variable globale pour stocker l'état actuel de l'écran
# On stocke : le message principal, la couleur de fond, le solde, etc.
current_state = {
    "message": "Scannez votre badge",
    "color": "blue",  # blue, green, red
    "balance": "0.00"
}

@app.route('/status')
def status():
    """ Cette route sera appelée par le Javascript de la page pour rafraichir sans recharger """
    return jsonify(current_state)

def update_display(message, color="blue", balance="--"):
    """ Fonction appelée par le TibeerController pour changer l'écran """
    global current_state
    current_state["message"] = message
    current_state["color"] = color
    current_state["balance"] = str(balance)

def run_server():
    # On lance Flask sur le port 5000
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
