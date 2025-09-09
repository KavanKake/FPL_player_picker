from flask import Flask, render_template, request
import requests
import pandas as pd

app = Flask(__name__)

def anbefalt_spiller(budsjett: float, posisjon: str):
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    data = requests.get(url, verify=False).json()

    players = pd.json_normalize(data, record_path=['elements'])
    teams = pd.json_normalize(data, record_path=['teams'])
    types = pd.json_normalize(data, record_path=['element_types'])

    df = players.merge(teams[['id','name']], left_on='team', right_on='id', suffixes=('','_team')).merge(
        types[['id','singular_name']], left_on='element_type', right_on='id', suffixes=('','_type'))
    df.rename(columns={'singular_name':'position', 'name':'team_name'}, inplace=True)

    df = df[df['position'].str.lower() == posisjon.lower()]
    df = df[df['now_cost'] / 10 <= budsjett]

    if df.empty:
        return None

    df['form'] = df['form'].astype(float)
    df['points_per_game'] = df['points_per_game'].astype(float)

    df['form_norm'] = (df['form'] - df['form'].mean()) / df['form'].std()
    df['ppg_norm'] = (df['points_per_game'] - df['points_per_game'].mean()) / df['points_per_game'].std()
    df['score'] = df['form_norm'] + df['ppg_norm']

    best = df.sort_values('score', ascending=False).iloc[0]

    # konverter til dict for Jinja
    return {
        "first_name": best["first_name"],
        "second_name": best["second_name"],
        "team_name": best["team_name"],
        "now_cost": best["now_cost"],
        "form": best["form"],
        "points_per_game": best["points_per_game"],
        "score": best["score"]
    }


@app.route('/', methods=['GET','POST'])
def index():
    spiller = None
    if request.method == 'POST':
        budsjett = float(request.form['budsjett'])
        posisjon = request.form['posisjon']
        spiller = anbefalt_spiller(budsjett, posisjon)
    return render_template('index.html', spiller=spiller)

if __name__ == "__main__":
    app.run(debug=True)

"""
Lag en fil: templates/index.html

<!DOCTYPE html>
<html lang="no">
<head>
    <meta charset="UTF-8">
    <title>FPL Anbefaler</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f8f9fa; padding: 20px; }
        .container { max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { text-align: center; }
        form { display: flex; flex-direction: column; gap: 10px; }
        input, select, button { padding: 10px; font-size: 1rem; border-radius: 5px; border: 1px solid #ccc; }
        button { background: #007bff; color: white; border: none; cursor: pointer; }
        button:hover { background: #0056b3; }
        .result { margin-top: 20px; padding: 15px; background: #e9f7ef; border-left: 5px solid #28a745; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Fantasy Premier League Anbefaler</h1>
        <form method="POST">
            <label for="budsjett">Budsjett (£ millioner):</label>
            <input type="number" step="0.1" name="budsjett" required>

            <label for="posisjon">Posisjon:</label>
            <select name="posisjon" required>
                <option value="Goalkeeper">Goalkeeper</option>
                <option value="Defender">Defender</option>
                <option value="Midfielder">Midfielder</option>
                <option value="Forward">Forward</option>
            </select>

            <button type="submit">Finn spiller</button>
        </form>

        {% if spiller %}
        <div class="result">
            <h2>Anbefalt spiller:</h2>
            <p><strong>{{ spiller.first_name }} {{ spiller.second_name }}</strong> ({{ spiller.team_name }})</p>
            <p>Pris: £{{ spiller.now_cost/10 }}m</p>
            <p>Form: {{ spiller.form }}</p>
            <p>Poeng per kamp: {{ spiller.points_per_game }}</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""
