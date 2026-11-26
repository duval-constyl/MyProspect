# Outil de prospection V2 : scores Mobile et Cloud, messages, relances

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chaque prospect reçoit trois scores (Web, Mobile, Cloud/logiciel) ; l'outil rédige un brouillon d'approche (e-mail et script d'appel) et gère les relances.

**Architecture:** On étend l'analyse de site (signaux de réservation, versions des technologies), on ajoute deux fonctions de score sur le modèle de `score_web`, et un module de brouillons qui appelle un modèle de langage avec repli sur des modèles de texte fixes. Les relances ajoutent deux tables et une page « Aujourd'hui ».

**Tech Stack:** celui de la V1 + SDK Python `anthropic`.

**Spec:** `docs/superpowers/specs/2026-11-25-outil-prospection-design.md` (sections 7 et 8, V2). **Prérequis :** V1 terminée (`2026-11-25-v1-prospect-core.md`).

## Global Constraints

Toutes celles de la V1, et en plus :
- Le brouillon n'est **jamais envoyé** par l'outil ; Duval le relit.
- Un brouillon d'e-mail contient toujours : la source (« votre entreprise figure au registre officiel des entreprises »), l'identité de l'expéditeur, et une phrase de désinscription.
- Un brouillon ne cite que des faits présents dans les raisons du score.
- Aucun brouillon pour un prospect « ne plus contacter ».
- Fuseau horaire des relances : Europe/Paris.

## Review Focus

- Activité hors liste « réservation/commande » : score Mobile à 0 sans erreur (Task 2).
- Texte de page contenant « réservation » (mentions légales, article) sans vrai lien de réservation : pas de faux positif (Task 1).
- Clé du modèle de langage absente, appel en échec, ou réponse trop longue : brouillon de repli, jamais d'erreur 500 (Task 6).
- Prospect « ne plus contacter » : aucun brouillon, réponse 409 (Task 6).
- Relance à une date passée ou à minuit autour du changement d'heure : apparaît bien dans « Aujourd'hui » une seule fois (Task 7).

---

### Task 1: Signaux de réservation et versions techniques

**Files:**
- Modify: `backend/app/domain.py` (`SiteAnalysis` : ajouter `has_booking: bool`, `has_online_order: bool`), `backend/app/analysis/site.py`, `backend/app/models.py` + migration `0002_site_signals.py`
- Test: `backend/tests/test_site_signals.py`

**Interfaces:**
- Produces: `def detect_booking_signals(html: str) -> tuple[bool, bool]` (réservation, commande) ; `tech` contient désormais des entrées `nom@version` (`"wordpress@5.8"`, `"jquery@1.12.4"`) quand la version est lisible, sinon `nom`.

Détection : domaines de prestataires connus dans les liens ou iframes (planity, calendly, zenchef, thefork, lafourchette, doctolib, resalib, uber eats, deliveroo, foodles) ; ou liens dont le **texte** ou l'**URL** contient « réserver », « prendre rendez-vous », « commander ». Le texte courant des paragraphes ne compte pas.

- [x] **Step 1: Tests.** `test_detects_planity_link_as_booking`. `test_detects_order_link_text`. `test_paragraph_mentioning_reservation_is_not_booking`. `test_reads_wordpress_version_from_generator_meta`. `test_reads_jquery_version_from_script_src`. `test_existing_v1_fields_unchanged`.
- [x] **Step 2: Lancer** `pytest tests/test_site_signals.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter** et migrer (colonnes par défaut `false` pour les analyses déjà enregistrées).
- [x] **Step 4: Lancer** `alembic upgrade head && pytest backend/tests -v`. Attendu : PASS.
- [x] **Step 5: Commit** `feat: signaux de réservation et versions techniques`.

### Task 2: Score Mobile

**Files:**
- Create: `backend/app/scoring/mobile.py`
- Test: `backend/tests/test_scoring_mobile.py`

**Interfaces:**
- Consumes: `SiteAnalysis`, `ScoreResult`, `Reason`, `Offer`, `tier_of`.
- Produces: `BOOKING_NAF: frozenset[str]` = `{"56.10A","56.10C","96.02A","96.02B","96.04Z","45.20A"}` ; `ORDER_NAF = {"56.10A","56.10C"}` ; `def score_mobile(naf: str, has_known_site: bool, analysis: SiteAnalysis | None) -> ScoreResult`.

Si `naf` n'est pas dans `BOOKING_NAF` : valeur 0, aucune raison. Sinon : pas de réservation en ligne détectée **+50** (`no_online_booking`) ; pour `ORDER_NAF`, pas de commande en ligne **+20** (`no_online_order`) ; pas de site **+20** (`no_site_for_mobile`) ; site sans viewport **+10** (`not_mobile_ready`). Plafond 100. Pas de site : réservation et commande sont considérées absentes.

- [x] **Step 1: Tests.** `test_naf_outside_list_scores_zero_no_reasons`. `test_hairdresser_without_site_scores_70` (50 + 20). `test_restaurant_without_booking_or_order_with_site_scores_70`. `test_restaurant_with_booking_and_order_scores_0`. `test_garage_site_without_viewport_adds_10`. `test_cap_100`.
- [x] **Step 2: Lancer** `pytest tests/test_scoring_mobile.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter.**
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: score mobile`.

### Task 3: Score Cloud et logiciel

**Files:**
- Create: `backend/app/scoring/cloud.py`
- Test: `backend/tests/test_scoring_cloud.py`

**Interfaces:**
- Produces: `def score_cloud(effectif_code: str | None, created_on: date | None, analysis: SiteAnalysis | None, today: date, hiring_tech: bool = False) -> ScoreResult`.

Points : technologie obsolète **+30** (`outdated_tech` : jQuery < 3, WordPress < 6) ; entreprise créée depuis moins de 24 mois **+25** (`recent_company`) ; effectif dans `{"03","11","12","21"}` (6 à 99 salariés) **+20** (`mid_size`) ; offre d'emploi technique ouverte **+25** (`hiring_tech`). Plafond 100.

- [x] **Step 1: Tests.** `test_jquery_1_is_outdated_jquery_3_is_not`. `test_wordpress_5_outdated`. `test_recent_company_boundary` (23 mois oui, 25 mois non). `test_mid_size_codes`. `test_hiring_flag_adds_25`. `test_all_unknown_inputs_scores_0_no_error` (tous les paramètres à `None`).
- [x] **Step 2: Lancer** `pytest tests/test_scoring_cloud.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter.**
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: score cloud`.

### Task 4: Offres d'emploi techniques (étude puis intégration facultative)

**Files:**
- Create: `backend/app/sources/jobs.py`
- Test: `backend/tests/test_jobs_source.py`

**Interfaces:**
- Produces: `async def has_open_tech_job(company_name: str, siret: str, client=None) -> bool` ; réglage `Settings.francetravail_client_id/secret: str | None`.

- [x] **Step 1: Étude (une heure maximum).** Lire la documentation de l'API « Offres d'emploi » de France Travail (inscription gratuite requise) et décider si une recherche par entreprise est possible. **Si non : sauter cette tâche** ; `hiring_tech` reste à `False` et la Task 3 est inchangée.
- [x] **Step 2: Tests (si retenue).** `test_returns_false_without_credentials`. `test_true_when_offer_matches_company_and_tech_keywords` (développeur, informatique, devops). `test_false_when_api_errors`.
- [x] **Step 3: Implémenter** avec jeton OAuth mis en cache.
- [x] **Step 4: Lancer** `pytest tests/test_jobs_source.py -v`. Attendu : PASS.
- [x] **Step 5: Commit** `feat: offres d'emploi techniques`.

### Task 5: Trois scores dans la récolte, l'API et l'interface

**Files:**
- Modify: `backend/app/collect.py`, `backend/app/routers/prospects.py`, `backend/app/schemas.py`, `frontend/src/pages/{MapPage,ProspectsPage,ProspectPage}.tsx`
- Test: `backend/tests/test_multi_offer.py`, `frontend/src/pages/ProspectsPage.test.tsx`

**Interfaces:**
- Consumes: `score_web`, `score_mobile`, `score_cloud`, `contact_priority`.
- Produces: la récolte enregistre une `ScoreRow` par offre ; `GET /prospects?offer=web|mobile|cloud` filtre et trie sur cette offre ; `ProspectDetail.priority_by_offer: dict[Offer, {value, reasons}]` ; sélecteur d'offre dans la carte et la liste ; la fiche affiche les trois `ScoreCard`.

- [x] **Step 1: Tests.** `test_collect_stores_three_scores_per_prospect`. `test_list_sorted_by_mobile_priority_when_offer_is_mobile`. `test_recollect_updates_scores_without_duplicates`. Front : `test_offer_selector_changes_query_param`, `test_profile_shows_three_score_cards`.
- [x] **Step 2: Lancer** `pytest backend/tests/test_multi_offer.py -v` et `npx vitest run`. Attendu : FAIL.
- [x] **Step 3: Implémenter.**
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: trois scores par prospect`.

### Task 6: Brouillons d'approche

**Files:**
- Create: `backend/app/outreach.py`, `backend/app/routers/outreach.py`, migration `0003_outreach.py`
- Modify: `backend/app/models.py`, `backend/app/config.py` (`anthropic_api_key`, `sender_name`, `sender_business`), `frontend/src/pages/ProspectPage.tsx`
- Test: `backend/tests/test_outreach.py`

**Interfaces:**
- Produces: modèle `OutreachDraft(id, prospect_id, offer, channel: "email"|"call", subject: str | None, body: str, source: "llm"|"template", variant: str, created_at)` ; `async def generate_outreach(prospect_id: int, offer: Offer, channel: str, session, llm=None) -> OutreachDraft` ; `POST /prospects/{id}/outreach` (`{offer, channel}`) ; `GET /prospects/{id}/outreach`.
- Le modèle reçoit uniquement : nom de l'entreprise, métier, ville, raisons du score pour l'offre, `sender_name`, `sender_business`. Demande : texte en français, vouvoiement, 120 mots maximum, aucune promesse de résultat chiffré.
- Repli (`source="template"`) : modèle fixe par offre et par canal, rempli avec les raisons.

- [x] **Step 1: Tests (modèle de langage simulé).** `test_email_draft_contains_source_sender_and_optout`. `test_draft_mentions_only_given_reasons` (le brouillon d'un prospect sans HTTPS parle de sécurité du site, pas de lenteur). `test_call_script_under_120_words`. `test_without_api_key_uses_template`. `test_llm_error_falls_back_to_template`. `test_overlong_llm_answer_is_rejected_then_template`. `test_do_not_contact_prospect_returns_409`. `test_unknown_prospect_404`. `test_variant_is_stored_for_later_statistics`.
- [x] **Step 2: Lancer** `pytest tests/test_outreach.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter.** Le contrôle de présence de la source, de l'identité et de la phrase de désinscription se fait **après** génération ; s'il manque un élément, on l'ajoute de façon fixe.
- [x] **Step 4: Lancer.** Attendu : PASS.
- [x] **Step 5: Commit** `feat: brouillons d'approche`.

### Task 7: Relances et page « Aujourd'hui »

**Files:**
- Create: `backend/app/routers/followups.py`, `frontend/src/pages/TodayPage.tsx`, migration `0004_followups.py`
- Modify: `backend/app/models.py`, `frontend/src/App.tsx`
- Test: `backend/tests/test_followups.py`, `frontend/src/pages/TodayPage.test.tsx`

**Interfaces:**
- Produces: `FollowUp(id, prospect_id, due_on: date, note, done_at)` ; `TrackingEvent(id, prospect_id, at, kind: "status"|"note"|"followup", text)` écrit à chaque changement de suivi ; `POST /prospects/{id}/followups` (`{due_on, note}`) ; `POST /followups/{id}/done` ; `GET /today` → `{followups_due: [...], top_priority: [...20 prospects]}` ; `top_priority` exclut les statuts `contacted`, `replied`, `refused`.

- [x] **Step 1: Tests.** `test_followup_due_today_appears_once`. `test_past_due_followup_appears_in_today`. `test_done_followup_disappears`. `test_due_date_uses_paris_calendar_day` (21 h 30 UTC le 24 novembre = 25 novembre à Paris). `test_status_change_writes_event`. `test_top_priority_excludes_contacted_and_refused`. Front : `test_today_page_lists_followups_and_top_prospects`.
- [x] **Step 2: Lancer** `pytest backend/tests/test_followups.py -v`. Attendu : FAIL.
- [x] **Step 3: Implémenter.**
- [x] **Step 4: Lancer** les tests Python et `npx vitest run`. Attendu : PASS.
- [x] **Step 5: Commit** `feat: relances et page aujourd'hui`.

---

## Auto-relecture

- **Couverture (V2)** : scores Mobile et Cloud : Tasks 1 à 5 ; brouillons d'e-mail et de script d'appel : 6 ; relances et historique : 7 ; offres d'emploi (« à étudier » dans le document) : 4 avec point d'arrêt.
- **Cohérence** : `score_mobile`, `score_cloud`, `tier_of`, `SiteAnalysis.has_booking` portent les mêmes noms dans toutes les tâches.
- **Écart assumé** : la V2 ne touche pas à la V1 sauf pour ajouter des champs et des paramètres facultatifs.
