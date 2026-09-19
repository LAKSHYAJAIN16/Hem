"""Qdrant adapter. Embeddings must come from one consistently configured model."""
import math
import uuid
from urllib.parse import quote

import httpx


class VectorIndex:
    def __init__(self, url, collection, dimensions, api_key='', transport=None):
        if dimensions < 1:
            raise ValueError('Positive embedding dimensions required')
        self.dimensions = dimensions
        self.path = '/collections/' + quote(collection, safe='')
        self.client = httpx.Client(base_url=url.rstrip('/'), timeout=15,
                                   headers={'api-key': api_key} if api_key else {}, transport=transport)

    def close(self):
        self.client.close()

    def validate(self, vector):
        if len(vector) != self.dimensions or any(not math.isfinite(x) for x in vector) or not any(vector):
            raise ValueError('Expected a finite, nonzero vector of configured dimensions')

    def create_collection(self):
        response = self.client.put(self.path, json={'vectors': {'size': self.dimensions, 'distance': 'Cosine'}})
        response.raise_for_status()

    def upsert(self, owner_id, document_id, text, vector, source_url=''):
        if not owner_id:
            raise ValueError('An owner scope is required')
        self.validate(vector)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, owner_id + ':' + document_id))
        response = self.client.put(self.path + '/points', params={'wait': 'true'}, json={'points': [{
            'id': point_id, 'vector': vector, 'payload': {'owner_id': owner_id, 'document_id': document_id,
                                                       'text': text, 'source_url': source_url}}]})
        response.raise_for_status()
        return point_id

    def search(self, owner_id, vector, limit=5):
        if not owner_id or not 1 <= limit <= 20:
            raise ValueError('Owner scope and limit between 1 and 20 required')
        self.validate(vector)
        response = self.client.post(self.path + '/points/query', json={
            'query': vector, 'limit': limit, 'with_payload': True,
            'filter': {'must': [{'key': 'owner_id', 'match': {'value': owner_id}}]}})
        response.raise_for_status()
        return response.json()['result']['points']
