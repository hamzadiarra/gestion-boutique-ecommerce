"""Safely update selected English PO entries without text replacement heuristics."""

from __future__ import annotations

import ast
import re
from pathlib import Path


PO_PATH = Path("locale/en/LC_MESSAGES/django.po")

TRANSLATIONS = {
    "Votre sélection, simplement.": "Your selection, made simple.",
    "La sélection du moment": "Featured selection",
    "Des essentiels choisis pour votre quotidien.": "Essentials selected for your everyday life.",
    "Découvrez des produits utiles, élégants et soigneusement sélectionnés pour rendre chaque achat plus simple.": "Discover useful, elegant and carefully selected products to make every purchase simpler.",
    "Découvrir les produits": "Discover products",
    "Voir les catégories": "View categories",
    "Suivie jusqu'à chez vous": "Tracked to your door",
    "Un achat en toute confiance": "Shop with confidence",
    "Une équipe à votre écoute": "A team here to help",
    "Produit vedette": "Featured product",
    "Sélection de vêtements de la boutique": "Shop clothing selection",
    "Tout ce qu'il faut pour trouver rapidement votre prochain coup de cœur.": "Everything you need to quickly find your next favourite.",
    "Les dernières pièces ajoutées à la boutique.": "The latest items added to the shop.",
    "Offres sélectionnées": "Selected offers",
    "Les bons produits, au bon moment.": "The right products at the right time.",
    "Profitez des prix promotionnels disponibles actuellement.": "Enjoy the promotional prices currently available.",
    "Voir les offres": "View offers",
    "Les produits qui trouvent déjà leur place chez nos clients.": "Products already finding their place with our customers.",
    "La sélection Gestion Boutique": "The Gestion Boutique selection",
    "Des produits choisis avec exigence.": "Products selected with care.",
    "Explorez notre sélection vedette et trouvez ce qui vous correspond vraiment.": "Explore our featured selection and find what suits you best.",
    "Découvrir toute la boutique": "Discover the entire shop",
    "Simple.": "Simple.",
    "Utile.": "Useful.",
    "À vous.": "Yours.",
    "Les engagements de la boutique": "Our shop commitments",
    "Choisis avec exigence": "Carefully selected",
    "Des offres qui ont du sens": "Offers that make sense",
    "Une commande suivie": "Order tracking",
    "Un parcours rassurant": "A reassuring journey",
    "Gestion Boutique, accueil": "Shop Management, home",
    "Une expérience d'achat plus simple.": "A simpler shopping experience.",
    "Une sélection pensée pour vos envies, avec un service clair du premier clic au suivi de votre commande.": "A selection designed around your needs, with clear service from the first click to order tracking.",
    "Tous les produits": "All products",
    "Compte": "Account",
    "Besoin d'aide ?": "Need help?",
    "Notre équipe est disponible pour vous accompagner.": "Our team is here to help.",
    "Écrire sur WhatsApp": "Contact us on WhatsApp",
    "Une boutique pensée pour vous.": "A shop designed for you.",
    "Changer de thème": "Change theme",
}


def po_value(block: str, field: str) -> str | None:
    match = re.search(rf"(?m)^{field} (?P<value>\".*\")(?:\r?$|\n)", block)
    if not match:
        return None
    return ast.literal_eval(match.group("value"))


def update_block(block: str) -> tuple[str, bool]:
    msgid = po_value(block, "msgid")
    if msgid not in TRANSLATIONS or po_value(block, "msgstr") != "":
        return block, False
    english = TRANSLATIONS[msgid]
    updated, count = re.subn(
        r'(?m)^msgstr ""(?:\r?\n(?=")[^\r\n]*)*',
        f'msgstr {english!r}'.replace("'", '"'),
        block,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Unable to update msgstr for {msgid!r}")
    return updated, True


def main() -> None:
    source = PO_PATH.read_text(encoding="utf-8")
    blocks = re.split(r"(\r?\n\s*\r?\n)", source)
    changed = 0
    for index in range(0, len(blocks), 2):
        blocks[index], did_change = update_block(blocks[index])
        changed += did_change
    PO_PATH.write_text("".join(blocks), encoding="utf-8")
    print(f"updated={changed}")


if __name__ == "__main__":
    main()
