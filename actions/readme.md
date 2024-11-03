# TiBillet / Action
#### Plugin de gestion d'action pour Lespass

## spec' vite fait'

- Priorisation et hierarchie des actions 
  - [x] Une action peut être enfant d'une autre action
  - [x] Possibilité de voter pour prioriser
  - [ ] peut filtrer par qty de vote
  - [ ] Une action peut être liée a un évènement LesPass

- Crowdfunding : Financement des actions
  - [x] Chaque sous action possède sa propre jauge de financement
  - [x] Jauge % visible des financements total des enfants sur action parent
  - [ ] Paiement direct via Stripe
  - [ ] Possibilité de financer l'action depuis son propre portefeuille TiBillet
  - [ ] Monnaie temps, euro, locale, libre

- Gestion de temps
  - [ ] Déclaration de contribution par user et par temps
  - [ ] Possiblité de limiter temps / user
  - [ ] Validation du temps passé par créateur de l'action

- Co-rémunération
  - [ ] Action validable par créateur de l'action
  - [ ] Rétribution sur portefeuille tibillet monnaie temps / fiduciaire / cadeau 
  - [ ] Stripe connect pour :
    - [ ] Virement vers compte Stripe des contributeurs
    - [ ] Vérification de la légalité de la structure contributrice

- Signature de contrat
  - [ ] Gestion de fichier pour facturation / devis / feuille de mission
  - [ ] Interop DocuSeal pour contrat de bénévolat / volontariat / feuille de mission / devis

- Intéropérabilité
  - Documents à signer :
    - [ ] Minio
    - [ ] Nextcloud
    - [ ] DocuSeal
  - Valorisation temps / co rem
    - [ ] Loot
    - [ ] Bénévalibre
  - Social
    - [ ] ActivityPub
  - Gestion de tâche :
    - [ ] Noé
    - [ ] Vikunja / WeKan / Github project, etc ...
    - [ ] Oceco si reprise de contact avec OpenAtlas (La balle est sortie du camp *sic*)
