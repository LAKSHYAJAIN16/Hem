"""Explicit location and dated Open-Meteo forecasts; no guessed user location."""
import math
from datetime import datetime, timezone

import httpx


class Weather:
    def __init__(self, transport=None):
        self.transport = transport

    async def locate(self, name):
        async with httpx.AsyncClient(timeout=10, transport=self.transport) as client:
            response = await client.get('https://geocoding-api.open-meteo.com/v1/search',
                                        params={'name': name, 'count': 5, 'language': 'en', 'format': 'json'})
            response.raise_for_status()
        return [{'latitude': r['latitude'], 'longitude': r['longitude'],
                 'label': ', '.join(filter(None, [r['name'], r.get('admin1'), r.get('country')]))}
                for r in response.json().get('results', [])]

    async def forecast(self, latitude, longitude, day=None):
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError('Invalid coordinates')
        params = {'latitude': latitude, 'longitude': longitude, 'timezone': 'auto',
                  'daily': 'temperature_2m_min,temperature_2m_max,apparent_temperature_min,precipitation_probability_max',
                  'forecast_days': 2}
        if day:
            params.update(start_date=day, end_date=day)
            params.pop('forecast_days')
        async with httpx.AsyncClient(timeout=10, transport=self.transport) as client:
            response = await client.get('https://api.open-meteo.com/v1/forecast', params=params)
            response.raise_for_status()
        data = response.json()
        daily = data['daily']
        index = 0
        result = {'date': daily['time'][index], 'low_c': daily['temperature_2m_min'][index],
                  'high_c': daily['temperature_2m_max'][index],
                  'feels_like_low_c': daily['apparent_temperature_min'][index],
                  'rain_chance': daily['precipitation_probability_max'][index],
                  'timezone': data['timezone'], 'source_url': 'https://open-meteo.com/',
                  'retrieved_at': datetime.now(timezone.utc).isoformat()}
        if any(not isinstance(result[k], (int, float)) or not math.isfinite(result[k])
               for k in ('low_c', 'high_c', 'feels_like_low_c', 'rain_chance')):
            raise ValueError('Forecast values unavailable')
        return result
