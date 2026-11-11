# Bot d'alertes Vinted

Surveille Vinted et t'envoie une notification (Telegram et/ou Discord) dès qu'un
nouvel article correspondant à tes filtres est mis en ligne.

## Installation

Il faut Python 3.8 ou plus récent.

```bash
pip install -r requirements.txt
```

```bash
cp config.example.toml config.toml
```

## Configuration

Tout se règle dans `config.toml`.

### Notifications

**Telegram**

1. Écris à [@BotFather](https://t.me/BotFather), envoie `/newbot` et copie le token dans `token`.
2. Écris à [@userinfobot](https://t.me/userinfobot) et copie ton identifiant dans `chat_id`.
3. Envoie un premier message à ton bot (sinon il n'a pas le droit de t'écrire).

**Discord**

Dans le salon voulu : *Paramètres > Intégrations > Webhooks > Nouveau webhook*,
puis copie l'URL dans `webhook_url`.

Vérifie que ça marche :

```bash
python vinted_bot.py --test-notif
```

### Alertes

Un bloc `[[alertes]]` par recherche, autant que tu veux :

```toml
[[alertes]]
nom = "PS5"
recherche = "ps5"
prix_min = 150
prix_max = 350
mots_exclus = ["manette", "jeu", "boite vide"]
```

| Clé | Rôle |
| --- | --- |
| `nom` | Nom affiché dans la notification (unique) |
| `recherche` | Texte recherché sur Vinted |
| `prix_min`, `prix_max` | Fourchette de prix |
| `mots_exclus` | Ignore l'annonce si son titre contient l'un de ces mots |
| `mots_requis` | Le titre doit contenir tous ces mots |
| `catalog_ids`, `brand_ids`, `taille_ids`, `etat_ids` | Catégorie, marque, taille, état |

Les mots sont comparés sans tenir compte des majuscules ni des accents.

Pour trouver les identifiants de catégorie, marque, taille ou état : fais ta
recherche sur le site Vinted avec les filtres voulus et relève les nombres dans
l'URL (`catalog[]=`, `brand_ids[]=`, `size_ids[]=`, `status_ids[]=`).

## Lancement

```bash
python vinted_bot.py
```

Au premier passage, le bot mémorise les annonces déjà en ligne sans te notifier ;
tu ne reçois ensuite que les nouvelles. Les articles vus sont enregistrés dans
`articles_vus.json`, donc un redémarrage ne renvoie pas d'anciennes alertes.

Pour une seule vérification (par exemple depuis cron) :

```bash
python vinted_bot.py --once
```

## Faire tourner le bot sur GitHub Actions

Le dépôt contient un workflow (`.github/workflows/alertes.yml`) qui lance le bot
toutes les 5 minutes sans que ta machine soit allumée.

1. Sur GitHub : *Settings > Secrets and variables > Actions > New repository secret*,
   crée deux secrets : `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID`.
2. Règle tes alertes dans `config.actions.toml` (ce fichier est public : n'y mets
   pas de token).
3. Onglet *Actions* : active les workflows si GitHub le demande, puis lance
   « Alertes Vinted » avec *Run workflow* pour un premier essai.

Limites : GitHub lance les tâches planifiées avec un retard variable (souvent
quelques minutes, parfois plus), et désactive le workflow après 60 jours sans
activité sur le dépôt.

## À savoir

- Le bot lit la page de recherche du site Vinted (il n'existe pas d'API
  publique) : si Vinted modifie son site ou bloque les requêtes (erreur
  403/429), le bot peut cesser de fonctionner. En cas de blocage, augmente
  `intervalle_secondes`.
- Fais-le tourner depuis une connexion personnelle (PC, Raspberry Pi) : les
  adresses IP de serveurs cloud sont souvent bloquées par Vinted.
