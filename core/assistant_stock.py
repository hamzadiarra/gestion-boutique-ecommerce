"""Read-only availability answers using the public catalog and current stock."""
import re

STOCK_WORDS = {'stock', 'stocks', 'disponible', 'disponibles', 'disponibilite', 'availability', 'available', 'rupture', 'epuise', 'epuisee', 'restant', 'restants', 'reste', 'restent'}
STOCK_FILLER = STOCK_WORDS | {'in', 'out', 'of', 'still', 'left', 'many', 'much', 'how', 'there', 'are', 'any', 'remaining', 'sold', 'combien', 'encore', 'reste', 'restent', 'en', 'on', 'a', 't', 'il', 'elle', 'ils', 'elles', 'one', 'ones', 'its', 'ceux', 'celle', 'celui', 'ces', 'cette', 'cettes', 'categorie', 'category', 'dans', 'rayon', 'ce', 'cet', 'tell', 'please', 'est', 'sont', 'aussi', 'modele', 'model'}
VARIANT_WORDS = {'taille', 'tailles', 'pointure', 'pointures', 'size', 'sizes', 'couleur', 'couleurs', 'color', 'colour', 'colors', 'colours', 'rouge', 'rouges', 'bleu', 'bleue', 'bleues', 'bleus', 'noir', 'noire', 'noirs', 'noires', 'blanc', 'blanche', 'blancs', 'blanches', 'vert', 'verte', 'jaune', 'rose', 'red', 'blue', 'black', 'white', 'green', 'yellow', 'pink', 'xl', 'xxl', 'xs'}


def is_stock_question(question):
    words = set(question.split())
    # Preserve the established broad catalog-discovery greeting.
    if question in {'what is available', 'quels produits disponibles'}:
        return False
    return bool(words & STOCK_WORDS or re.search(r'\b(?:avez vous|vous avez|do you have)\b', question) or {'many', 'left'} <= words or {'many', 'remaining'} <= words or re.search(r'how many (?:are )?(?:left|remaining)|sold out', question))


def stock_answer(message, language, state, context):
    from django.db import DatabaseError
    try:
        return _stock_answer(message, language, state, context)
    except DatabaseError:
        return {'intent': 'STOCK_PRODUIT', 'score': 20, 'availability': 'unknown',
                'answer': ('Je ne peux pas vérifier le stock actuellement. Réessayez plus tard.' if language == 'fr' else 'I cannot verify stock right now. Please try again later.'),
                'actions': [], 'state': {}}


def _stock_answer(message, language, state, context):
    from .assistant import (INTENTS, ORDINALS, ORDINAL_WORDS, _category_for_terms,
                            _is_continuation, _ordinal_position, _page_product, _product_ids, _public_products,
                            _retain_search_context, _search_catalog, _search_terms,
                            _serialize_product, normalize_question, tokenize)
    from categories.models import Category
    from django.urls import resolve, Resolver404

    french = language == 'fr'
    result = {'intent': 'STOCK_PRODUIT', 'score': 20, 'availability': 'unknown',
              'answer': INTENTS['STOCK_PRODUIT'][language], 'actions': [], 'state': {}}
    ids = _product_ids(state)
    words = set(tokenize(message))
    def keep(step='SELECT_PRODUCT', selected=None):
        next_state = {'intent': 'STOCK_PRODUIT', 'step': step, 'product_ids': ids}
        if selected is not None:
            next_state['selected_product_id'] = selected
        result['state'] = _retain_search_context(next_state, state)

    if words & VARIANT_WORDS or re.search(r'\b(?:en|in) (?:s|m|l|\d{2})\b', normalize_question(message)):
        result['answer'] = ('Je ne peux pas vérifier le stock par taille ou couleur. Consultez la fiche produit ou contactez la boutique.' if french else 'I cannot verify stock by size or color. Check the product page or contact the shop.')
        keep(selected=state.get('selected_product_id') if state.get('selected_product_id') in ids else None)
        return result

    def missing():
        result['availability'] = 'not_found'
        result['answer'] = ('Je ne trouve pas ce produit dans le catalogue public. Précisez son nom ou relancez la recherche.' if french else 'I cannot find that product in the public catalog. Give its name or search again.')
        return result

    if re.search(r"\b(?:avez vous|vous avez|do you have) \d+\b", normalize_question(message)):
        result['answer'] = ('Précisez le produit pour vérifier une quantité demandée. Je ne peux pas confirmer cette quantité.' if french else 'Please identify the product to check a requested quantity. I cannot confirm that quantity.')
        keep()
        return result
    position = _ordinal_position(message)
    product = None
    terms = [] if _is_continuation(message) else [term for term in _search_terms(message) if term not in STOCK_FILLER | {word for word in ORDINAL_WORDS if not word.isdigit()}]
    if position is not None:
        product = _public_products().filter(pk=ids[position]).first() if position < len(ids) else None
        if product is None:
            return missing()
    else:
        category_id, remaining = _category_for_terms(terms) if terms else (None, [])
        category_reference = bool(words & {'categorie', 'category', 'rayon'})
        if not terms and (category_reference or not ids):
            category_id = state.get('category_id')
            if isinstance(context, str) and context.startswith('/') and not context.startswith('//') and len(context) <= 300:
                try:
                    route = resolve(context)
                    if route.url_name == 'category_detail':
                        category_reference = True
                        category_id = Category.objects.filter(active=True, slug=route.kwargs.get('slug')).values_list('pk', flat=True).first()
                except Resolver404:
                    pass
        if category_id and not remaining and (terms or category_reference):
            if type(category_id) is not int or not Category.objects.filter(pk=category_id, active=True).exists():
                return missing()
            available = _public_products().filter(categorie_id=category_id, stock__gt=0)
            count = available.count()
            result.update(available_count=count, category_id=category_id, availability='available' if count else 'out_of_stock')
            result['answer'] = (f'{count} produit(s) en stock dans cette catégorie.' if french else f'{count} product(s) in stock in this category.')
            products = list(available.order_by('nom', 'pk')[:5])
            result['results'] = [_serialize_product(item, language) for item in products]
            result['state'] = {'intent': 'STOCK_PRODUIT', 'step': 'CONTINUE', 'category_id': category_id, 'search_query': '', 'product_ids': [item.pk for item in products]}
            return result
        if terms:
            queryset = _public_products()
            if category_id:
                queryset = queryset.filter(categorie_id=category_id)
            products = list(_search_catalog(queryset, remaining if category_id else terms).order_by('nom', 'pk')[:5])
            if not products:
                return missing()
            if len(products) == 1:
                product = products[0]
            else:
                ids = [item.pk for item in products]
                result['results'] = [_serialize_product(item, language) for item in products]
        else:
            product = _page_product(context)
            selected = state.get('selected_product_id')
            if product is not None:
                pass
            elif type(selected) is int and selected in ids:
                product = _public_products().filter(pk=selected).first()
                if product is None:
                    return missing()
            elif len(ids) == 1:
                product = _public_products().filter(pk=ids[0]).first()
                if product is None:
                    return missing()
            elif not ids:
                product = _page_product(context)
    if product is None:
        result['availability'] = 'ambiguous' if len(ids) > 1 else 'unknown'
        if len(ids) > 1:
            result['answer'] = ('Plusieurs produits correspondent. Lequel souhaitez-vous vérifier ? Précisez son nom ou sa position.' if french else 'Several products match. Which one should I check? Give its name or position.')
        keep()
        return result
    item = _serialize_product(product, language)
    result['availability'] = 'available' if item['available'] else 'out_of_stock'
    result['results'] = [item]
    result['answer'] = ((f"{item['name']} : disponible, {product.stock} en stock." if item['available'] else f"{item['name']} : en rupture de stock.") if french else (f"{item['name']}: available, {product.stock} in stock." if item['available'] else f"{item['name']}: out of stock."))
    result['actions'] = [{'label': 'Voir le produit' if french else 'View product', 'url': item['url']}]
    ids = ids if product.pk in ids else [product.pk]
    keep('CONTINUE', product.pk)
    return result
