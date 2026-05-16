from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

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
# Winner: Austria (JJ) — 258 jury + 178 televote = 436 total
# NOTE: These are approximate figures for app testing; verify against official results.
COUNTRIES_2025 = [
    {'name': 'Albania',     'flag': '🇦🇱'},
    {'name': 'Armenia',     'flag': '🇦🇲'},
    {'name': 'Australia',   'flag': '🇦🇺'},
    {'name': 'Austria',     'flag': '🇦🇹'},
    {'name': 'Denmark',     'flag': '🇩🇰'},
    {'name': 'Estonia',     'flag': '🇪🇪'},
    {'name': 'Finland',     'flag': '🇫🇮'},
    {'name': 'France',      'flag': '🇫🇷'},
    {'name': 'Georgia',     'flag': '🇬🇪'},
    {'name': 'Germany',     'flag': '🇩🇪'},
    {'name': 'Greece',      'flag': '🇬🇷'},
    {'name': 'Iceland',     'flag': '🇮🇸'},
    {'name': 'Israel',      'flag': '🇮🇱'},
    {'name': 'Italy',       'flag': '🇮🇹'},
    {'name': 'Latvia',      'flag': '🇱🇻'},
    {'name': 'Lithuania',   'flag': '🇱🇹'},
    {'name': 'Luxembourg',  'flag': '🇱🇺'},
    {'name': 'Malta',       'flag': '🇲🇹'},
    {'name': 'Netherlands', 'flag': '🇳🇱'},
    {'name': 'Norway',      'flag': '🇳🇴'},
    {'name': 'Poland',      'flag': '🇵🇱'},
    {'name': 'Serbia',      'flag': '🇷🇸'},
    {'name': 'Spain',       'flag': '🇪🇸'},
    {'name': 'Sweden',      'flag': '🇸🇪'},
    {'name': 'Switzerland', 'flag': '🇨🇭'},
    {'name': 'Ukraine',     'flag': '🇺🇦'},
]

# Jury scores sum = 2,146  (37 blocs × 58 pts)
JURY_2025 = {
    'Albania': 50,  'Armenia': 32,  'Australia': 156, 'Austria': 258,
    'Denmark': 29,  'Estonia': 54,  'Finland': 88,    'France': 194,
    'Georgia': 45,  'Germany': 13,  'Greece': 42,     'Iceland': 24,
    'Israel': 101,  'Italy': 112,   'Latvia': 37,     'Lithuania': 72,
    'Luxembourg': 50, 'Malta': 63,  'Netherlands': 21, 'Norway': 173,
    'Poland': 40,   'Serbia': 27,   'Spain': 19,      'Sweden': 233,
    'Switzerland': 124, 'Ukraine': 89,
}

# Televote scores sum = 2,204  (38 blocs × 58 pts)
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
        'phase': 'jury',                  # 'jury' | 'televote'
        'countries': [c.copy() for c in COUNTRIES_2026],
        'jury_scores': {},
        'televote_scores': {},
        'reveal_order': [],               # country names, lowest→highest jury
        'current_reveal_index': 0,
        'total_jury_blocs': 35,
        'total_televote_blocs': 36,
        'total_jury_points': 2030,        # 35 × 58
        'total_televote_points': 2088,    # 36 × 58
        'test_mode': False,
        'fetch_message': None,
    }

state = make_default_state()


def compute_reveal_order():
    js = state['jury_scores']
    scored = sorted(state['countries'], key=lambda c: (js.get(c['name'], 0), c['name']))
    state['reveal_order'] = [c['name'] for c in scored]


def compute_enriched_state():
    js = state['jury_scores']
    ts = state['televote_scores']
    countries = state['countries']
    reveal_order = state['reveal_order']
    total_tv_pts = state['total_televote_points']
    total_tv_blocs = state['total_televote_blocs']
    current_idx = state['current_reveal_index']

    revealed_total = sum(ts.values())
    revealed_count = len(ts)
    total_count = len(countries)
    unrevealed_count = total_count - revealed_count
    remaining_pool = total_tv_pts - revealed_total

    # Best combined total among revealed countries
    best_total = 0
    best_country = None
    for name, tv in ts.items():
        combined = js.get(name, 0) + tv
        if combined > best_total:
            best_total = combined
            best_country = name

    # Trend floor = last revealed country's televote score
    trend_floor = 0
    if current_idx > 0 and reveal_order:
        last_name = reveal_order[current_idx - 1]
        trend_floor = ts.get(last_name, 0)

    country_data = []
    for pos, name in enumerate(reveal_order):
        c_info = next((c for c in countries if c['name'] == name), None)
        if not c_info:
            continue

        jury_score = js.get(name, 0)
        tv_score = ts.get(name)
        is_revealed = tv_score is not None
        combined = jury_score + (tv_score if is_revealed else 0)
        max_possible = jury_score + (total_tv_blocs * 12)

        if is_revealed:
            if name == best_country:
                status = 'leading'
            elif combined < best_total:
                status = 'eliminated'
            else:
                status = 'confirmed'
        else:
            if max_possible < best_total:
                status = 'eliminated'
            else:
                status = 'pending'

        fair_share = None
        if not is_revealed and unrevealed_count > 0:
            fair_share = round(remaining_pool / unrevealed_count)

        country_data.append({
            'name': name,
            'flag': c_info['flag'],
            'jury_score': jury_score,
            'tv_score': tv_score,
            'combined': combined,
            'max_possible': max_possible,
            'is_revealed': is_revealed,
            'status': status,
            'fair_share': fair_share,
            'trend_floor': trend_floor if not is_revealed else None,
            'pos': pos,
            'is_next': pos == current_idx,
        })

    revealed_sorted = sorted(
        [c for c in country_data if c['is_revealed']], key=lambda x: -x['combined']
    )
    unrevealed_sorted = sorted(
        [c for c in country_data if not c['is_revealed']], key=lambda x: -x['max_possible']
    )
    leaderboard = revealed_sorted + unrevealed_sorted

    return {
        'phase': state['phase'],
        'countries': country_data,
        'leaderboard': leaderboard,
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
        'total_jury_blocs': state['total_jury_blocs'],
        'total_televote_blocs': state['total_televote_blocs'],
        'total_jury_points': state['total_jury_points'],
        'total_televote_points': state['total_televote_points'],
        'test_mode': state['test_mode'],
        'is_complete': state['phase'] == 'televote' and revealed_count == total_count,
        'fetch_message': state.get('fetch_message'),
        'jury_scores_raw': dict(js),
        'country_flags': {c['name']: c['flag'] for c in countries},
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/state')
def get_state():
    return jsonify(compute_enriched_state())


@app.route('/api/fetch-jury')
def fetch_jury():
    country_names = [c['name'] for c in state['countries']]
    scores, source, error = try_scrape_scores(country_names)
    if error:
        return jsonify({'success': False, 'error': error, 'scores': {}})
    return jsonify({'success': True, 'source': source, 'scores': scores})


@app.route('/api/set-jury', methods=['POST'])
def set_jury():
    data = request.json
    raw = data.get('scores', {})
    jury = {}
    for c in state['countries']:
        name = c['name']
        try:
            jury[name] = max(0, int(raw.get(name, 0) or 0))
        except (ValueError, TypeError):
            jury[name] = 0
    state['jury_scores'] = jury
    state['phase'] = 'televote'
    state['televote_scores'] = {}
    state['current_reveal_index'] = 0
    state['fetch_message'] = None
    compute_reveal_order()
    return jsonify({'success': True})


@app.route('/api/reveal', methods=['POST'])
def reveal():
    data = request.json
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
    state = make_default_state()
    return jsonify({'success': True})


@app.route('/api/load-test-2025', methods=['POST'])
def load_test_2025():
    global state
    state = {
        'phase': 'televote',
        'countries': [c.copy() for c in COUNTRIES_2025],
        'jury_scores': dict(JURY_2025),
        'televote_scores': {},
        'reveal_order': [],
        'current_reveal_index': 0,
        'total_jury_blocs': 37,
        'total_televote_blocs': 38,
        'total_jury_points': 2146,
        'total_televote_points': 2204,
        'test_mode': True,
        'fetch_message': None,
    }
    compute_reveal_order()
    return jsonify({'success': True})


@app.route('/api/test-reveal-next', methods=['POST'])
def test_reveal_next():
    idx = state['current_reveal_index']
    if idx >= len(state['reveal_order']):
        return jsonify({'success': False, 'error': 'All countries revealed'})
    name = state['reveal_order'][idx]
    score = TELEVOTE_2025.get(name, 0)
    state['televote_scores'][name] = score
    state['current_reveal_index'] = idx + 1
    return jsonify({'success': True, 'country': name, 'score': score})


@app.route('/api/test-reveal-all', methods=['POST'])
def test_reveal_all():
    for name in state['reveal_order'][state['current_reveal_index']:]:
        state['televote_scores'][name] = TELEVOTE_2025.get(name, 0)
    state['current_reveal_index'] = len(state['reveal_order'])
    return jsonify({'success': True})


# ── Scraping ──────────────────────────────────────────────────────────────────

def try_scrape_scores(country_names):
    scrapers = [
        ('eurovision.tv',      scrape_eurovision_tv),
        ('eurovisionworld.com', scrape_eurovisionworld),
        ('esctoday.com',       scrape_esctoday),
    ]
    for source_name, fn in scrapers:
        try:
            scores = fn(country_names)
            if scores and sum(1 for v in scores.values() if v > 0) >= 20:
                return scores, source_name, None
        except Exception:
            pass
    return None, None, (
        'Could not fetch scores from any source '
        '(eurovision.tv, eurovisionworld.com, esctoday.com). '
        'Please enter scores manually below.'
    )


def _get_soup(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Eurovision Tracker)'}
    resp = requests.get(url, timeout=12, headers=headers)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser')


def _extract_scores_from_text(text, country_names):
    scores = {}
    for name in country_names:
        m = re.search(rf'\b{re.escape(name)}\b[^\d]{{0,30}}(\d{{1,4}})', text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 0 < val <= 2030:
                scores[name] = val
    return scores


def scrape_eurovision_tv(country_names):
    soup = _get_soup('https://eurovision.tv/event/vienna-2026/grand-final/results')
    scores = {}
    for script in soup.find_all('script'):
        t = script.string or ''
        if 'score' in t.lower() or 'jury' in t.lower():
            scores.update(_extract_scores_from_text(t, country_names))
    if not scores:
        scores.update(_extract_scores_from_text(soup.get_text(), country_names))
    return scores


def scrape_eurovisionworld(country_names):
    soup = _get_soup('https://eurovisionworld.com/eurovision/2026')
    scores = {}
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            row_text = cells[0].get_text(strip=True)
            for name in country_names:
                if name.lower() in row_text.lower():
                    for cell in cells[1:]:
                        val = cell.get_text(strip=True)
                        if val.isdigit() and 0 < int(val) <= 2030:
                            scores[name] = int(val)
                            break
    if not scores:
        scores.update(_extract_scores_from_text(soup.get_text(), country_names))
    return scores


def scrape_esctoday(country_names):
    soup = _get_soup('https://esctoday.com')
    result_url = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '2026' in href and any(k in href.lower() for k in ('result', 'final', 'score')):
            result_url = href if href.startswith('http') else 'https://esctoday.com' + href
            break
    if not result_url:
        return {}
    soup2 = _get_soup(result_url)
    return _extract_scores_from_text(soup2.get_text(), country_names)


if __name__ == '__main__':
    print('━' * 50)
    print('  Eurovision 2026 Voting Tracker')
    print('  Open http://localhost:5000')
    print('━' * 50)
    app.run(debug=True, port=5000)
