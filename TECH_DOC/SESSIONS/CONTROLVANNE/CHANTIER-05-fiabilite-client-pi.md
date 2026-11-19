# CHANTIER 05 — Coupure de la vanne et fiabilité du client Pi

**Statut :** PROPOSÉ le 2026-11-19. Rien n'est codé.
**Périmètre :** le client Raspberry Pi (`controlvanne/Pi/`) et les vues serveur qu'il appelle
(`controlvanne/viewsets.py`, `controlvanne/billing.py`, `controlvanne/calibration_views.py`).
**Méthode :** lecture complète du code, puis deux relectures indépendantes. Chaque défaut porte
un statut : **vérifié** (relu dans le code) ou **à confirmer** (signalé par une relecture, pas
encore relu ligne à ligne).

---

## 1. Point de départ

Au salon du Capitole du Libre, la tireuse tournait en 4G. Deux constats ont été faits.

**Jonas :**
- La vanne ne se coupe pas tout de suite quand on retire la carte.
- Elle ne se coupe pas tout de suite non plus quand le solde tombe à zéro.
- Le badge est lent à être accepté.
- Il manque une doc pour les utilisateurs : tutoriel, branchements, calibration.

**Mike :**
- `CARD_GRACE_PERIOD_S` absorbe les micro-coupures du lecteur NFC.
- Ce qui est mesuré est facturé : il n'y a pas de perte.
- La lecture de la carte côté Pi prend moins de 0,35 s.
- La lenteur vient de l'autorisation par le serveur.

---

## 2. Comment le Pi fonctionne aujourd'hui

### 2.1 Une seule boucle

`Pi/controllers/tibeer_controller.py:68-107` est une boucle unique. Elle fait un tour toutes les
100 ms (`time.sleep(0.1)`, ligne 107). À chaque tour :

1. elle lit le lecteur NFC (`read_uid()`, ligne 69) ;
2. si une carte est là et qu'elle est nouvelle, elle demande l'autorisation au serveur ;
3. si c'est la même carte et que le service est en cours, elle envoie le volume au serveur ;
4. si aucune carte n'est là depuis plus de `CARD_GRACE_PERIOD_S` (3 s, ligne 25), elle ferme la
   session.

Les appels au serveur sont **synchrones** (`requests.post`). Pendant un appel, la boucle est
arrêtée : elle ne lit plus la carte et ne contrôle plus le volume.

### 2.2 Le débitmètre compte même quand la boucle est arrêtée

Le débitmètre est lu par un callback pigpio, déclenché par une interruption. Le compteur
`total_pulses` reste donc juste, même pendant un appel réseau. Seul le **contrôle** du volume
est retardé, pas la **mesure**.

### 2.3 Les appels au serveur

| Événement | Quand | Délai d'attente | Fichier |
|---|---|---|---|
| `authorize` | nouvelle carte | 2 s | `Pi/network/backend_client.py:76` |
| `pour_start` | juste après l'ouverture de la vanne | 3 s | `backend_client.py:111-114` |
| `pour_update` | au plus une fois par seconde | 1 s | `backend_client.py:111-114` |
| `pour_end` | plafond atteint ou fin de session | 3 s | `backend_client.py:111-114` |
| `card_removed` | carte retirée, dans tous les cas | 3 s | `backend_client.py:111-114` |

Avec `requests`, le délai d'attente vaut **pour chaque phase** : 2 s pour se connecter, **puis**
2 s pour recevoir la réponse. La résolution DNS n'est pas bornée. Un appel peut donc bloquer
plus longtemps que le chiffre écrit.

### 2.4 Qui décide du volume

- Le serveur calcule `allowed_ml` **une seule fois**, à l'`authorize`, selon le solde.
- Le Pi coupe la vanne lui-même quand le volume servi atteint `allowed_ml`.
- À la fin, le serveur facture `min(volume servi, allowed_ml)`. Le débordement au-delà du
  plafond n'est pas facturé (`billing.py`, docstring de `facturer_tirage`).

---

## 3. Ce qui est juste dans le diagnostic actuel

- **La période de grâce est nécessaire.** Le RC522 rate des lectures, probablement une sur deux
  (pas de `HALT` après `Anticoll`). Sans grâce, la vanne s'ouvrirait et se fermerait en boucle.
- **La lecture côté Pi est rapide.** La lenteur au badge vient bien du réseau.
- **La coupure au retrait prend environ 3 s**, pas plus. La grâce se compte depuis la dernière
  lecture réussie (`last_seen_ts`, ligne 78), prise avant l'appel bloquant.
- **Le débordement au plafond n'est pas facturé au client.** Le client ne paie jamais plus que
  son solde.

## 4. Ce qui est faux ou incomplet

- **« Ce qui est mesuré est facturé » a des trous.** Voir D1, D2 et D6 ci-dessous.
- **Le ressenti de Jonas est juste, mais la cause n'est pas la grâce.** Avec un robinet
  mécanique, le client ferme lui-même le robinet : les 3 s de grâce se voient peu. Ce qui gêne
  vraiment :
  - l'attente au badge, sans aucun retour visible pendant l'appel `authorize` ;
  - l'écran en retard sur la vanne : il passe par Pi → 4G → serveur → WebSocket → écran ;
  - le temps entre deux clients, à cause de `pour_end` qui est lent (D11).

---

## 5. Défauts

### 5.1 Argent et bière gratuite

**D1 — `card_removed` à 0 ml peut rendre un tirage gratuit.** *Vérifié.*
- Le Pi envoie toujours `card_removed` avec un volume de 0 (`tibeer_controller.py:204`).
- Le serveur traite `card_removed` comme `pour_end`, avec le volume reçu (`viewsets.py:1011-1016`).
- Il ne facture que si `volume_ml > 0` (`viewsets.py:328` et `347`).
- **Scénario :** `pour_end` échoue (délai dépassé, 4G coupée). Le Pi l'attrape (ligne 238) et
  continue. Puis `card_removed` arrive avec 0 ml. La session est close **sans facture**.
- **Correctif :** côté serveur, pour `card_removed`, facturer
  `max(volume reçu, session.dernier_volume_ml)`. Le serveur connaît déjà ce dernier volume
  (`viewsets.py:998`). Ce correctif protège aussi les Pi déjà installés, sans mise à jour.

**D2 — Une nouvelle calibration n'est pas appliquée par le Pi.** *Vérifié.*
- « Appliquer » enregistre le facteur en base seulement (`calibration_views.py:353-356`).
- Le Pi lit le facteur au démarrage (`Pi/main.py:74-77`) et au retrait d'une carte de
  maintenance (`tibeer_controller.py:219-220`). Nulle part ailleurs.
- **Effet :** après « Appliquer », les clients sont mesurés avec l'**ancien** facteur, jusqu'au
  prochain redémarrage ou au prochain passage d'une carte de maintenance.
- **Effet en plus :** la série de calibration suivante calcule
  `facteur_actuel × delta / réel` avec le facteur de la base, alors que le Pi a mesuré avec
  l'ancien. Le résultat est faux.
- **Correctif :** `authorize` renvoie `calibration_factor`. Le Pi l'applique **avant** de prendre
  `session_start_vol` (ligne 138). Sinon, le volume servi ferait un saut, car `volume_l()`
  recalcule tout le compteur avec le nouveau facteur.

**D3 — Le facteur par défaut est 6,5.** *À confirmer.*
- `Pi/hardware/flow_meter.py:21-23` : 6,5 par défaut.
- La fiche courante du YF-S201 donne 7,5. Sans calibration, l'écart serait d'environ 15 % sur
  chaque tirage.
- **À faire :** confirmer la référence exacte du capteur utilisé et sa fiche technique.

**D10 — Débitmètre muet : la vanne reste ouverte sans limite.** *À confirmer.*
- Si le débitmètre est débranché ou en panne, il n'y a aucune impulsion. Le plafond n'est jamais
  atteint. La bière coule gratuitement tant que la carte reste posée.
- Même cas, sans fraude : une carte oubliée sur le lecteur garde la session ouverte et bloque le
  client suivant.
- **Correctif :** si la vanne est ouverte et qu'aucune impulsion n'arrive pendant N secondes, la
  session se ferme. N reste à choisir (voir la section 9).

**D15 — Aucun volume minimal à l'`authorize`.** *À confirmer.*
- Une carte avec 1 centime ouvre la vanne au moins une seconde.
- **Correctif :** refuser si `allowed_ml` est sous un seuil.

### 5.2 Coupure en retard

**D6 — Le plafond n'est contrôlé qu'une fois par seconde.** *Vérifié.*
- `_handle_pouring_loop` sort tout de suite si moins d'une seconde s'est écoulée depuis le
  dernier envoi (lignes 166-167). Le contrôle du plafond (ligne 172) est **après** cette sortie.
- **Effet :** la vanne se coupe jusqu'à une seconde après le plafond, plus la durée d'un
  `pour_update` en attente réseau. Ce débordement n'est pas facturé : c'est une perte pour le
  lieu.
- Le contrôle n'a pas lieu non plus pendant la grâce (carte absente, service en cours).
- **Correctif :** contrôler le plafond à **chaque tour de boucle**, avant de tester si la carte
  est présente ou absente. L'envoi de `pour_update` reste limité à une fois par seconde.

### 5.3 Plantages

**D4 — `pour_start` n'est pas dans un `try`.** *Vérifié.*
- `tibeer_controller.py:152`. Une erreur réseau à ce moment remonte jusqu'à `main.py`, qui fait
  `sys.exit(1)`.
- La vanne vient d'être ouverte (ligne 141). systemd relance le service (`Restart=always`,
  `RestartSec=2`), et chaque relance fait d'abord un `git pull` (D13).

**D5 — `pour_end` au plafond n'est pas dans un `try`.** *Vérifié.*
- `tibeer_controller.py:175`. Même effet que D4. C'est l'appel le plus lent (D11), donc le plus
  exposé à un délai dépassé.

**À faire en premier :** chercher `Erreur fatale` dans `~/tibeer/logs/tibeer.log` du Pi du salon.
Ces deux plantages expliquent peut-être une partie de ce qui a été vu.

**D17 — Une session orpheline qui plante bloque la tireuse.** *À confirmer.*
- Au prochain `authorize`, le serveur ferme les sessions restées ouvertes
  (`viewsets.py:387` et suivantes). Si cette facturation lève une erreur, chaque `authorize`
  répond 500. La tireuse ne sert plus personne.
- Risque en plus : l'ancien Fedow peut être débité à chaque essai.

**D18 — Lecteur VMA405 : boucle lente et erreur non attrapée.** *À confirmer.*
- `readline` avec `timeout=1` : chaque tour prend 1,1 s.
- `RFIDReadError` n'est attrapée nulle part.

### 5.4 Lenteur réseau

**D7 — Pas de `requests.Session`.** *Vérifié.*
- Chaque appel refait DNS, TCP et TLS : 4 à 5 allers-retours 4G au lieu d'un seul.
- **Correctif :** une `requests.Session` créée une fois dans `BackendClient.__init__`.

**D8 — Les délais d'attente ne bornent pas l'appel entier.** *Vérifié.* Voir 2.3.

**D11 — `pour_end` fait attendre le Pi pour un simple affichage.** *Vérifié pour la lecture du
solde.*
- Après la facture, le serveur relit le solde sur l'ancien Fedow, par le réseau, pour l'afficher
  (`_lire_le_solde_de_la_carte`, vers `viewsets.py:1101`).
- Le Pi attend cette lecture avant de servir le client suivant.
- **Correctif :** ne plus faire attendre la réponse au Pi pour cette lecture. Le moyen reste à
  choisir : solde calculé en local, ou envoi par WebSocket après la réponse.

**D13 — `git pull` à chaque redémarrage du service.** *Vérifié.*
- `config/tibeer.service` : `ExecStartPre=git-update.sh`. En 4G faible, cela peut prendre
  jusqu'à 90 s. Avec D4 ou D5, chaque plantage coûte donc ce temps.

### 5.5 États bloqués

**D9 — Après un `authorize` raté, la carte est « morte » et l'écran ment.** *Vérifié pour la
carte morte.*
- `current_uid` est posé **avant** l'appel (ligne 86). Si l'appel échoue (lignes 119-123), la
  carte reste enregistrée comme « en cours ». La même carte est ignorée tant qu'elle n'a pas été
  retirée plus de 3 s.
- Côté serveur, la session est créée et le WebSocket est poussé **avant** la réponse. Si le Pi a
  abandonné l'attente, l'écran affiche « autorisé » alors que la vanne reste fermée.
- **Correctif :** après une erreur réseau, remettre `current_uid` à `None` pour retenter au tour
  suivant, avec une courte pause. La session fantôme sera close comme orpheline au prochain
  `authorize`.

**D12 — `card_removed` pendant un `authorize` lent.** *À confirmer.*
- La session peut être créée après coup, et l'écran reste figé sur « autorisé ».

**D16 — Un 404 sur `pour_update` ne ferme pas la vanne.** *À confirmer.*
- Une réponse autre que 200 renvoie `None`, sans erreur. Si le serveur a déjà clos la session,
  le Pi continue de servir.
- **Correctif :** sur 404, fermer la vanne et finir la session.

### 5.6 Code et tests

**D14 — `pytest.ini` n'a pas de `testpaths`.** *Vérifié.*
- Un `pytest` lancé sans argument à la racine collecte `controlvanne/Pi/tests/test_*.py`. Ces
  fichiers font `exit(1)` à l'import.

**D19 — `FlowMeter.update()` est du code mort, et sa formule est fausse.** *Vérifié.*
- Le débit calculé est 60 fois trop grand (`flow_meter.py:78-80`). La formule est recopiée dans
  le README.
- La boucle l'appelle à chaque tour (ligne 74) sans utiliser le résultat.

**D20 — Le contrôleur ne s'importe pas sans le matériel.** *Vérifié.*
- Les imports des lignes 16-19 (`RFIDReader`, `Valve`, `FlowMeter`, `BackendClient`) ne servent
  pas : les objets sont injectés par le constructeur. Ils chargent pourtant `pigpio` et `mfrc522`,
  ce qui empêche de tester le contrôleur sur une machine sans Pi.

**D21 — Le simulateur ne se comporte pas comme le vrai Pi.** *À confirmer.*
- `static/controlvanne/js/simu_pi.js` : grâce de 1 s au lieu de 3 s, plafond contrôlé à chaque
  tick, envois asynchrones. Les défauts D4, D5, D6 et D9 n'y apparaissent donc pas.

---

## 6. Solutions écartées

**Fermer la vanne à la première lecture manquée, en gardant la session.**
Écartée. Avec un RC522 qui rate une lecture sur deux, la vanne battrait à environ 5 Hz :
mousse, usure du relais, impulsions parasites sur le débitmètre.

**Contrôler le plafond dans le callback pigpio.**
Écartée. Le gain est d'au plus 5 ml, alors que le capteur est précis à ±10 %. Elle ajoute un
état partagé entre deux threads. Le contrôle à chaque tour de boucle (D6) suffit.

**Un fil d'envoi séparé, avec une file d'attente (`queue.Queue`).**
Reportée. Elle libérerait la boucle des appels réseau. Mais telle quelle, elle est dangereuse :
un `pour_end` encore dans la file peut fermer la **nouvelle** session du même client. Si elle
devient nécessaire, il faudra soit une file unique qui inclut `authorize`, soit un `session_id`
dans chaque événement et une file vidée avant chaque `authorize`. À ne faire que si les mesures
de l'étape 0 la justifient.

---

## 7. Plan

Chaque correctif commence par un test, vu en échec avant le correctif.

### Étape 0 — Mesurer

1. Lire les journaux du salon : `Erreur fatale` dans `~/tibeer/logs/tibeer.log`.
2. Ajouter des mesures horodatées dans les journaux du Pi :
   - durée de chaque appel HTTP ;
   - taux de lectures manquées du RC522 ;
   - temps entre la dernière lecture et la fermeture de la vanne.

### Étape 1 — Harnais de tests

1. Retirer les imports inutiles des lignes 16-19 (D20).
2. Écrire des faux objets : lecteur NFC, vanne, débitmètre, client serveur. Ils s'injectent par
   le constructeur `TibeerController(rfid, valve, flow_meter, client)`.
3. Extraire le corps de la boucle dans `un_tour_de_boucle(maintenant)`. Le test pilote ainsi le
   temps, sans `sleep`.
4. Ajouter `testpaths` dans `pytest.ini` (D14).

### Étape 2 — Correctifs courts

| Ordre | Défaut | Correctif | Test |
|---|---|---|---|
| 1 | D1 | `card_removed` facture `max(volume reçu, dernier_volume_ml)` | serveur : `pour_update` à 200 ml, puis `card_removed` à 0 → facture de 200 ml |
| 2 | D2 | `authorize` renvoie `calibration_factor`, appliqué avant `session_start_vol` | Pi : facteur changé entre deux sessions → la 2ᵉ utilise le nouveau |
| 3 | D4, D5 | `try` autour de `pour_start` et de `pour_end` au plafond | Pi : client qui lève `BackendError` → pas de plantage, vanne fermée au plafond |
| 4 | D6 | plafond contrôlé à chaque tour | Pi : plafond atteint 0,2 s après un `pour_update` → vanne fermée au tour suivant |
| 5 | D7 | `requests.Session` | lecture du code ; mesure de l'étape 0 avant et après |
| 6 | D9 | retenter `authorize` après une erreur réseau | Pi : 1ᵉʳ `authorize` en erreur, 2ᵉ accepté → vanne ouverte |
| 7 | D10 | fin de session si aucune impulsion pendant N s | Pi : vanne ouverte, 0 impulsion pendant N s → vanne fermée |
| 8 | D16 | 404 sur `pour_update` → fin de session | Pi : client qui renvoie 404 → vanne fermée |

### Étape 3 — Côté serveur

- D11 : ne plus faire attendre la réponse de `pour_end` pour la lecture du solde.
- D17 : une orpheline qui plante ne doit pas bloquer les `authorize` suivants.
- D15 : volume minimal à l'`authorize`.
- D21 : aligner `simu_pi.js` sur le vrai Pi.

### Étape 4 — Selon les mesures de l'étape 0

- Régler `CARD_GRACE_PERIOD_S` selon le taux réel de lectures manquées.
- Décider du fil d'envoi séparé (section 6).

### Étape 5 — Doc utilisateur

- Tutoriel d'installation, repris depuis `controlvanne/README.md:159-257`.
- Schéma de câblage complet. `Pi/asset/Cnx Pi.png` n'est référencé nulle part, et il ne montre
  ni le débitmètre ni la vanne.
- Câblage de puissance : diode de roue libre sur la vanne, signal 5 V du débitmètre face aux
  GPIO 3,3 V du Pi.
- Procédure de calibration, une fois D2 corrigé.
- Corriger la formule de débit recopiée dans le README (D19).

---

## 8. Hors périmètre

- Le passage au fil d'envoi séparé, tant que les mesures ne le justifient pas.
- Tout changement du protocole entre le Pi et le serveur, hors `calibration_factor` dans la
  réponse d'`authorize`.

## 9. Questions ouvertes

1. Quelle est la référence exacte du débitmètre, et d'où vient le facteur 6,5 ? (D3)
2. Les journaux du Pi du salon sont-ils encore disponibles ? (étape 0)
3. Le lecteur VMA405 est-il utilisé sur une vraie tireuse ? (D18)
4. Quel délai sans impulsion avant de fermer la vanne ? (D10) Il dépend du temps qu'un client
   met à ouvrir le robinet.
5. Quel volume minimal pour accepter une carte ? (D15)
6. Le relais et la vanne ont-ils déjà une diode de roue libre ? Le signal du débitmètre passe-t-il
   par un pont diviseur ? (étape 5)

## 10. Ce qui n'a pas été vérifié

- Les défauts marqués *à confirmer* viennent des relectures. Ils n'ont pas été relus ligne à
  ligne.
- Aucun test n'a été lancé. Aucune mesure n'a été faite sur un vrai Pi.
- Le taux de lectures manquées du RC522 (« une sur deux ») est une estimation tirée du code, pas
  une mesure.
