# POSTIZ — Hub du chantier

> **Objet :** explorer un couplage **TiBillet ↔ Postiz** (planificateur de publications sur
> 28+ réseaux sociaux, auto-hébergeable, AGPL-3.0), dans la lignée exacte du chantier
> [NEWSLETTER](../NEWSLETTER/INDEX.md) qui pousse des brouillons vers **Ghost**.

**Statut :** **exploration seule.** Pas de spec, pas de plan, pas de code, pas de branche.
**Date :** 2026-07-13

---

## Documents

| Document | Contenu | Statut |
|---|---|---|
| [EXPLORATION.md](EXPLORATION.md) | Le point technique : quel LLM, OpenRouter, auto-hébergement, MCP, licence. Vérifié dans le code source. | Fait |

---

## En une phrase

Postiz sait publier sur 28+ réseaux (Mastodon, Bluesky, Facebook, Instagram, LinkedIn, X…).
**Son IA interne est facultative et contournable** : il expose une **API REST publique**, un
**serveur MCP** et un **CLI**. On peut donc s'en servir comme d'un **pur moteur de publication**
piloté par Lespass — même schéma que Ghost pour la newsletter : Django pousse du déterministe,
aucun LLM dans la boucle serveur.

---

## Les quatre réponses aux questions posées

1. **Leur LLM, c'est OpenAI câblé en dur.** `gpt-4.1` est écrit dans le code, à cinq endroits,
   par-dessus **quatre** bibliothèques IA distinctes (SDK `openai`, LangChain, CopilotKit, Mastra).
   Aucun `baseURL` n'est passé nulle part.

2. **OpenRouter n'est pas supporté officiellement** (issue #1074 ouverte, sans réponse des
   mainteneurs). Mais le SDK `openai-node` lit `OPENAI_BASE_URL` **tout seul** depuis l'env :
   un proxy **LiteLLM** devant Postiz permet de router vers ce qu'on veut **sans forker**.
   → Détails et réserves : [EXPLORATION §2](EXPLORATION.md#2-brancher-openrouter).

3. **On n'est pas obligé d'utiliser un LLM du tout.** C'est la voie qui nous intéresse.
   → [EXPLORATION §3](EXPLORATION.md#3-se-passer-completement-du-llm).

4. **L'auto-hébergement est total** (AGPL pure, aucune fonctionnalité réservée au cloud), **mais
   le coût d'infra a explosé** : le compose officiel monte **8 conteneurs**, dont un **second
   Postgres** et un **Elasticsearch**, à cause du passage à **Temporal**.
   → [EXPLORATION §4](EXPLORATION.md#4-lauto-hebergement).

---

## Ce qui reste à vérifier avant toute décision

Deux points **non validés en réel**. Ils ne bloquent que la voie « on utilise l'IA de Postiz » —
la voie « Postiz sans LLM » n'en dépend pas.

- [ ] `OPENAI_BASE_URL` traverse-t-il bien les **quatre** couches IA ? (LangChain est le doute :
      il construit `new OpenAIClient(params)` avec ses propres options.)
- [ ] Les **structured outputs** (`zodResponseFormat` + `chat.completions.parse()`) survivent-ils
      au modèle qu'on choisirait derrière LiteLLM ?

## Les pistes ouvertes (rien n'est tranché)

- **Le cas d'usage évident :** pousser l'**agenda des événements** (le même ensemble fédéré que la
  newsletter Ghost) vers Mastodon / Bluesky / Facebook. La collecte est **déjà écrite** dans
  `newsletter/collecte.py` — c'est le rendu et la destination qui changeraient.
- **SSO :** Postiz gère un **OAuth générique OIDC** (`POSTIZ_GENERIC_OAUTH`, documenté pour
  Authentik). Brancher l'authentification sur **AuthBillet** est plausible.
- **Réutiliser le pattern `GhostConfig`** : singleton par tenant, URL + clé chiffrée Fernet,
  bouton dans l'admin Unfold. Tout est déjà là.
