# Journal d'avancement

## Fait

- Mise en place : `CLAUDE.md`, ce journal, `.gitignore`, commit initial des documents de conception et des plans.
- **V1 – Tâche 1 (socle)** : Docker Compose (`db` PostGIS 16-3.4, `api`, `web`), `.env.example`, FastAPI avec `GET /health` (exécute `SELECT postgis_version()`), `Settings`, `get_session()`, types partagés de `domain.py`, Alembic prêt. Test `test_health_reports_db_ok` vert ; conteneur `api` vérifié à la main (`/health` → `{"status":"ok","postgis":true}`).

## Décisions et écarts par rapport au plan

- **Nom du document de conception** : le plan V1 cite `docs/superpowers/specs/2026-11-25-outil-prospection-design.md`, le fichier présent s'appelle `docs/superpowers/specs/outil-prospection-design.md` (même contenu, daté du 25/11/2026). Fichier laissé tel quel ; c'est lui qui fait foi.
- **Commit initial hors tâche** : les documents (conception, plans, `CLAUDE.md`, ce journal) sont commités à part avant la tâche 1, pour que chaque tâche ait un point de départ propre.
- **Branche** : dépôt neuf, travail directement sur `main` (outil personnel, un seul développeur).
- **T1 – Port de la base : 5433** (variable `DB_PORT`). Le port 5432 est déjà occupé sur la machine (conteneur `emanager_db` et un PostgreSQL local). Ports de l'API et de l'interface réglables aussi (`API_PORT`, `WEB_PORT`).
- **T1 – Base de test séparée** : `tests/conftest.py` force `DATABASE_URL` vers `TEST_DATABASE_URL` (défaut `prospect_test` sur le port 5433) et crée cette base avec PostGIS si besoin. La suite ne touche jamais la base de travail.
- **T1 – Fichiers ajoutés hors liste du plan** : `backend/Dockerfile` et `backend/.dockerignore` (nécessaires au service `api`), `backend/alembic/script.py.mako` et `backend/alembic/versions/.gitkeep` (nécessaires à `alembic revision` en tâche 2), `backend/tests/conftest.py`, `backend/app/__init__.py`, `.gitattributes` (fins de ligne LF, pour que les fichiers lus dans les conteneurs ne reçoivent pas de CRLF sous Windows).
- **T1 – Fonctions en plus des interfaces du plan** : `get_settings()` (configuration mise en cache) et `get_engine()` / `get_session_factory()` dans `db.py`, pour ne rien connecter au moment de l'import. `Settings` et `get_session()` gardent exactement la forme du plan.
- **T1 – `HOME_LAT` / `HOME_LONG` obligatoires, sans valeur par défaut** : une position inventée fausserait le bonus de proximité. Compose refuse de démarrer `api` s'ils manquent, avec un message en français. `PAGESPEED_API_KEY` vide est traité comme absent.
- **T1 – Service `web`** : déclaré dès maintenant (image `node:22-alpine`, dossier `frontend/` monté). Il ne fonctionnera qu'après la tâche 12, qui crée le frontend.
- **T1 – Versions installées** (dernières disponibles) : FastAPI 0.165, Starlette 1.10, SQLAlchemy 2.1.9, GeoAlchemy2 0.21, Alembic 1.20, psycopg 3.3, pydantic-settings 2.16, httpx 0.28, selectolax 1.0, shapely 2.2, pytest 9.2, pytest-asyncio 1.5, respx 0.23.
- **T2 – Détails du schéma laissés au constructeur** : `Prospect.geom` peut être vide (une entreprise sans position est gardée mais pas affichée, test prévu en tâche 9) ; valeurs énumérées protégées par des contraintes `CHECK` ; contrainte d'unicité `(prospect_id, kind, value)` sur `contacts` pour que la tâche 9 n'écrive jamais deux fois la même coordonnée ; suppression en cascade des contacts, analyses, scores et suivi quand un prospect est supprimé (tâche 11) ; `tech` et `naf_codes` en tableaux, `reasons` et `geojson` en JSONB ; clé `id` ajoutée à `SiteAnalysisRow` et `Tracking` (le plan ne donne que `prospect_id` unique).
- **T2 – Alembic** : en plus des aides de GeoAlchemy2, un filtre empêche l'autogénération de toucher aux tables qui ne sont pas à nous. L'image PostGIS installe le géocodeur « tiger » dans la base de travail, et sans ce filtre la migration proposait de supprimer ses tables. `path_separator = os` ajouté dans `alembic.ini` (avertissement d'Alembic 1.20).
- **T2 – Tests sur le vrai schéma** : la suite applique les migrations sur `prospect_test` (fixture `migrated_database`) et vide toutes les tables après chaque test (fixture `db_session`).

## Questions ouvertes

- **`httpx2` pour le client de test** : Starlette 1.10 affiche un avertissement (« utiliser `httpx2` plutôt que `httpx` avec `starlette.testclient` »). L'installation de `httpx2` a été bloquée par le contrôle de sécurité de l'outil ; je ne l'ai pas forcée. Les tests passent avec `httpx`, l'avertissement est sans effet. À décider : ajouter `httpx2` aux dépendances de test après avoir vérifié le paquet, ou masquer l'avertissement.
- **Ta position dans `.env`** : ton `.env` local (non commité) contient pour l'instant le centre de Paris (48.8566, 2.3522) comme valeur provisoire. Remplace-la par ta vraie position pour que le bonus « proche » soit juste.
