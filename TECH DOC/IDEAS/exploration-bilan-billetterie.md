J'aimerais explorer les obligation légales de billetteries pour la France.
Par exemple le système SIBIL : https://www.culture.gouv.fr/thematiques/theatre-spectacles/pour-les-professionnels/sibil-systeme-d-information-billetterie
10:15
Web recherché

Bonne exploration ! Le cadre légal français pour les billetteries de spectacle vivant est assez riche. Voici une vue d'ensemble structurée.
Obligations légales des billetteries en France — Vue d'ensemble
1. SIBIL — Déclaration statistique obligatoire

SIBIL a été mis en place le 1er juillet 2018 en application de l'article 48 de la loi « Liberté de création, architecture et patrimoine » du 7 juillet 2016. Cette loi dispose que les entrepreneurs de spectacles vivants détenant une licence mettent à la disposition du ministre chargé de la Culture les informations de billetterie : le prix global payé par le spectateur (ou la gratuité), le nom du spectacle, le domaine, la localisation et le type de lieu de chaque représentation.
culture

Concrètement, SIBIL impose :

    La transmission des données par voie dématérialisée, leur collecte pouvant être automatisée depuis n'importe quel système d'information de billetterie.
    culture
    Les données relatives aux représentations du trimestre écoulé sont transmises avant le dixième jour du premier mois de chaque trimestre civil.
    culture
    L'absence de transmission est sanctionnée par une amende administrative.
    culture

Le déploiement s'est fait en trois vagues, allant des opérateurs d'État (2018) jusqu'à la généralisation à toutes les structures de spectacle vivant (environ 15 000) depuis le 1er avril 2020.
2. Taxes fiscales sur les spectacles

Il existe deux taxes fiscales distinctes selon le genre du spectacle :

La taxe sur les spectacles de variétés est perçue au profit du Centre National de la Musique (CNM), et la taxe sur les spectacles dramatique, lyrique et chorégraphique est collectée au profit de l'ASTP (Association de Soutien au Théâtre Privé). C'est la nature et le genre du spectacle qui déterminent l'organisme auprès duquel la taxe doit être payée, et non le lieu dans lequel il est présenté. Ainsi, un festival qui programme des spectacles de genres différents doit déclarer la taxe par spectacle, au CNM pour les spectacles de variétés et à l'ASTP pour les spectacles dramatiques.
ARTCENA

Taux : Le taux de perception est fixé à 3,5 %, applicable sur la recette de billetterie hors taxes pour les spectacles payants, ou sur le prix du contrat de cession hors taxes pour les représentations gratuites.
CNM

Qui est redevable ? La taxe est due par tout organisateur de spectacles détenteur de la billetterie, ou par le vendeur pour les spectacles présentés gratuitement, qu'il soit professionnel ou non, structure privée, associative ou publique. Sont également concernés les « organisateurs occasionnels » — comités des fêtes, offices de tourisme, entreprises d'événementiel, foires et expositions, etc.
CNM

Seuil d'exonération de fait : La taxe n'est pas acquittée lorsque le montant cumulé sur une année civile pour un même redevable est inférieur à 80 €. En pratique, les organisateurs doivent quand même déclarer, et le CNM procède en fin d'année civile au reversement si ce seuil n'est pas atteint.
CNM
3. TVA sur la billetterie

La TVA s'applique sur le prix du billet. Le taux généralement retenu est de 5,5 % du prix du billet (pour la billetterie) ou du montant de la cession. Il existe également un taux « super-réduit » à 2,1 %, applicable uniquement aux recettes de billetteries réalisées sur les 140 premières représentations d'un même spectacle — ce taux n'est pas applicable dans les cas où un bar propose des consommations pendant la représentation.
Music-hdf

La billetterie de concert est une activité à but lucratif, qui doit rester accessoire pour les associations de loi 1901 : elle est dans ce cas exonérée de TVA dans la limite de six manifestations par an. Au-delà, même si l'association n'a pas de but lucratif, elle devra appliquer la TVA et sera soumise à l'impôt sur les sociétés.
Music-hdf
4. Droits d'auteur (SACEM / SACD)

La déclaration et le paiement des sommes dues à la SACEM ou à la SACD sont une obligation distincte de la taxe fiscale. Le paiement des droits d'auteur et le paiement de la taxe sur les spectacles sont deux obligations différentes — une association exonérée de taxe sur les spectacles peut donc être redevable de droits d'auteurs à la SACEM, et inversement.
Assistant-juridique
Synthèse pour TiBillet

Du point de vue d'une plateforme comme TiBillet, les obligations à couvrir (ou à documenter pour les organisateurs) sont donc :
Obligation	Organisme	Fréquence / délai
Déclaration SIBIL	Ministère de la Culture	Trimestrielle (J+10 du trimestre suivant)
Taxe spectacles variétés	CNM	Au plus tard le dernier jour du 3e mois après la représentation
Taxe spectacles dramatiques	ASTP	Même calendrier
TVA	DGFiP	Selon régime TVA de l'organisateur
Droits d'auteur	SACEM / SACD	Par représentation

La question la plus intéressante pour TiBillet est probablement l'automatisation de l'export SIBIL — le décret prévoit explicitement que la collecte peut être automatisée depuis les systèmes de billetterie. Est-ce que tu veux creuser l'API ou le format de données attendu par SIBIL ? Ou tu veux qu'on cartographie d'autres obligations (licence d'entrepreneur de spectacle, sécurité, accessibilité ERP, etc.) ?

Le but est de fabriquer un bilan de billetterie pour TiBillet avec toute ces informations.
Continue d'explorer l'API et le format de donnée attendu.
Va aussi voir du coté de la documentation des autres billetteries de type Billetweb, weezevent, ticketmaster ce qu'ils proposent, leur méthode, voire même leur UX
10:19
Web recherché

Excellent, j'ai maintenant une image complète. Voici la synthèse structurée — technique et stratégique — pour concevoir le bilan de billetterie TiBillet.
Analyse complète : API, formats et UX des billetteries
1. L'API SIBIL — Ce que TiBillet doit implémenter

Le tutoriel officiel révèle le protocole complet. Voici ce qu'on a appris :

Authentification L'authentification des systèmes de billetterie aux API SIBIL se fait via la réception d'un jeton JWT accessible depuis le service POST /api/authenticate. Le déclarant doit créer un compte secondaire de type « SIB » (Système d'Information de Billetterie) avec un identifiant et un mot de passe qui servent à générer ce token.
culture

Les 3 familles de services de l'API SIBIL L'API SIBIL offre aux systèmes de billetterie trois familles de services : (1) la lecture du référentiel — rechercher un lieu ou un festival ; (2) la proposition de nouvelles entrées dans les référentiels — proposer un nouveau spectacle, lieu ou festival ; (3) l'envoi de représentations — créer, modifier, supprimer ou consulter une déclaration.
culture

Le format de déclaration — 4 sections obligatoires

Une déclaration est constituée de 4 sections : Description (festival ou spectacle, domaine, jeune public), Lieu (recherche par SIRET ou saisie manuelle, type de lieu), Date (représentation unique ou série), et Billetterie (fréquentation payante/exonérée et recette TTC).
culture

Les données de billetterie attendues précisément :

    Nombre de billets au tarif normal
    Nombre de billets en abonnements/forfaits/adhésions
    Nombre de billets exonérés ou gratuits
    Recette TTC totale
    Recette plein tarif
    Recette abonnements
    Le prix moyen est calculé automatiquement

Le mode CSV (alternative à l'API) La première colonne du fichier CSV, « Type Donnée », indique le type de ligne : déclaration, spectacle, festival ou lieu. Les données de billetterie d'une déclaration comprennent : nom du festival ou du spectacle, lieu, date unique ou dates de série, et l'ensemble des chiffres de fréquentation et de recette.
culture

Les domaines de représentation reconnus par SIBIL (liste complète extraite du tutoriel) : Théâtre, Conte, Marionnettes, Mime, Cirque de création, Cirque de tradition, Arts de la Rue, Humour/Sketch, Comédie musicale, Cabaret/Music-Hall, Opéra, Musique classique, Musiques contemporaines, Chanson/Variétés, Jazz/Blues, Pop/Rock/Reggae, Musiques urbaines, Musique électronique, Musique traditionnelle, Musiques du Monde, Danse de Création, Danse traditionnelle, Danses Urbaines, Danse Jazz, Danse Classique, Danses du Monde, Pluridisciplinaire/Autre.

Les types de lieux reconnus : THEATRE, ESPACE_POLYVALENT, CASINO_DISCOTHEQUE_HOTEL_CAFE_RESTAURANT, SALLE_CONCERT_AUDITORIUM_OPERA_ZENITH, CABARET_MUSIC_HALL, PLEIN_AIR_PARC_LOISIRS_ATTRACTION, STRUCTURE_ITINERANTE_DEMONTABLE_CHAPITEAU, LIEU_DE_CULTE, LIEU_DE_SANTE, AUTRE.

Rythme de déclaration Les données relatives aux représentations du trimestre écoulé doivent être transmises avant le dixième jour du premier mois du trimestre suivant. Une tolérance est accordée jusqu'au 10 du mois suivant. Sans déclaration, le déclarant reçoit deux relances par email avant qu'un rapport de non-déclaration soit envoyé au ministère.
culture

Le document de référence API pour les éditeurs est intitulé SIBIL-SFD-002-Spécifications Editeur_v2.4 — il faut le demander directement à sibil.dgca@culture.gouv.fr.
2. Ce que font les concurrents — Benchmark API/UX

Weezevent expose une API REST JSON complète (partenaires uniquement). Les endpoints clés sont :

    GET /events — liste des événements avec statut de vente
    GET /dates — dates par événement (multi-dates)
    GET /tickets — catégories de tarifs avec price, participants, quota
    GET /tickets/:id/stats — statistiques de scan (total, scanned, in, out)
    GET /participant/list — liste paginée des participants avec filtres last_update, create_date_from, incluant les données cashless (upselling)
    GET /event/:id/details — détail complet avec venue, organizer, sale_period

La réponse participant Weezevent inclut nativement le cashless via upselling — très proche de l'architecture Fedow/TiBillet.

Billetweb propose une API similaire (clé API + user en query param ou header Basic Auth). Elle permet l'export incrémental des attendees (participants), limité à 10 appels/minute. Une fois le festival terminé, l'organisateur dispose d'un historique complet : bilans financiers, taux de remplissage, ventilation des inscriptions par tarif — des données précieuses pour négocier avec des partenaires, ajuster la programmation de l'année suivante ou prouver la viabilité économique d'un événement.
Trajectio
3. Architecture proposée pour le bilan TiBillet

En croisant tout ça, voici les données que TiBillet doit agréger pour produire un bilan complet :

┌─────────────────────────────────────────────────────────┐
│               BILAN DE BILLETTERIE TIBILLET              │
├─────────────────────┬───────────────────────────────────┤
│  SECTION SIBIL      │  SECTION FISCALE                  │
│  (déclaration légale│  (CNM / ASTP)                     │
│  trimestrielle)     │                                   │
│                     │  Recette HT billetterie            │
│  Nom spectacle      │  Taxe CNM = recette HT × 3,5%    │
│  Domaine SIBIL      │  TVA = recette HT × 5,5%         │
│  Lieu (SIRET)       │  (ou 2,1% si < 140 repres.)      │
│  Type de lieu       │                                   │
│  Festival (O/N)     │  SECTION SACEM / SACD             │
│  Jeune public (O/N) │  (droits d'auteur à déclarer      │
│  Date(s)            │   séparément)                     │
│  Nb billets payants │                                   │
│  Nb billets abo/    │  SECTION ORGANISATEUR             │
│    forfaits         │                                   │
│  Nb billets gratuits│  Taux de remplissage              │
│  Recette TTC totale │  Prix moyen                       │
│  Recette plein tarif│  Ventilation par tarif            │
│  Recette abo        │  Canal de vente (ligne/guichet)   │
│                     │  Données cashless (Fedow)         │
└─────────────────────┴───────────────────────────────────┘

Ce qui est spécifique à TiBillet / différenciant :

    La dimension cashless (Fedow) qui manque à SIBIL mais qui est précieuse pour l'organisateur
    La fédération multi-lieux : un même spectacle tournant dans plusieurs salles TiBillet peut agréger ses données
    Le calcul automatique de la taxe CNM à partir de la recette HT
    L'export SIBIL automatisé par trimestre sans action manuelle

La prochaine étape serait de récupérer le document SIBIL-SFD-002-Spécifications Editeur_v2.4 pour connaître le format JSON/CSV exact attendu par l'API. Tu veux qu'on modélise les modèles Django pour stocker toutes ces données, ou qu'on commence par la maquette UX du bilan ?

récupere le document SIBIL-SFD-002-Spécifications Editeur_v2.4 pour connaître le format JSON/CSV exact attendu par l'API.
10:24
Web recherché

Il y a un PDF de documentation et un fichier CSV/JSON de données réelles publiés sur data.gouv.fr. Récupérons-les.
Exécuté 2 commandes

Le réseau est désactivé dans le container. Je dois passer par l'outil web_fetch.
Web recherché

Le document SIBIL-SFD-002 est à accès restreint (transmis uniquement aux éditeurs qui en font la demande à sibil.dgca@culture.gouv.fr). En revanche, j'ai maintenant toutes les pièces du puzzle : le tutoriel PDF, la FAQ officielle, la description des champs open data, et le retour de terrain de Festik. Je peux reconstituer le schéma complet avec une grande fiabilité. Voici la documentation de référence que j'ai produite :
Vérifier les skills disponibles avant de créer le document

Maintenant je vais produire la documentation de référence complète en Markdown (plus utile qu'un docx pour TiBillet vu votre workflow CLI/git), en reconstituant le schéma SIBIL depuis toutes les sources croisées.
Fichier créé, lu un fichier

Voilà le résultat de la recherche. Points importants à retenir :

Le document SIBIL-SFD-002 n'est pas public. Il est transmis uniquement aux éditeurs sur demande directe à sibil.dgca@culture.gouv.fr. Bonne nouvelle : le développement de l'interface connectée à l'API ne correspond qu'à 2 ou 3 jours de développement selon CapGemini
MGB Mag
, ce qui est très raisonnable.

Ce que j'ai pu reconstituer depuis le tutoriel officiel, la FAQ, les données open data et les retours de terrain (Festik notamment) :

L'architecture API est claire :

    Auth JWT via POST /api/authenticate avec un compte secondaire de type SIB
    3 familles d'endpoints : lecture référentiels, proposition de nouveaux référentiels, CRUD déclarations
    Import CSV alternatif avec colonnes ordonnées et colonne Type_Donnee en première position

Le schéma de données de la déclaration est complet — les 4 sections (Description, Lieu, Date, Billetterie) avec toutes les règles de validation croisée.

Un point critique de mapping TiBillet → SIBIL : les tarifs réduits n'ont pas de champ dédié et ne doivent être inclus que dans le champ « Total billetterie ». Les Pass doivent être déclarés dans le champ « Abonnements, forfaits et adhésions ».
Ministère de la Culture
Ça veut dire que les adhésions TiBillet (côté Fedow) tombent naturellement dans la catégorie abonnements SIBIL — une belle correspondance.
