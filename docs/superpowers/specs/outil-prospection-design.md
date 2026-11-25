# Outil de prospection : document de conception

Date : 25 novembre 2026. Statut : **à valider par Duval avant tout développement.**

## 1. Intention et pourquoi

Duval est développeur fullstack (web, mobile, cloud) et veut trouver lui-même ses clients. Il a vu un outil de prospection pour webmasters (« Blean Prospect », dans une vidéo TikTok) et veut construire **son propre outil**, adapté à ce qu'il vend.

L'outil lui permet de :
1. choisir une zone sur une carte et des filtres ;
2. récupérer les entreprises de cette zone et les analyser ;
3. obtenir pour chacune un **score d'opportunité** expliqué, par offre (web, mobile, cloud/logiciel) ;
4. savoir **qui contacter en premier, par quel canal (téléphone, e-mail) et avec quel angle d'approche**.

Duval envoie lui-même les messages et passe les appels. L'outil ne contacte personne à sa place.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Cible : les entreprises (B2B), de tous secteurs et de toutes tailles, **partout en France**.
- Carte avec zone (commune, cercle, dessin libre) et filtres (métier, taille, site ou pas de site, score, statut).
- Score 0-100 par offre, avec les raisons lisibles, et un classement « à contacter en premier ».
- Fiche prospect : coordonnées connues, analyse du site, scores, suivi (favori, statut, notes).

**Non-objectifs (pour l'instant)**
- Aucun envoi automatique d'e-mails, d'appels ou de SMS (décision de Duval : « le premier cas pour l'instant »).
- Pas de multi-utilisateurs, pas de comptes, pas de facturation.
- Pas de base nationale préchargée, pas de couverture hors France.
- Pas de prospection de particuliers.

**Anti-objectifs (l'outil serait un échec même s'il « marche »)**
- Un score opaque : chaque score doit montrer ses raisons.
- Des milliers de prospects sans priorisation.
- Des contacts obsolètes ou faux présentés comme fiables : chaque coordonnée garde sa source et sa date.
- Copier l'interface ou la marque de l'outil de la vidéo. On s'en inspire pour les idées, pas pour le design.
- Ignorer les entreprises non diffusibles ou opposées à la prospection.

## 3. Contraintes

- Données gratuites ou quasi gratuites : registre officiel des entreprises (SIRENE / API Recherche d'entreprises), OpenStreetMap, API de mesure de performance de site (PageSpeed).
- Le registre officiel ne donne en général **ni téléphone ni e-mail** : ils viennent d'OpenStreetMap et de l'analyse des sites. Beaucoup de fiches auront donc peu de coordonnées.
- Limites de débit des API : la collecte doit être progressive, avec reprise en cas d'erreur.
- Cadre légal (RGPD / CNIL, à vérifier par Duval avant usage) : le démarchage B2B par e-mail est possible sous conditions (pertinence pour la fonction, source indiquée, désinscription simple). Pour les entreprises individuelles, le nom du dirigeant est une donnée personnelle : durée de conservation limitée et suppression sur demande.
- Projet mené seul : tout doit rester simple à construire et à maintenir.

## 4. Approches envisagées

1. **Collecte à la demande (choisie).** Duval trace une zone et des métiers, l'outil récolte et analyse, puis enregistre dans sa base. Carte et filtres instantanés ensuite. Léger, adapté à un usage solo, on n'analyse que les zones utiles. Inconvénient : il faut lancer une récolte avant de voir une zone nouvelle.
2. **Base nationale préchargée.** Import de tout le registre. Carte immédiate partout, mais beaucoup de stockage, mises à jour lourdes, et presque aucune entreprise analysée au départ. Écartée, reconsidérable plus tard.
3. **Tout en direct, sans stockage.** Le plus simple à écrire, mais lent, limité par les quotas et sans historique de suivi. Écartée.

## 5. Décisions prises

**Validées par Duval**
- Approche 1 (collecte à la demande).
- Technologies : React (interface), backend Python, PostgreSQL avec PostGIS, MapLibre pour la carte.
- Pays : France uniquement.
- Contact : l'outil recommande, Duval agit.

## 6. Mes propositions (non encore validées, à corriger)

- **Hébergement :** usage local (Docker Compose sur son ordinateur), un seul utilisateur, pas de connexion au départ. Un déploiement cloud viendra plus tard si besoin.
- **Succès :** en moins de 10 minutes, choisir une commune, lancer une récolte et obtenir une liste d'environ 20 prospects classés, chacun avec la raison du score et un angle d'approche.
- **Métiers :** une liste de départ (garage, coiffeur, restaurant, plombier, agence immobilière) basée sur des codes d'activité (NAF), modifiable. Les entreprises sans site sont incluses, pas seulement celles avec un site faible.
- **Récoltes :** un journal des zones déjà récoltées avec date, et un bouton pour les rafraîchir.
- **Conformité :** exclusion automatique des entreprises non diffusibles ; chaque fiche peut être supprimée définitivement et ajoutée à une liste « ne plus contacter ».

## 7. Le score d'opportunité (première version)

Un score 0-100 **par offre**, avec la liste des raisons.

- **Web :** pas de site ; site sans HTTPS ; titre, description ou balise principale manquants ; mauvaise vitesse sur mobile ; site non adapté au mobile.
- **Mobile (à partir de la V2) :** activité qui prend des commandes ou des réservations (restaurant, coiffeur, garage) sans prise de rendez-vous ni commande en ligne détectée.
- **Cloud et logiciel sur mesure (à partir de la V2) :** technologie vieillissante détectée, entreprise en croissance (effectif, création récente), offres d'emploi tech ouvertes (à étudier).

**« Qui contacter en premier » = opportunité × facilité de contact × adéquation.** Exemple de points : téléphone connu, e-mail connu, petite structure (décideur joignable), proximité de Duval. Les poids sont des règles lisibles, réglables, pas un modèle opaque.

## 8. Périmètre par étapes

**V1 (premier objectif)**
- Carte et tracé de zone (commune, cercle, dessin libre) ; récolte registre + OpenStreetMap ; analyse des sites (HTTPS, balises, vitesse) ; score Web ; liste filtrable ; fiche prospect ; favoris, statut (à contacter, contacté, répondu, refusé) et notes ; export CSV.

**V2**
- Scores Mobile et Cloud/logiciel.
- Angle d'approche, e-mail et script d'appel générés par prospect (modèle de langage, à relire par Duval).
- Relances : rappel à une date, historique des échanges.

**V3 (idées de fonctionnalités en plus)**
- Avis et fiche Google comme signaux (note faible, peu d'avis, fiche non revendiquée).
- Maquette « avant/après » ou mini-rapport d'audit à joindre au premier message.
- Tableau de bord : taux de réponse par type de prospect, par message, par zone.
- Détection de doublons et de fermetures, alertes sur de nouvelles entreprises dans une zone suivie.
- Envoi assisté (brouillons préparés, jamais envoyés automatiquement).

## 9. Données (esquisse)

Entreprise (identifiant SIRET, nom, activité, effectif, date de création, position, adresse, téléphone, e-mail, site, source et date de chaque champ) ; analyse de site ; scores avec raisons ; zones récoltées ; suivi (statut, notes, historique) ; liste d'exclusion.

## 10. Laissé à la personne qui construit

Choix du framework Python, de la file de tâches pour la collecte, du regroupement des points sur la carte, du schéma exact, de la méthode d'analyse des sites, du nom du projet. À vérifier au démarrage : ce que l'API Recherche d'entreprises permet comme recherche par zone, et les quotas d'OpenStreetMap et de PageSpeed.
