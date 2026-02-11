import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.api import app

client = TestClient(app)

r1 = client.get('/stats/quality?limit_hours=24')
r2 = client.get('/events/recent?limit=5')
r3 = client.get('/stats/summary')

print('V3_STATUS quality=', r1.status_code, 'recent=', r2.status_code, 'summary=', r3.status_code)
print('V3_COUNTS event_quality=', len(r1.json().get('event_quality', [])), 'skip_reasons=', len(r1.json().get('skip_reasons', [])))
print('V3_COUNTS recent_items=', len(r2.json().get('items', [])), 'messages=', r3.json().get('messages'), 'events=', r3.json().get('events'))
