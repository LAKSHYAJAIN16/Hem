import json

import httpx
import pytest

from hem.retrieval import VectorIndex
from hem.sources import parse_feed


def test_vector_scope_and_dimensions():
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'result': {'points': []}})
    index = VectorIndex('https://example.test', 'fashion', 2, transport=httpx.MockTransport(handle))
    try:
        a = index.upsert('alice', 'shirt', 'navy shirt', [0.2, 0.8])
        b = index.upsert('bob', 'shirt', 'cream shirt', [0.8, 0.2])
        assert a != b
        assert index.search('alice', [0.2, 0.8]) == []
        assert requests[-1]['filter']['must'][0]['match']['value'] == 'alice'
        with pytest.raises(ValueError):
            index.search('alice', [1])
        with pytest.raises(ValueError):
            index.search('', [0.2, 0.8])
    finally:
        index.close()


def test_feed_provenance_and_unsafe_links():
    result = parse_feed('<rss><channel><item><title>Layering</title><link>/p/layers</link>'
                        '<description>&lt;b&gt;Try linen&lt;/b&gt;</description></item>'
                        '<item><link>javascript:alert(1)</link></item></channel></rss>', 'https://fashion.example/feed')
    assert len(result) == 1
    assert result[0]['url'] == 'https://fashion.example/p/layers'
    assert result[0]['summary'] == 'Try linen'
    with pytest.raises(ValueError):
        parse_feed('<!DOCTYPE rss><rss/>', 'https://example.test')


def test_atom_feed():
    rows = parse_feed('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Texture</title>'
                      '<link href="https://fashion.example/texture"/><summary>Mix textures</summary>'
                      '</entry></feed>', 'https://fashion.example/feed')
    assert rows[0]['title'] == 'Texture'
