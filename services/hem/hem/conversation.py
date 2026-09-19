"""Conversational intent resolution and validated state changes."""
import json
import re

from hem.ai import Intent, NamedGarment
from hem.stylist import respond

KINDS = (
    ('outerwear', r'\b(jacket|coat|blazer|parka|raincoat|windbreaker|puffer)\b'),
    ('dress', r'\b(dress|jumpsuit|romper|gown)\b'),
    ('shoes', r'\b(shoes?|sneakers?|boots?|sandals?|loafers?|heels?|trainers?|oxfords?)\b'),
    ('bottom', r'\b(jeans|pants|trousers|shorts|skirt|leggings|joggers|sweatpants)\b'),
    ('top', r'\b(shirt|t-shirt|tee|sweater|jumper|hoodie|blouse|top|tank|polo|cardigan|sweatshirt)\b'),
    ('accessory', r'\b(hat|cap|scarf|belt|tie|bag|watch|necklace|sunglasses|gloves)\b'),
)


def infer_garment(description):
    description = re.sub(r'^(?:a pair of|pair of|a|an|my|some)\s+', '', description.strip(), flags=re.I)
    if re.search(r'\bdress shirt\b', description, re.I):
        return NamedGarment(category='top', description=description)
    for category, pattern in KINDS:
        if re.search(pattern, description, re.I):
            return NamedGarment(category=category, description=description)
    return None


def intent(action, **values):
    return Intent(action=action, garments=values.get('garments', []), item_ids=values.get('item_ids', []),
                  photo_indices=values.get('photo_indices', []), value=values.get('value', ''),
                  sentiment=values.get('sentiment', 'none'), clarification=values.get('clarification', ''))


def context(db, user, text):
    focus = db.execute('SELECT * FROM dialogue_focus WHERE user_id=?', (user,)).fetchone()
    photo = None
    if focus and focus['kind'] == 'photo':
        row = db.execute("SELECT id,garments FROM photo_drafts WHERE id=? AND user_id=? AND status='pending'",
                         (focus['target_id'], user)).fetchone()
        if row:
            photo = {'id': row['id'], 'garments': json.loads(row['garments'])}
    return {'message': text, 'pending_photo': photo,
            'wardrobe': [dict(r) for r in db.execute('SELECT id,category,description,available FROM garments WHERE user_id=?', (user,))],
            'conversation': [dict(r) for r in db.execute('SELECT role,content FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT 8', (user,))][::-1]}


def quick_intent(ctx):
    """Handle clear everyday wording even during provider outages; ambiguity stays explicit."""
    text = ctx['message'].strip()
    lower = text.lower().strip(' .!')
    photo = ctx['pending_photo']
    if lower in {'yes', 'yep', 'yeah', 'yes please', 'sure', 'add them', 'add those', 'save them',
                 'yes add those', 'yes, add those', 'yes add them', 'yes, add them', 'those are mine',
                 'they are mine', "they're mine", 'add all of them', 'looks right'}:
        return intent('confirm_photo') if photo else intent('clarify', clarification='What would you like me to add?')
    if photo:
        if lower in {'no', 'no thanks', 'discard it', 'discard those', 'forget that photo', 'skip those'}:
            return intent('discard_photo')
        if re.search(r"\b(not mine|someone else|inspiration|match this|recreate|like this look|like their outfit)\b", lower):
            return intent('style_photo')
        only = re.fullmatch(r'(?:yes,? )?(?:add|save|keep)?\s*(?:just|only) (?:the )?(.+)', lower)
        if only:
            indices = match_names(only[1], photo['garments'])
            if len(indices) == 1:
                return intent('confirm_photo', photo_indices=indices)
            return intent('clarify', clarification='Which pieces should I keep? You can describe their colors or names.')
        correction = re.fullmatch(r"(?:actually[, ]+)?(?:that(?:'s| is)|it(?:'s| is)|the (first|second|third|fourth) (?:one )?is) (.+)", lower)
        if correction:
            ordinal = correction[1]
            index = ['first', 'second', 'third', 'fourth'].index(ordinal) if ordinal else 0
            garment = infer_garment(correction[2])
            if garment and (ordinal or len(photo['garments']) == 1) and index < len(photo['garments']):
                return intent('edit_photo', photo_indices=[index], garments=[garment])
    if lower in {'wardrobe', 'what clothes do i have', 'what do i own', "what's in my wardrobe", 'show me my clothes',
                 'show my wardrobe', 'what is in my wardrobe'}:
        return intent('wardrobe')
    ownership = re.fullmatch(r"(?:i (?:have|own|bought|got)|add|remember) (.+?)(?: to my wardrobe)?", text, re.I)
    if ownership and not re.search(r"\b(don't|do not|not|wish|want|would|could|maybe|if|should|might)\b|\?", ownership[1], re.I):
        descriptions = re.split(r'\s+and\s+|,\s*', ownership[1])
        garments = [infer_garment(d) for d in descriptions]
        if garments and len(garments) <= 12 and all(garments):
            return intent('add', garments=garments)
    availability = re.fullmatch(r"(?:my |the )?(.+?) (?:is|are) (?:in (?:the )?(?:wash|laundry)|dirty)", lower)
    clean = re.fullmatch(r"(?:my |the )?(.+?) (?:is|are) (?:clean|back from (?:the )?(?:wash|laundry|cleaners))", lower)
    if availability or clean:
        matches = match_names((availability or clean)[1], ctx['wardrobe'])
        if len(matches) == 1:
            return intent('laundry' if availability else 'clean', item_ids=[ctx['wardrobe'][matches[0]]['id']])
        return intent('clarify', clarification='Which item do you mean? Tell me its color or description.')
    if lower in {'i wore that', 'i wore that outfit', 'i wore those', 'i ended up wearing that', 'wore that today'}:
        return intent('wear')
    location = re.fullmatch(r"(?:i live in|i'm in|i am in|i'm based in|i am based in) (.{2,100})", text, re.I)
    if location:
        return intent('location', value=location[1])
    return None


def match_names(description, items):
    words = set(re.findall(r'[a-z]+', description.lower())) - {'the', 'one', 'my', 'a', 'an', 'pair', 'of'}
    return [index for index, item in enumerate(items)
            if words and words <= set(re.findall(r'[a-z]+', item['description'].lower()))]


def apply_simple(db, user, plan):
    if plan.action == 'add':
        if not plan.garments:
            raise ValueError('No garments specified')
        added = []
        for garment in plan.garments:
            respond(db, user, f'add {garment.category}: {garment.description}')
            added.append(garment.description)
        return 'Got it — I’ve saved ' + ', '.join(added) + ' in your wardrobe.'
    if plan.action == 'wardrobe':
        rows = db.execute('SELECT description,available FROM garments WHERE user_id=? ORDER BY rowid', (user,)).fetchall()
        return '\n'.join('• ' + r['description'] + ('' if r['available'] else ' (in the laundry)') for r in rows) or 'Send me a photo of your wardrobe, or tell me about a few pieces you own.'
    if plan.action in {'laundry', 'clean'}:
        if not plan.item_ids:
            raise ValueError('No garment selected')
        names = []
        for item_id in plan.item_ids:
            row = db.execute('SELECT description FROM garments WHERE id=? AND user_id=?', (item_id, user)).fetchone()
            if not row:
                raise ValueError('Unowned garment')
            names.append(row['description'])
        for item_id in plan.item_ids:
            db.execute('UPDATE garments SET available=? WHERE id=? AND user_id=?', (plan.action == 'clean', item_id, user))
            if plan.action == 'clean':
                db.execute('UPDATE care_rules SET wears_since_clean=0 WHERE garment_id=?', (item_id,))
        return ', '.join(names) + (' is ready to wear again.' if plan.action == 'clean' else ' is in the laundry. I’ll leave it out of outfit suggestions.')
    if plan.action == 'preference':
        if not plan.value or len(plan.value) > 120 or plan.sentiment not in {'like', 'dislike'}:
            raise ValueError('Invalid preference')
        return respond(db, user, f'I {plan.sentiment} {plan.value}')
    if plan.action == 'clarify':
        return plan.clarification or 'Which piece do you mean? A photo or a short description will help.'
    return None
