# CHANTIER 05 — Coupure de la vanne et fiabilité du client Pi

**Statut :** EN COURS. Il ne reste que D3 (réponse de Mike) et la doc utilisateur (section 7).
- D7 et D9 : faits par la PR #506 (fusionnée le 2026-11-19).
- D1, D2, D4, D5, D6 et D20 : faits et commités le 2026-11-19 (`b1b474df`, `0636f911`). Voir
  `CHANGELOG/2026-11-19-tireuse-retrait-facture-et-calibration-au-badge.md` et
  `CHANGELOG/2026-11-19-tireuse-plafond-et-erreurs-reseau.md`.
- D8 et D12 : acceptés en l'état.
- D11, D14, D16, D17, D18, D21 : abandonnés après tri (section 8).
- D13, D15 : reportés (section 8).

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
| `authorize` | nouvelle carte | 3 s connexion, 4 s réponse (PR #506) | `Pi/network/backend_client.py` (`AUTHORIZE_TIMEOUT_S`) |
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

**D1 — `card_removed` à 0 ml peut rendre un tirage gratuit.** ✅ *Fait le 2026-11-19 : plancher au
`dernier_volume_ml` dans `_cloturer_session_et_facturer`, pour toutes les clôtures.*
- Le Pi envoie toujours `card_removed` avec un volume de 0 (`tibeer_controller.py:204`).
- Le serveur traite `card_removed` comme `pour_end`, avec le volume reçu (`viewsets.py:1011-1016`).
- Il ne facture que si `volume_ml > 0` (`viewsets.py:328` et `347`).
- **Scénario :** `pour_end` échoue (délai dépassé, 4G coupée). Le Pi l'attrape (ligne 238) et
  continue. Puis `card_removed` arrive avec 0 ml. La session est close **sans facture**.
- **Correctif :** côté serveur, pour `card_removed`, facturer
  `max(volume reçu, session.dernier_volume_ml)`. Le serveur connaît déjà ce dernier volume
  (`viewsets.py:998`). Ce correctif protège aussi les Pi déjà installés, sans mise à jour.

**D2 — Une nouvelle calibration n'est pas appliquée par le Pi.** ✅ *Fait le 2026-11-19 : facteur
dans les deux réponses d'`authorize`, appliqué avant `session_start_vol`. La relecture après une
carte de maintenance est supprimée. Déployer le serveur avant les Pi.*
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

**D3 — Le facteur par défaut est 6,5.** *À confirmer. En attente de Mike (décision du 2026-11-19).*
- `Pi/hardware/flow_meter.py:21-23` : 6,5 par défaut.
- La fiche courante du YF-S201 donne 7,5. Sans calibration, l'écart serait d'environ 15 % sur
  chaque tirage.
- **À faire :** confirmer la référence exacte du capteur utilisé et sa fiche technique.

### 5.2 Coupure en retard

**D6 — Le plafond n'est contrôlé qu'une fois par seconde.** ✅ *Fait le 2026-11-19 :
`_fermer_si_plafond_atteint()` à chaque tour de `run()`, aussi pendant la grâce.*
- `_handle_pouring_loop` sort tout de suite si moins d'une seconde s'est écoulée depuis le
  dernier envoi (lignes 166-167). Le contrôle du plafond (ligne 172) est **après** cette sortie.
- **Effet :** la vanne se coupe jusqu'à une seconde après le plafond, plus la durée d'un
  `pour_update` en attente réseau. Ce débordement n'est pas facturé : c'est une perte pour le
  lieu.
- Le contrôle n'a pas lieu non plus pendant la grâce (carte absente, service en cours).
- **Correctif :** contrôler le plafond à **chaque tour de boucle**, avant de tester si la carte
  est présente ou absente. L'envoi de `pour_update` reste limité à une fois par seconde.

**Débordement restant après D6 (relecture Opus et Fable du 2026-11-19).**
- Pendant un appel réseau, la boucle est bloquée et le plafond n'est pas vérifié. L'appel qui
  compte est `pour_update`, une fois par seconde pendant le service.
- Ordre de grandeur, avec un débit supposé de 50 ml/s (non mesuré) :

  | Réseau | Débordement |
  |---|---|
  | Boucle libre | 5 ml au plus |
  | 4G correcte (0,3 à 0,5 s par appel) | 5 à 10 ml en moyenne, 25 ml au pire : sous l'erreur du capteur |
  | 4G faible (environ 2 s par appel) | environ 50 ml en moyenne, 100 ml au pire : 0,35 à 0,80 € |

- Le plafond n'est atteint que quand le solde s'épuise pendant le service : au plus une fois par
  carte.
- Un trou plus rare existe au début du service : `pour_start` part juste après `valve.open()`,
  avec un délai de 3 s pour la connexion puis 3 s pour la réponse. Il ne compte que pour un petit
  solde sur un réseau lent. Le client met aussi environ 1 s à ouvrir le robinet.
- **Décision : ne rien faire de plus pour l'instant, et mesurer.** Le serveur journalise déjà
  chaque débordement : `Débordement non facturé … servi X ml, autorisé Y ml`
  (`controlvanne/billing.py`, dans `facturer_tirage`). Relever ces lignes après le prochain salon.
- **Parade de secours, si les journaux montrent une vraie perte :** ne plus envoyer
  `pour_update` dans les ~150 derniers ml avant le plafond (2 à 3 lignes dans
  `_handle_pouring_loop`). Aucun appel réseau ne bloque alors la boucle près du plafond, et D6
  suffit. Prix : l'écran reste figé environ 3 s avant la fin. Si le `pour_end` final se perd,
  jusqu'à 150 ml ne sont pas facturés.

### 5.3 Plantages

**D4 — `pour_start` n'est pas dans un `try`.** ✅ *Fait le 2026-11-19.*
- `tibeer_controller.py:152`. Une erreur réseau à ce moment remonte jusqu'à `main.py`, qui fait
  `sys.exit(1)`.
- La vanne vient d'être ouverte (ligne 141). systemd relance le service (`Restart=always`,
  `RestartSec=2`), et chaque relance fait d'abord un `git pull` (D13, reporté).

**D5 — `pour_end` au plafond n'est pas dans un `try`.** ✅ *Fait le 2026-11-19 : la vanne se ferme
avant l'appel, l'appel est dans un `try`.*
- `tibeer_controller.py:175`. Même effet que D4. C'est l'appel le plus lent (D11), donc le plus
  exposé à un délai dépassé.

**À vérifier :** chercher `Erreur fatale` dans `~/tibeer/logs/tibeer.log` du Pi du salon. Ces deux
plantages expliquent peut-être une partie de ce qui a été vu.

**D17 — Une session orpheline qui plante bloque la tireuse.** ❌ *Abandonné (section 8).*
- Au prochain `authorize`, le serveur ferme les sessions restées ouvertes
  (`viewsets.py:387` et suivantes). Si cette facturation lève une erreur, chaque `authorize`
  répond 500. La tireuse ne sert plus personne.
- Risque en plus : l'ancien Fedow peut être débité à chaque essai.

**D18 — Lecteur VMA405 : boucle lente et erreur non attrapée.** ❌ *Abandonné (section 8).*
- `readline` avec `timeout=1` : chaque tour prend 1,1 s.
- `RFIDReadError` n'est attrapée nulle part.

### 5.4 Lenteur réseau

**D7 — Pas de `requests.Session`.** ✅ *Fait par la PR #506.*
- Chaque appel refait DNS, TCP et TLS : 4 à 5 allers-retours 4G au lieu d'un seul.
- **Correctif :** une `requests.Session` créée une fois dans `BackendClient.__init__`.

**D8 — Les délais d'attente ne bornent pas l'appel entier, et le serveur attend plus longtemps
que le Pi.** *Vérifié.*
- Côté Pi : voir 2.3. Le délai vaut pour chaque phase (connexion, puis réponse).
- Côté serveur : les appels à l'ancien Fedow ont un délai de **30 s** par défaut
  (`fedow_connect/fedow_api.py:117`, `130` et `781`). `authorize` peut en faire jusqu'à deux :
  rapatrier une carte inconnue, puis lire le solde.
- **Effet :** le Pi abandonne au bout de 4 s, mais le serveur continue. Il peut créer la session
  et pousser « autorisé » bien après. C'est la cause de D12, et du risque résiduel de D17.
- **Décision du 2026-11-19 : accepté en l'état.** Un ordre de grandeur de 9 s n'est pas un souci.
  Les délais de Fedow ne changent pas.

**D11 — `pour_end` fait attendre le Pi pour un simple affichage.** ❌ *Abandonné (section 8).*
- Après la facture, le serveur relit le solde sur l'ancien Fedow, par le réseau, pour l'afficher
  (`_lire_le_solde_de_la_carte`, vers `viewsets.py:1101`).
- Le Pi attend cette lecture avant de servir le client suivant.
- **Correctif :** ne plus faire attendre la réponse au Pi pour cette lecture. Le moyen reste à
  choisir : solde calculé en local, ou envoi par WebSocket après la réponse.

### 5.5 États bloqués

**D9 — Après un `authorize` raté, la carte est « morte » et l'écran ment.** ✅ *Fait par la PR
#506 : nouvel essai toutes les 2,5 s sur erreur réseau seulement, `card_removed` conservé.*
- `current_uid` est posé **avant** l'appel (ligne 86). Si l'appel échoue (lignes 119-123), la
  carte reste enregistrée comme « en cours ». La même carte est ignorée tant qu'elle n'a pas été
  retirée plus de 3 s.
- Côté serveur, la session est créée et le WebSocket est poussé **avant** la réponse. Si le Pi a
  abandonné l'attente, l'écran affiche « autorisé » alors que la vanne reste fermée.
- **Correctif (PR #506) :** après une erreur réseau, l'indicateur `authorize_a_refaire` relance
  `authorize` à la lecture suivante, après 2,5 s de pause. La carte reste la carte courante : son
  retrait envoie `card_removed`. Une réponse du serveur, même une page 500, n'est jamais réessayée.

**D12 — `card_removed` pendant un `authorize` lent.** *Vérifié dans le code, pas reproduit.*
- Le Pi abandonne `authorize` (4 s), attend 2,5 s, puis 3 s de grâce, et envoie `card_removed`.
- Si le serveur est encore dans `authorize` (Fedow lent, voir D8), `card_removed` ne trouve aucune
  session : l'écran revient à « En attente ».
- Puis `authorize` se termine, crée la session et pousse « autorisé ». L'écran reste figé
  jusqu'au badge suivant. Côté argent, rien : la session est close à 0 ml au badge suivant.
- Depuis la PR #506, il faut un `authorize` de plus de 9,5 s côté serveur.
- **Décision du 2026-11-19 : accepté en l'état**, comme D8.

**D16 — Un 404 sur `pour_update` ne ferme pas la vanne.** ❌ *Abandonné (section 8).*
- Une réponse autre que 200 renvoie `None`, sans erreur. Si le serveur a déjà clos la session,
  le Pi continue de servir.
- **Correctif :** sur 404, fermer la vanne et finir la session.

### 5.6 Code et tests

**D14 — `pytest.ini` n'a pas de `testpaths`.** ❌ *Abandonné (section 8).*
- Un `pytest` lancé sans argument à la racine collecte `controlvanne/Pi/tests/test_*.py`. Ces
  fichiers font `exit(1)` à l'import.

**D19 — `FlowMeter.update()` est du code mort, et sa formule est fausse.** *Vérifié. Facultatif :
à faire en passant, avec la doc.*
- Le débit calculé est 60 fois trop grand (`flow_meter.py:78-80`). La formule est recopiée dans
  le README.
- La boucle l'appelle à chaque tour (ligne 74) sans utiliser le résultat.

**D20 — Le contrôleur ne s'importe pas sans le matériel.** ✅ *Fait le 2026-11-19 : imports retirés,
premiers tests dans `tests/pytest/test_controlvanne_pi_controleur.py`.*
- Les imports des lignes 16-19 (`RFIDReader`, `Valve`, `FlowMeter`, `BackendClient`) ne servent
  pas : les objets sont injectés par le constructeur. Ils chargent pourtant `pigpio` et `mfrc522`,
  ce qui empêche de tester le contrôleur sur une machine sans Pi.

**D21 — Le simulateur ne se comporte pas comme le vrai Pi.** ❌ *Abandonné (section 8).*
- `static/controlvanne/js/simu_pi.js` : grâce de 1 s au lieu de 3 s, plafond contrôlé à chaque
  tick, envois asynchrones. Les défauts D4, D5, D6 et D9 n'y apparaissent donc pas.

---

## 6. Solutions écartées

**Fermer la session quand le débitmètre ne compte plus rien pendant N secondes.**
Écartée le 2026-11-19. Sur le terrain, une vanne ouverte sans débit se voit tout de suite. Une
coupure automatique gênerait surtout un client lent à se servir.

**Fermer la vanne à la première lecture manquée, en gardant la session.**
Écartée. Avec un RC522 qui rate une lecture sur deux, la vanne battrait à environ 5 Hz :
mousse, usure du relais, impulsions parasites sur le débitmètre.

**Fermer la vanne depuis le callback pigpio du débitmètre, à chaque impulsion.**
Écartée le 2026-11-19, après relecture par Opus et Fable.
- L'idée marche techniquement : dans pigpio 1.78, le callback tourne dans son propre thread
  (`_callback_thread`). Il continue pendant qu'un appel réseau bloque la boucle.
- **Mais une erreur dans le callback arrête le comptage, sans rien signaler.** La boucle `run()`
  de `_callback_thread` appelle `cb.func(...)` sans aucun `try`. Aujourd'hui, `_callback` ne fait
  que deux additions et ne peut pas planter. Avec `valve.close()` dedans, une erreur (pigpiod
  coupé, journal) tuerait le thread : plus aucune impulsion comptée jusqu'au redémarrage, donc
  plus de plafond ni de facture. La seule parade serait un `try` qui avale l'erreur.
- Autres pièges : un seuil resté armé couperait la session suivante dès sa première impulsion.
  Et le vrai callback ne se teste pas hors du Pi, car `flow_meter.py` importe pigpio.
- Le gain ne le justifie pas : voir « Débordement restant après D6 » dans la fiche D6.

**Deux boucles : une boucle locale et un fil d'envoi au serveur.**
Option gardée sous condition (décision du 2026-11-19).
- **Le principe :** une boucle lit la carte et le débitmètre et pilote la vanne, sans jamais
  attendre le réseau. Une seconde boucle envoie les messages au serveur.
- **Son seul gain réel :** `pour_update` bloque la boucle chaque seconde pendant le service, le
  temps d'un aller-retour réseau (environ 0,3 à 0,5 s en 4G correcte, jusqu'à 2 s en 4G
  faible). Pendant ce temps, la boucle ne voit pas le plafond. Les autres appels arrivent quand
  la vanne est fermée, ou doivent rester dans l'ordre.
- **Depuis D6**, le débordement au plafond se limite à un aller-retour réseau de débit. Il n'est
  pas facturé.
- **À faire seulement si** ce débordement reste gênant en 4G, et si la parade de secours de D6
  (pas de `pour_update` près du plafond) ne suffit pas.
- **Version réduite à faire dans ce cas :** seul `pour_update` part par la seconde boucle. La
  boucle principale attend que la file soit vide avant chaque `pour_end`, `card_removed` et
  `authorize`. Cette attente est indispensable : depuis D1, la clôture facture au moins le
  dernier `pour_update` reçu. Un `pour_update` en retard qui tomberait sur la session suivante
  du même client lui ferait facturer l'ancien volume.

---

## 7. Ce qui reste à faire

1. **D3 :** attendre la réponse de Mike sur la référence du débitmètre et l'origine du 6,5.
2. **Doc utilisateur :**
   - tutoriel d'installation, repris depuis `controlvanne/README.md:159-257` ;
   - schéma de câblage complet : `Pi/asset/Cnx Pi.png` n'est référencé nulle part, et il ne
     montre ni le débitmètre ni la vanne ;
   - câblage de puissance : diode de roue libre sur la vanne, signal 5 V du débitmètre face aux
     GPIO 3,3 V du Pi ;
   - procédure de calibration : le facteur s'applique au badge suivant (D2) ;
   - en passant, D19 : supprimer `FlowMeter.update()` et corriger la formule du README.
3. **À vérifier une fois :** chercher `Erreur fatale` dans les journaux du Pi du salon.
4. **Après le prochain salon :** relever `Débordement non facturé` dans les journaux du serveur.
   Si la perte est réelle, appliquer la parade de secours de D6.

Les tests du contrôleur du Pi sont dans `tests/pytest/test_controlvanne_pi_controleur.py`. Ils
utilisent de faux objets et une fausse horloge, et font tourner la vraie boucle `run()`.

---

## 8. Hors périmètre

### Reportés, à revoir plus tard (décision du 2026-11-19)

Ces deux points ne posent pas de souci tout de suite.

**D15 — Aucun volume minimal à l'`authorize`.** *À confirmer.*
- Une carte avec 1 centime ouvre la vanne au moins une seconde.
- **Correctif :** refuser si `allowed_ml` est sous un seuil.

**D13 — `git pull` à chaque redémarrage du service.** *Vérifié.*
- `config/tibeer.service` : `ExecStartPre=git-update.sh`. En 4G faible, cela peut prendre
  jusqu'à 90 s. Avec D4 ou D5, chaque plantage coûte donc ce temps.

### Abandonnés après tri (décision du 2026-11-19)

Ces points sont théoriques ou sans effet sur le terrain. Les traiter serait de la
sur-ingénierie.

- **D11** : attendre la lecture de Fedow pour afficher le solde restant est voulu.
- **D14** : pytest se lance toujours avec le chemin `tests/pytest/`.
- **D16** : le serveur ne clôt pas une session pendant que le Pi sert, sauf action dans l'admin.
- **D17** : jamais observé. S'il arrive, Sentry le montrera, et on corrigera la cause.
- **D18** : le lecteur VMA405 n'est pas utilisé.
- **D21** : `simu_pi.js` est un outil de démo.
- **Ajouter des mesures horodatées dans le Pi** : Mike a déjà mesuré ce qui comptait (PR #506).
- **Extraire `un_tour_de_boucle(maintenant)`** : la fausse horloge suffit pour tester `run()`.

### Exclus

- Les deux boucles, tant que le débordement au plafond ne gêne pas (section 6).
- Tout changement du protocole entre le Pi et le serveur, hors `calibration_factor` dans la
  réponse d'`authorize`.

## 9. Questions ouvertes

1. Quelle est la référence exacte du débitmètre, et d'où vient le facteur 6,5 ? (D3)
2. Les journaux du Pi du salon sont-ils encore disponibles ?
3. Le relais et la vanne ont-ils déjà une diode de roue libre ? Le signal du débitmètre passe-t-il
   par un pont diviseur ? (doc utilisateur)

## 10. Ce qui n'a pas été vérifié

- Aucun correctif n'a été essayé sur un vrai Pi. Les tests à faire à la main sont dans les deux
  fichiers `CHANGELOG/` du 2026-11-19.
- Les correctifs sont couverts par des tests automatiques : serveur dans
  `tests/pytest/test_controlvanne_api.py`, Pi dans `tests/pytest/test_controlvanne_pi_controleur.py`.
- Le taux de lectures manquées du RC522 (« une sur deux ») est une estimation tirée du code, pas
  une mesure.
