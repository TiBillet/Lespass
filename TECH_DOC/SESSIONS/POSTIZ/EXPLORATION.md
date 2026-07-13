# EXPLORATION — TiBillet × Postiz

> **Hub :** [INDEX.md](INDEX.md)
> **Date :** 2026-07-13 · **Statut :** exploration, aucun code, aucune branche.
>
> Tout ce qui suit a été **vérifié dans le code source** de `gitroomhq/postiz-app` (repo public,
> lu via `gh api`), pas seulement dans la documentation. Les chemins de fichiers cités sont ceux
> du repo Postiz. Ce qui n'a **pas** été vérifié est signalé explicitement.

---

## 0. Ce qu'est Postiz

Un planificateur de publications sur les réseaux sociaux : on connecte ses comptes, on écrit, on
programme, il publie. **28+ canaux** : X, LinkedIn (+ pages), Reddit, Instagram, Facebook,
Threads, YouTube, TikTok, Pinterest, Dribbble, Discord, Slack, Twitch, Kick, **Mastodon**,
**Bluesky**, Lemmy, Farcaster, Telegram, Nostr, VK, Medium, Dev.to, Hashnode, WordPress, ListMonk,
Google My Business…

**Stack :** NextJS (front) + NestJS (back) + Prisma/PostgreSQL + Redis + **Temporal**, en monorepo
pnpm. Licence **AGPL-3.0**.

---

## 1. Le LLM : OpenAI, en dur

Il n'y a **pas** de couche d'abstraction LLM dans Postiz. C'est OpenAI, câblé, avec le nom du
modèle écrit dans le code.

### 1.1 Le modèle est hardcodé

`gpt-4.1` apparaît en dur dans :

| Fichier | Usage |
|---|---|
| `libraries/nestjs-libraries/src/openai/openai.service.ts` | génération de posts, prompts d'image, découpage en threads, slides |
| `libraries/nestjs-libraries/src/agent/agent.graph.service.ts` | l'agent (LangGraph) |
| `libraries/nestjs-libraries/src/agent/agent.graph.insert.service.ts` | idem |
| `libraries/nestjs-libraries/src/database/prisma/autopost/autopost.service.ts` | l'autopost |
| `apps/backend/src/api/routes/copilot.controller.ts` | le chat de l'interface |

Les images passent par `chatgpt-image-latest` (l'ex-DALL·E) via `openai.images.generate()`.
La **voix** est chez **ElevenLabs** (`ELEVENSLABS_API_KEY`), la **vidéo** chez **fal.ai**
(`FAL_KEY`), **KieAI** et **Transloadit** — chacun sa clé, chacun son fournisseur.

### 1.2 Quatre bibliothèques IA empilées

C'est ce qui rend le sujet moins simple qu'il n'y paraît. Il n'y a pas *un* point à modifier :

| Couche | Paquet | Où |
|---|---|---|
| SDK OpenAI brut | `openai` | `openai.service.ts` |
| LangChain | `@langchain/openai` (`ChatOpenAI`, `DallEAPIWrapper`) | `agent.graph.*`, `autopost.service.ts` |
| CopilotKit | `@copilotkit/runtime` (`OpenAIAdapter`) | `copilot.controller.ts` |
| Mastra + Vercel AI SDK | `@mastra/core`, `@ai-sdk/openai` | `chat/mastra.service.ts`, `chat/load.tools.service.ts` |

### 1.3 Le point commun : aucun `baseURL`

Partout, l'instanciation est la même — et elle ne passe **jamais** d'URL de base :

```ts
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || 'sk-proj-',
});
```

---

## 2. Brancher OpenRouter

### 2.1 Officiellement : non

- **Issue [#1074](https://github.com/gitroomhq/postiz-app/issues/1074)** — « Support ENV Variables
  for Custom OpenAI Base URL & Model », demandant `OPENAI_BASE_URL` + `OPENAI_MODEL` pour Ollama /
  LM Studio / **OpenRouter** / vLLM. **Ouverte. Aucune réponse de mainteneur. Aucune PR.**
- **Issue [#1648](https://github.com/gitroomhq/postiz-app/issues/1648)** — support natif de
  Gemini / Vertex. Même silence.

Ce n'est pas une priorité du projet. **Ne pas compter dessus.**

### 2.2 En pratique : la porte dérobée `OPENAI_BASE_URL`

**Le SDK `openai-node` lit `OPENAI_BASE_URL` tout seul depuis l'environnement.** C'est la valeur
par défaut de son constructeur (vérifié dans `openai/openai-node`, `src/client.ts` et
`src/azure.ts`) :

```ts
baseURL = readEnv('OPENAI_BASE_URL') ?? 'https://api.openai.com/v1'
```

Comme Postiz ne passe jamais `baseURL` explicitement, **ce défaut s'applique**. Poser
`OPENAI_BASE_URL` dans l'environnement du conteneur devrait donc rerouter le trafic **sans patcher
une ligne de Postiz**. Le SDK Vercel (`@ai-sdk/openai`) a la même prise en charge (mentionnée dans
son changelog), et CopilotKit s'appuie sur le même client OpenAI.

> **RÉSERVE — non vérifié en réel.** **LangChain** est le doute : il construit
> `new OpenAIClient(params)` en lui passant ses propres options
> (`libs/providers/langchain-openai/src/chat_models/base.ts`). Si `params.baseURL` vaut
> `undefined`, le défaut du SDK s'applique et tout va bien ; s'il force une valeur, la couche
> agent/autopost continuera de taper OpenAI. **À tester avant de s'engager.**

### 2.3 L'obstacle restant : le nom du modèle

`gpt-4.1` est en dur (§1.1). **OpenRouter attend des identifiants préfixés** (`openai/gpt-4.1`,
`anthropic/claude-…`) : il recevra `gpt-4.1` tout nu et le rejettera. **Pointer `OPENAI_BASE_URL`
directement sur OpenRouter ne suffit donc pas.**

### 2.4 La solution propre : un proxy LiteLLM

On déclare chez LiteLLM un modèle **nommé** `gpt-4.1` — le nom que Postiz réclame en dur — qui
route en réalité vers ce qu'on veut. **Postiz reste vanilla.**

```yaml
# litellm — config.yaml
model_list:
  - model_name: gpt-4.1                       # le nom que Postiz exige
    litellm_params:
      model: openrouter/mistralai/mistral-large   # ce qu'on veut vraiment
      api_key: os.environ/OPENROUTER_API_KEY
```

```yaml
# postiz — docker-compose
OPENAI_BASE_URL: 'http://litellm:4000/v1'
OPENAI_API_KEY: '<clé litellm>'
```

**Pourquoi c'est la bonne voie :** zéro fork → zéro dette de maintenance à chaque montée de
version de Postiz, **et zéro complication AGPL** (voir §4.1).

**Deux frictions à anticiper :**

1. **Structured outputs.** Postiz utilise `zodResponseFormat` + `chat.completions.parse()`
   (`response_format: json_schema` en mode strict). Tous les modèles ne le servent pas
   correctement. **À valider modèle par modèle.**
2. **Génération d'images.** Postiz appelle `/images/generations`, un endpoint qu'**OpenRouter
   n'expose pas** (il ne fait que du chat). LiteLLM sait router cet endpoint vers d'autres
   backends — mais il faut le configurer, ou renoncer à la génération d'images.

---

## 3. Se passer complètement du LLM

**C'est possible, et c'est probablement ce qui nous intéresse.**

### 3.1 L'IA est facultative, par conception

- Le compose officiel livre **`OPENAI_API_KEY: ''`** par défaut.
- `copilot.controller.ts` : si la clé est absente, il **log un warning et rend la main**.
- `videos/images-slides/images.slides.ts` : la fonctionnalité est gardée derrière un
  `!!process.env.OPENAI_API_KEY &&`.
- Le cœur — calendrier, connexion des comptes, file d'attente, **publication** — ne touche jamais
  à l'IA.

### 3.2 Le pilotage externe est un usage de première classe

Ce n'est pas un détournement : Postiz est *conçu* pour être piloté de l'extérieur.

- **Serveur MCP intégré** — `libraries/nestjs-libraries/src/chat/start.mcp.ts`, via le `MCPServer`
  de Mastra. Authentification par **clé d'API** (`getOrgByApiKey`) **ou OAuth2** (jetons préfixés
  `pos_`, RFC 9728). Des *tools* sont déjà écrits : `integration.list`, `group.list`,
  `generate.image`, `video.function`…
- **API REST publique** documentée (`docs.postiz.com/public-api`), annoncée pour n8n / Make /
  Zapier.
- **CLI npm `postiz`** — le repo [`gitroomhq/postiz-agent`](https://github.com/gitroomhq/postiz-agent)
  se présente littéralement comme *« connect it to Claude / OpenClaw / etc. »*, et est distribué
  comme **skill**.
- Le frontend affiche l'**origine** de chaque post :
  `creationMethod: 'WEB' | 'API' | 'MCP' | 'AUTOPOST' | 'CLI'`. Ils *tracent* le fait qu'un agent
  externe publie.

> **Piège documenté par leur propre skill :** tout fichier média doit **d'abord** passer par
> `postiz upload` ; les chemins locaux et les URL externes sont **refusés** par le pipeline de
> publication (TikTok, Instagram, YouTube rejettent ce qui n'est pas une URL vérifiée par Postiz).
> **C'est l'inverse du choix fait pour Ghost**, où l'on référence les images par URL publique
> TiBillet sans rien uploader. À intégrer dès la conception.

### 3.3 Conséquence pour nous

**Postiz redevient un pur moteur de publication multi-canal**, et l'intelligence reste chez nous.
C'est exactement la ligne tenue sur Ghost dans le chantier [NEWSLETTER](../NEWSLETTER/INDEX.md) :
Django pousse du déterministe, aucun LLM dans la boucle serveur. En prime, la porte MCP est déjà
ouverte si l'on veut un jour qu'un agent s'en serve.

---

## 4. L'auto-hébergement

### 4.1 La licence : AGPL-3.0 pure

Vérifié dans le fichier `LICENSE` : **AGPL-3.0, sans Commons Clause, sans édition entreprise,
sans restriction commerciale.** La doc affirme qu'il n'y a **aucune différence de fonctionnalités
entre le cloud et l'auto-hébergé**.

**Ce qu'il faut en retenir pour Lespass :** appeler l'**API HTTP** de Postiz ne fait pas de Lespass
une œuvre dérivée → **aucune contamination AGPL**. En revanche, **héberger un Postiz _modifié_ et
l'exposer à des utilisateurs déclenche l'article 13** (obligation de publier les sources
modifiées). **Argument décisif en faveur du proxy LiteLLM (§2.4) plutôt que d'un patch.**

### 4.2 Le compose officiel : 8 conteneurs

Le passage à **Temporal** pour l'orchestration a alourdi la note. Le
[`docker-compose.yaml` officiel](https://github.com/gitroomhq/postiz-docker-compose) monte :

| Service | Image | Note |
|---|---|---|
| `postiz` | `ghcr.io/gitroomhq/postiz-app:latest` | **un seul** conteneur : front + back + workers. Port `4007:5000` |
| `postiz-postgres` | `postgres:17-alpine` | |
| `postiz-redis` | `redis:7.2` | |
| `temporal` | `temporalio/auto-setup:1.28.1` | l'orchestrateur |
| `temporal-postgresql` | `postgres:16` | **un second Postgres**, rien que pour Temporal |
| `temporal-elasticsearch` | `elasticsearch:7.17.27` | **un Elasticsearch** |
| `temporal-ui` | `temporalio/ui:2.34.0` | port `8080` |
| `temporal-admin-tools` | | |

**La doc annonce « testé sur 2 Go de RAM / 2 vCPU ». Avec Elasticsearch dans la boucle, c'est très
optimiste — tabler sur 4 Go.**

### 4.3 Configuration : tout en variables d'environnement

Trois voies possibles : dans le `docker-compose.yml`, dans un `postiz.env` monté sur `/config`,
ou dans un `.env` (déconseillé).

**Les variables qui nous concernent :**

| Variable | Intérêt |
|---|---|
| `MAIN_URL`, `FRONTEND_URL`, `NEXT_PUBLIC_BACKEND_URL`, `BACKEND_INTERNAL_URL` | les 4 URLs à câbler correctement derrière Traefik — source classique d'erreurs |
| `DATABASE_URL`, `REDIS_URL`, `TEMPORAL_ADDRESS`, `JWT_SECRET` | le socle |
| `DISABLE_REGISTRATION` | fermer les inscriptions |
| `STORAGE_PROVIDER` | `local` **ou** `cloudflare` (R2). Les variables s'appellent `CLOUDFLARE_*` mais **R2 est du S3** → un **MinIO** devrait passer via `CLOUDFLARE_BUCKET_URL`. **Non vérifié.** |
| `POSTIZ_GENERIC_OAUTH` + `POSTIZ_OAUTH_*` | **OAuth générique OIDC** (documenté pour Authentik) → **piste SSO avec AuthBillet** |
| `OPENAI_API_KEY` | **vide par défaut** (§3.1) |
| `API_LIMIT` | 30 par défaut |
| `RUN_CRON`, `IS_GENERAL` | mode d'exécution |

### 4.4 Le vrai coût d'entrée n'est pas Postiz

**C'est qu'il faut créer une app développeur chez chaque réseau** et fournir un `CLIENT_ID` /
`CLIENT_SECRET` : `X_API_KEY`, `LINKEDIN_CLIENT_ID`, `FACEBOOK_APP_ID`, `TIKTOK_CLIENT_ID`,
`YOUTUBE_CLIENT_ID`, `REDDIT_CLIENT_ID`…

- **Faciles :** Mastodon, Bluesky, Discord, Telegram, Slack.
- **Pénibles :** Meta (Facebook/Instagram/Threads) et TikTok — parcours de validation longs, avec
  revue humaine et exigences de conformité.

**C'est ce point, et non la technique, qui déterminera le périmètre réaliste d'un chantier Postiz.**

---

## 5. Ce qui n'a PAS été vérifié

À traiter avant toute décision d'architecture. **Aucun ne bloque la voie « Postiz sans LLM »
(§3), qui est la plus probable.**

1. **`OPENAI_BASE_URL` traverse-t-il les 4 couches ?** LangChain est le doute (§2.2).
2. **Les structured outputs survivent-ils au modèle choisi** derrière LiteLLM ? (§2.4)
3. **MinIO passe-t-il par les variables `CLOUDFLARE_*` ?** (§4.3)
4. **Le contenu exact des tools MCP** exposés (le `posts:create` n'a pas été lu ligne à ligne).
5. **La consommation mémoire réelle** du compose complet.

---

## 6. Références

**Postiz**
- Dépôt : <https://github.com/gitroomhq/postiz-app> (AGPL-3.0)
- Compose officiel : <https://github.com/gitroomhq/postiz-docker-compose>
- CLI / skill agent : <https://github.com/gitroomhq/postiz-agent>
- Doc : <https://docs.postiz.com/> · configuration : <https://docs.postiz.com/configuration/reference>
- API publique : <https://docs.postiz.com/public-api/introduction>
- Issue #1074 (base URL custom) : <https://github.com/gitroomhq/postiz-app/issues/1074>
- Issue #1648 (Gemini natif) : <https://github.com/gitroomhq/postiz-app/issues/1648>

**Preuves lues dans le code**
- `libraries/nestjs-libraries/src/openai/openai.service.ts` — `new OpenAI({apiKey})`, `gpt-4.1`, `chatgpt-image-latest`
- `libraries/nestjs-libraries/src/agent/agent.graph.service.ts` — `ChatOpenAI`, `DallEAPIWrapper`
- `apps/backend/src/api/routes/copilot.controller.ts` — `OpenAIAdapter`, sortie anticipée sans clé
- `libraries/nestjs-libraries/src/chat/start.mcp.ts` — le serveur MCP, l'auth par clé d'API / OAuth2
- `openai/openai-node`, `src/client.ts` — `baseURL = readEnv('OPENAI_BASE_URL')`

**Interne**
- [NEWSLETTER](../NEWSLETTER/INDEX.md) — le chantier jumeau (Ghost). Le pattern à reprendre :
  `GhostConfig` (singleton par tenant, clé chiffrée Fernet), boutons dans l'admin Unfold,
  collecte fédérée dans `newsletter/collecte.py`.
