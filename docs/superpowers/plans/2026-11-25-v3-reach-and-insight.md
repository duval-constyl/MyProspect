# Outil de prospection V3 : réputation, rapports, veille, statistiques

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exploiter l'outil à plein potentiel : signaux d'avis, rapport d'audit à joindre, veille automatique des zones, statistiques de réponse et envoi assisté.

**Architecture:** Des modules indépendants branchés sur les données V1/V2 : un client de lieux Google (avec plafond de dépenses), un rendu de rapport HTML → PDF, une tâche planifiée de veille, des agrégats de statistiques et un générateur de fichiers `.eml`.

**Tech Stack:** celui de la V2 + APScheduler, WeasyPrint, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-25-outil-prospection-design.md` (section 8, V3). **Prérequis :** V1 et V2 terminées.

## Global Constraints

Toutes celles de la V1 et de la V2, et en plus :
- Un rapport d'audit ne contient **jamais** les notes privées de Duval, ni d'informations sur d'autres prospects.
- Toute API payante (lieux Google) respecte un **plafond mensuel** réglable ; au plafond, l'appel est refusé sans erreur bloquante.
- Aucun envoi réel : l'envoi assisté produit un fichier brouillon ou un lien, rien de plus.
- Toute fonctionnalité V3 est désactivable par réglage ; l'outil reste complet sans elle.

## Review Focus

- Rapport PDF d'un prospect sans site, sans coordonnées ou avec un nom très long : généré, lisible, sans notes privées (Task 3).
- Plafond mensuel des lieux Google atteint en pleine récolte : arrêt propre, scores calculés sans ce signal (Task 2).
- Veille lancée deux fois de suite sans changement dans le registre : aucune nouvelle alerte (Task 5).
- Site impossible à charger pour la capture d'écran : le rapport est généré avec un texte à la place de l'image (Task 4).
- Fichier `.eml` avec accents, retours à la ligne et sujet long : lisible dans un client mail ; sans adresse du destinataire : erreur 422 claire (Task 7).

---

### Task 1: Doublons et entreprises disparues

**Files:**
- Create: `backend/app/reconcile.py`
- Test: `backend/tests/test_reconcile.py`

**Interfaces:**
- Produces: `def find_duplicates(session, max_distance_m: int = 30) -> list[tuple[int, int]]` (paires d'identifiants de prospects de même nom normalisé et proches) ; `async def mark_closed(session, zone_id: int, lookup=registry_lookup_by_siret) -> int` (nombre de prospects de la zone absents de la dernière récolte et déclarés fermés par le registre, marqués `closed=True`).

- [x] **Step 1: Tests.** `test_duplicates_same_name_within_30m`. `test_same_name_far_apart_not_duplicate`. `test_absent_and_closed_company_is_marked_closed`. `test_absent_but_still_active_is_kept`. `test_closed_prospects_hidden_from_default_list_but_kept_in_database`.
- [x] **Step 2: Lancer** `pytest tests/test_reconcile.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter.** Le filtre par défaut de `GET /prospects` exclut `closed=True` (paramètre `include_closed`).
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: doublons et fermetures`.

### Task 2: Signaux d'avis (lieux Google) avec plafond

> **Sautée le 25/11/2026, décision de Duval** : les conditions Google Maps Platform pour l'EEE (15.1, aucun usage avec une carte ; 15.4, seules latitude et longitude peuvent être mises en cache) contredisent le stockage de la note et son usage dans un score affiché sur la carte. Voir `docs/PROGRESS.md`.

**Files:**
- Create: `backend/app/sources/places.py`, migration `0005_places.py`
- Modify: `backend/app/scoring/web.py`, `backend/app/config.py` (`places_api_key`, `places_monthly_cap_eur: float = 5.0`)
- Test: `backend/tests/test_places.py`

**Interfaces:**
- Produces: `@dataclass PlaceSignals(rating: float | None, review_count: int | None, fetched_on: date)` ; `async def fetch_place_signals(name: str, address: str, session, client=None) -> PlaceSignals | None` ; table `ApiUsage(month: "YYYY-MM", api: str, cost_eur: float)`.
- Modifie : `score_web(has_known_site, analysis, place: PlaceSignals | None = None)` ajoute **+10** `low_rating` (note < 4,0) et **+10** `few_reviews` (moins de 10 avis). L'appel sans `place` donne les mêmes résultats qu'en V1.

Avant de se lancer, relire la grille tarifaire en vigueur de l'API Places et la saisir dans `places.py` comme constante `COST_PER_CALL_EUR`.

- [ ] **Step 1: Tests.** `test_no_key_returns_none`. `test_low_rating_and_few_reviews_add_20_points`. `test_score_web_without_place_unchanged_from_v1`. `test_call_refused_when_monthly_cap_reached_and_returns_none`. `test_usage_recorded_per_call`. `test_cap_reached_midway_collection_still_finishes_scoring`.
- [ ] **Step 2: Lancer** `pytest tests/test_places.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.** Ne rechercher que pour les prospects dont le score Web ≥ 40, pour limiter les coûts.
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: signaux d'avis avec plafond`.

### Task 3: Rapport d'audit PDF

**Files:**
- Create: `backend/app/report.py`, `backend/app/templates/audit.html`, route dans `backend/app/routers/exports.py`
- Test: `backend/tests/test_report.py`

**Interfaces:**
- Produces: `def render_audit_html(detail: ProspectDetail, offer: Offer) -> str` ; `def render_audit_pdf(detail: ProspectDetail, offer: Offer) -> bytes` ; `GET /prospects/{id}/audit.pdf?offer=web`.
- Contenu : nom de l'entreprise, score et palier, raisons en langage clair, chiffres clés du site (HTTPS, mobile, temps de réponse), signature de l'expéditeur. **Exclus** : notes, statut, priorité interne, autres prospects.

- [ ] **Step 1: Tests.** `test_html_contains_score_and_every_reason`. `test_html_never_contains_private_notes_or_status`. `test_prospect_without_site_renders`. `test_long_company_name_renders`. `test_pdf_starts_with_pdf_header_and_is_not_empty`. `test_unknown_prospect_404`.
- [ ] **Step 2: Lancer** `pytest tests/test_report.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter** avec Jinja2 et WeasyPrint.
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: rapport d'audit pdf`.

### Task 4: Captures d'écran dans le rapport

**Files:**
- Create: `backend/app/analysis/screenshot.py`
- Modify: `backend/app/report.py`, `backend/app/templates/audit.html`
- Test: `backend/tests/test_screenshot.py`

**Interfaces:**
- Produces: `@dataclass Screenshots(desktop_png: bytes | None, mobile_png: bytes | None)` ; `async def capture_site(url: str, timeout_s: int = 15) -> Screenshots` (ne lève jamais ; `None` en cas d'échec) ; `render_audit_html(detail, offer, screenshots: Screenshots | None = None)`.
- Tailles : bureau 1280×800, mobile 390×844.

- [ ] **Step 1: Tests (navigateur simulé).** `test_returns_both_images_on_success`. `test_returns_none_images_on_timeout`. `test_malformed_url_returns_none_images`. `test_report_shows_placeholder_text_when_screenshot_missing`. `test_report_embeds_images_as_data_uri_when_present`.
- [ ] **Step 2: Lancer** `pytest tests/test_screenshot.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter** avec Playwright (Chromium) ; l'image Docker `api` installe le navigateur.
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: captures d'écran du site`.

### Task 5: Zones suivies et alertes

**Files:**
- Create: `backend/app/watch.py`, `backend/app/routers/alerts.py`, migration `0006_watch.py`, `frontend/src/pages/AlertsPage.tsx`
- Modify: `backend/app/models.py` (`Zone.watch: bool`, `Zone.watch_every_days: int = 7`, `Alert(id, zone_id, prospect_id, kind: "new_company"|"closed", created_at, seen_at)`, contrainte unique `(zone_id, prospect_id, kind)`), `backend/app/main.py`
- Test: `backend/tests/test_watch.py`

**Interfaces:**
- Produces: `async def run_watch(session_factory, now: datetime) -> int` (récolte les zones dont l'échéance est passée, crée les alertes, renvoie leur nombre) ; planificateur APScheduler lancé au démarrage de l'API, vérification toutes les heures ; `PATCH /zones/{id}` (`{watch, watch_every_days}`) ; `GET /alerts?unseen=true` ; `POST /alerts/{id}/seen`.

- [ ] **Step 1: Tests.** `test_new_company_in_watched_zone_creates_one_alert`. `test_run_twice_without_change_creates_no_new_alert`. `test_zone_not_due_is_skipped`. `test_closed_company_creates_closed_alert`. `test_excluded_company_never_alerts`. `test_failed_collection_creates_no_alert_and_does_not_crash_scheduler`.
- [ ] **Step 2: Lancer** `pytest tests/test_watch.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.** Le premier passage d'une zone nouvellement suivie fixe l'état de départ sans alerte.
- [ ] **Step 4: Lancer** les tests et `npx vitest run`. Attendu : PASS.
- [ ] **Step 5: Commit** `feat: zones suivies et alertes`.

### Task 6: Statistiques de réponse

**Files:**
- Create: `backend/app/routers/stats.py`, `frontend/src/pages/StatsPage.tsx`
- Test: `backend/tests/test_stats.py`

**Interfaces:**
- Consumes: `OutreachDraft.variant`, `Tracking.status`, `Zone`.
- Produces: `GET /stats/outreach?group_by=offer|variant|zone` → `[{key, contacted, replied, refused, reply_rate}]` où `reply_rate = replied / contacted` (0 si `contacted` vaut 0).

Un prospect compte comme « contacté » dès qu'il a le statut `contacted`, `replied` ou `refused`.

- [ ] **Step 1: Tests.** `test_reply_rate_by_offer`. `test_group_by_variant`. `test_zero_contacted_gives_rate_0_not_division_error`. `test_prospect_without_draft_counted_under_variant_none`. Front : `test_stats_page_renders_rows_and_percentages`.
- [ ] **Step 2: Lancer** `pytest tests/test_stats.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: statistiques de réponse`.

### Task 7: Envoi assisté (brouillon `.eml`)

**Files:**
- Create: `backend/app/eml.py`, route dans `backend/app/routers/outreach.py`, bouton dans `frontend/src/pages/ProspectPage.tsx`
- Test: `backend/tests/test_eml.py`

**Interfaces:**
- Consumes: `OutreachDraft`.
- Produces: `def build_eml(draft: OutreachDraft, to: str, sender_name: str, sender_email: str, audit_pdf: bytes | None = None) -> bytes` ; `GET /outreach/{id}/draft.eml?to=…` ; l'en-tête `X-Unsent: 1` fait ouvrir le fichier comme brouillon dans les clients mail qui le gèrent. Aucun envoi : le module n'ouvre aucune connexion SMTP.

- [ ] **Step 1: Tests.** `test_eml_has_headers_and_unsent_flag`. `test_accents_and_long_subject_are_encoded_correctly` (sujet de 120 caractères avec « é » relu par le module `email` standard). `test_body_line_breaks_preserved`. `test_pdf_attached_when_given`. `test_missing_to_returns_422`. `test_call_draft_returns_409` (un script d'appel n'a pas de fichier e-mail). `test_module_does_not_import_smtplib`.
- [ ] **Step 2: Lancer** `pytest tests/test_eml.py -v`. Attendu : FAIL.
- [ ] **Step 3: Implémenter** avec `email.message.EmailMessage`.
- [ ] **Step 4: Lancer.** Attendu : PASS.
- [ ] **Step 5: Commit** `feat: brouillon eml`.

### Task 8: Maquette « après » (étude, avec point d'arrêt)

**Files:**
- Create (si retenue): `backend/app/concept.py`
- Test: `backend/tests/test_concept.py`

- [ ] **Step 1: Étude (deux heures maximum).** Essayer de produire, pour trois prospects réels, une page d'accueil conceptuelle générée à partir du nom, du métier et de la ville, puis photographiée avec Playwright. **Décider avec Duval** si le résultat est assez crédible pour être joint à un message. **Si non : abandonner cette tâche**, sans autre impact.
- [ ] **Step 2: Tests (si retenue).** `test_concept_page_is_marked_as_illustration` (mention « maquette d'illustration » visible). `test_concept_uses_only_known_facts` (nom, métier, ville ; aucune information inventée comme des horaires ou des tarifs). `test_failure_returns_none`.
- [ ] **Step 3: Implémenter** `async def render_concept(prospect_id: int, session, llm=None) -> bytes | None` et l'ajouter au rapport (Task 4).
- [ ] **Step 4: Lancer** `pytest tests/test_concept.py -v`. Attendu : PASS.
- [ ] **Step 5: Commit** `feat: maquette d'illustration`.

---

## Auto-relecture

- **Couverture (V3)** : avis : Task 2 ; mini-rapport d'audit : 3 et 4 ; maquette avant/après : 4 (capture du site actuel) et 8 (étude) ; statistiques : 6 ; doublons, fermetures et alertes de nouvelles entreprises : 1 et 5 ; envoi assisté sans envoi réel : 7.
- **Cohérence** : `render_audit_html` gagne un paramètre facultatif en Task 4 ; `score_web` en gagne un en Task 2 ; les anciens appels restent valides.
- **Écart assumé** : la fiche Google « non revendiquée », citée comme idée dans le document de conception, n'est pas exposée par l'API de lieux ; elle est remplacée par la note et le nombre d'avis.
