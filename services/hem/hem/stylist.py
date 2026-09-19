"""Deterministic first slice. Never claims that unconfigured AI has understood an image."""
import itertools
import json
import re
import uuid
from datetime import date, timedelta


CATEGORIES = {'top', 'bottom', 'shoes', 'dress', 'outerwear', 'accessory'}
HELP = (
    "I'm Hem. Start with clothes you actually own:\n"
    "add top: cream cotton sweater\nadd bottom: navy straight-leg trousers\n"
    "add shoes: white sneakers\n\n"
    "Then ask: What should I wear today?\n"
    "Tell me: I like navy / I dislike orange.\n"
    "Say 'wore it' only after wearing a suggestion.\n"
    "Other commands: wardrobe, history, preferences, laundry <item ID>, clean <item ID>, forget <preference>."
)


def short_id():
    return uuid.uuid4().hex[:10]


def recommend(db, user_id, occasion, today, weather=None, inspiration=None):
    items = [dict(r) for r in db.execute('SELECT * FROM garments WHERE user_id=? AND available=1 ORDER BY rowid', (user_id,))]
    groups = {category: [i for i in items if i['category'] == category] for category in CATEGORIES}
    # Bound combination work; this starter is meant for small personal wardrobes.
    candidates = list(itertools.islice(itertools.product(groups['top'], groups['bottom'], groups['shoes']), 2000))
    candidates += list(itertools.islice(itertools.product(groups['dress'], groups['shoes']), 1000))
    if not candidates:
        return "I need an available top, bottom and pair of shoes—or a dress and shoes. Add them with 'add top: ...'. Use 'clean <ID>' for items back from laundry."
    preferences = list(db.execute('SELECT value,sentiment FROM preferences WHERE user_id=?', (user_id,)))
    recently_worn = {}
    for row in db.execute('SELECT o.item_ids,w.worn_on FROM wears w JOIN outfits o ON o.id=w.outfit_id WHERE w.user_id=?', (user_id,)):
        age = (today - date.fromisoformat(row['worn_on'])).days
        if 0 <= age <= 3:
            for item_id in json.loads(row['item_ids']):
                recently_worn[item_id] = max(recently_worn.get(item_id, 0), 4 - age)
    def score(outfit):
        text = ' '.join(i['description'].lower() for i in outfit)
        taste = sum((3 if p['sentiment'] == 'like' else -8) for p in preferences if p['value'] in text)
        if inspiration:
            for item in outfit:
                words = set(re.findall(r'[a-z]{3,}', item['description'].lower()))
                references = [r for r in inspiration if r['category'] == item['category']]
                taste += 4 * max((len(words & set(re.findall(r'[a-z]{3,}', r['description'].lower()))) for r in references), default=0)
        return taste + context_score(outfit, occasion, weather) - sum(recently_worn.get(i['id'], 0) * 5 for i in outfit)
    outfit = max(candidates, key=score)
    if weather and weather['feels_like_low_c'] < 15 and groups['outerwear']:
        outfit = (*outfit, max(groups['outerwear'], key=lambda item: context_score([item], occasion, weather)))
    outfit_id = short_id()
    db.execute('INSERT INTO outfits(id,user_id,item_ids,occasion) VALUES(?,?,?,?)',
               (outfit_id, user_id, json.dumps([i['id'] for i in outfit]), occasion))
    repeats = any(i['id'] in recently_worn for i in outfit)
    explanation = "Some pieces repeat because of your available wardrobe." if repeats else "None of these pieces were logged as worn in the last three days."
    return "Try " + ', '.join(i['description'] for i in outfit) + f".\n{explanation}\nOutfit {outfit_id}. Say 'wore it' after you wear it."


def context_score(outfit, occasion, weather):
    description = ' '.join(i['description'].lower() for i in outfit)
    formal = any(word in occasion.lower() for word in ('wedding', 'formal', 'interview', 'office', 'business'))
    athletic = any(word in occasion.lower() for word in ('gym', 'workout', 'running', 'hike'))
    score = 0
    if formal:
        score += 5 * sum(word in description for word in ('blazer', 'trousers', 'oxford', 'loafers', 'dress shirt', 'suit'))
        score -= 6 * sum(word in description for word in ('hoodie', 'shorts', 'sweatpants', 'flip flop'))
    if athletic:
        score += 5 * sum(word in description for word in ('running', 'athletic', 'sneakers', 'leggings', 'shorts'))
    if weather:
        if weather['feels_like_low_c'] < 12:
            score += 4 * sum(word in description for word in ('sweater', 'wool', 'coat', 'boots', 'jacket'))
            score -= 6 * sum(word in description for word in ('shorts', 'sandals', 'tank'))
        if weather['high_c'] > 25:
            score += 4 * sum(word in description for word in ('linen', 'lightweight', 'shorts', 'tee'))
            score -= 6 * sum(word in description for word in ('wool', 'heavy', 'fleece'))
        if weather['rain_chance'] >= 50:
            score += 5 * sum(word in description for word in ('waterproof', 'raincoat', 'boots'))
            score -= 5 * sum(word in description for word in ('suede', 'sandals'))
    return score


def respond(db, user_id, text, today=None):
    today = today or date.today()
    db.execute('INSERT OR IGNORE INTO users(id) VALUES(?)', (user_id,))
    text = text.strip()
    lower = text.lower()
    if lower in {'help', 'hello', 'hi', 'start'}:
        return HELP
    if lower.startswith('add '):
        match = re.fullmatch(r'add\s+(\w+)\s*:\s*(.{2,200})', text, re.I)
        if not match or match[1].lower() not in CATEGORIES:
            return 'Use add <category>: <description>. Categories: ' + ', '.join(sorted(CATEGORIES))
        category, description = match[1].lower(), match[2].strip()
        existing = db.execute('SELECT id FROM garments WHERE user_id=? AND category=? AND lower(description)=lower(?)', (user_id, category, description)).fetchone()
        if existing:
            return f"You already added that item ({existing['id']})."
        item_id = short_id()
        db.execute('INSERT INTO garments(id,user_id,category,description) VALUES(?,?,?,?)', (item_id, user_id, category, description))
        return f"Added {description} to your wardrobe. Item {item_id}."
    preference = re.fullmatch(r'(?:i\s+)?(like|love|dislike|hate)\s+(.{1,120})', lower)
    if preference:
        sentiment = 'like' if preference[1] in {'like', 'love'} else 'dislike'
        value = preference[2].rstrip('.!')
        db.execute('INSERT INTO preferences VALUES(?,?,?) ON CONFLICT(user_id,value) DO UPDATE SET sentiment=excluded.sentiment', (user_id, value, sentiment))
        return f"I'll remember that you {sentiment} {value}. Say 'forget {value}' to remove this preference."
    if lower.startswith('forget '):
        value = lower[7:].strip()
        db.execute('DELETE FROM preferences WHERE user_id=? AND value=?', (user_id, value))
        return f"Removed the preference '{value}'."
    if lower == 'preferences':
        rows = list(db.execute('SELECT value,sentiment FROM preferences WHERE user_id=?', (user_id,)))
        return '\n'.join(f"You {r['sentiment']} {r['value']}." for r in rows) or "I haven't saved any preferences yet."
    if lower == 'wardrobe':
        rows = list(db.execute('SELECT * FROM garments WHERE user_id=? ORDER BY rowid', (user_id,)))
        return '\n'.join(f"{r['id']} · {r['description']}" + ('' if r['available'] else ' [in laundry]') for r in rows) or "Your wardrobe is empty. Try 'add top: cream sweater'."
    laundry = re.fullmatch(r'(laundry|clean)\s+([a-f0-9]{10})', lower)
    if laundry:
        cursor = db.execute('UPDATE garments SET available=? WHERE id=? AND user_id=?', (laundry[1] == 'clean', laundry[2], user_id))
        return 'Wardrobe availability updated.' if cursor.rowcount else "That item isn't in your wardrobe."
    if lower in {'wore it', 'i wore it'} or lower.startswith('wore '):
        if lower in {'wore it', 'i wore it'}:
            row = db.execute('SELECT id FROM outfits WHERE user_id=? ORDER BY rowid DESC LIMIT 1', (user_id,)).fetchone()
        else:
            row = db.execute('SELECT id FROM outfits WHERE user_id=? AND id=?', (user_id, lower[5:].strip())).fetchone()
        if not row:
            return "Ask me for an outfit first, or use 'wore <outfit ID>' for an earlier suggestion."
        cursor = db.execute('INSERT OR IGNORE INTO wears VALUES(?,?,?)', (user_id, row['id'], today.isoformat()))
        return "Logged for today. I'll account for this next time." if cursor.rowcount else 'Already logged for today—no duplicate entry.'
    if lower == 'history' or 'what did i wear' in lower:
        rows = list(db.execute('SELECT w.worn_on,o.item_ids FROM wears w JOIN outfits o ON o.id=w.outfit_id WHERE w.user_id=? ORDER BY w.worn_on DESC LIMIT 10', (user_id,)))
        result = []
        for row in rows:
            names = [db.execute('SELECT description FROM garments WHERE id=? AND user_id=?', (i, user_id)).fetchone()['description'] for i in json.loads(row['item_ids'])]
            result.append(row['worn_on'] + ': ' + ', '.join(names))
        return '\n'.join(result) or "No outfits logged yet. Suggestions only become history when you say 'wore it'."
    if 'what should i wear' in lower or 'pick an outfit' in lower or lower == 'outfit':
        return recommend(db, user_id, text, today)
    return "I can help with your wardrobe, preferences and outfit history. Say 'help' for the current commands. Free-form styling and photo understanding are next."


def chat(store, user_id, text, today=None):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        return respond(db, user_id, text, today)
