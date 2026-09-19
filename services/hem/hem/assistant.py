"""Shared chat orchestration for messaging, CLI, and authenticated development clients."""
import asyncio
import json
import re
import os
from datetime import date, timedelta
from xml.etree.ElementTree import ParseError

import httpx

from hem.ai import AI, AIUnavailable
from hem.actions import handle_action, record_care_wear
from hem.media import load_image
from hem.sources import retrieve, fetch_feed, import_feed
from hem.stylist import recommend, respond, short_id
from hem.weather import Weather
from hem.conversation import context as conversation_context, quick_intent, apply_simple


def is_command(text):
    lower = text.lower().strip()
    return (lower in {'help', 'hello', 'hi', 'start', 'wardrobe', 'preferences', 'history', 'wore it', 'i wore it'}
            or re.fullmatch(r'add\s+\w+\s*:.+', lower) is not None
            or lower.startswith(('forget ', 'laundry ', 'clean ', 'wore '))
            or 'what did i wear' in lower
            or re.fullmatch(r'(?:i\s+)?(?:like|love|dislike|hate)\s+.{1,120}', lower) is not None)


class Assistant:
    def __init__(self, store, ai=None, weather=None):
        self.store = store
        self.ai = ai if ai is not None else AI()
        self.weather = weather if weather is not None else Weather()
        self.locks = [asyncio.Lock() for _ in range(64)]

    def finish(self, db, user, text, reply, request_id, focus=None):
        db.execute('INSERT INTO conversations(user_id,role,content) VALUES(?,?,?)', (user, 'user', text[:4000]))
        db.execute('INSERT INTO conversations(user_id,role,content) VALUES(?,?,?)', (user, 'assistant', reply))
        # Keep a bounded recent conversation, separate from factual wardrobe/wear memory.
        db.execute('DELETE FROM conversations WHERE user_id=? AND id NOT IN '
                   '(SELECT id FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT 40)', (user, user))
        if request_id:
            db.execute('INSERT INTO receipts(id,user_id,reply) VALUES(?,?,?)', (request_id, user, reply))
        db.execute('DELETE FROM dialogue_focus WHERE user_id=?', (user,))
        if focus:
            db.execute('INSERT INTO dialogue_focus(user_id,kind,target_id) VALUES(?,?,?)', (user, *focus))
        return reply

    async def reply(self, user, text, images=(), request_id=None, occasion='', on_date=None, photo_mode='auto'):
        async with self.locks[hash(user) % len(self.locks)]:
            with self.store.connect() as db:
                if request_id:
                    receipt = db.execute('SELECT reply FROM receipts WHERE id=? AND user_id=?', (request_id, user)).fetchone()
                    if receipt:
                        return receipt['reply']
                db.execute('INSERT OR IGNORE INTO users(id) VALUES(?)', (user,))
            inspiration_mode = photo_mode == 'inspiration' or (photo_mode == 'auto' and re.search(
                r'\b(match|recreate|inspiration|inspo|someone|their outfit|like this|this look|dress like)\b', text, re.I))
            if images and inspiration_mode:
                return await self.inspiration_photo(user, text, images, request_id, occasion, on_date)
            if not images and not self.legacy_syntax(text):
                with self.store.connect() as db:
                    ctx = conversation_context(db, user, text)
                plan = None
                if self.ai.configured and hasattr(self.ai, 'interpret'):
                    try:
                        plan = await self.ai.interpret(ctx)
                    except AIUnavailable:
                        pass
                plan = plan or quick_intent(ctx)
                if plan and plan.action != 'chat':
                    return await self.conversational_action(user, text, plan, ctx, request_id, occasion, on_date)
            return await self._reply(user, text.strip(), images, request_id, occasion, on_date)

    @staticmethod
    def legacy_syntax(text):
        lower = text.strip().lower()
        return (lower in {'help', 'hello', 'hi', 'start', 'outfit', 'history', 'preferences', 'wore it', 'i wore it', 'sources', 'photos', 'requests', 'location'}
                or re.match(r'^(?:add \w+\s*:|(?:confirm|discard|edit|style|match) photo [a-f0-9]{10}|'
                            r'(?:laundry|clean|wore|care) [a-f0-9]{10}|(?:approve|cancel|complete) request [a-f0-9]{10}|'
                            r'location |source |auto[- ]|order request:|forget )', lower) is not None)

    async def conversational_action(self, user, text, plan, ctx, request_id, occasion, on_date):
        if plan.action == 'location':
            return await self.location(user, 'location ' + plan.value, request_id)
        if plan.action == 'wear':
            return await self._reply(user, 'wore it', (), request_id, occasion, on_date)
        if plan.action in {'confirm_photo', 'edit_photo', 'discard_photo', 'style_photo'}:
            photo = ctx['pending_photo']
            if photo and plan.action == 'style_photo':
                return await self._reply(user, 'style photo ' + photo['id'], (), request_id, occasion, on_date)
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if not photo:
                    return self.finish(db, user, text, 'Send me the photo you mean, and I’ll take a look.', request_id)
                if plan.action == 'edit_photo':
                    if len(plan.garments) != 1 or len(plan.photo_indices) != 1 or not 0 <= plan.photo_indices[0] < len(photo['garments']):
                        return self.finish(db, user, text, 'Which piece should I correct? Describe its color or where it is in the photo.', request_id, ('photo', photo['id']))
                    garment = plan.garments[0]
                    self.photo_command(db, user, f"edit photo {photo['id']} {plan.photo_indices[0] + 1} {garment.category}: {garment.description}")
                    reply = f"Got it — {garment.description}. Shall I add the clothes from this photo to your wardrobe?"
                    return self.finish(db, user, text, reply, request_id, ('photo', photo['id']))
                if plan.action == 'confirm_photo':
                    indices = plan.photo_indices or list(range(len(photo['garments'])))
                    if any(i < 0 or i >= len(photo['garments']) for i in indices):
                        return self.finish(db, user, text, 'Which pieces should I add? Describe them by color or name.', request_id, ('photo', photo['id']))
                    self.photo_command(db, user, f"confirm photo {photo['id']} " + ','.join(str(i + 1) for i in indices))
                    reply = 'Added ' + ', '.join(photo['garments'][i]['description'] for i in sorted(set(indices))) + ' to your wardrobe. What are you dressing for?'
                else:
                    self.photo_command(db, user, 'discard photo ' + photo['id'])
                    reply = 'Okay, I won’t add those clothes.'
                return self.finish(db, user, text, reply, request_id)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                reply = apply_simple(db, user, plan)
            except ValueError:
                reply = 'Which piece do you mean? Describe it or send a photo so I can get it right.'
            focus = ('photo', ctx['pending_photo']['id']) if plan.action == 'clarify' and ctx['pending_photo'] else None
            return self.finish(db, user, text, reply or 'Tell me a little more about what you’d like to do.', request_id, focus)

    async def _reply(self, user, text, images, request_id, occasion, on_date, inspiration=None):
        lower = text.lower()
        if images:
            return await self.photo(user, text, images, request_id)
        match_photo = re.fullmatch(r'(?:style|match) photo ([a-f0-9]{10})', lower)
        if match_photo:
            with self.store.connect() as db:
                draft = db.execute('SELECT garments FROM photo_drafts WHERE id=? AND user_id=? AND status!=?',
                                   (match_photo[1], user, 'discarded')).fetchone()
                if not draft:
                    return self.finish(db, user, text, 'That photo is not available in your drafts.', request_id)
            return await self._reply(user, 'Recreate the look in my reference photo using my own wardrobe.',
                                     (), request_id, occasion, on_date, json.loads(draft['garments']))
        if lower.startswith(('confirm photo ', 'discard photo ', 'edit photo ')) or lower == 'photos':
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                reply = self.photo_command(db, user, text)
                match = re.match(r'edit photo ([a-f0-9]{10})', lower)
                focus = ('photo', match[1]) if match else None
                return self.finish(db, user, text, reply, request_id, focus)
        if lower.startswith('location ') or lower == 'location':
            return await self.location(user, text, request_id)
        if lower.startswith('source '):
            try:
                url = text[7:].strip()
                xml = await fetch_feed(url)
                count = import_feed(self.store, user, xml, url)
                reply = f'Imported {count} inspiration entries with source links. Ask how to adapt a look to your wardrobe.'
            except (ValueError, ParseError, httpx.HTTPError):
                reply = 'Could not import that feed. Use source https://publication.substack.com/feed or an authorized RSS/Atom export.'
            with self.store.connect() as db:
                return self.finish(db, user, text, reply, request_id)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            action_reply = handle_action(db, user, text)
            if action_reply is not None:
                return self.finish(db, user, text, action_reply, request_id)
        if is_command(text):
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                before = db.execute('SELECT count(*) FROM wears WHERE user_id=?', (user,)).fetchone()[0]
                reply = respond(db, user, text)
                after = db.execute('SELECT count(*) FROM wears WHERE user_id=?', (user,)).fetchone()[0]
                if after > before:
                    worn = db.execute('SELECT outfit_id FROM wears WHERE user_id=? ORDER BY rowid DESC LIMIT 1', (user,)).fetchone()
                    care_note = record_care_wear(db, user, worn['outfit_id'])
                    if care_note:
                        reply += '\n' + care_note
                clean = re.fullmatch(r'clean ([a-f0-9]{10})', lower)
                if clean:
                    db.execute('UPDATE care_rules SET wears_since_clean=0 WHERE garment_id IN '
                               '(SELECT id FROM garments WHERE id=? AND user_id=?)', (clean[1], user))
                if lower in {'help', 'hello', 'hi', 'start'}:
                    reply = ("Hey, I’m Hem. Send me a photo of your wardrobe or tell me about a few clothes you own — "
                             "I’ll figure out the pieces. You can also show me an outfit you like and I’ll help recreate it. "
                             "I’m using Toronto weather for now. What are you dressing for?")
                return self.finish(db, user, text, reply, request_id)
        if lower == 'sources':
            with self.store.connect() as db:
                rows = db.execute('SELECT title,url FROM source_documents WHERE user_id=? ORDER BY imported_at DESC LIMIT 10', (user,)).fetchall()
                reply = '\n'.join(f"{r['title']} — {r['url']}" for r in rows) or 'No inspiration sources imported yet. Import an authorized RSS or Atom feed through the local API.'
                return self.finish(db, user, text, reply, request_id)

        snapshot = self.store.snapshot(user)
        with self.store.connect() as db:
            profile = db.execute('SELECT * FROM profiles WHERE user_id=?', (user,)).fetchone()
            if not profile and not db.execute('SELECT user_id FROM weather_opt_out WHERE user_id=?', (user,)).fetchone():
                profile = {'latitude': float(os.getenv('HEM_DEFAULT_LATITUDE', '43.65')),
                           'longitude': float(os.getenv('HEM_DEFAULT_LONGITUDE', '-79.38')),
                           'label': os.getenv('HEM_DEFAULT_CITY', 'Toronto')}
            history = [dict(r) for r in db.execute('SELECT role,content FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT 12', (user,))][::-1]
            query = ' '.join([text, occasion] + [item['description'] for item in (inspiration or snapshot['wardrobe']) if item.get('available', True)])
            sources = retrieve(db, user, query)
        weather, weather_note = None, 'Tell me your city if you’d like weather-aware suggestions.'
        requested_day = on_date.isoformat() if on_date else None
        if not requested_day:
            explicit_date = re.search(r'\b\d{4}-\d{2}-\d{2}\b', text)
            if explicit_date:
                try:
                    requested_day = date.fromisoformat(explicit_date[0]).isoformat()
                except ValueError:
                    weather_note = 'That date is invalid; use YYYY-MM-DD.'
        if profile:
            try:
                weather = await self.weather.forecast(profile['latitude'], profile['longitude'], requested_day)
                if not requested_day and 'tomorrow' in lower:
                    requested_day = (date.fromisoformat(weather['date']) + timedelta(days=1)).isoformat()
                    weather = await self.weather.forecast(profile['latitude'], profile['longitude'], requested_day)
                weather_note = (f"{profile['label']}, {weather['date']}: {weather['low_c']:g}–{weather['high_c']:g}°C, "
                                f"feels as low as {weather['feels_like_low_c']:g}°C; rain chance {weather['rain_chance']:g}%. "
                                'Forecast: https://open-meteo.com/')
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                weather_note = 'Weather is unavailable for this request; no live forecast was used.'
        context = {'request': text, 'occasion': occasion or text, 'requested_date': requested_day,
                   'available_wardrobe': [i for i in snapshot['wardrobe'] if i['available']],
                   'garment_attributes': snapshot['details'], 'preferences': snapshot['preferences'],
                   'confirmed_wears': snapshot['wears'][:20], 'recent_outfits': snapshot['outfits'],
                   'conversation': history, 'weather': weather, 'inspiration_garments': inspiration or [],
                   'sources': [{k: s[k] for k in ('id', 'title', 'summary', 'published_at')} for s in sources]}
        ai_error = None
        if self.ai.configured:
            try:
                advice = await self.ai.advise(context)
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    reply = self.apply_advice(db, user, advice, sources, occasion or text)
                    if inspiration:
                        reply = 'Recreating the reference look with your wardrobe:\n' + reply
                    if weather:
                        reply += '\n\n' + weather_note
                    elif 'weather' in lower or 'wear' in lower or lower == 'outfit':
                        reply += '\n\n' + weather_note
                    return self.finish(db, user, text, reply, request_id)
            except (AIUnavailable, ValueError):
                ai_error = 'AI styling is temporarily unavailable; here is a rule-based suggestion.'
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            wants_outfit = bool(inspiration or occasion or any(word in lower for word in ('wear', 'outfit', 'style', 'wedding', 'office', 'gym', 'interview')))
            if wants_outfit:
                reply = recommend(db, user, occasion or text, date.today(), weather, inspiration)
                reply += '\n\n' + weather_note
                if ai_error:
                    reply = ai_error + '\n' + reply
                if sources:
                    reply += '\n\nRelated reading (not used to rank this outfit):\n' + '\n'.join(f"{s['title']} — {s['url']}" for s in sources[:3])
            else:
                reply = 'I’m having trouble thinking that through right now. Try again in a moment, or tell me about a piece you own.'
            return self.finish(db, user, text, reply, request_id)

    def apply_advice(self, db, user, advice, sources, occasion):
        source_map = {s['id']: s for s in sources}
        if any(source not in source_map for source in advice.source_ids):
            raise ValueError('Unretrieved source ID')
        if len(set(advice.item_ids)) != len(advice.item_ids):
            raise ValueError('Duplicate garment IDs')
        # URLs are generated from trusted stored provenance, never model output.
        if re.search(r'https?://|www\.', advice.answer, re.I):
            raise ValueError('Model-generated URL')
        items = []
        for item_id in advice.item_ids:
            item = db.execute('SELECT * FROM garments WHERE id=? AND user_id=? AND available=1', (item_id, user)).fetchone()
            if not item:
                raise ValueError('Unavailable or unowned garment')
            items.append(item)
        reply = advice.answer
        if items:
            categories = {i['category'] for i in items}
            if not ({'top', 'bottom', 'shoes'} <= categories or {'dress', 'shoes'} <= categories):
                raise ValueError('Incomplete outfit')
            outfit_id = short_id()
            db.execute('INSERT INTO outfits(id,user_id,item_ids,occasion) VALUES(?,?,?,?)',
                       (outfit_id, user, json.dumps(advice.item_ids), occasion))
            reply += '\n\nFrom your wardrobe: ' + ', '.join(i['description'] for i in items)
            reply += '.\nLet me know if you wear it, and I’ll remember for next time.'
        if advice.source_ids:
            reply += '\n\nSources:\n' + '\n'.join(
                f"{source_map[i]['title']} — {source_map[i]['url']}" +
                (f" ({source_map[i]['published_at']})" if source_map[i]['published_at'] else '')
                for i in dict.fromkeys(advice.source_ids))
        else:
            reply += '\n\nGeneral styling advice; no imported source cited.'
        return reply

    async def photo(self, user, text, images, request_id):
        draft_id = None
        try:
            if not self.ai.configured:
                raise AIUnavailable('I can’t analyze photos right now. You can still tell me about your clothes.')
            if len(images) > 2:
                raise ValueError('Send up to two photos at a time.')
            data = [await load_image(image) for image in images]
            result = await self.ai.describe(data, text)
            if not result.garments:
                reply = 'I could not identify a garment in these photos. Try a clear, well-lit photo of one item. ' + result.notes
            else:
                draft_id = short_id()
                reply = 'I can see ' + ', '.join(item.description for item in result.garments) + '. '
                reply += result.notes + '\nAre these yours? I can add them to your wardrobe, or use the photo as inspiration for a look.'
        except (AIUnavailable, ValueError, httpx.HTTPError) as exc:
            reply = str(exc) if isinstance(exc, (AIUnavailable, ValueError)) else 'Could not retrieve that photo. Try uploading a JPEG, PNG or WebP.'
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if draft_id:
                db.execute('INSERT INTO photo_drafts(id,user_id,garments) VALUES(?,?,?)',
                           (draft_id, user, json.dumps([g.model_dump() for g in result.garments])))
                for image in data:
                    db.execute('INSERT INTO photo_assets(id,user_id,draft_id,image) VALUES(?,?,?,?)', (short_id(), user, draft_id, image))
            return self.finish(db, user, text or '[garment photo]', reply, request_id, ('photo', draft_id) if draft_id else None)

    async def inspiration_photo(self, user, text, images, request_id, occasion, on_date):
        try:
            if not self.ai.configured:
                raise AIUnavailable('Photo styling needs the AI integration configured.')
            if len(images) > 2:
                raise ValueError('Send up to two inspiration photos at a time.')
            data = [await load_image(image) for image in images]
            result = await self.ai.describe(data, text)
            if not result.garments:
                raise ValueError('I could not see enough of the outfit. Try a clearer photo of the clothes you want to match.')
        except (AIUnavailable, ValueError, httpx.HTTPError) as exc:
            reply = str(exc) if isinstance(exc, (AIUnavailable, ValueError)) else 'Could not retrieve the inspiration photo.'
            with self.store.connect() as db:
                return self.finish(db, user, text or '[inspiration photo]', reply, request_id)
        inspiration = [g.model_dump() for g in result.garments]
        prompt = (text or 'Recreate this look with my clothes.') + '\nReference clothes: ' + ', '.join(g.description for g in result.garments)
        # Reference photos never create owned garments or photo-import drafts.
        return await self._reply(user, prompt, (), request_id, occasion, on_date, inspiration)

    def photo_command(self, db, user, text):
        if text.lower() == 'photos':
            rows = db.execute("SELECT id,garments FROM photo_drafts WHERE user_id=? AND status='pending'", (user,)).fetchall()
            return '\n'.join(f"{r['id']}: " + ', '.join(i['description'] for i in json.loads(r['garments'])) for r in rows) or 'No photos awaiting confirmation.'
        match = re.fullmatch(r'(confirm|discard|edit) photo ([a-f0-9]{10})(?: (.+))?', text, re.I)
        if not match:
            return 'Use confirm photo <ID>, discard photo <ID>, or edit photo <ID> <number> <category>: <description>.'
        action, draft_id, selection = match.groups()
        row = db.execute('SELECT * FROM photo_drafts WHERE id=? AND user_id=?', (draft_id.lower(), user)).fetchone()
        if not row:
            return 'That photo is not in your wardrobe drafts.'
        if row['status'] != 'pending':
            return 'That photo has already been confirmed or discarded.'
        items = json.loads(row['garments'])
        if action.lower() == 'edit':
            correction = re.fullmatch(r'(\d+) (top|bottom|shoes|dress|outerwear|accessory): (.{2,200})', selection or '', re.I)
            if not correction or not 1 <= int(correction[1]) <= len(items):
                return 'Use edit photo <ID> <number> <category>: <description>.'
            # A manual correction replaces uncertain model attributes too.
            items[int(correction[1]) - 1].update(category=correction[2].lower(), description=correction[3],
                colors=[], material='unknown', pattern='unknown', formality='unknown', warmth='unknown', confidence=1)
            db.execute('UPDATE photo_drafts SET garments=? WHERE id=? AND user_id=?', (json.dumps(items), row['id'], user))
            return f"Updated item {correction[1]}. Reply 'confirm photo {row['id']}' to save it."
        if action.lower() == 'discard':
            db.execute("UPDATE photo_drafts SET status='discarded' WHERE id=? AND user_id=?", (row['id'], user))
            db.execute('DELETE FROM photo_assets WHERE draft_id=? AND user_id=?', (row['id'], user))
            return 'Discarded the photo draft and its stored images.'
        try:
            indices = sorted(set(int(i.strip()) - 1 for i in selection.split(','))) if selection else list(range(len(items)))
            if not indices or any(i < 0 or i >= len(items) for i in indices):
                raise ValueError()
        except ValueError:
            return 'Choose valid item numbers, separated by commas.'
        assets = db.execute('SELECT id FROM photo_assets WHERE draft_id=? AND user_id=? ORDER BY rowid', (row['id'], user)).fetchall()
        # A multi-photo draft is not a reliable one-image-per-garment mapping.
        asset_id = assets[0]['id'] if len(assets) == 1 else None
        added = []
        for index in indices:
            item = items[index]
            duplicate = db.execute('SELECT id FROM garments WHERE user_id=? AND category=? AND lower(description)=lower(?)',
                                   (user, item['category'], item['description'])).fetchone()
            if duplicate:
                continue
            garment_id = short_id()
            db.execute('INSERT INTO garments(id,user_id,category,description) VALUES(?,?,?,?)',
                       (garment_id, user, item['category'], item['description']))
            db.execute('INSERT INTO garment_details(garment_id,attributes,asset_id) VALUES(?,?,?)',
                       (garment_id, json.dumps(item), asset_id))
            added.append(f"{item['description']} ({garment_id})")
        db.execute("UPDATE photo_drafts SET status='confirmed' WHERE id=? AND user_id=?", (row['id'], user))
        return ('Added ' + ', '.join(added) + '.') if added else 'Those garments are already in your wardrobe.'

    async def location(self, user, text, request_id):
        value = text[8:].strip()
        profile = None
        if value.lower() == 'clear':
            with self.store.connect() as db:
                db.execute('DELETE FROM profiles WHERE user_id=?', (user,))
                db.execute('INSERT OR IGNORE INTO weather_opt_out(user_id) VALUES(?)', (user,))
                return self.finish(db, user, text, 'Cleared your weather location.', request_id)
        coordinates = re.fullmatch(r'(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)(?:\s+(.{1,100}))?', value)
        try:
            if coordinates:
                lat, lon = float(coordinates[1]), float(coordinates[2])
                if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    raise ValueError()
                profile = {'latitude': lat, 'longitude': lon, 'label': coordinates[3] or f'{lat}, {lon}'}
            elif value.lower() == 'toronto':
                profile = {'latitude': 43.65, 'longitude': -79.38, 'label': 'Toronto'}
            elif value:
                candidates = await self.weather.locate(value[:100])
                if len(candidates) == 1:
                    profile = candidates[0]
                elif candidates:
                    reply = 'I found a few places with that name. Which do you mean?\n' + '\n'.join(c['label'] for c in candidates)
                else:
                    reply = 'No matching city found. Use location <latitude>,<longitude> <city label>.'
            else:
                with self.store.connect() as db:
                    row = db.execute('SELECT label FROM profiles WHERE user_id=?', (user,)).fetchone()
                reply = 'Weather location: ' + row['label'] if row else 'Set location <city> or location <latitude>,<longitude> <label>.'
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            reply = 'Could not resolve that location. Use location <latitude>,<longitude> <city label>.'
        with self.store.connect() as db:
            if profile:
                db.execute('DELETE FROM weather_opt_out WHERE user_id=?', (user,))
                db.execute('INSERT INTO profiles(user_id,latitude,longitude,label) VALUES(?,?,?,?) '
                           'ON CONFLICT(user_id) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,label=excluded.label',
                           (user, profile['latitude'], profile['longitude'], profile['label']))
                reply = 'Got it — I’ll use the forecast for ' + profile['label'] + '.'
            return self.finish(db, user, text, reply, request_id)
