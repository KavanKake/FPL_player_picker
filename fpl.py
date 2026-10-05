# fpl.py
from flask import Flask, render_template, request
import requests
import pandas as pd
from datetime import datetime

app = Flask(__name__)

# --- posisjonskart (godtar flere varianter) ---
POSITION_MAP = {
    'goalkeeper': 1, 'keeper': 1, 'gk': 1, 'målmann': 1,
    'defender': 2, 'forsvarer': 2, 'def': 2,
    'midfielder': 3, 'midtbane': 3, 'mid': 3,
    'forward': 4, 'angriper': 4, 'fw': 4, 'striker': 4
}

def parse_position_input(s: str):
    if not s:
        return None
    key = s.strip().lower()
    return POSITION_MAP.get(key, None)

def foto_url(code):
    """ Bygg URL til spillerbildet fra Premier League sin CDN. """
    if code is None or pd.isna(code):
        return None
    return f"https://resources.premierleague.com/premierleague/photos/players/110x140/p{int(code)}.png"

# ----------------- Hent data -----------------
def hent_data():
    try:
        players = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=10).json()
        fixtures = requests.get("https://fantasy.premierleague.com/api/fixtures/", timeout=10).json()
        return players, fixtures
    except Exception as e:
        raise RuntimeError("Feil ved henting av FPL-data: " + str(e))

# ----------------- Lagform -----------------
def lag_form(team_id, fixtures, window=5):
    """ Beregn gjennomsnitt mål scoret og sluppet for siste 'window' avsluttede kamper. """
    matches = [m for m in fixtures if m.get('finished') is True and (m.get('team_h') == team_id or m.get('team_a') == team_id)]
    if not matches:
        return 0.0, 0.0

    # sorter på kickoff_time (sikre at vi kan parse dato)
    def _t(m):
        try:
            return pd.to_datetime(m.get('kickoff_time'))
        except Exception:
            return pd.to_datetime("1970-01-01")
    matches = sorted(matches, key=_t)[-window:]

    gs, gc = 0, 0
    for k in matches:
        # scores kan være None for eldre kamper, bruk 0 som fallback
        h_score = k.get('team_h_score')
        a_score = k.get('team_a_score')
        h_score = 0 if h_score is None else int(h_score)
        a_score = 0 if a_score is None else int(a_score)

        if k.get('team_h') == team_id:
            gs += h_score
            gc += a_score
        else:
            gs += a_score
            gc += h_score

    n = len(matches)
    return gs / n, gc / n

# ----------------- Beste nå (enkel score basert på form + ppg) -----------------
def anbefalt_spillere(budsjett: float, posisjon_input: str, antall: int = 5, min_minutter: int = 0):
    players_json = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=10).json()
    players = pd.json_normalize(players_json, record_path=['elements'])
    teams = pd.json_normalize(players_json, record_path=['teams'])
    types = pd.json_normalize(players_json, record_path=['element_types'])

    # merge for lesbare navn
    df = players.merge(teams[['id','name']], left_on='team', right_on='id', suffixes=('','_team')).merge(
        types[['id','singular_name']], left_on='element_type', right_on='id', suffixes=('','_type'))
    df.rename(columns={'singular_name':'position', 'name':'team_name'}, inplace=True)

    # map posisjon til element_type (1-4) hvis mulig, ellers fallback til string-matching
    elem_type = parse_position_input(posisjon_input)
    if elem_type is not None:
        df = df[df['element_type'] == elem_type]
    else:
        df = df[df['position'].str.lower() == posisjon_input.strip().lower()]

    # filter på budsjett (now_cost er i 0.1M enheter; 50 -> £5.0)
    df = df[df['now_cost'] / 10 <= budsjett]

    # filtrer bort spillere med for lite spilletid (gir støy i form/ppg)
    df = df[pd.to_numeric(df['minutes'], errors='coerce').fillna(0) >= min_minutter]

    if df.empty:
        return []

    # trygg konvertering til floats
    df['form'] = pd.to_numeric(df['form'], errors='coerce').fillna(0.0)
    df['points_per_game'] = pd.to_numeric(df['points_per_game'], errors='coerce').fillna(0.0)

    # unngå deling på null standardavvik
    def zscore(col):
        std = col.std()
        if std == 0 or pd.isna(std):
            return col - col.mean()
        return (col - col.mean()) / std

    df['form_norm'] = zscore(df['form'])
    df['ppg_norm'] = zscore(df['points_per_game'])
    df['score'] = df['form_norm'] + df['ppg_norm']

    top = df.sort_values('score', ascending=False).head(antall)
    spillere = []
    for _, row in top.iterrows():
        spillere.append({
            "first_name": row.get("first_name", ""),
            "second_name": row.get("second_name", ""),
            "team_name": row.get("team_name", ""),
            "position": row.get("position", ""),
            "minutes": int(pd.to_numeric(row.get("minutes"), errors='coerce') or 0),
            "photo": foto_url(row.get("code")),
            "now_cost": float(row.get("now_cost", 0)),
            "form": float(row.get("form", 0.0)),
            "points_per_game": float(row.get("points_per_game", 0.0)),
            "score": float(row.get("score", 0.0))
        })
    return spillere

# ----------------- Forventet score fremover -----------------
def forventet_score(spiller_row, fixtures, antall_fixtures=3):
    team_id = int(spiller_row.get('team'))
    pos_type = int(spiller_row.get('element_type'))
    base_form = 0.0
    try:
        base_form = float(spiller_row.get('form') or 0.0)
    except Exception:
        base_form = 0.0
    if base_form == 0:
        # bruk points_per_game som fallback-baseline hvis form er 0
        try:
            base_form = float(spiller_row.get('points_per_game') or 0.0)
        except Exception:
            base_form = 0.0
    if base_form <= 0:
        base_form = 0.1

    team_gs, team_gc = lag_form(team_id, fixtures, window=5)

    # kommende kamper for laget (upcomig)
    upcoming = [f for f in fixtures if not f.get('finished') and (f.get('team_h') == team_id or f.get('team_a') == team_id)]
    if not upcoming:
        return 0.0
    # sorter og ta de første
    upcoming = sorted(upcoming, key=lambda x: pd.to_datetime(x.get('kickoff_time') or '1970-01-01'))[:antall_fixtures]

    pred_scores = []
    for kamp in upcoming:
        if kamp.get('team_h') == team_id:
            opponent = int(kamp.get('team_a'))
            fdr = kamp.get('team_h_difficulty', 3)
        else:
            opponent = int(kamp.get('team_h'))
            fdr = kamp.get('team_a_difficulty', 3)

        opp_gs, opp_gc = lag_form(opponent, fixtures, window=5)

        # små epsilon for å unngå deling på 0
        eps = 0.1
        fdr_factor = (6 - (int(fdr) if fdr is not None else 3)) / 5.0  # 1 -> 1.0, 5 -> 0.2

        if pos_type in (3, 4):  # mid/forward -> offensive faktor
            attack_factor = (team_gs + eps) / (opp_gc + eps)
            kamp_score = base_form * attack_factor * fdr_factor
        else:  # goalkeeper/defender -> defensive faktor (clean sheet-vennlig)
            defense_factor = (1.0 / (opp_gs + eps))
            kamp_score = base_form * defense_factor * fdr_factor

        pred_scores.append(float(kamp_score))

    return sum(pred_scores) / len(pred_scores) if pred_scores else 0.0

def anbefalt_spillere_fremover(budsjett: float, posisjon_input: str, antall: int = 5, min_minutter: int = 0):
    players_json, fixtures = hent_data()
    df_players = pd.DataFrame(players_json['elements'])
    df_teams = pd.DataFrame(players_json['teams'])
    df_types = pd.DataFrame(players_json['element_types'])

    df = df_players.merge(df_teams[['id','name']], left_on='team', right_on='id', suffixes=('','_team')).merge(
        df_types[['id','singular_name']], left_on='element_type', right_on='id', suffixes=('','_type'))
    df.rename(columns={'singular_name':'position', 'name':'team_name'}, inplace=True)

    elem_type = parse_position_input(posisjon_input)
    if elem_type is not None:
        df = df[df['element_type'] == elem_type]
    else:
        df = df[df['position'].str.lower() == posisjon_input.strip().lower()]

    df = df[df['now_cost'] / 10 <= budsjett]
    df = df[pd.to_numeric(df['minutes'], errors='coerce').fillna(0) >= min_minutter]
    if df.empty:
        return []

    resultater = []
    for _, row in df.iterrows():
        try:
            score = forventet_score(row, fixtures, antall_fixtures=3)
        except Exception:
            score = 0.0
        resultater.append({
            "first_name": row.get("first_name", ""),
            "second_name": row.get("second_name", ""),
            "team_name": row.get("team_name", ""),
            "position": row.get("position", ""),
            "minutes": int(pd.to_numeric(row.get("minutes"), errors='coerce') or 0),
            "photo": foto_url(row.get("code")),
            "now_cost": float(row.get("now_cost", 0)),
            "form": float(pd.to_numeric(row.get("form"), errors='coerce') or 0.0),
            "points_per_game": float(pd.to_numeric(row.get("points_per_game"), errors='coerce') or 0.0),
            "future_score": float(score)
        })

    resultater = sorted(resultater, key=lambda x: x['future_score'], reverse=True)[:antall]
    return resultater

# ----------------- Flask routes -----------------
@app.route('/', methods=['GET','POST'])
def index():
    spillere = []
    fremover = []
    mode = None
    error = None
    budsjett = None
    posisjon = 'Midfielder'
    min_minutter = 180

    if request.method == 'POST':
        try:
            posisjon = request.form.get('posisjon', '')
            mode = request.form.get('mode', 'na')
            budsjett = float(request.form.get('budsjett', 0))
            min_minutter = max(0, int(request.form.get('min_minutter') or 0))

            if mode == 'na':
                spillere = anbefalt_spillere(budsjett, posisjon, antall=5, min_minutter=min_minutter)
            elif mode == 'fremover':
                fremover = anbefalt_spillere_fremover(budsjett, posisjon, antall=5, min_minutter=min_minutter)
        except Exception as e:
            error = str(e)

    resultater = spillere if mode == 'na' else fremover
    return render_template('index.html', resultater=resultater, mode=mode, error=error,
                           budsjett=budsjett, posisjon=posisjon, min_minutter=min_minutter)

if __name__ == "__main__":
    app.run(debug=True)