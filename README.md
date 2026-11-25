# MyProspect

Outil local de prospection B2B. On trace une zone en France, on choisit des métiers, et l'outil :
- récolte les entreprises du registre officiel ;
- les enrichit avec OpenStreetMap ;
- analyse leur site web ;
- calcule un **score d'opportunité Web expliqué** et une **priorité de contact**.

Le suivi (statut, favori, notes) et l'export CSV complètent l'ensemble.

L'outil **prépare** le travail, il n'envoie jamais d'e-mail, d'appel ni de SMS : c'est vous qui agissez.

## Démarrer

Prérequis : Docker Desktop.

```bash
cp .env.example .env        # puis éditez .env (voir « Variables »)
docker compose up --build   # la première fois, ou après une mise à jour du code
```

- Interface : <http://localhost:5173> (ou le port choisi dans `WEB_PORT`)
- API et documentation interactive : <http://localhost:8000/docs>
- État de l'API et de la base : <http://localhost:8000/health>

Arrêt : `docker compose down`. Pour effacer aussi toutes les données : `docker compose down -v`.

### Variables (`.env`)

| Variable | Rôle |
|---|---|
| `POSTGRES_PASSWORD` | **Obligatoire.** Mot de passe de la base locale : choisissez-le long et aléatoire, et reportez-le dans `DATABASE_URL` et `TEST_DATABASE_URL`. Aucun mot de passe par défaut n'existe dans le dépôt. |
| `HOME_LAT`, `HOME_LONG` | **Obligatoires.** Votre position en degrés décimaux. Elle sert au bonus « proche » (≤ 20 km) de la priorité de contact. |
| `SENDER_NAME`, `SENDER_BUSINESS` | Votre nom et votre activité, repris dans chaque brouillon d'approche (signature, présentation au téléphone). |
| `ANTHROPIC_API_KEY` | Facultative. Clé de l'API Claude pour rédiger les brouillons ; sans elle, des modèles de texte fixes sont utilisés. |
| `AUDIT_REPORT_ENABLED` | `true` par défaut : rapport d'audit PDF à joindre à un premier message (lien sur la fiche). |
| `WEASYPRINT_DLL_DIRECTORIES` | Windows hors Docker uniquement : dossier des bibliothèques GTK dont le rapport PDF a besoin (par exemple `C:\Program Files\Inkscape\bin`). Inutile dans Docker. |
| `FRANCETRAVAIL_CLIENT_ID`, `FRANCETRAVAIL_CLIENT_SECRET` | Facultatives. Application francetravail.io abonnée à « Offres d'emploi v2 » : repère les entreprises qui recrutent sur un poste technique (bonus du score Cloud). |
| `PAGESPEED_API_KEY` | Facultative. Clé Google PageSpeed Insights pour mesurer la vitesse mobile des sites. Sans clé, cette mesure est simplement absente. |
| `POSTGRES_USER`, `POSTGRES_DB` | Utilisateur et nom de la base locale. |
| `DB_PORT`, `API_PORT`, `WEB_PORT` | Ports publiés **sur votre machine uniquement** (`127.0.0.1`), par défaut 5433, 8000, 5173 : rien n'est accessible depuis le réseau. |
| `DATABASE_URL`, `TEST_DATABASE_URL` | Utilisées seulement quand le backend tourne hors Docker (tests, migrations). Gardez `127.0.0.1` plutôt que `localhost` : sous Windows, `localhost` tente d'abord IPv6 et chaque connexion perd une dizaine de secondes. |

**Windows : « Ports are not available … bind »** au démarrage de `web` ? Windows (Hyper-V) réserve des plages de ports. Vérifiez-les avec `netsh interface ipv4 show excludedportrange protocol=tcp`, puis choisissez un `WEB_PORT` hors de ces plages (par exemple 5300).

## Utilisation

1. **Carte** : choisissez une zone et cochez un ou plusieurs métiers, puis « Lancer la récolte ». Trois types de zone :
   - **Commune** : nom ou code INSEE ;
   - **Cercle** : centre de la carte et rayon ;
   - **Dessin libre** : cliquez au moins trois points sur la carte.

   Une barre suit la progression. Les points sont colorés selon le palier d'opportunité (1 à 6), et les compteurs indiquent ce qui est dans la vue. Une zone de plus de 50 km de large est refusée.
2. **Prospects** : la liste se trie par priorité, score ou nom (cliquez à nouveau pour inverser le sens). Filtres : métier, site connu, score minimum, statut, opposition à la prospection, favoris, recherche par nom ou SIRET. « Exporter en CSV » reprend les filtres actifs.
3. **Fiche** :
   - les coordonnées, chacune avec sa source et sa date (bouton « Copier ») ;
   - la priorité et ses raisons ;
   - le score Web et ses raisons ;
   - l'analyse du site ;
   - le suivi : statut, favori, notes ;
   - les actions « Ne plus contacter » et « Supprimer définitivement ».

Récolter deux fois la même zone ne crée pas de doublon et ne touche pas au suivi.

## Comment les scores sont calculés

**Score Web (0-100)** :

| Cas | Points |
|---|---|
| Aucun site connu | 75 |
| Site inaccessible | 70 |
| Site joignable, sans HTTPS | +20 |
| Site joignable, titre, description ou H1 manquant | +15 |
| Site joignable, pas de balise viewport | +15 |
| Site joignable, vitesse mobile < 50 | +20 |
| Site joignable, vitesse mobile entre 50 et 89 | +10 |

Le palier vaut `min(6, score // 17 + 1)`.

**Priorité de contact** : la moitié du score Web, puis :
- téléphone connu : +12 ;
- e-mail connu : +8 ;
- petite structure (tranche d'effectif vide, NN, 00, 01 ou 02) : +8 ;
- à 20 km ou moins de chez vous : +6.

Chaque point gagné apparaît comme une raison lisible sur la fiche.

## Sources de données et limites

- **Registre officiel** : [API Recherche d'entreprises](https://recherche-entreprises.api.gouv.fr/docs/), endpoint `near_point`. Limite de l'API : 7 appels/s ; l'outil s'en tient à 5. Les établissements fermés et les entreprises non diffusibles sont écartés.
- **OpenStreetMap** : téléphone, e-mail et site via [Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API). Le serveur public est souvent surchargé ; en cas d'échec, la récolte continue sans ces données. Sa politique d'usage demande de rester très économe (moins d'une centaine de requêtes par jour en usage régulier) et réserve l'usage commercial aux serveurs auto-hébergés ou payants.
- **Contour des communes** : [API Géo](https://geo.api.gouv.fr).
- **Fond de carte** : [OpenFreeMap](https://openfreemap.org), sans clé.

Limites connues :
- **« Aucun site web connu » ne veut pas dire « pas de site »**. Le registre ne donne ni téléphone ni site, et OpenStreetMap n'en connaît qu'une partie. Sur un essai réel (66 salons de coiffure au centre de Lyon), 9 sites et 13 téléphones ont été trouvés.
- Un site qui bloque les robots (HTTP 403) est compté comme « inaccessible ».
- Le rapprochement avec OpenStreetMap exige une distance ≤ 80 m et des noms proches. Il peut se tromper, d'où la source et la date affichées pour chaque coordonnée.

## Cadre légal (à vérifier par vous avant usage)

- **Uniquement des entreprises (B2B)**, uniquement en France.
- Prospection B2B par e-mail : possible si le message concerne la fonction de la personne. Indiquez la source de vos données et proposez une désinscription simple.
- Pour une entreprise individuelle, le nom du dirigeant est une **donnée personnelle**. Gardez-la le temps nécessaire, et supprimez-la sur demande (bouton « Supprimer définitivement », qui empêche aussi toute future récolte de ce SIRET).
- **Opposition à la prospection commerciale** : certaines entreprises l'ont déclarée au registre. L'outil les garde mais les signale partout (liste, fiche, export) : c'est à vous de décider.
- « Ne plus contacter » garde la fiche, passe le statut à « Refusé » et exclut l'entreprise des récoltes suivantes.

## Développement

Backend (Python 3.12) :

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"    # sous Linux/macOS : .venv/bin/python
docker compose up -d db                             # base PostgreSQL + PostGIS
.venv/Scripts/python -m pytest                      # tests (base « prospect_test » créée automatiquement)
.venv/Scripts/python -m alembic upgrade head        # migrations sur la base de travail
```

Frontend :

```bash
cd frontend
npm install
npx vitest run       # tests
npx tsc --noEmit     # vérification des types
npm run dev          # http://localhost:5173, /api relayé vers http://localhost:8000
```

Aucun test ne fait de vraie requête réseau : le registre, OpenStreetMap, les sites et l'API sont simulés.
