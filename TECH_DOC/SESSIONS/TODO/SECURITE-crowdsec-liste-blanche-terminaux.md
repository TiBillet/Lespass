# Sécurité — ne jamais laisser crowdsec bannir les caisses d'un lieu

> **Statut** : idée, spec à écrire. Demande du mainteneur (2026-10-11), en préparant la nuit de
> bascule du chantier 05 (passage à Traefik v3 + crowdsec).
> Pré-requis : Traefik v3 et crowdsec en production, et **quelques jours de mesures en mode
> simulation** (voir « Mesurer d'abord »).

## Le problème, en une phrase
crowdsec bannit 4 h une IP qui « ressemble à un robot » ; or 30 caisses (ou le public sur le wifi
du lieu) sortent par **une seule IP publique**, et chaque geste HTMX appelle une URL différente :
la caisse d'un festival peut être bannie en pleine soirée.

## Ce qui est en place (pile `~/Gits/TraefikV3/wildcard_conf`)
- crowdsec lit le journal d'accès de Traefik (`acquis.yaml`) ; collection `crowdsecurity/traefik`
  (scénarios HTTP de base, dont `http-crawl-non_statics` et `http-probing`) ;
- toute alerte → **bannissement 4 h** (`crowdsec/config/profiles.yaml`) ;
- le bouncer (plugin Traefik) ne filtre pas les IP de `clientTrustedIPs`
  (`traefik_dynamic.yml`) : aujourd'hui, seulement les plages privées.

## L'idée du mainteneur : la liste blanche suit l'appairage des terminaux
Un nouvel appareil est appairé (code PIN : `discovery.PairingDevice` → `laboutik.Terminal` →
`AuthBillet.TermUser`) : on prend son IP et on la met en liste blanche.

**Jouable, avec une correction importante : l'IP à prendre n'est pas celle de l'appairage.**
Un terminal est souvent appairé au bureau, puis emporté au festival (autre box, 4G) ; et l'IP
publique d'une box change. L'IP de l'appairage serait fausse le soir même.
→ Prendre **l'IP vue à chaque requête authentifiée du terminal** (« dernière IP vue »), et la
garder en liste blanche **pour une durée courte** (ex. 24 h, prolongée tant que le terminal parle).

### Forme proposée (à trancher dans la spec)
1. **Lespass note la dernière IP de chaque terminal** : à chaque requête authentifiée d'un
   `TermUser` actif, `AuthBillet/utils.py` `get_client_ip(request)` (elle remonte déjà la chaîne
   des proxys de confiance : le client ne peut pas la falsifier). Un champ « dernière IP » et
   « vue le » sur le terminal, mis à jour au plus une fois par minute (pas une écriture par requête).
2. **Lespass expose la liste** des IP de terminaux actifs vus depuis moins de 24 h : une route
   interne protégée (clé API dédiée, réseau interne seulement), qui ne rend que des IP, sans nom
   de lieu ni de terminal (minimisation des données).
3. **Un petit script sur l'hôte**, toutes les minutes (cron ou timer systemd), lit cette liste et
   la recopie dans crowdsec : `cscli allowlists` (listes blanches centralisées, crowdsec ≥ 1.6.8 ;
   **à vérifier** sur la version installée) avec une expiration, ou à défaut retire les
   bannissements (`cscli decisions delete --ip`). Lespass ne parle jamais au socket Docker ni au
   conteneur crowdsec : c'est l'hôte qui tire, pas Lespass qui pousse.
4. Terminal révoqué (`TermUser.is_active = False`) → son IP sort de la liste au tour suivant.

### Limites à écrire dans la spec
- Une IP partagée (wifi du festival) blanchit aussi le public derrière la même box : acceptable,
  c'est le même lieu, et crowdsec continue de protéger tout le reste d'Internet.
- Un terminal volé et encore actif blanchit l'IP de son voleur : la révocation (point 4) suffit.
- Le premier geste d'un terminal sur une IP nouvelle n'est pas encore en liste blanche (une
  minute) : sans conséquence, un bannissement demande une rafale de requêtes.

## Plus simple, à essayer AVANT d'automatiser
- **Liste blanche par chemin** : un parseur crowdsec
  (`/etc/crowdsec/parsers/s02-enrich/tibillet-caisses.yaml`, `expression:
  evt.Meta.http_path startsWith '/laboutik/'`) : le trafic de caisse n'est plus analysé, quelle
  que soit l'IP. Zéro code dans Lespass. Défaut : un robot qui ne frapperait QUE `/laboutik/`
  échapperait à l'analyse (ces routes demandent une authentification de toute façon).
- **Mode simulation** pour les deux scénarios à risque (`cscli simulation enable
  crowdsecurity/http-crawl-non_statics`, `crowdsecurity/http-probing`) : alertes notées, aucun
  bannissement.
- **Lieux à IP fixe connue** : dans `clientTrustedIPs` de `traefik_dynamic.yml`.

## Mesurer d'abord
1. `docker exec crowdsec cscli metrics` (section « Scenario Metrics », colonne « Overflow ») et
   `cscli alerts list` pendant quelques jours en simulation : des IP de lieux y apparaissent-elles ?
2. Rejouer un vrai soir de festival : `docker exec crowdsec crowdsec -c /etc/crowdsec/config.yaml
   -dsn file:///var/log/traefik/access.log -type traefik -no-api`, puis `cscli alerts list`.
3. Panne de crowdsec : `docker stop crowdsec` puis
   `scripts/nuit_de_bascule/verifier_traefik.sh 51.77.151.34` : si tout passe en 403, le plugin
   bloque quand crowdsec est injoignable → le régler pour laisser passer.

**Décision attendue** : si les mesures ne montrent aucune IP de lieu, la liste blanche par chemin
suffit ; l'automatisation par terminal n'a de sens que si des lieux sont bannis malgré elle.
