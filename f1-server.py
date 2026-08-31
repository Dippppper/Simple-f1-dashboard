#!/usr/bin/env python3
"""F1 Dashboard Backend — route /api/current to auto-detect current race."""
import http.server
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlparse

PORT = 5500
DIR = os.path.dirname(os.path.abspath(__file__))

SEASON_2026 = [
    {"round":"1","event":"Australian Grand Prix","circuit":"Albert Park","location":"Melbourne","country":"Australia","date":"2026-03-08","format":"conventional"},
    {"round":"2","event":"Chinese Grand Prix","circuit":"Shanghai","location":"Shanghai","country":"China","date":"2026-03-15","format":"sprint_qualifying"},
    {"round":"3","event":"Japanese Grand Prix","circuit":"Suzuka","location":"Suzuka","country":"Japan","date":"2026-03-29","format":"conventional"},
    {"round":"4","event":"Miami Grand Prix","circuit":"Miami","location":"Miami Gardens","country":"USA","date":"2026-05-03","format":"sprint_qualifying"},
    {"round":"5","event":"Canadian Grand Prix","circuit":"Montreal","location":"Montreal","country":"Canada","date":"2026-05-24","format":"sprint_qualifying"},
    {"round":"6","event":"Monaco Grand Prix","circuit":"Monaco","location":"Monte Carlo","country":"Monaco","date":"2026-06-07","format":"conventional"},
    {"round":"7","event":"Barcelona Grand Prix","circuit":"Barcelona","location":"Barcelona","country":"Spain","date":"2026-06-14","format":"conventional"},
    {"round":"8","event":"Austrian Grand Prix","circuit":"Red Bull Ring","location":"Spielberg","country":"Austria","date":"2026-06-28","format":"conventional"},
    {"round":"9","event":"British Grand Prix","circuit":"Silverstone","location":"Silverstone","country":"UK","date":"2026-07-05","format":"sprint_qualifying"},
    {"round":"10","event":"Belgian Grand Prix","circuit":"Spa-Francorchamps","location":"Spa","country":"Belgium","date":"2026-07-19","format":"conventional"},
    {"round":"11","event":"Hungarian Grand Prix","circuit":"Hungaroring","location":"Budapest","country":"Hungary","date":"2026-07-26","format":"conventional"},
    {"round":"12","event":"Dutch Grand Prix","circuit":"Zandvoort","location":"Zandvoort","country":"Netherlands","date":"2026-08-23","format":"sprint_qualifying"},
    {"round":"13","event":"Italian Grand Prix","circuit":"Monza","location":"Monza","country":"Italy","date":"2026-09-06","format":"conventional"},
    {"round":"14","event":"Spanish Grand Prix","circuit":"Madrid","location":"Madrid","country":"Spain","date":"2026-09-13","format":"conventional"},
    {"round":"15","event":"Azerbaijan Grand Prix","circuit":"Baku","location":"Baku","country":"Azerbaijan","date":"2026-09-26","format":"conventional"},
    {"round":"16","event":"Singapore Grand Prix","circuit":"Marina Bay","location":"Singapore","country":"Singapore","date":"2026-10-11","format":"sprint_qualifying"},
    {"round":"17","event":"US Grand Prix","circuit":"COTA","location":"Austin","country":"USA","date":"2026-10-25","format":"conventional"},
    {"round":"18","event":"Mexico City Grand Prix","circuit":"Mexico City","location":"Mexico City","country":"Mexico","date":"2026-11-01","format":"conventional"},
    {"round":"19","event":"Sao Paulo Grand Prix","circuit":"Interlagos","location":"Sao Paulo","country":"Brazil","date":"2026-11-08","format":"conventional"},
    {"round":"20","event":"Las Vegas Grand Prix","circuit":"Las Vegas","location":"Las Vegas","country":"USA","date":"2026-11-21","format":"conventional"},
    {"round":"21","event":"Qatar Grand Prix","circuit":"Lusail","location":"Lusail","country":"Qatar","date":"2026-11-29","format":"conventional"},
    {"round":"22","event":"Abu Dhabi Grand Prix","circuit":"Yas Marina","location":"Abu Dhabi","country":"UAE","date":"2026-12-06","format":"conventional"}
]

# Parse every race date once at startup instead of re-parsing per request.
_SEASON_DATES = [(datetime.strptime(ev['date'], '%Y-%m-%d'), ev) for ev in SEASON_2026]

PROVIDERS = {
    'deepseek': ('https://api.deepseek.com/v1/chat/completions', 'deepseek-chat'),
    'moonshot': ('https://api.moonshot.cn/v1/chat/completions', 'moonshot-v1-8k'),
    'kimi':     ('https://api.moonshot.cn/v1/chat/completions', 'moonshot-v1-8k'),
}

def find_current():
    now = datetime.now()
    for ed, ev in _SEASON_DATES:
        if ed - timedelta(days=3) <= now <= ed + timedelta(days=1):
            return ev
    for ed, ev in _SEASON_DATES:
        if now < ed:
            return ev
    return SEASON_2026[-1]

def _sess(name, label, when):
    return {"name": name, "date": when.strftime('%Y-%m-%dT%H:%M:%SZ'), "label": label, "day": when.strftime('%b %d')}

def _race(rd):
    # Race time stays hardcoded +02:00 — timezone fix deliberately deferred.
    return {"name": "Race", "date": rd.strftime('%Y-%m-%dT15:00:00+02:00'), "label": "Race", "day": rd.strftime('%b %d')}

def build_sessions(ev):
    rd = datetime.strptime(ev['date'], '%Y-%m-%d')
    d = lambda days: rd + timedelta(days=days)
    if ev['format'] == 'sprint_qualifying':
        return {
            "fp1": _sess("Practice 1", "FP1", d(-2)),
            "sq": _sess("Sprint Qualifying", "SQ", d(-2)),
            "sprint": _sess("Sprint", "Sprint", d(-1)),
            "qualifying": _sess("Qualifying", "Qualifying", d(-1)),
            "race": _race(rd)
        }
    return {
        "fp1": _sess("Practice 1", "FP1", d(-2)),
        "fp2": _sess("Practice 2", "FP2", d(-2)),
        "fp3": _sess("Practice 3", "FP3", d(-1)),
        "qualifying": _sess("Qualifying", "Qualifying", d(-1)),
        "race": _race(rd)
    }

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_GET(self):
        if urlparse(self.path).path == '/api/current':
            ev = find_current()
            # Copy instead of mutating SEASON_2026 — keeps `season` clean and
            # thread-safe now that the server handles requests concurrently.
            current = {**ev, 'sessions': build_sessions(ev)}
            stored = None
            data_file = os.path.join(DIR, 'data.json')
            if os.path.exists(data_file):
                try:
                    with open(data_file, 'r', encoding='utf-8') as f:
                        stored = json.load(f)
                except (OSError, ValueError):
                    stored = None
            resp = {
                'currentEvent': current,
                'hasData': stored is not None and stored.get('event',{}).get('round')==ev['round'],
                'lastUpdated': stored.get('lastUpdated') if stored else None,
                'season': SEASON_2026
            }
            body = json.dumps(resp, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Access-Control-Allow-Origin','*')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != '/api/ai-predict':
            self.send_json({'error': 'not found'}, 404)
            return
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_len))
        except (ValueError, json.JSONDecodeError):
            self.send_json({'error': 'invalid JSON body'}, 400)
            return
        provider = body.get('provider', 'deepseek')
        if provider not in PROVIDERS:
            self.send_json({'error': f'unknown provider: {provider}'}, 400)
            return
        api_key = body.get('apiKey', '')
        if not api_key:
            self.send_json({'error': 'No API key provided'}, 400)
            return
        event_info = body.get('eventInfo', {})
        url, model = PROVIDERS[provider]

        prompt = self.build_prediction_prompt(event_info)
        req_body = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'You are an F1 data analyst. Output ONLY valid JSON, no markdown, no explanation.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 2000
        }).encode('utf-8')

        try:
            req = urllib.request.Request(url, data=req_body, headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + api_key
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            content = result['choices'][0]['message']['content'].strip()
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace').strip()
            try:
                detail = json.loads(detail).get('error', {}).get('message', detail)
            except ValueError:
                pass
            self.send_json({'error': f'provider API error ({e.code}): {detail}'}, 502)
            return
        except urllib.error.URLError as e:
            self.send_json({'error': f'cannot reach provider: {e.reason}'}, 502)
            return
        except (KeyError, IndexError, ValueError) as e:
            self.send_json({'error': f'unexpected provider response: {e}'}, 502)
            return

        # Strip code fences / stray prose around the JSON payload.
        content = re.sub(r'^```(?:json)?\s*\n?', '', content)
        content = re.sub(r'\n?```\s*$', '', content)
        m = re.search(r'\{[\s\S]*\}', content)
        if m:
            content = m.group(0)
        try:
            prediction = json.loads(content)
        except json.JSONDecodeError:
            self.send_json({'error': 'AI returned invalid JSON: ' + content[:160]}, 502)
            return
        self.send_json({'success': True, 'prediction': prediction})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def build_prediction_prompt(self, info):
        return f"""Analyze the following F1 2026 season data and provide predictions as JSON:

Current Standings (Top 10):
{json.dumps(info.get('standings', []), indent=2)}

Most Recent Qualifying Results:
{json.dumps(info.get('qualifying', []), indent=2)}

Next Race: {info.get('nextRace', '')}

Return ONLY this JSON structure (no other text):
{{
    "podium": [
        {{"name": "Driver Name", "team": "Team Name", "prob": 75}},
        {{"name": "Driver Name", "team": "Team Name", "prob": 55}},
        {{"name": "Driver Name", "team": "Team Name", "prob": 40}}
    ],
    "wdc": [
        {{"name": "Driver Name", "team": "Team Name", "prob": 60, "reason": "Chinese reason (20+ chars)"}},
        {{"name": "Driver Name", "team": "Team Name", "prob": 20, "reason": "Chinese reason (20+ chars)"}},
        {{"name": "Driver Name", "team": "Team Name", "prob": 15, "reason": "Chinese reason (20+ chars)"}},
        {{"name": "Driver Name", "team": "Team Name", "prob": 5, "reason": "Chinese reason (20+ chars)"}}
    ],
    "stars": [
        {{"name": "Driver Name", "team": "Team Name", "reason": "Brief reason in Chinese (15 chars)", "confidence": "高"}},
        {{"name": "Driver Name", "team": "Team Name", "reason": "Brief reason", "confidence": "高"}},
        {{"name": "Driver Name", "team": "Team Name", "reason": "Brief reason", "confidence": "中"}}
    ]
}}"""

if __name__ == '__main__':
    ev = find_current()
    print(f"F1 Dashboard: {ev['event']} (R{ev['round']}) port {PORT}")
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"http://127.0.0.1:{PORT}/f1-dashboard.html")
        httpd.serve_forever()
