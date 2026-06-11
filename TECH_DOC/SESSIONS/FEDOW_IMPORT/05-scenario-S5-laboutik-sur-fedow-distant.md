# Recherche 05 — Scénario S5 : Fedow reste en place, LaBoutik V2 s'y branche en HTTP

Date : 2026-06-10
Proposition mainteneur : on laisse Fedow standalone là où il est, on le garde.
La caisse intégrée LaBoutik V2 (interne à Lespass) se branche sur le Fedow
**distant** via HTTP, plutôt que sur un `fedow_core` local.

Autrement dit : **aucune fusion**. Le chantier change de nature — ce n'est plus
« importer Fedow », c'est « porter la caisse intégrée en la câblant sur
l'existant ».

---

## 1. Ce que ça donne

- **Un seul moteur, un seul réseau FED** (comme S4) : nouveaux et anciens lieux
  partagent les mêmes cartes, les mêmes assets, la même fédération. Pas de
  dual-run, pas de dispatch, pas de double registre.
- **Zéro migration, zéro bascule DNS, zéro chirurgie** : pas d'ETL, pas de
  clash `AUTH_USER_MODEL`, pas de re-chiffrement de secrets, pas d'unification
  stripe ^12/^15, pas de nuit de bascule. Le risque immédiat est le plus bas
  des cinq scénarios.
- **Fedow reste isolé** : l'objection « couplage d'uptime » de S4 disparaît —
  un déploiement de Lespass ne touche jamais le moteur monétaire.
- **Le client existe déjà et est prouvé en prod** : `fedow_connect.FedowAPI`
  couvre tous les flux POS (scan carte, vente, recharge, remboursement,
  liaison, vidage) puisque LaBoutik V1 vit dessus depuis des années, à
  l'échelle festival (15 000 personnes). Pas de nouvelle API à concevoir.
- **La décision « adhésions hors assets » survit naturellement** : la caisse
  étant DANS Lespass, elle lit `BaseBillet.Membership` en DB directe pour la
  vérification d'adhésion au scan — plus besoin d'assets SUB ni du webhook
  `Membership_fwh` (la danse LaBoutik V1 → Fedow → webhook → Membership
  devient une simple écriture locale). C'est même plus simple que le V1.

## 2. Ce que ça coûte

1. **Le câblage de la caisse V2 est un vrai chantier** : le laboutik de
   `lespass-main` est construit sur les services `fedow_core` en DB directe
   (`CarteService.scanner_carte`, `fusionner_wallet_ephemere`,
   `rembourser_en_especes`, `process_cashless_refill`…). Il faut réécrire sa
   couche cashless contre `FedowAPI` (HTTP). Travail borné au module cashless
   du POS — produits, commandes, impressions, clôtures, comptabilité sont
   indépendants de Fedow. À noter : **S4 aurait aussi exigé ce câblage**
   (le laboutik V2 visait le fedow_core V2, pas le moteur legacy importé) —
   ce coût est commun aux deux scénarios, pas un surcoût de S5.
2. **L'API inter-service devient éternelle** (ou très durable) : RSA, handshake,
   API keys, cache wallet 10 s, gestion des pannes réseau en pleine vente —
   toute la plomberie que la fusion voulait tuer est non seulement conservée,
   mais gagne un consommateur de plus. La dette d'architecture continue de
   produire ses intérêts.
3. **Latence par action de caisse** : chaque scan/paiement = HTTPS + signature
   RSA vers un serveur distant. Prouvé acceptable par LaBoutik V1 en prod —
   mais le POS V2 devra soigner l'UX d'erreur réseau (file d'attente du bar à
   2 h du matin).
4. **Fedow standalone devient une infra de long terme à assumer** : SQLite
   mono-writer (plafond de scalabilité lointain mais réel), sauvegardes,
   monitoring, hébergement, et la classe de bugs DRIFT reste sur ce code
   (patch F() en place, drift corrigé cette nuit, forks de chaîne tolérés).
5. **L'objectif initial du chantier est abandonné — ou différé** : pas de
   suppression de l'API, pas d'intégration de la base. À dire explicitement.

## 3. Le point stratégique : S5 ne ferme aucune porte — il compose avec S4

S5 et S4 ne sont pas concurrents, ce sont des **phases** :

- **S5 = la phase produit** : livrer la caisse intégrée aux nouveaux tenants,
  sur le réseau existant, au plus vite et au moindre risque.
- **S4 = la phase infra**, optionnelle et plus tard : déménager Fedow dans
  Lespass (DNS + ETL tel quel). Le jour où S4 passe, les appels HTTP du POS V2
  se désamorcent comme tous les autres call sites de `fedow_connect` —
  ils en font simplement partie.

Pas besoin de couche d'abstraction « wallet provider » pour préparer ça
(sur-ingénierie) : le POS V2 appelle `FedowAPI` directement, comme BaseBillet
le fait aujourd'hui ; le désamorçage éventuel remplacera ces appels comme les
autres.

## 4. Verdict

S5 est **le chemin le plus court et le moins risqué vers la valeur produit**
(nouveaux tenants avec caisse intégrée + réseau FED unique), au prix de
l'abandon — ou du report sine die — de l'objectif d'architecture (un seul
moteur, suppression de l'API inter-service).

Classement révisé selon l'objectif prioritaire :
- **Priorité produit / risque minimal** : S5, puis S4 plus tard si désiré.
- **Priorité architecture / extinction de la dette** : S4 directement.
- S1, S2, S3 restent dépassés dans tous les cas.

La question décisive : **assumes-tu de maintenir le serveur Fedow et son API
RSA comme infrastructure de long terme ?** Si oui → S5. Si l'objectif reste de
les éteindre → S4, et S5 peut quand même servir d'étape intermédiaire
(le câblage HTTP du POS V2 n'est pas du travail perdu, il est désamorçable).

## 5. Périmètre du chantier si S5 est acté

1. Port du laboutik V2 dans ce repo (hors couche cashless) — gros morceau,
   indépendant de Fedow.
2. Réécriture de la couche cashless du POS contre `FedowAPI` (HTTP),
   avec UX d'erreur réseau soignée.
3. Vérification d'adhésion au scan via `BaseBillet.Membership` en DB directe
   (suppression de la dépendance aux assets SUB pour les tenants à caisse V2).
4. Onboarding des nouveaux tenants : flux existant (handshake place,
   FedowConfig) — déjà en prod.
5. Aucun portage de `fedow_core`, aucun ETL, aucune bascule.

Les findings de l'audit (doc 02) deviennent sans objet pour ce chantier,
SAUF : la fiabilité opérationnelle de Fedow standalone (DRIFT corrigé à
vérifier : drift=0), et les findings sur le flux d'onboarding
(`Onboard_laboutik`, `link_cashless_to_place`) qui restent le chemin actif.
