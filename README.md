# Suivi de Colis

Intégration Home Assistant pour le suivi de colis via l'[API 17track v2.4](https://api.17track.net/en/doc).

Suivi de plus de 1200 transporteurs (Chronopost, Colissimo, DHL, UPS, Amazon, Cainiao, Colis Privé…) avec détection automatique depuis les emails.

## Fonctionnalités

- **1 capteur par colis** : statut, statut détaillé (douane, destinataire absent, adresse invalide, retour à l'expéditeur, perdu…), localisation, transporteur, historique des événements
- **Date de livraison estimée** (fournie par le transporteur ou estimée par 17track) et **heure réelle de livraison**
- **Événements traduits** dans la langue de Home Assistant quand le transporteur fournit une traduction officielle (colis ajoutés à partir de cette version)
- **Capteur « Quota 17track restant »** : crédits de suivi restants, avec le total, les crédits utilisés et ceux du jour en attributs
- **Ajout manuel** via le service `suivi_colis.add_package` ou le bouton "+" de la carte
- **Sélecteur de transporteur** : choix manuel ou détection automatique
- **Détection automatique du transporteur** à partir du format du numéro de suivi, avec fallback auto-détection 17track si rejeté
- **Scan IMAP multi-boîtes** : détection automatique des numéros de suivi depuis une ou plusieurs boîtes mail (perso ou dédiées)
- **Suppression automatique** des colis livrés après un délai configurable
- **Carte Lovelace** incluse avec historique dépliable au clic et suppression des colis livrés

## Installation

### HACS (recommandé)

1. Ajouter ce dépôt comme dépôt personnalisé dans HACS
2. Installer **Suivi de Colis**
3. Redémarrer Home Assistant
4. Ajouter l'intégration via **Paramètres → Intégrations**

### Manuelle

Copier le dossier `custom_components/suivi_colis/` dans votre répertoire `config/custom_components/`.

## Configuration

### Étape 1 — Clé API 17track

1. Créer un compte sur [api.17track.net](https://api.17track.net/register)
2. Dans le dashboard 17track, aller dans **Settings → Security → API Key**
3. Copier la clé API

Depuis le 7 janvier 2026, 17track ne renouvelle plus les 100 trackings gratuits mensuels : un nouveau compte reçoit une dotation unique de 200 numéros de suivi. Chaque nouveau numéro enregistré consomme 1 crédit ; les mises à jour d'un colis déjà suivi sont gratuites.

### Étape 2 — Boîtes mail IMAP (optionnel)

Ajoutez **une ou plusieurs boîtes mail** IMAP pour détecter automatiquement les numéros de suivi. Les boîtes s'ajoutent, se modifient, se suspendent ou se suppriment ensuite depuis **Paramètres → Appareils et services → Suivi de Colis → Configurer**.

Pour chaque boîte :

1. **Fournisseur** : préremplit le serveur, le port et le chiffrement (Gmail, Outlook, Yahoo, iCloud, Orange, Free, SFR, La Poste, GMX, IONOS, OVH, Proton Mail Bridge) ou « Autre » pour une saisie manuelle.
2. **Connexion** (testée immédiatement, avec un message d'erreur précis : identifiants, certificat, port, serveur introuvable…) :
   - serveur, port (vide = port standard), nom affiché ;
   - chiffrement : **SSL/TLS** (993), **STARTTLS** (143) ou **aucun** ;
   - vérification du certificat (désactivable pour un certificat auto-signé) ;
   - identifiant, mot de passe, délai d'attente.
3. **Analyse** :
   - **dossiers** à analyser (liste lue sur le serveur, plusieurs choix possibles) ;
   - **boîte dédiée** : analyse tous les emails, pas seulement ceux des transporteurs connus. Idéal si vous transférez vos notifications de livraison vers une adresse dédiée ;
   - période analysée (en jours) et nombre max. d'emails par dossier ;
   - uniquement les non lus, et/ou marquer comme lus les emails contenant un numéro de suivi ;
   - boîte active / suspendue.

> Gmail, Yahoo et iCloud exigent un **mot de passe d'application**. Les comptes Microsoft (Outlook, Hotmail) n'acceptent plus que l'OAuth2, qui n'est pas pris en charge pour l'instant.

Une configuration créée avec une version précédente (une seule boîte) est migrée automatiquement.

### Options

- **Archivage automatique** : nombre de jours après livraison avant suppression (défaut : 2, 0 = désactivé)
- **Intervalle de vérification emails** : en minutes (défaut : 15)

## Services

| Service | Description |
|---------|-------------|
| `suivi_colis.add_package` | Ajouter un numéro de suivi |
| `suivi_colis.remove_package` | Arrêter le suivi d'un colis |
| `suivi_colis.refresh` | Forcer une mise à jour immédiate |
| `suivi_colis.archive_delivered` | Archiver tous les colis livrés |

### Exemple : ajouter un colis

```yaml
service: suivi_colis.add_package
data:
  tracking_number: "XX123456789FR"
  friendly_name: "Clavier MX Keys"
  carrier: "chronopost"  # optionnel, détecté automatiquement
```

## Carte Lovelace

La carte custom s'enregistre automatiquement au démarrage de Home Assistant.

1. Aller sur un dashboard → **Ajouter une carte**
2. Chercher **"Suivi de Colis"** dans le picker
3. Aucune configuration nécessaire

La carte affiche pour chaque colis :
- Logo du transporteur, nom, numéro de suivi
- Statut coloré et dernière info/localisation
- **Clic sur un colis** : déplie l'historique complet des événements
- **Bouton "+"** : ajouter un colis avec sélecteur de transporteur (Auto, La Poste, Chronopost, UPS, DHL, AliExpress, Colis Privé)
- **Bouton "x"** sur les colis livrés : suppression manuelle

## Transporteurs supportés

Détection automatique : Chronopost, Colissimo, La Poste, DHL, UPS, Amazon, Cainiao/AliExpress, Colis Privé.

Tous les 1200+ transporteurs supportés par 17track fonctionnent en ajout manuel.

## Développement

### Tests

```bash
pip install -r requirements_test.txt
pytest
```

### Intégration continue

À chaque push et pull request, GitHub Actions lance :
- **Hassfest** : validation officielle Home Assistant (manifest, traductions, services) ;
- **HACS** : validation du dépôt pour HACS ;
- **Tests** : la suite `pytest`.

### Versions

Chaque merge sur `main` publie automatiquement une nouvelle version (tag `vX.Y.Z`, release GitHub utilisée par HACS, `CHANGELOG.md` et version du `manifest.json` mis à jour) :
- version du `manifest.json` augmentée à la main dans la PR → c'est elle qui est publiée ;
- sinon, d'après les messages de commit depuis la dernière version :
  - `feat: …` → version mineure (1.**2**.0) ;
  - `type!: …` ou `BREAKING CHANGE` dans le message → version majeure (**2**.0.0) ;
  - tout le reste (`fix: …`, `docs: …`…) → correctif (1.1.**1**).

Les notes de version reprennent les pull requests fusionnées (ou les commits s'il n'y en a pas).

## Licence

MIT, voir [LICENSE](LICENSE).
