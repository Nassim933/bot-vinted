#!/usr/bin/env python3
"""Bot d'alertes Vinted : prévient dès qu'un nouvel article correspond à tes filtres.

Usage :
    python vinted_bot.py                 # tourne en continu
    python vinted_bot.py --once          # une seule vérification (pratique avec cron)
    python vinted_bot.py --test-notif    # envoie une notification de test
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import tomllib
import unicodedata
from pathlib import Path

import requests

log = logging.getLogger("vinted-bot")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MAX_IDS_MEMORISES = 3000  # par alerte


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def charger_config(chemin: Path) -> dict:
    if not chemin.exists():
        sys.exit(
            f"Fichier de configuration introuvable : {chemin}\n"
            "Copie config.example.toml vers config.toml puis adapte-le."
        )
    with chemin.open("rb") as f:
        config = tomllib.load(f)

    alertes = config.get("alertes") or []
    if not alertes:
        sys.exit("Aucune alerte définie : ajoute au moins un bloc [[alertes]].")
    noms = set()
    for alerte in alertes:
        if not alerte.get("nom"):
            sys.exit("Chaque alerte doit avoir un 'nom'.")
        if alerte["nom"] in noms:
            sys.exit(f"Deux alertes portent le même nom : {alerte['nom']}")
        noms.add(alerte["nom"])
        if not alerte.get("recherche") and not alerte.get("catalog_ids"):
            sys.exit(f"Alerte '{alerte['nom']}' : il faut 'recherche' ou 'catalog_ids'.")
    return config


# --------------------------------------------------------------------------- #
# Client Vinted
# --------------------------------------------------------------------------- #

class ClientVinted:
    """Petit client pour l'API de recherche utilisée par le site Vinted."""

    def __init__(self, domaine: str = "www.vinted.fr"):
        self.base = f"https://{domaine}"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            }
        )
        self._cookies_ok = False

    def _obtenir_cookies(self) -> None:
        # L'API exige les cookies de session posés par la page d'accueil.
        self.session.cookies.clear()
        r = self.session.get(self.base + "/", timeout=20)
        r.raise_for_status()
        self._cookies_ok = True

    def rechercher(self, alerte: dict, par_page: int = 40) -> list[dict]:
        params = {
            "page": 1,
            "per_page": par_page,
            "order": "newest_first",
            "search_text": alerte.get("recherche", ""),
        }
        if alerte.get("prix_min") is not None:
            params["price_from"] = alerte["prix_min"]
        if alerte.get("prix_max") is not None:
            params["price_to"] = alerte["prix_max"]
        for cle_config, cle_api in (
            ("catalog_ids", "catalog_ids"),
            ("brand_ids", "brand_ids"),
            ("etat_ids", "status_ids"),
            ("taille_ids", "size_ids"),
        ):
            if alerte.get(cle_config):
                params[cle_api] = ",".join(str(v) for v in alerte[cle_config])

        for tentative in (1, 2):
            if not self._cookies_ok:
                self._obtenir_cookies()
            r = self.session.get(
                self.base + "/api/v2/catalog/items", params=params, timeout=20
            )
            if r.status_code in (401, 403) and tentative == 1:
                log.info("Session expirée (HTTP %s), renouvellement…", r.status_code)
                self._cookies_ok = False
                continue
            r.raise_for_status()
            return r.json().get("items", [])
        return []


# --------------------------------------------------------------------------- #
# Filtres
# --------------------------------------------------------------------------- #

def normaliser(texte: str) -> str:
    """Minuscules sans accents, pour comparer les mots-clés."""
    sans_accents = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in sans_accents if not unicodedata.combining(c)).lower()


def prix_article(article: dict) -> float | None:
    prix = article.get("price")
    if isinstance(prix, dict):
        prix = prix.get("amount")
    try:
        return float(prix)
    except (TypeError, ValueError):
        return None


def devise_article(article: dict) -> str:
    prix = article.get("price")
    if isinstance(prix, dict) and prix.get("currency_code"):
        return prix["currency_code"]
    return article.get("currency") or "EUR"


def correspond(article: dict, alerte: dict) -> bool:
    """Filtres appliqués côté bot, en plus de ceux envoyés à Vinted."""
    prix = prix_article(article)
    if prix is not None:
        if alerte.get("prix_min") is not None and prix < alerte["prix_min"]:
            return False
        if alerte.get("prix_max") is not None and prix > alerte["prix_max"]:
            return False

    titre = normaliser(article.get("title") or "")
    if any(normaliser(m) in titre for m in alerte.get("mots_exclus", [])):
        return False
    if not all(normaliser(m) in titre for m in alerte.get("mots_requis", [])):
        return False
    return True


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #

def infos_article(article: dict, base: str) -> dict:
    url = article.get("url") or f"/items/{article.get('id')}"
    if url.startswith("/"):
        url = base + url
    prix = prix_article(article)
    photo = article.get("photo") or {}
    return {
        "titre": article.get("title") or "(sans titre)",
        "prix": f"{prix:.2f} {devise_article(article)}" if prix is not None else "?",
        "marque": article.get("brand_title") or "",
        "taille": article.get("size_title") or "",
        "etat": article.get("status") or "",
        "vendeur": (article.get("user") or {}).get("login") or "",
        "url": url,
        "photo": photo.get("url") if isinstance(photo, dict) else None,
    }


class Notifieur:
    def __init__(self, config: dict):
        notif = config.get("notifications", {})
        tg = notif.get("telegram", {})
        self.tg_token = os.environ.get("TELEGRAM_TOKEN") or tg.get("token") or ""
        self.tg_chat = os.environ.get("TELEGRAM_CHAT_ID") or str(tg.get("chat_id") or "")
        self.discord = (
            os.environ.get("DISCORD_WEBHOOK_URL")
            or notif.get("discord", {}).get("webhook_url")
            or ""
        )
        if not (self.tg_token and self.tg_chat) and not self.discord:
            log.warning(
                "Aucun canal de notification configuré : "
                "les alertes s'afficheront seulement dans le terminal."
            )

    def envoyer(self, nom_alerte: str, info: dict) -> None:
        details = " · ".join(
            v for v in (info["marque"], info["taille"], info["etat"]) if v
        )
        log.info("🔔 [%s] %s — %s — %s", nom_alerte, info["titre"], info["prix"], info["url"])
        if self.tg_token and self.tg_chat:
            self._telegram(nom_alerte, info, details)
        if self.discord:
            self._discord(nom_alerte, info, details)

    def _telegram(self, nom_alerte: str, info: dict, details: str) -> None:
        lignes = [f"🔔 {nom_alerte}", info["titre"], f"💶 {info['prix']}"]
        if details:
            lignes.append(details)
        if info["vendeur"]:
            lignes.append(f"👤 {info['vendeur']}")
        lignes.append(info["url"])
        texte = "\n".join(lignes)
        api = f"https://api.telegram.org/bot{self.tg_token}"
        try:
            r = None
            if info["photo"]:
                r = requests.post(
                    f"{api}/sendPhoto",
                    data={"chat_id": self.tg_chat, "photo": info["photo"], "caption": texte},
                    timeout=20,
                )
            if r is None or not r.ok:  # pas de photo, ou photo refusée par Telegram
                r = requests.post(
                    f"{api}/sendMessage",
                    data={"chat_id": self.tg_chat, "text": texte},
                    timeout=20,
                )
            if not r.ok:
                log.error("Telegram a refusé le message : %s", r.text[:300])
        except requests.RequestException as e:
            log.error("Envoi Telegram impossible : %s", type(e).__name__)

    def _discord(self, nom_alerte: str, info: dict, details: str) -> None:
        embed = {
            "title": info["titre"][:250],
            "url": info["url"],
            "description": f"**{info['prix']}**" + (f"\n{details}" if details else ""),
            "footer": {"text": f"Alerte : {nom_alerte}"},
        }
        if info["vendeur"]:
            embed["author"] = {"name": info["vendeur"]}
        if info["photo"]:
            embed["image"] = {"url": info["photo"]}
        try:
            r = requests.post(self.discord, json={"embeds": [embed]}, timeout=20)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 2)))
                r = requests.post(self.discord, json={"embeds": [embed]}, timeout=20)
            if not r.ok:
                log.error("Discord a refusé le message : %s", r.text[:300])
        except requests.RequestException as e:
            log.error("Envoi Discord impossible : %s", type(e).__name__)


# --------------------------------------------------------------------------- #
# Mémoire des articles déjà vus
# --------------------------------------------------------------------------- #

def charger_etat(chemin: Path) -> dict[str, list[int]]:
    if chemin.exists():
        try:
            return json.loads(chemin.read_text())
        except json.JSONDecodeError:
            log.warning("%s illisible, on repart de zéro.", chemin)
    return {}


def sauver_etat(chemin: Path, etat: dict[str, list[int]]) -> None:
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(etat))
    tmp.replace(chemin)


# --------------------------------------------------------------------------- #
# Boucle principale
# --------------------------------------------------------------------------- #

def verifier_alerte(
    client: ClientVinted, notifieur: Notifieur, alerte: dict, etat: dict
) -> int:
    """Interroge Vinted pour une alerte ; renvoie le nombre de notifications envoyées."""
    nom = alerte["nom"]
    articles = client.rechercher(alerte)
    premiere_fois = nom not in etat
    vus = etat.setdefault(nom, [])
    deja_vus = set(vus)

    # Du plus ancien au plus récent, pour notifier dans l'ordre de mise en ligne.
    nouveaux = [a for a in reversed(articles) if a.get("id") not in deja_vus]
    vus.extend(a["id"] for a in nouveaux if a.get("id") is not None)
    del vus[:-MAX_IDS_MEMORISES]

    if premiere_fois:
        # Au premier passage on mémorise l'existant sans notifier,
        # sinon on recevrait 40 alertes d'un coup pour de vieilles annonces.
        log.info("[%s] initialisation : %d articles existants ignorés.", nom, len(nouveaux))
        return 0

    envoyes = 0
    for article in nouveaux:
        if correspond(article, alerte):
            notifieur.envoyer(nom, infos_article(article, client.base))
            envoyes += 1
    return envoyes


def tour(client, notifieur, alertes, etat, chemin_etat) -> None:
    for alerte in alertes:
        try:
            verifier_alerte(client, notifieur, alerte, etat)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            log.error("[%s] Vinted a répondu HTTP %s.", alerte["nom"], code)
            if code in (403, 429):
                log.error("Vinted limite ou bloque les requêtes : augmente intervalle_secondes.")
        except (requests.RequestException, ValueError) as e:
            log.error("[%s] erreur : %s: %s", alerte["nom"], type(e).__name__, e)
        time.sleep(random.uniform(1, 3))  # petite pause entre deux alertes
    sauver_etat(chemin_etat, etat)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot d'alertes Vinted")
    parser.add_argument("-c", "--config", default="config.toml", help="fichier de configuration")
    parser.add_argument("--once", action="store_true", help="une seule vérification puis quitte")
    parser.add_argument("--test-notif", action="store_true", help="envoie une notification de test")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%d/%m %H:%M:%S"
    )

    chemin_config = Path(args.config)
    config = charger_config(chemin_config)
    general = config.get("general", {})
    notifieur = Notifieur(config)

    if args.test_notif:
        notifieur.envoyer(
            "Test",
            {
                "titre": "Notification de test",
                "prix": "0.00 EUR",
                "marque": "",
                "taille": "",
                "etat": "",
                "vendeur": "",
                "url": "https://www.vinted.fr",
                "photo": None,
            },
        )
        return

    client = ClientVinted(general.get("domaine", "www.vinted.fr"))
    intervalle = max(15, int(general.get("intervalle_secondes", 60)))
    chemin_etat = chemin_config.resolve().parent / general.get("fichier_etat", "articles_vus.json")
    etat = charger_etat(chemin_etat)
    alertes = config["alertes"]

    log.info("%d alerte(s) : %s", len(alertes), ", ".join(a["nom"] for a in alertes))
    try:
        while True:
            tour(client, notifieur, alertes, etat, chemin_etat)
            if args.once:
                break
            time.sleep(intervalle + random.uniform(0, intervalle * 0.2))
    except KeyboardInterrupt:
        log.info("Arrêt.")


if __name__ == "__main__":
    main()
