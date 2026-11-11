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

## À savoir

- Le bot utilise l'API interne du site Vinted, qui n'est pas officielle : elle
  peut changer ou bloquer les requêtes (erreur 403/429). Dans ce cas, augmente
  `intervalle_secondes`.
- Fais-le tourner depuis une connexion personnelle (PC, Raspberry Pi) : les
  adresses IP de serveurs cloud sont souvent bloquées par Vinted.
