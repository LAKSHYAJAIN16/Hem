"""Parse supplied public/authorized RSS or Atom exports. Does not fetch arbitrary URLs."""
import re
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
