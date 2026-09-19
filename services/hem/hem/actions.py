"""Prepare care and purchase requests. Approval never books, pays, or sends."""
import json
import re

from hem.stylist import short_id


def create_request(db, user, kind, item_ids, brief):
    for item_id in item_ids:
        if not db.execute('SELECT id FROM garments WHERE id=? AND user_id=?', (item_id, user)).fetchone():
            raise ValueError('A selected garment is not in your wardrobe.')
    existing = db.execute("SELECT id FROM action_requests WHERE user_id=? AND kind=? AND item_ids=? AND brief=? AND status IN ('draft','approved')",
                          (user, kind, json.dumps(sorted(item_ids)), brief)).fetchone()
    if existing:
        return existing['id']
    request_id = short_id()
    db.execute('INSERT INTO action_requests(id,user_id,kind,item_ids,brief) VALUES(?,?,?,?,?)',
               (request_id, user, kind, json.dumps(sorted(item_ids)), brief))
    return request_id


def prepare_due_care(db, user):
    due = db.execute('SELECT g.id,g.description,c.method FROM garments g JOIN care_rules c ON c.garment_id=g.id '
                     'WHERE g.user_id=? AND c.wears_since_clean>=c.every_wears', (user,)).fetchall()
    active = set()
    for row in db.execute("SELECT item_ids FROM action_requests WHERE user_id=? AND status IN ('draft','approved') AND kind IN ('laundry','dryclean')", (user,)):
        active.update(json.loads(row['item_ids']))
    prepared = []
    for kind in ('laundry', 'dryclean'):
        items = [r for r in due if r['method'] == kind and r['id'] not in active]
        if items:
            brief = 'Care due by your saved wear-count rule: ' + ', '.join(r['description'] for r in items)
            request_id = create_request(db, user, kind, [r['id'] for r in items], brief)
            prepared.append(f"Prepared {kind} request {request_id}. Review with 'requests'; approve with 'approve request {request_id}'.")
    return '\n'.join(prepared)


def record_care_wear(db, user, outfit_id):
    outfit = db.execute('SELECT item_ids FROM outfits WHERE id=? AND user_id=?', (outfit_id, user)).fetchone()
    if outfit:
        for item_id in json.loads(outfit['item_ids']):
            db.execute('UPDATE care_rules SET wears_since_clean=wears_since_clean+1 WHERE garment_id=?', (item_id,))
    return prepare_due_care(db, user)


def handle_action(db, user, text):
    lower = text.lower().strip()
    care = re.fullmatch(r'care ([a-f0-9]{10}): (laundry|dryclean) every (\d+) wears?', lower)
    if care:
        if not 1 <= int(care[3]) <= 100:
            return 'Choose a cleaning interval between 1 and 100 wears.'
        if not db.execute('SELECT id FROM garments WHERE id=? AND user_id=?', (care[1], user)).fetchone():
            return 'That item is not in your wardrobe.'
        db.execute('INSERT INTO care_rules(garment_id,method,every_wears) VALUES(?,?,?) '
                   'ON CONFLICT(garment_id) DO UPDATE SET method=excluded.method,every_wears=excluded.every_wears',
                   (care[1], care[2], int(care[3])))
        return 'Care rule saved. Confirm the method against the garment label. Requests will be prepared after confirmed wears reach your interval.'
    if lower.startswith('care '):
        return 'Use care <item ID>: laundry every 3 wears, or care <item ID>: dryclean every 5 wears.'
    if lower == 'requests':
        rows = db.execute('SELECT * FROM action_requests WHERE user_id=? ORDER BY rowid DESC LIMIT 20', (user,)).fetchall()
        return '\n'.join(f"{r['id']} · {r['kind']} · {r['status']}\n{r['brief']}" for r in rows) or 'No prepared requests yet.'
    transition = re.fullmatch(r'(approve|cancel|complete) request ([a-f0-9]{10})', lower)
    if transition:
        action, request_id = transition.groups()
        row = db.execute('SELECT * FROM action_requests WHERE id=? AND user_id=?', (request_id, user)).fetchone()
        if not row:
            return 'That request is not yours.'
        if row['status'] in {'completed', 'cancelled'}:
            return 'That request is already closed.'
        if action == 'complete' and row['status'] != 'approved':
            return 'Approve the request first. Mark it complete only after the real-world task is done.'
        status = {'approve': 'approved', 'cancel': 'cancelled', 'complete': 'completed'}[action]
        db.execute('UPDATE action_requests SET status=? WHERE id=? AND user_id=?', (status, request_id, user))
        if action == 'complete' and row['kind'] in {'laundry', 'dryclean'}:
            for item_id in json.loads(row['item_ids']):
                db.execute('UPDATE garments SET available=1 WHERE id=? AND user_id=?', (item_id, user))
                db.execute('UPDATE care_rules SET wears_since_clean=0 WHERE garment_id=?', (item_id,))
        if action == 'approve':
            return 'Request approved and ready to arrange. No booking, purchase, payment or provider message has been made.'
        return 'Request cancelled.' if action == 'cancel' else 'Marked complete based on your confirmation.'
    order = re.fullmatch(r'(?:auto[- ]order|order request):?\s+(.{2,1000})', text, re.I)
    if order:
        brief = order[1].strip() + '\nBefore ordering: confirm product link, size, total price, delivery address and payment method.'
        request_id = create_request(db, user, 'order', [], brief)
        return f"Prepared order request {request_id}: {brief}\nReview with 'requests', then 'approve request {request_id}'. Nothing purchased."
    if lower in {'auto-order', 'auto order'}:
        return 'Describe what to source: auto order: waterproof boots, size 9, budget CAD 150. I will prepare a request for approval.'
    if lower in {'auto laundry', 'auto-laundry', 'auto drycleaner', 'auto-drycleaner', 'auto dryclean', 'auto dry-cleaning'}:
        kind = 'laundry' if 'laundry' in lower else 'dryclean'
        rows = db.execute('SELECT g.id,g.description FROM garments g JOIN care_rules c ON c.garment_id=g.id '
                          'WHERE g.user_id=? AND c.method=? AND (g.available=0 OR c.wears_since_clean>=c.every_wears)', (user, kind)).fetchall()
        if not rows:
            return f'No items are due under a saved {kind} rule. Set care <item ID>: {kind} every 3 wears using the care label.'
        brief = 'Prepare pickup for: ' + ', '.join(r['description'] for r in rows) + '. Confirm provider, quote, pickup address and time before booking.'
        request_id = create_request(db, user, kind, [r['id'] for r in rows], brief)
        return f"Prepared {kind} request {request_id}. Review with 'requests', then 'approve request {request_id}'. No booking made."
    return None
