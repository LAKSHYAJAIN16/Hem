"""Parse supplied public/authorized RSS or Atom exports. Does not fetch arbitrary URLs."""
import re
import hashlib
import os
import httpx
from html import unescape
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET


def parse_feed(xml, source_url):
    raw = xml.encode() if isinstance(xml, str) else xml
    if len(raw) > 2_000_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Feed too large or unsupported XML declarations')
    root = ET.fromstring(raw)
    atom = '{http://www.w3.org/2005/Atom}'
    entries = root.findall('./channel/item') if root.tag == 'rss' else root.findall(atom + 'entry')
    documents = []
    for entry in entries[:100]:
        def value(tag):
            return entry.findtext(tag) or entry.findtext(atom + tag) or ''
        link = value('link')
        if not link:
            node = next((n for n in entry.findall(atom + 'link') if n.get('rel', 'alternate') == 'alternate'), None)
            link = node.get('href', '') if node is not None else ''
        url = urljoin(source_url, link)
        if not link or urlparse(url).scheme not in {'http', 'https'}:
            continue
        summary = value('description') or value('summary') or value('content')
        documents.append({'id': value('guid') or value('id') or url,
                          'title': value('title').strip(), 'url': url, 'source_url': source_url,
                          'published_at': value('pubDate') or value('published') or value('updated'),
                          'summary': unescape(re.sub(r'<[^>]+>', ' ', summary)).strip()[:2000]})
    return documents


def import_feed(store, user_id, xml, source_url):
    parsed = urlparse(source_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use the original HTTPS feed URL for provenance.')
    documents = parse_feed(xml, source_url)
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO users(id) VALUES(?)', (user_id,))
        for document in documents:
            document_id = hashlib.sha256(document['url'].encode()).hexdigest()[:20]
            db.execute('''INSERT INTO source_documents(id,user_id,title,url,source_url,published_at,summary)
                          VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET
                          title=excluded.title,source_url=excluded.source_url,published_at=excluded.published_at,
                          summary=excluded.summary,imported_at=CURRENT_TIMESTAMP''',
                       (document_id, user_id, document['title'][:300], document['url'], source_url,
                        document['published_at'][:100], document['summary']))
    return len(documents)


def retrieve(db, user_id, query, limit=5):
    # Local lexical retrieval is transparent and does not require an embedding service.
    stopwords = {'what', 'should', 'wear', 'with', 'that', 'this', 'have', 'from', 'today', 'outfit', 'please'}
    tokens = set(re.findall(r'[a-z]{3,}', query.lower())) - stopwords
    rows = [dict(r) for r in db.execute('SELECT * FROM source_documents WHERE user_id=? ORDER BY imported_at DESC LIMIT 500', (user_id,))]
    def score(row):
        title = set(re.findall(r'[a-z]{3,}', row['title'].lower()))
        body = set(re.findall(r'[a-z]{3,}', row['summary'].lower()))
        return 3 * len(tokens & title) + len(tokens & body)
    return sorted((row for row in rows if score(row)), key=score, reverse=True)[:limit]


async def fetch_feed(url, transport=None):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    hosts = {h.strip().lower() for h in os.getenv('HEM_SOURCE_HOSTS', '').split(',') if h.strip()}
    allowed = host.endswith('.substack.com') or host in hosts
    if parsed.scheme != 'https' or not allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use an HTTPS Substack feed URL, or configure the publisher in HEM_SOURCE_HOSTS.')
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport) as client:
        async with client.stream('GET', url) as response:
            if response.is_redirect:
                raise ValueError('Use the final feed URL; redirects are not followed.')
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 2_000_000:
                    raise ValueError('Feed exceeds 2 MB.')
    return bytes(body)
