from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
import threading
import time
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('eurovision')

# ── 2026 Competing Countries ──────────────────────────────────────────────────
COUNTRIES_2026 = [
    {'name': 'Albania',        'flag': '🇦🇱'},
    {'name': 'Australia',      'flag': '🇦🇺'},
    {'name': 'Austria',        'flag': '🇦🇹'},
    {'name': 'Belgium',        'flag': '🇧🇪'},
    {'name': 'Bulgaria',       'flag': '🇧🇬'},
    {'name': 'Croatia',        'flag': '🇭🇷'},
    {'name': 'Cyprus',         'flag': '🇨🇾'},
    {'name': 'Czechia',        'flag': '🇨🇿'},
    {'name': 'Denmark',        'flag': '🇩🇰'},
    {'name': 'Finland',        'flag': '🇫🇮'},
    {'name': 'France',         'flag': '🇫🇷'},
    {'name': 'Germany',        'flag': '🇩🇪'},
    {'name': 'Greece',         'flag': '🇬🇷'},
    {'name': 'Israel',         'flag': '🇮🇱'},
    {'name': 'Italy',          'flag': '🇮🇹'},
    {'name': 'Lithuania',      'flag': '🇱🇹'},
    {'name': 'Malta',          'flag': '🇲🇹'},
    {'name': 'Moldova',        'flag': '🇲🇩'},
    {'name': 'Norway',         'flag': '🇳🇴'},
    {'name': 'Poland',         'flag': '🇵🇱'},
    {'name': 'Romania',        'flag': '🇷🇴'},
    {'name': 'Serbia',         'flag': '🇷🇸'},
    {'name': 'Sweden',         'flag': '🇸🇪'},
    {'name': 'Ukraine',        'flag': '🇺🇦'},
    {'name': 'United Kingdom', 'flag': '🇬🇧'},
]

# ── 2025 Test Data (Basel) ────────────────────────────────────────────────────
# 26 countries, 37 jury blocs (2,146 pts), 38 televote blocs (2,204 pts)
# Winner: Austria (JJ) — 258 jury + 178 televote = 436
# NOTE: Approximate figures for testing purposes.
COUNTRIES_2025 = [
    {'name': 'Albania',     'flag': '🇦🇱'}, {'name': 'Armenia',     'flag': '🇦🇲'},
    {'name': 'Australia',   'flag': '🇦🇺'}, {'name': 'Austria',     'flag': '🇦🇹'},
    {'name': 'Denmark',     'flag': '🇩🇰'}, {'name': 'Estonia',     'flag': '🇪🇪'},
    {'name': 'Finland',     'flag': '🇫🇮'}, {'name': 'France',      'flag': '🇫🇷'},
    {'name': 'Georgia',     'flag': '🇬🇪'}, {'name': 'Germany',     'flag': '🇩🇪'},
    {'name': 'Greece',      'flag': '🇬🇷'}, {'name': 'Iceland',     'flag': '🇮🇸'},
    {'name': 'Israel',      'flag': '🇮🇱'}, {'name': 'Italy',       'flag': '🇮🇹'},
    {'name': 'Latvia',      'flag': '🇱🇻'}, {'name': 'Lithuania',   'flag': '🇱🇹'},
    {'name': 'Luxembourg',  'flag': '🇱🇺'}, {'name': 'Malta',       'flag': '🇲🇹'},
    {'name': 'Netherlands', 'flag': '🇳🇱'}, {'name': 'Norway',      'flag': '🇳🇴'},
    {'name': 'Poland',      'flag': '🇵🇱'}, {'name': 'Serbia',      'flag': '🇷🇸'},
    {'name': 'Spain',       'flag': '🇪🇸'}, {'name': 'Sweden',      'flag': '🇸🇪'},
    {'name': 'Switzerland', 'flag': '🇨🇭'}, {'name': 'Ukraine',     'flag': '🇺🇦'},
]

JURY_2025 = {
    'Albania': 50,  'Armenia': 32,  'Australia': 156, 'Austria': 258,
    'Denmark': 29,  'Estonia': 54,  'Finland': 88,    'France': 194,
    'Georgia': 45,  'Germany': 13,  'Greece': 42,     'Iceland': 24,
    'Israel': 101,  'Italy': 112,   'Latvia': 37,     'Lithuania': 72,
    'Luxembourg': 50, 'Malta': 63,  'Netherlands': 21, 'Norway': 173,
    'Poland': 40,   'Serbia': 27,   'Spain': 19,      'Sweden': 233,
    'Switzerland': 124, 'Ukraine': 89,
}

TELEVOTE_2025 = {
    'Albania': 184, 'Armenia': 72,  'Australia': 44,  'Austria': 178,
    'Denmark': 24,  'Estonia': 54,  'Finland': 133,   'France': 42,
    'Georgia': 48,  'Germany': 8,   'Greece': 121,    'Iceland': 42,
    'Israel': 261,  'Italy': 32,    'Latvia': 38,     'Lithuania': 61,
    'Luxembourg': 12, 'Malta': 82,  'Netherlands': 22, 'Norway': 156,
    'Poland': 172,  'Serbia': 88,   'Spain': 10,      'Sweden': 56,
    'Switzerland': 36, 'Ukraine': 228,
}

# ── State ─────────────────────────────────────────────────────────────────────

def make_default_state():
    return {
        'phase': 'jury',
        'countries': [c.copy() for c in COUNTRIES_2026],
        'jury_scores': {},
        'televote_scores': {},
        'reveal_order': [],
        'current_reveal_index': 0,
        'total_jury_blocs': 35,
        'total_televote_blocs': 36,
        'total_jury_points': 2030,
        'total_televote_points': 2088,
        'test_mode': False,
        # Scraper state
        'scrape_status': 'idle',      # idle | scanning | found | failed
        'scrape_source': None,
        'scrape_last_attempt': None,
        'scrape_message': None,
        'scrape_count': 0,
    }

state = make_default_state()
state_lock = threading.Lock()


def compute_reveal_order():
    js = state['jury_scores']
    scored = sorted(state['countries'],
                    key=lambda c: (js.get(c['name'], 0), c['name']))
    state['reveal_order'] = [c['name'] for c in scored]


def compute_enriched_state():
    with state_lock:
        js = dict(state['jury_scores'])
        ts = dict(state['televote_scores'])
        countries = list(state['countries'])
        reveal_order = list(state['reveal_order'])
        total_tv_pts = state['total_televote_points']
        total_tv_blocs = state['total_televote_blocs']
        current_idx = state['current_reveal_index']
        snap = dict(state)   # shallow copy for metadata

    revealed_total = sum(ts.values())
    revealed_count = len(ts)
    total_count = len(countries)
    unrevealed_count = total_count - revealed_count
    remaining_pool = total_tv_pts - revealed_total

    best_total = 0
    best_country = None
    for name, tv in ts.items():
        combined = js.get(name, 0) + tv
        if combined > best_total:
            best_total = combined
            best_country = name

    trend_floor = 0
    if current_idx > 0 and reveal_order:
        last_name = reveal_order[current_idx - 1]
        trend_floor = ts.get(last_name, 0)

    flag_map = {c['name']: c['flag'] for c in countries}

    country_data = []
    for pos, name in enumerate(reveal_order):
        c_info = next((c for c in countries if c['name'] == name), None)
        if not c_info:
            continue

        jury = js.get(name, 0)
        tv = ts.get(name)
        is_revealed = tv is not None
        combined = jury + (tv if is_revealed else 0)
        max_possible = jury + total_tv_blocs * 12

        is_last_unrevealed = not is_revealed and unrevealed_count == 1
        guaranteed_tv = remaining_pool if is_last_unrevealed else None
        guaranteed_total = (jury + remaining_pool) if is_last_unrevealed else None
        is_guaranteed_winner = is_last_unrevealed and guaranteed_total > best_total

        needed_to_lead = max(0, best_total + 1 - jury) if not is_revealed else None
        can_reach_lead = ((max_possible - jury) >= needed_to_lead) if needed_to_lead is not None else None

        if is_revealed:
            if name == best_country:
                status = 'leading'
            elif combined < best_total:
                status = 'eliminated'
            else:
                status = 'confirmed'
        elif is_guaranteed_winner:
            status = 'guaranteed'
        elif max_possible < best_total:
            status = 'eliminated'
        else:
            status = 'pending'

        fair_share = round(remaining_pool / unrevealed_count) if (not is_revealed and unrevealed_count > 0) else None

        country_data.append({
            'name': name,
            'flag': c_info['flag'],
            'jury': jury,
            'tv': tv,
            'combined': combined,
            'max_possible': max_possible,
            'is_revealed': is_revealed,
            'status': status,
            'fair_share': fair_share,
            'trend_floor': trend_floor if not is_revealed else None,
            'needed_to_lead': needed_to_lead,
            'can_reach_lead': can_reach_lead,
            'guaranteed_tv': guaranteed_tv,
            'guaranteed_total': guaranteed_total,
            'is_guaranteed_winner': is_guaranteed_winner,
            'pos': pos,
            'is_next': pos == current_idx,
        })

    revealed_sorted = sorted([c for c in country_data if c['is_revealed']], key=lambda x: -x['combined'])
    unrevealed_sorted = sorted([c for c in country_data if not c['is_revealed']], key=lambda x: -x['max_possible'])

    return {
        'phase': snap['phase'],
        'countries': country_data,
        'leaderboard': revealed_sorted + unrevealed_sorted,
        'reveal_order': reveal_order,
        'current_reveal_index': current_idx,
        'revealed_count': revealed_count,
        'unrevealed_count': unrevealed_count,
        'total_count': total_count,
        'revealed_total': revealed_total,
        'remaining_pool': remaining_pool,
        'best_total': best_total,
        'best_country': best_country,
        'trend_floor': trend_floor,
        'jury_sum': sum(js.values()),
        'total_jury_blocs': snap['total_jury_blocs'],
        'total_televote_blocs': snap['total_televote_blocs'],
        'total_jury_points': snap['total_jury_points'],
        'total_televote_points': snap['total_televote_points'],
        'test_mode': snap['test_mode'],
        'is_complete': snap['phase'] == 'televote' and revealed_count == total_count,
        'country_flags': flag_map,
        'jury_scores_raw': js,
        # Scraper metadata
        'scrape_status': snap['scrape_status'],
        'scrape_source': snap['scrape_source'],
        'scrape_last_attempt': snap['scrape_last_attempt'],
        'scrape_message': snap['scrape_message'],
        'scrape_count': snap['scrape_count'],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/state')
def get_state():
    return jsonify(compute_enriched_state())


@app.route('/api/set-jury', methods=['POST'])
def set_jury():
    data = request.json
    raw = data.get('scores', {})
    with state_lock:
        for c in state['countries']:
            name = c['name']
            try:
                state['jury_scores'][name] = max(0, int(raw.get(name, 0) or 0))
            except (ValueError, TypeError):
                state['jury_scores'][name] = 0
        state['phase'] = 'televote'
        state['televote_scores'] = {}
        state['current_reveal_index'] = 0
        compute_reveal_order()
    return jsonify({'success': True})


@app.route('/api/reveal', methods=['POST'])
def reveal():
    data = request.json
    with state_lock:
        idx = state['current_reveal_index']
        if idx >= len(state['reveal_order']):
            return jsonify({'success': False, 'error': 'All countries already revealed'})
        name = state['reveal_order'][idx]
        try:
            score = max(0, int(data.get('score', 0) or 0))
        except (ValueError, TypeError):
            score = 0
        state['televote_scores'][name] = score
        state['current_reveal_index'] = idx + 1
    return jsonify({'success': True, 'country': name, 'score': score})


@app.route('/api/reset', methods=['POST'])
def reset():
    global state
    with state_lock:
        state = make_default_state()
    # Restart the scraper
    start_scraper()
    return jsonify({'success': True})


@app.route('/api/load-test-2025', methods=['POST'])
def load_test_2025():
    global state
    with state_lock:
        state = make_default_state()
        state.update({
            'phase': 'televote',
            'countries': [c.copy() for c in COUNTRIES_2025],
            'jury_scores': dict(JURY_2025),
            'televote_scores': {},
            'reveal_order': [],
            'total_jury_blocs': 37,
            'total_televote_blocs': 38,
            'total_jury_points': 2146,
            'total_televote_points': 2204,
            'test_mode': True,
            'scrape_status': 'idle',
        })
        compute_reveal_order()
    return jsonify({'success': True})


@app.route('/api/test-reveal-next', methods=['POST'])
def test_reveal_next():
    with state_lock:
        idx = state['current_reveal_index']
        if idx >= len(state['reveal_order']):
            return jsonify({'success': False, 'error': 'All countries revealed'})
        name = state['reveal_order'][idx]
        state['televote_scores'][name] = TELEVOTE_2025.get(name, 0)
        state['current_reveal_index'] = idx + 1
    return jsonify({'success': True, 'country': name})


@app.route('/api/test-reveal-all', methods=['POST'])
def test_reveal_all():
    with state_lock:
        for name in state['reveal_order'][state['current_reveal_index']:]:
            state['televote_scores'][name] = TELEVOTE_2025.get(name, 0)
        state['current_reveal_index'] = len(state['reveal_order'])
    return jsonify({'success': True})


@app.route('/api/scrape-now', methods=['POST'])
def scrape_now():
    """Trigger an immediate scrape attempt (manual override)."""
    threading.Thread(target=run_scrape, daemon=True).start()
    return jsonify({'success': True, 'message': 'Scrape started'})


# ── Scraper ───────────────────────────────────────────────────────────────────

SCRAPE_INTERVAL = 30   # seconds between automatic attempts
HEADERS = {'User-Agent': 'Mozilla/5.0 (Eurovision 2026 Tracker; contact: tracker@local)'}

scraper_thread = None
scraper_stop = threading.Event()


def start_scraper():
    global scraper_thread, scraper_stop
    scraper_stop.set()   # stop any existing thread
    scraper_stop = threading.Event()
    scraper_thread = threading.Thread(target=scraper_loop, daemon=True)
    scraper_thread.start()
    log.info('Scraper started')


def scraper_loop():
    """Poll for jury scores every SCRAPE_INTERVAL seconds until found."""
    attempt = 0
    while not scraper_stop.is_set():
        with state_lock:
            phase = state['phase']
            already_have = bool(state['jury_scores'])
            test = state['test_mode']

        # Only scrape in jury phase, not test mode, not already populated
        if phase == 'jury' and not already_have and not test:
            attempt += 1
            run_scrape(attempt)

        # Sleep in small increments so we can respond to stop signal quickly
        for _ in range(SCRAPE_INTERVAL * 2):
            if scraper_stop.is_set():
                return
            time.sleep(0.5)


def run_scrape(attempt=None):
    """Single scrape pass — tries all sources, updates state if scores found."""
    with state_lock:
        country_names = [c['name'] for c in state['countries']]
        state['scrape_status'] = 'scanning'
        if attempt:
            state['scrape_count'] = attempt

    log.info(f'Scrape attempt {attempt} starting…')

    sources = [
        ('eurovision.tv',       scrape_eurovision_tv),
        ('eurovisionworld.com', scrape_eurovisionworld),
        ('esctoday.com',        scrape_esctoday),
        ('wiwibloggs.com',      scrape_wiwibloggs),
    ]

    found_scores = None
    found_source = None

    for source_name, fn in sources:
        try:
            log.info(f'  Trying {source_name}…')
            scores = fn(country_names)
            hits = sum(1 for v in scores.values() if v > 0)
            log.info(f'  {source_name}: {hits} countries found')
            if hits >= 20:
                found_scores = scores
                found_source = source_name
                break
        except Exception as e:
            log.info(f'  {source_name} failed: {e}')

    import time as _time
    ts = _time.strftime('%H:%M:%S')

    with state_lock:
        state['scrape_last_attempt'] = ts
        if found_scores:
            state['jury_scores'] = {
                name: found_scores.get(name, 0)
                for name in country_names
            }
            state['scrape_status'] = 'found'
            state['scrape_source'] = found_source
            state['scrape_message'] = f'Auto-fetched from {found_source} at {ts}'
            log.info(f'Scores found via {found_source}!')
        else:
            state['scrape_status'] = 'scanning'
            state['scrape_message'] = f'Checked at {ts} — scores not yet published. Will retry in {SCRAPE_INTERVAL}s.'
            log.info('No scores found this pass.')


# ── Scraping functions ────────────────────────────────────────────────────────

def _get(url, timeout=12):
    return requests.get(url, timeout=timeout, headers=HEADERS)


def _text_scores(text, names):
    """Regex fallback: find country name followed by a number."""
    scores = {}
    for name in names:
        m = re.search(rf'\b{re.escape(name)}\b[^0-9]{{0,40}}?(\d{{1,4}})', text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 0 < val <= 2030:
                scores[name] = val
    return scores


def _table_scores(soup, names):
    """Generic table parser: look for country name in a cell, grab nearest number."""
    scores = {}
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            row_text = cells[0].get_text(strip=True)
            for name in names:
                if name.lower() in row_text.lower():
                    for cell in cells[1:]:
                        val = cell.get_text(strip=True)
                        if val.isdigit() and 0 < int(val) <= 2030:
                            scores[name] = int(val)
                            break
    return scores


def _json_scores(text, names):
    """Try to find JSON blobs in the page and extract scores from them."""
    import json
    scores = {}
    # Find anything that looks like {"country": ..., "score": ...}
    blobs = re.findall(r'\{[^{}]{10,500}\}', text)
    for blob in blobs:
        try:
            d = json.loads(blob)
            for name in names:
                for key in ('score', 'jury', 'juryPoints', 'juryScore', 'points', 'total'):
                    if key in d and name.lower() in str(d).lower():
                        val = int(d[key])
                        if 0 < val <= 2030:
                            scores[name] = val
        except Exception:
            pass
    return scores


def scrape_eurovision_tv(names):
    r = _get('https://eurovision.tv/event/vienna-2026/grand-final/results')
    soup = BeautifulSoup(r.text, 'html.parser')
    scores = {}
    # Try structured data first
    for script in soup.find_all('script', type='application/ld+json'):
        scores.update(_json_scores(script.string or '', names))
    for script in soup.find_all('script'):
        t = script.string or ''
        if any(n.lower() in t.lower() for n in names[:3]):
            scores.update(_json_scores(t, names))
            scores.update(_text_scores(t, names))
    scores.update(_table_scores(soup, names))
    if not scores:
        scores.update(_text_scores(soup.get_text(), names))
    return scores


def scrape_eurovisionworld(names):
    r = _get('https://eurovisionworld.com/eurovision/2026')
    soup = BeautifulSoup(r.text, 'html.parser')
    scores = _table_scores(soup, names)
    if not scores:
        # eurovisionworld uses div-based tables in some years
        for div in soup.find_all('div', class_=re.compile(r'country|result|score', re.I)):
            text = div.get_text()
            for name in names:
                if name.lower() in text.lower():
                    m = re.search(r'(\d{1,4})', text)
                    if m:
                        val = int(m.group(1))
                        if 0 < val <= 2030 and name not in scores:
                            scores[name] = val
    if not scores:
        scores.update(_text_scores(soup.get_text(), names))
    return scores


def scrape_esctoday(names):
    r = _get('https://esctoday.com')
    soup = BeautifulSoup(r.text, 'html.parser')
    result_url = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '2026' in href and any(k in href.lower() for k in ('result', 'final', 'score', 'point')):
            result_url = href if href.startswith('http') else 'https://esctoday.com' + href
            break
    if not result_url:
        return {}
    r2 = _get(result_url)
    soup2 = BeautifulSoup(r2.text, 'html.parser')
    scores = _table_scores(soup2, names)
    if not scores:
        scores.update(_text_scores(soup2.get_text(), names))
    return scores


def scrape_wiwibloggs(names):
    r = _get('https://wiwibloggs.com/2026/05/eurovision-2026-grand-final-results/')
    soup = BeautifulSoup(r.text, 'html.parser')
    scores = _table_scores(soup, names)
    if not scores:
        scores.update(_text_scores(soup.get_text(), names))
    return scores


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('━' * 52)
    print('  Eurovision 2026 Voting Tracker  (Python edition)')
    print('  Open http://localhost:5000')
    print(f'  Auto-scraping jury scores every {SCRAPE_INTERVAL}s')
    print('━' * 52)
    start_scraper()
    app.run(debug=False, port=5000, use_reloader=False)
