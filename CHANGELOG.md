# Changelog

## v1.4.1 — 2026-11-22

### fix(laposte): appeler le suivi La Poste comme la page laposte.fr ([#6](https://github.com/antvgr/hacs-suivi-colis/pull/6))

#### Problème

Depuis Home Assistant, `suivi-unifie/<numéro>` répondait **HTTP 403** (vu dans les logs debug sur une vraie installation) : le service exige les cookies de session posés par la page de suivi et des en-têtes de navigateur. Le créneau La Poste n'arrivait donc jamais dans le capteur ni dans le calendrier.

#### Correction

- Ouverture d'abord de la page de suivi `https://www.laposte.fr/outils/suivre-vos-envois?code=<numéro>` pour obtenir les cookies de session.
- Puis appel de `…/suivi-unifie/<numéro>?lang=fr` avec ces cookies, la page en `Referer` et des en-têtes de navigateur (`User-Agent`, `Accept`, `Accept-Language`, `Sec-Fetch-*`).
- Session dédiée avec son propre cookie jar, fermée au déchargement de l'intégration.
- Toujours appelé uniquement quand 17track annonce une livraison ; en cas de refus, les données 17track sont gardées.

<details>
<summary>Détail des 1 commits</summary>

##### Corrections

- Laposte : call the tracking service like the laposte.fr page ([adb14cb](https://github.com/antvgr/hacs-suivi-colis/commit/adb14cb90bd3d2c2070ef61a9c22a805a2833292))

</details>

---

**Mise à jour** : HACS → Suivi de Colis → Mettre à jour, puis redémarrer Home Assistant et recharger la page du navigateur pour obtenir la nouvelle carte.
**Toutes les modifications** : https://github.com/antvgr/hacs-suivi-colis/compare/v1.4.0...v1.4.1

## v1.4.0 — 2026-11-22

### feat: calendrier des livraisons, créneau Colissimo via La Poste, diagnostics ([#5](https://github.com/antvgr/hacs-suivi-colis/pull/5))

#### Calendrier « Livraisons »

Nouvelle entité `calendar` (`calendar.suivi_de_colis_livraisons`) :
- un événement « Livraison : <colis> » par colis non livré ayant une date prévue ;
- événement horodaté sur le créneau quand il est connu (La Poste, transporteur) ;
- événement sur la journée entière quand seul le jour est connu (17track envoie minuit UTC, géré été comme hiver) ;
- description : numéro de suivi, transporteur, dernier événement, source de l'estimation.

#### Créneau de livraison Colissimo / La Poste

Pour un colis Colissimo / La Poste, le service public de suivi La Poste (`/ssu/sun/back/suivi-unifie/<numéro>`, utilisé par laposte.fr) donne le créneau horaire que 17track n'a pas.
- Appelé **uniquement** quand 17track annonce la livraison : nouvelle date prévue, ou passage en cours de livraison (polling et webhook), une fois par annonce.
- `estimDate` donne le jour ; le créneau `estimHourMin`/`estimHourMax` n'est retenu que s'il tombe ce jour-là, sinon la journée entière.
- `estimated_delivery_source: La Poste` ; non écrasé par les mises à jour 17track tant que 17track n'annonce rien de nouveau. Une nouvelle date 17track remplace d'abord l'ancien créneau, puis La Poste est redemandée.
- Endpoint non officiel : toute erreur (HTTP, délai, blocage) garde les données 17track.

#### Diagnostics

« Télécharger les diagnostics » contient, par numéro, la dernière réponse brute de 17track (polling ou webhook), avec la clé API, l'identifiant du webhook et les identifiants des boîtes mail masqués. Les dates 17track au format `2026/11/20` ou `2026-11-20 10:00` sont aussi lues.

<details>
<summary>Détail des 3 commits</summary>

##### Nouveautés

- Diagnostics with the raw 17track data, more tolerant dates ([1d22bc2](https://github.com/antvgr/hacs-suivi-colis/commit/1d22bc2b32c525efd3a984d0d3205387b7ed5374))
- Colissimo delivery day and time slot from La Poste ([203df06](https://github.com/antvgr/hacs-suivi-colis/commit/203df06e3ce98f89a280ed3e7e60d001ac805ccd))
- Deliveries calendar; ask La Poste only when 17track announces a delivery ([0e5e897](https://github.com/antvgr/hacs-suivi-colis/commit/0e5e897a134a3a7b174569156bec7fbbf439c302))

</details>

---

**Mise à jour** : HACS → Suivi de Colis → Mettre à jour, puis redémarrer Home Assistant et recharger la page du navigateur pour obtenir la nouvelle carte.
**Toutes les modifications** : https://github.com/antvgr/hacs-suivi-colis/compare/v1.3.1...v1.4.0

## v1.3.1 — 2026-11-19

### fix: faux colis créés depuis les emails, doublons et réimports ([#4](https://github.com/antvgr/hacs-suivi-colis/pull/4))

#### Problème

Chaque email de mise à jour UPS (« Mise à jour UPS : le colis est programmé en livraison demain ») créait de nouveaux capteurs : `sensor.decoration`, `sensor.ingnumberrow`…

Le parseur analysait le HTML brut. Le motif générique `track…[A-Z0-9]{10,30}` (insensible à la casse) attrapait du balisage :
- `class="trackingNumberRow"` → `INGNUMBERROW`
- `text-decoration` (CSS) → `DECORATION`

17track accepte ces « numéros » à l'enregistrement (1 crédit de quota chacun), puis renvoie `not_found`.

#### Corrections

**Extraction depuis les emails**
- Analyse uniquement le texte visible du HTML (sans balises, `<style>`, `<script>`, `<head>`, commentaires ; entités décodées)
- Limites de mot (`\b`) sur les motifs génériques
- Un numéro doit contenir au moins un chiffre
- Un numéro douteux venant d'un email n'est jamais enregistré sur 17track (pas de quota dépensé)
- Au démarrage, les colis créés par erreur depuis un email (numéro sans chiffre) sont supprimés

**Doublons / réimports**
- Numéros normalisés partout (majuscules, sans espaces) : un numéro saisi à la main avec des espaces correspond à celui trouvé dans les mails
- Les colis supprimés (à la main ou automatiquement après livraison) sont mémorisés 120 jours (plus que la fenêtre de recherche max de 90 jours) et ne sont plus réimportés depuis un email ; les rajouter à la main reste possible. Liste persistée dans le store (`removed`).

<details>
<summary>Détail des 2 commits</summary>

##### Corrections

- Email : stop creating packages from HTML/CSS words in carrier emails ([4115231](https://github.com/antvgr/hacs-suivi-colis/commit/411523140a64a70b2a158278b8923217033a5dd8))
- No duplicate or re-imported packages from emails ([ab5fe38](https://github.com/antvgr/hacs-suivi-colis/commit/ab5fe38cbccb8fa3feb7d30fd092ed9839aecab3))

</details>

---

**Mise à jour** : HACS → Suivi de Colis → Mettre à jour, puis redémarrer Home Assistant et recharger la page du navigateur pour obtenir la nouvelle carte.
**Toutes les modifications** : https://github.com/antvgr/hacs-suivi-colis/compare/v1.3.0...v1.3.1

## v1.3.0 — 2026-11-13

### ⚠️ À lire avant de mettre à jour

- Home Assistant **2025.1.0** ou plus récent est maintenant nécessaire.

### Colis, synthèse et diagnostic sur la page de l'intégration + README réécrit ([#3](https://github.com/antvgr/hacs-suivi-colis/pull/3))

#### Page de l'intégration

Toutes les entités sont rattachées à un appareil **Suivi de Colis**, donc chaque colis en cours apparaît maintenant sur la page de l'intégration.

- **Colis** : un capteur par colis. Son état est une énumération traduite dans l'interface (« En transit »…) et l'identifiant d'entité ne change pas. L'historique (`events`) n'est plus enregistré dans la base.
- **Synthèse** : colis en cours, livraisons aujourd'hui, colis à retirer (nombres, avec la liste en attribut), prochaine livraison (horodatage), problème de livraison (capteur binaire).
- **Événement** : `suivi_colis_status_changed` sur le bus, plus une entité événement « Changement de statut », avec l'ancien et le nouveau statut, le nom et le transporteur.
- **Diagnostic** :
  - quota 17track restant, déplacé dans cette section avec le même identifiant unique ;
  - dernière actualisation (avec le dernier webhook et la dernière vérification des emails) ;
  - un capteur de connectivité par boîte mail.
- Ajouter, supprimer ou renommer une boîte mail recharge l'intégration et retire les entités devenues inutiles.

#### Divers

- Le coordinateur reçoit maintenant l'entrée de configuration, ce que Home Assistant rendra obligatoire. La version minimale de Home Assistant passe à **2025.1** dans `hacs.json`.
- README entièrement réécrit : installation, configuration, menu des options, entités, carte, services, exemples d'automatisations, dépannage, désinstallation et migration.

<details>
<summary>Détail des 4 commits</summary>

##### Nouveautés

- Integration device with package, summary and diagnostic entities ([6165252](https://github.com/antvgr/hacs-suivi-colis/commit/61652529489e865ddfdc83a85d8a93e9d1fb95b6))

##### Documentation

- Rebuild CHANGELOG with the new release notes ([10aa852](https://github.com/antvgr/hacs-suivi-colis/commit/10aa852ab7921241b2a7128d1bb2f2eea252f69d))

##### Maintenance

- Richer release notes from pull request descriptions ([35934e5](https://github.com/antvgr/hacs-suivi-colis/commit/35934e560244b9896aa6099b97f02ca8136a411f))
- List every commit of a pull request in the release notes ([fff3684](https://github.com/antvgr/hacs-suivi-colis/commit/fff36845d06960e2f76c9ea834640bacddc27c7c))

</details>

---

**Mise à jour** : HACS → Suivi de Colis → Mettre à jour, puis redémarrer Home Assistant et recharger la page du navigateur pour obtenir la nouvelle carte.
**Toutes les modifications** : https://github.com/antvgr/hacs-suivi-colis/compare/v1.2.0...v1.3.0

## v1.2.0 — 2026-11-13

### Webhook 17track temps réel, changement de transporteur et relance rapide des nouveaux colis ([#2](https://github.com/antvgr/hacs-suivi-colis/pull/2))

#### Nouveaux colis : plus de « Inconnu » pendant 30 min

17track met de quelques secondes à plusieurs minutes pour récupérer un nouveau numéro chez le transporteur. Le rafraîchissement juste après l'ajout arrivait trop tôt et le suivant n'avait lieu que 30 minutes plus tard.
- L'intégration interroge à nouveau 17track à 1, 3 et 10 minutes tant que le colis n'a pas de données. Les minuteries sont annulées au déchargement.
- La carte affiche « En attente » au lieu de « Inconnu ».

#### Webhook 17track (temps réel, optionnel)

- Nouvel écran d'options **Notifications en temps réel** : il active le webhook et affiche l'URL à coller dans le tableau de bord 17track. C'est un cloudhook Nabu Casa si disponible, sinon l'URL externe.
- Chaque appel est vérifié avec l'en-tête `sign` de 17track (SHA-256 de corps + "/" + clé). Un appel non signé reçoit 401.
- `TRACKING_UPDATED` met le colis à jour immédiatement. `TRACKING_STOPPED` le signale (« Suivi arrêté par 17track » sur la carte).
- L'interrogation toutes les 30 minutes reste active en secours.

#### Service `suivi_colis.change_carrier`

- Suit un colis chez un autre transporteur : liste prédéfinie ou n'importe quel code 17track.
- Utilise `carrier_old` d'après les données 17track. Les erreurs (limite de 5 changements, etc.) sont remontées à l'appelant.
- Transporteurs ajoutés : Mondial Relay, Relais Colis, DPD, GLS, FedEx, TNT et Vinted Go, dans le sélecteur de la carte et les icônes.

#### Migrations

- Entrée de configuration **2.1 → 2.2** : ajout de l'identifiant secret du webhook. C'est une version mineure, donc une version 2.x antérieure lit encore l'entrée. Une entrée v1 passe d'abord par 2.1.
- Les nouveaux champs des colis (`carrier_code`, `tracking_stopped`) ont une valeur par défaut, donc les colis enregistrés par 1.0.x et 1.1.0 se chargent sans changement.

<details>
<summary>Détail des 4 commits</summary>

##### Nouveautés

- 17track webhook and change_carrier service ([0a2425a](https://github.com/antvgr/hacs-suivi-colis/commit/0a2425a7ad1c428bc7df74388f1542d32e81433c))
- Card : redesign in Home Assistant style, keep package names ([2f37022](https://github.com/antvgr/hacs-suivi-colis/commit/2f370229057f3316520bc562186800dbb453d3ff))

##### Corrections

- Poll 17track again shortly after adding a package ([d1bd2ce](https://github.com/antvgr/hacs-suivi-colis/commit/d1bd2ce80fe289710a25947518131cb04dc1ced4))

##### Documentation

- Describe the new card in the README ([5bc4cae](https://github.com/antvgr/hacs-suivi-colis/commit/5bc4caee744e5a24596d129fcb78887c34228daf))

</details>

---

**Mise à jour** : HACS → Suivi de Colis → Mettre à jour, puis redémarrer Home Assistant et recharger la page du navigateur pour obtenir la nouvelle carte.
**Toutes les modifications** : https://github.com/antvgr/hacs-suivi-colis/compare/v1.1.0...v1.2.0

## v1.1.0 — 2026-11-12

### Plusieurs boîtes mail IMAP, formulaire complet et API 17track v2.4 (corrige #2) ([#1](https://github.com/antvgr/hacs-suivi-colis/pull/1))

Même contenu que la PR proposée au dépôt original : hello-lemon/hacs-suivi-colis#3.

#### Résumé

- **IMAP** : correctif du bug `starttls` (hello-lemon/hacs-suivi-colis#2), plusieurs boîtes mail, nouveau formulaire de connexion (préréglages fournisseur, SSL/TLS / STARTTLS / aucun, certificat, dossiers lus sur le serveur, options d'analyse) et migration automatique de l'ancienne configuration.
- **17track** : codes transporteurs corrigés (DHL était envoyé comme FedEx), erreurs de quota bien détectées, passage à l'API v2.4 avec traduction des événements, sous-statut, date de livraison estimée, heure réelle de livraison et capteur de quota.
- **Carte** : affiche le sous-statut, la livraison prévue et l'heure de livraison.
- **CI** : hassfest, HACS et 39 tests à chaque push ; release automatique avec changelog à chaque merge sur `main`.
- **Licence MIT**, icônes déplacées dans `brand/`.

<details>
<summary>Détail des 3 commits</summary>

##### Documentation

- Add MIT license ([ff73489](https://github.com/antvgr/hacs-suivi-colis/commit/ff734896c0a1086a410639a4ed244942da39151a))

##### Maintenance

- HACS/hassfest validation, tests and automatic releases ([346a931](https://github.com/antvgr/hacs-suivi-colis/commit/346a9312fa54dc1b4618e943050246e64937b9c0))

##### Autres changements

- Multiple IMAP mailboxes, reworked email setup and 17track API v2.4 ([53835e4](https://github.com/antvgr/hacs-suivi-colis/commit/53835e4f0cf852ab233b87b29628297368529403))

</details>

---

**Mise à jour** : HACS → Suivi de Colis → Mettre à jour, puis redémarrer Home Assistant et recharger la page du navigateur pour obtenir la nouvelle carte.
**Toutes les modifications** : https://github.com/antvgr/hacs-suivi-colis/commits/v1.1.0
