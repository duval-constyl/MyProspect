# MyProspect — outil de prospection personnel

## But du projet
- Outil local de prospection B2B pour Duval (développeur fullstack, seul utilisateur).
- Il trace une zone sur une carte de France (commune, cercle, dessin libre) et choisit des métiers.
- L'outil récolte les entreprises (registre officiel + OpenStreetMap), analyse leur site et calcule un score d'opportunité expliqué par offre.
- Il classe « qui contacter en premier » (opportunité × facilité de contact × adéquation) et propose le canal.
- Il suit les contacts (favori, statut, notes) et exporte en CSV. Il prépare, Duval agit : aucun envoi automatique.

Documents de référence : `docs/superpowers/specs/outil-prospection-design.md` (conception),
`docs/superpowers/plans/2026-11-25-v1-prospect-core.md` (V1), plans V2 et V3 dans le même dossier.
Journal d'avancement : `docs/PROGRESS.md`.

## Global Constraints (reprises des plans)
- France uniquement, entreprises (B2B) uniquement.
- L'outil n'envoie jamais d'e-mail, d'appel ni de SMS.
- Entreprises non diffusibles exclues ; liste « ne plus contacter » respectée à chaque récolte.
- Chaque coordonnée (téléphone, e-mail, site) garde sa **source** et sa **date**.
- Chaque score garde la liste de ses **raisons** ; aucun score sans explication.
- Usage local, un seul utilisateur, sans connexion : tout tourne avec `docker compose up`.
- Ne pas copier l'interface ni la marque de « Blean Prospect ».
- Limite du registre : 7 appels/seconde maximum ; on se limite à 5.

## Règles non négociables
- Aucun secret dans le dépôt : tout passe par `.env` (`.env.example` sans valeurs réelles).
- Tests : aucune requête réseau réelle dans la suite automatique (HTTP simulé avec respx / mocks). La base PostgreSQL locale (Docker) est autorisée.
- Code et identifiants en anglais ; interface, messages d'erreur et libellés des raisons de score en français.

## Pile technique
- Backend : Python 3.12, FastAPI, SQLAlchemy 2 + GeoAlchemy2, Alembic, psycopg 3, pydantic-settings, httpx, selectolax, shapely ; tests pytest + pytest-asyncio + respx.
- Base : PostgreSQL 16 + PostGIS 3.4 (image `postgis/postgis:16-3.4`).
- Frontend : React + TypeScript + Vite, MapLibre GL (fond OpenFreeMap), TanStack Query ; tests vitest + Testing Library.
- Docker Compose : services `db`, `api`, `web`.

## Commandes
Préparer l'environnement backend (une fois) :
```bash
cp .env.example .env
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
```
Base de données seule (port hôte 5433 par défaut, variable `DB_PORT`) :
```bash
docker compose up -d db
```
Tests backend (la base de test `prospect_test` est créée automatiquement) :
```bash
cd backend && .venv/Scripts/python -m pytest -v
```
Migrations :
```bash
cd backend && .venv/Scripts/python -m alembic upgrade head
```
Frontend (une fois : `cd frontend && npm install`) :
```bash
cd frontend && npx vitest run      # tests
cd frontend && npx tsc --noEmit     # types
cd frontend && npm run dev          # http://localhost:5173 (proxy /api -> localhost:8000)
```
Tout lancer :
```bash
docker compose up
```
API : http://localhost:8000 (santé : `/health`). Interface : http://localhost:5173 (le navigateur appelle `/api/...`, Vite relaie vers l'API).

## Règle de travail
- Tâches de la V1 exécutées **dans l'ordre**, une à la fois. Chaque tâche : écrire les tests, les lancer et constater l'échec, implémenter, relancer et constater le succès, commit.
- On ne passe à la tâche suivante que si **toute la suite de tests passe**. Les cases du plan sont cochées au fur et à mesure.
- Un commit par tâche, avec le message indiqué dans le plan.
- Après chaque tâche : compte rendu de 3 lignes maximum (ce qui marche, ce qui a changé par rapport au plan, la suite), mise à jour de `docs/PROGRESS.md`.
- Signatures, noms et valeurs des plans respectés strictement ; tout écart est noté dans `docs/PROGRESS.md` avec sa raison.
- Quand un plan dit « à vérifier » : consulter la documentation actuelle (Context7 ou web) et noter le constat.
- Si le plan et la réalité se contredisent, ou si une décision change ce qui sera construit : s'arrêter et poser **une seule question à la fois**, avec une recommandation.
- Aucune fonctionnalité hors plan ; les idées vont dans `docs/PROGRESS.md`, rubrique « Questions ouvertes ».
- Fin de chaque version (V1, V2, V3) : s'arrêter, donner une liste de vérification manuelle, attendre le retour avant la version suivante. Les plans V2/V3 ne sont lus qu'au démarrage de la version.
- Tâches d'étude (offres d'emploi en V2, maquette « après » en V3) : s'arrêter après l'étude et présenter le constat.
