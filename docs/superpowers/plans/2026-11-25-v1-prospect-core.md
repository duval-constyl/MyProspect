# Outil de prospection V1 : plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une application locale où Duval trace une zone en France, récolte les entreprises, obtient un score Web expliqué et un classement « qui contacter en premier », et suit ses contacts.

**Architecture:** Collecte à la demande. Un backend FastAPI récolte le registre officiel (API Recherche d'entreprises) puis enrichit avec OpenStreetMap, analyse les sites, calcule les scores et enregistre tout dans PostgreSQL/PostGIS. Un frontend React affiche la carte (MapLibre), la liste et les fiches. Les récoltes tournent en tâche de fond avec une table `jobs` pour la progression (pas de Redis).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 + GeoAlchemy2, Alembic, httpx, selectolax, pytest + respx ; PostgreSQL 16 + PostGIS ; React + TypeScript + Vite, MapLibre GL, TanStack Query, vitest + Testing Library ; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-25-outil-prospection-design.md`

## Global Constraints

- France uniquement, entreprises (B2B) uniquement.
- L'outil n'envoie jamais d'e-mail, d'appel ni de SMS.
- Entreprises non diffusibles exclues ; liste « ne plus contacter » respectée à chaque récolte.
- Chaque coordonnée (téléphone, e-mail, site) garde sa **source** et sa **date**.
- Chaque score garde la liste de ses **raisons** ; aucun score sans explication.
- Usage local, un seul utilisateur, sans connexion : tout tourne avec `docker compose up`.
- Ne pas copier l'interface ni la marque de « Blean Prospect ».
- Limite du registre : 7 appels/seconde maximum ; on se limite à 5.

## Review Focus

- Fiche sans téléphone, sans e-mail ou sans site : l'écran et l'export fonctionnent, sans valeur vide trompeuse (Task 10, 14).
- Site mal formé, redirigé, très lent ou qui ne renvoie pas du HTML : résultat « inaccessible », jamais d'exception (Task 6).
- Zone démesurée (dessin libre de plus de 50 km de large) : refus avec un message clair avant tout appel (Task 5).
- Erreur 429 ou coupure en pleine récolte : reprise, résultats déjà obtenus conservés (Task 3, 9).
- Récolter deux fois la même zone : aucun doublon, notes/favoris/statuts conservés, entreprises exclues absentes (Task 9).

---

## Structure des fichiers

```
docker-compose.yml  .env.example  README.md
backend/pyproject.toml  backend/alembic.ini  backend/alembic/versions/
backend/app/
  main.py  config.py  db.py  domain.py  models.py  schemas.py
  geo.py                      # zone -> cercles, point dans la zone
  sources/registry.py         # API Recherche d'entreprises
  sources/osm.py              # Overpass + rapprochement
  sources/pagespeed.py        # perf mobile (optionnel)
  analysis/site.py            # analyse d'un site
  scoring/web.py  scoring/priority.py
  collect.py                  # orchestrateur + jobs
  routers/{zones,prospects,tracking,exports}.py
backend/tests/
frontend/package.json  frontend/src/{api.ts,types.ts,App.tsx}
frontend/src/pages/{MapPage,ProspectsPage,ProspectPage}.tsx
frontend/src/components/{ZoneControls,ScoreCard,ContactList,TrackingForm}.tsx
```

## Types partagés (`backend/app/domain.py`, créés en Task 1)

```python
class Offer(StrEnum): WEB="web"; MOBILE="mobile"; CLOUD="cloud"
class Status(StrEnum): NEW="new"; TO_CONTACT="to_contact"; CONTACTED="contacted"; REPLIED="replied"; REFUSED="refused"
@dataclass(frozen=True) class Reason: code: str; label: str; points: int
@dataclass(frozen=True) class ScoreResult: offer: Offer; value: int; tier: int; reasons: list[Reason]
@dataclass(frozen=True) class Circle: lat: float; long: float; radius_km: float
@dataclass(frozen=True) class RegistryCompany: siret: str; name: str; naf: str; effectif_code: str | None; created_on: date | None; lat: float | None; long: float | None; address: str; is_individual: bool; closed: bool
@dataclass(frozen=True) class OsmBusiness: osm_id: str; name: str; lat: float; long: float; phone: str | None; email: str | None; website: str | None
@dataclass(frozen=True) class SiteAnalysis: url: str; reachable: bool; https: bool; has_title: bool; has_description: bool; has_h1: bool; has_viewport: bool; response_ms: int | None; tech: list[str]; mobile_perf: int | None; analyzed_at: datetime
```

---

### Task 1: Socle du projet (Docker, base, santé)

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `backend/pyproject.toml`, `backend/app/{main,config,db,domain}.py`, `backend/alembic.ini`, `backend/alembic/env.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.main.app` (FastAPI) ; `app.config.Settings` (`database_url: str`, `home_lat: float`, `home_long: float`, `pagespeed_api_key: str | None`) ; `app.db.get_session() -> Iterator[Session]` ; les types de `domain.py` ci-dessus.

- [x] **Step 1: Test.** `test_health_reports_db_ok` : `GET /health` renvoie 200 et `{"status": "ok", "postgis": true}`.
- [x] **Step 2: Lancer** `docker compose up -d db && cd backend && pytest tests/test_health.py -v`. Attendu : FAIL (route absente).
- [x] **Step 3: Implémenter.** Services Compose : `db` (image `postgis/postgis:16-3.4`), `api`, `web`. `/health` exécute `SELECT postgis_version()`.
- [x] **Step 4: Relancer.** Attendu : PASS.
- [x] **Step 5: Commit** `chore: socle docker, fastapi, postgis`.

### Task 2: Modèles de données et migration

**Files:**
- Create: `backend/app/models.py`, `backend/alembic/versions/0001_initial.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces (SQLAlchemy) : `Prospect(id, siret unique, name, naf, effectif_code, created_on, geom Point 4326, address, is_individual, closed, first_seen_at, last_collected_at)` ; `Contact(id, prospect_id, kind: "phone"|"email"|"website", value, source: "osm"|"registry"|"site", seen_on: date)` ; `SiteAnalysisRow(prospect_id unique, …champs de SiteAnalysis…)` ; `ScoreRow(prospect_id, offer, value, tier, reasons JSON, computed_at, unique(prospect_id, offer))` ; `Tracking(prospect_id unique, status, favorite, notes, updated_at)` ; `Exclusion(siret pk, reason, added_at)` ; `Zone(id, kind: "commune"|"circle"|"polygon", geojson, naf_codes, collected_at)` ; `Job(id, zone_id, state: "pending"|"running"|"done"|"failed", done, total, error)`.

- [x] **Step 1: Tests.** `test_prospect_roundtrip_with_geometry` : insérer un `Prospect` avec point (2.3522, 48.8566), le relire, vérifier `ST_X`. `test_siret_is_unique` : deux insertions du même SIRET lèvent `IntegrityError`. `test_score_unique_per_offer`.
- [x] **Step 2: Lancer** `pytest tests/test_models.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter** les modèles et la migration `alembic revision --autogenerate`, avec `CREATE EXTENSION postgis` et un index GiST sur `Prospect.geom`.
- [x] **Step 4: Lancer** `alembic upgrade head && pytest tests/test_models.py -v`. Attendu : PASS.
- [x] **Step 5: Commit** `feat: modèles et migration initiale`.

### Task 3: Client du registre officiel

**Files:**
- Create: `backend/app/sources/registry.py`
- Test: `backend/tests/test_registry.py`

**Interfaces:**
- Consumes: `Circle`, `RegistryCompany`.
- Produces: `async def fetch_near_point(circle: Circle, naf_codes: list[str], client: httpx.AsyncClient | None = None) -> AsyncIterator[RegistryCompany]` ; `class RateLimiter(per_second: int)` avec `async def wait() -> None`.

Appelle `GET https://recherche-entreprises.api.gouv.fr/near_point` avec `lat`, `long`, `radius` (km, 50 max), `activite_principale` (codes NAF séparés par des virgules), `page`, `per_page`. Vérifier au démarrage dans la spécification OpenAPI de l'API le `per_page` maximum et le nom exact des champs d'un établissement.

- [x] **Step 1: Tests (respx).** `test_paginates_until_empty` : 2 pages de résultats simulées, 3 entreprises renvoyées. `test_skips_closed_and_non_diffusible` : un établissement fermé et un non diffusible sont absents ; `closed` n'est jamais `True` dans la sortie. `test_retries_on_429` : une réponse 429 puis 200 → résultat obtenu, une pause appliquée. `test_keeps_items_already_yielded_when_api_fails` : 200 puis 500 répété → les éléments de la première page sont déjà produits et l'erreur `RegistryUnavailable` est levée ensuite. `test_radius_over_50km_rejected` : `ValueError`.
- [x] **Step 2: Lancer** `pytest tests/test_registry.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter** `fetch_near_point` avec `RateLimiter(5)` partagé, 3 nouvelles tentatives avec attente croissante sur 429/5xx.
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: client registre officiel`.

### Task 4: Client OpenStreetMap et rapprochement

**Files:**
- Create: `backend/app/sources/osm.py`
- Test: `backend/tests/test_osm.py`

**Interfaces:**
- Consumes: `Circle`, `OsmBusiness`, `RegistryCompany`.
- Produces: `async def fetch_osm_businesses(circle: Circle, client=None) -> list[OsmBusiness]` ; `def match_osm_to_registry(companies: list[RegistryCompany], osm: list[OsmBusiness], max_distance_m: int = 80) -> dict[str, OsmBusiness]` (clé : SIRET).

Requête Overpass sur les éléments `shop`, `amenity`, `craft`, `office` ayant un nom, dans le cercle. Le rapprochement exige une distance ≤ 80 m **et** des noms normalisés (minuscules, sans accents ni forme juridique) dont la similarité (`difflib.SequenceMatcher`) est ≥ 0,6.

- [x] **Step 1: Tests.** `test_parses_phone_email_website_tags` (tags `phone`, `contact:phone`, `website`, `contact:email`). `test_match_requires_distance_and_name` : bon nom à 500 m → pas d'appariement ; nom proche à 20 m → apparié. `test_no_match_returns_empty` . `test_overpass_timeout_returns_empty_list_not_exception`.
- [x] **Step 2: Lancer** `pytest tests/test_osm.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter.**
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: client osm et rapprochement`.

### Task 5: Géométrie des zones

**Files:**
- Create: `backend/app/geo.py`
- Test: `backend/tests/test_geo.py`

**Interfaces:**
- Consumes: `Circle`.
- Produces: `class ZoneTooLarge(ValueError)` ; `def zone_to_circles(kind: str, geojson: dict) -> list[Circle]` ; `def point_in_zone(kind: str, geojson: dict, lat: float, long: float) -> bool` ; `async def commune_zone(name_or_code: str) -> dict` (contour GeoJSON via `https://geo.api.gouv.fr/communes?nom=…&fields=contour&format=geojson`).

Un cercle reste un cercle (≤ 50 km). Un polygone est recouvert par des cercles de 2 km de rayon placés sur une grille, puis filtré par `point_in_zone`. Largeur maximale : 50 km, sinon `ZoneTooLarge`.

- [x] **Step 1: Tests.** `test_circle_zone_returns_itself`. `test_polygon_is_covered_by_circles` : un carré de 3 km de côté produit ≥ 1 cercle et chaque coin est à moins de 2 km d'un centre. `test_polygon_wider_than_50km_raises_zone_too_large`. `test_point_in_zone_for_polygon_and_circle`. `test_commune_zone_returns_polygon` (HTTP simulé).
- [x] **Step 2: Lancer** `pytest tests/test_geo.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter** avec `shapely`.
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: géométrie des zones`.

### Task 6: Analyse d'un site

**Files:**
- Create: `backend/app/analysis/site.py`, `backend/app/sources/pagespeed.py`
- Test: `backend/tests/test_site_analysis.py`

**Interfaces:**
- Consumes: `SiteAnalysis`.
- Produces: `async def analyze_site(url: str, client=None) -> SiteAnalysis` (ne lève jamais) ; `async def mobile_perf(url: str, api_key: str | None, client=None) -> int | None` (score PageSpeed mobile 0-100, `None` si pas de clé ou erreur).

`analyze_site` normalise l'URL (ajoute `https://` si absent), suit jusqu'à 5 redirections, délai maximal 10 s, ne lit que du HTML (autre type de contenu → `reachable=False`). `https` vaut `True` si l'URL finale est en HTTPS. `tech` détecte `wordpress`, `wix`, `shopify`, `jquery` par balise generator ou scripts.

- [x] **Step 1: Tests (respx).** `test_good_site_all_flags_true`. `test_missing_title_description_h1_viewport_flags`. `test_http_only_site_has_https_false`. `test_redirect_http_to_https_counts_as_https`. `test_malformed_url_returns_unreachable_not_exception` (`"http//bad url"`). `test_timeout_returns_unreachable`. `test_pdf_response_is_unreachable`. `test_mobile_perf_none_without_key`.
- [x] **Step 2: Lancer** `pytest tests/test_site_analysis.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter** avec `httpx` et `selectolax`.
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: analyse des sites`.

### Task 7: Score Web

**Files:**
- Create: `backend/app/scoring/web.py`
- Test: `backend/tests/test_scoring_web.py`

**Interfaces:**
- Consumes: `SiteAnalysis`, `ScoreResult`, `Reason`, `Offer`.
- Produces: `def score_web(has_known_site: bool, analysis: SiteAnalysis | None) -> ScoreResult` ; `def tier_of(value: int) -> int` avec `min(6, value // 17 + 1)`.

Points (cumulés, plafonnés à 100) : pas de site connu **75** (`no_site`) ; site inaccessible **70** (`site_unreachable`) ; pas de HTTPS **+20** (`no_https`) ; titre, description ou H1 manquant **+15** (`missing_seo_tags`) ; pas de balise viewport **+15** (`no_viewport`) ; performance mobile < 50 **+20**, entre 50 et 89 **+10** (`slow_mobile`). Chaque règle déclenchée ajoute une `Reason` avec un libellé en français.

- [ ] **Step 1: Tests.** `test_no_site_scores_75_with_one_reason`. `test_unreachable_site_scores_70`. `test_all_defects_caps_at_100`. `test_healthy_site_scores_0_with_no_reasons`. `test_slow_mobile_tiers` (perf 40 → 20, perf 70 → 10, perf 95 → 0). `test_tier_boundaries` (0→1, 16→1, 17→2, 100→6). `test_reasons_sum_matches_value_before_cap`.
- [ ] **Step 2: Lancer** `pytest tests/test_scoring_web.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: score web`.

### Task 8: Priorité de contact

**Files:**
- Create: `backend/app/scoring/priority.py`
- Test: `backend/tests/test_priority.py`

**Interfaces:**
- Consumes: `ScoreResult`, `Reason`.
- Produces: `def contact_priority(opportunity: int, has_phone: bool, has_email: bool, effectif_code: str | None, distance_km_from_home: float | None) -> tuple[int, list[Reason]]`.

Valeur = `round(0,5 × opportunité)` + points, plafonnée à 100 : téléphone **+12** (`phone`), e-mail **+8** (`email`), petite structure (`effectif_code` vide, `"NN"`, `"00"`, `"01"` ou `"02"`) **+8** (`small_structure`), distance ≤ 20 km **+6** (`nearby`).

- [ ] **Step 1: Tests.** `test_base_is_half_of_opportunity`. `test_each_bonus_adds_its_points` (un test par bonus). `test_cap_at_100`. `test_unknown_distance_gives_no_bonus`.
- [ ] **Step 2: Lancer** `pytest tests/test_priority.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: priorité de contact`.

### Task 9: Orchestrateur de récolte et jobs

**Files:**
- Create: `backend/app/collect.py`, `backend/app/routers/zones.py`
- Test: `backend/tests/test_collect.py`

**Interfaces:**
- Consumes: Tasks 3 à 8.
- Produces: `async def run_collection(job_id: int, session_factory, registry=fetch_near_point, osm=fetch_osm_businesses, analyze=analyze_site) -> None` ; routes `POST /zones/collect` (corps : `{kind, geojson, naf_codes}` → `{job_id}`), `GET /jobs/{id}` (→ `{state, done, total, error}`), `GET /zones` (liste des zones récoltées avec date).

Déroulé : zone → cercles → registre → exclure les SIRET de `Exclusion` → OSM → rapprochement → upsert des `Prospect` et `Contact` (une ligne par valeur, `source`, `seen_on`) → analyse des sites (5 en parallèle) → scores → `done/total` mis à jour après chaque entreprise. Un upsert ne touche jamais à `Tracking`.

- [ ] **Step 1: Tests (sources simulées).** `test_collect_creates_prospects_contacts_scores`. `test_recollect_same_zone_creates_no_duplicates`. `test_recollect_keeps_notes_favorite_status` (le `Tracking` d'un prospect est identique avant et après). `test_excluded_siret_is_never_created`. `test_registry_failure_midway_keeps_prior_results_and_marks_job_failed_with_message`. `test_progress_counts_done_and_total`. `test_company_without_coordinates_is_stored_but_not_mapped` (le prospect existe, `geom` vide, aucune erreur). `test_zone_too_large_returns_422_before_any_call`.
- [ ] **Step 2: Lancer** `pytest tests/test_collect.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter** avec `BackgroundTasks` de FastAPI. Un job `running` au redémarrage de l'API passe à `failed` avec le message « interrompu ».
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: récolte et jobs`.

### Task 10: API des prospects (liste, carte, fiche)

**Files:**
- Create: `backend/app/routers/prospects.py`, `backend/app/schemas.py`
- Test: `backend/tests/test_prospects_api.py`

**Interfaces:**
- Produces : `GET /prospects?bbox=w,s,e,n&naf=&has_site=&offer=web&score_min=&status=&q=&favorite=&sort=priority|score|name&page=&per_page=` → `{items: ProspectListItem[], total}` ; `GET /prospects/clusters?bbox=…&zoom=…` → `{clusters: [{lat, long, count, max_score}]}` (regroupement `ST_SnapToGrid`) ; `GET /prospects/{id}` → `ProspectDetail` ; `GET /prospects/stats?bbox=…` → `{in_view, with_site, without_site}`.
- `ProspectDetail` : identité, `contacts[{kind, value, source, seen_on}]`, `site_analysis | null`, `scores[{offer, value, tier, reasons}]`, `priority{value, reasons}`, `tracking`. Aucun champ obligatoire ne peut être `null` de façon trompeuse : un contact absent est simplement absent de la liste.

- [ ] **Step 1: Tests.** `test_list_filters_by_has_site_and_score_min`. `test_list_sorted_by_priority_desc`. `test_search_by_name_and_siret`. `test_clusters_group_nearby_points_at_low_zoom`. `test_stats_counts_with_and_without_site`. `test_detail_for_prospect_without_contacts_or_site` (listes vides, `site_analysis` nul, 200). `test_detail_unknown_id_404`.
- [ ] **Step 2: Lancer** `pytest tests/test_prospects_api.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.** La priorité est calculée à la lecture avec `contact_priority` et `Settings.home_lat/home_long`.
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: api prospects`.

### Task 11: Suivi, exclusion, export CSV

**Files:**
- Create: `backend/app/routers/tracking.py`, `backend/app/routers/exports.py`
- Test: `backend/tests/test_tracking_export.py`

**Interfaces:**
- Produces : `PATCH /prospects/{id}/tracking` (`{status?, favorite?, notes?}`) ; `DELETE /prospects/{id}` (suppression définitive des données du prospect et ajout du SIRET à `Exclusion`, motif `"deleted"`) ; `POST /prospects/{id}/do-not-contact` (statut `refused` + `Exclusion` motif `"do_not_contact"`, données conservées) ; `GET /exports/prospects.csv?…mêmes filtres que la liste`.
- Colonnes CSV : `siret, nom, naf, ville_adresse, telephone, email, site, score_web, priorite, statut, favori, notes`. Cellules vides pour les valeurs absentes.

- [ ] **Step 1: Tests.** `test_patch_tracking_updates_only_given_fields`. `test_invalid_status_422`. `test_delete_removes_prospect_contacts_scores_and_adds_exclusion`. `test_do_not_contact_keeps_data_and_excludes_from_next_collect`. `test_csv_has_header_and_one_row_per_prospect`. `test_csv_empty_cells_for_missing_phone_email_site`. `test_csv_escapes_commas_quotes_and_newlines_in_notes`.
- [ ] **Step 2: Lancer** `pytest tests/test_tracking_export.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter** avec le module `csv` standard.
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: suivi, exclusion, export`.

### Task 12: Frontend, socle et page Carte

**Files:**
- Create: `frontend/` (Vite React TS), `src/api.ts`, `src/types.ts`, `src/App.tsx`, `src/pages/MapPage.tsx`, `src/components/ZoneControls.tsx`
- Test: `frontend/src/pages/MapPage.test.tsx`

**Interfaces:**
- Consumes: routes des Tasks 9 et 10.
- Produces : `api.collectZone(body) → {job_id}` ; `api.getJob(id)` ; `api.getClusters(bbox, zoom)` ; `api.getStats(bbox)` ; composant `ZoneControls({onCollect})` (onglets Commune / Cercle / Dessin libre, liste de métiers cochables : garage 45.20A, coiffure 96.02A, restauration 56.10A, plomberie 43.22A, agence immobilière 68.31Z).

Fond de carte MapLibre : style vectoriel gratuit OpenFreeMap (`https://tiles.openfreemap.org/styles/liberty`). Couleur d'un point selon `tier` (6 niveaux), regroupements avec leur nombre. Compteurs « dans la vue / avec site / sans site » rafraîchis au déplacement de la carte.

- [ ] **Step 1: Tests.** `test_shows_counters_from_stats`. `test_start_collection_posts_selected_naf_codes` (cocher deux métiers → corps de la requête avec leurs deux codes). `test_progress_bar_follows_job_until_done`. `test_error_message_shown_when_zone_too_large` (réponse 422).
- [ ] **Step 2: Lancer** `cd frontend && npx vitest run src/pages/MapPage.test.tsx`. Attendu : FAIL.
- [ ] **Step 3: Implémenter** (carte simulée dans les tests).
- [ ] **Step 4: Relancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: page carte`.

### Task 13: Page Liste des prospects

**Files:**
- Create: `frontend/src/pages/ProspectsPage.tsx`
- Test: `frontend/src/pages/ProspectsPage.test.tsx`

**Interfaces:**
- Consumes: `GET /prospects` et `GET /exports/prospects.csv`.
- Produces : tableau triable (nom, métier, ville, score Web, priorité, statut) avec filtres métier, site connu, score minimum, statut, favoris et recherche texte ; bouton « Exporter en CSV » qui reprend les filtres actifs.

- [ ] **Step 1: Tests.** `test_changing_filter_refetches_with_params`. `test_sort_by_priority_toggles_direction`. `test_export_link_contains_active_filters`. `test_row_without_phone_shows_dash_not_empty_or_null`.
- [ ] **Step 2: Lancer** `npx vitest run src/pages/ProspectsPage.test.tsx`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4: Relancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: page liste`.

### Task 14: Fiche prospect

**Files:**
- Create: `frontend/src/pages/ProspectPage.tsx`, `src/components/{ScoreCard,ContactList,TrackingForm}.tsx`
- Test: `frontend/src/pages/ProspectPage.test.tsx`

**Interfaces:**
- Consumes: `GET /prospects/{id}`, `PATCH /prospects/{id}/tracking`, `DELETE /prospects/{id}`, `POST /prospects/{id}/do-not-contact`.
- Produces : `ScoreCard({score})` (cercle de score, palier sur 6, liste des raisons) ; `ContactList({contacts})` (chaque ligne affiche la valeur, la source et la date, bouton copier) ; `TrackingForm({tracking, onChange})`.

- [ ] **Step 1: Tests.** `test_score_card_lists_every_reason`. `test_contact_shows_source_and_date`. `test_no_contacts_shows_message_instead_of_empty_block`. `test_status_change_sends_patch`. `test_delete_asks_confirmation_before_calling_api`. `test_do_not_contact_button_calls_api`.
- [ ] **Step 2: Lancer** `npx vitest run src/pages/ProspectPage.test.tsx`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4: Relancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: fiche prospect`.

### Task 15: Bout en bout et documentation

**Files:**
- Create: `README.md`, `backend/tests/test_e2e_smoke.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Test.** `test_smoke_collect_list_detail_export` : avec registre, OSM et sites simulés, récolter une zone de 3 entreprises, lister, ouvrir une fiche, exporter le CSV et vérifier 3 lignes de données.
- [ ] **Step 2: Lancer** `pytest backend/tests -v`. Attendu : tout PASS.
- [ ] **Step 3: README** : `cp .env.example .env`, `docker compose up`, adresse de l'interface, variables (`HOME_LAT`, `HOME_LONG`, `PAGESPEED_API_KEY` facultative), rappel du cadre légal (B2B, source indiquée, désinscription, suppression sur demande).
- [ ] **Step 4: Vérifier à la main** : récolter une commune réelle, vérifier que la carte, la liste, une fiche et l'export CSV fonctionnent.
- [ ] **Step 5: Commit** `docs: readme et test bout en bout`.

---

## Auto-relecture

- **Couverture du document de conception (V1)** : carte, zone (commune, cercle, dessin libre) et filtres : Tasks 5, 10, 12, 13 ; registre + OSM : 3, 4 ; analyse des sites et score Web : 6, 7 ; priorité de contact : 8 ; fiche et suivi (favori, statut, notes) : 11, 14 ; export CSV : 11, 13 ; non diffusibles, liste d'exclusion, suppression : 3, 9, 11 ; source et date des coordonnées : 2, 9, 14 ; usage local : 1, 15.
- **Cohérence des noms** : `score_web`, `contact_priority`, `analyze_site`, `fetch_near_point`, `run_collection` sont utilisés avec les mêmes signatures partout.
- **Proportion** : chaque tâche donne des signatures, des noms de tests et des valeurs, sans corps de fonction.
