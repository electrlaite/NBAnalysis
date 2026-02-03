import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nba_api.stats.endpoints import teamgamelog, leaguedashplayerstats
from nba_api.stats.static import teams

# ==========================================
# 1. CONFIGURATION & STYLE
# ==========================================
st.set_page_config(
    page_title="NBA Scouting Report Pro",
    layout="wide",
    page_icon="🏀",
    initial_sidebar_state="expanded"
)

# CSS Custom pour un look "Dark Analytics"
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: white; }
    div[data-testid="stMetricValue"] { font-size: 26px; font-weight: bold; }
    .highlight { color: #FEC524; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 2. DATA ENGINE
# ==========================================

@st.cache_data
def get_all_teams():
    return teams.get_teams()


@st.cache_data
def load_team_data(team_id, season='2024-25'):
    # Récupération des logs de matchs
    log = teamgamelog.TeamGameLog(team_id=team_id, season=season).get_data_frames()[0]

    # Conversion numérique
    cols = ['PTS', 'FGM', 'FGA', 'FG3M', 'FG3A', 'FTA', 'OREB', 'DREB', 'REB', 'AST', 'STL', 'BLK', 'TOV']
    for c in cols:
        log[c] = pd.to_numeric(log[c])

    log['GAME_DATE'] = pd.to_datetime(log['GAME_DATE'])

    # CALCUL AVANCÉ : ESTIMATION DES POSSESSIONS
    # Formule simple : FGA + 0.44*FTA - ORB + TOV
    log['POSS'] = log['FGA'] + 0.44 * log['FTA'] - log['OREB'] + log['TOV']
    log['ORTG'] = (log['PTS'] / log['POSS']) * 100

    return log


@st.cache_data
def get_top_players(team_id, season='2024-25'):
    # Cette API peut être lente, on la met en cache.
    # Récupère les stats globales des joueurs pour l'équipe
    try:
        df = leaguedashplayerstats.LeagueDashPlayerStats(
            team_id_nullable=team_id, season=season
        ).get_data_frames()[0]
        return df.sort_values('PTS', ascending=False).head(5)
    except:
        return pd.DataFrame()


def calculate_aggregated_stats(df, games_count, location):
    filtered_df = df.copy()

    # Filtres
    if location == 'Home':
        filtered_df = filtered_df[filtered_df['MATCHUP'].str.contains(' vs. ')]
    elif location == 'Away':
        filtered_df = filtered_df[filtered_df['MATCHUP'].str.contains(' @ ')]

    if games_count != 'All Season':
        n = int(games_count.split()[1])
        filtered_df = filtered_df.head(n)

    if filtered_df.empty:
        return None, filtered_df

    # Moyennes pondérées
    stats = {
        'PTS': filtered_df['PTS'].mean(),
        'POSS': filtered_df['POSS'].mean(),
        'ORTG': filtered_df['ORTG'].mean(),
        'AST': filtered_df['AST'].mean(),
        'REB': filtered_df['REB'].mean(),
        'TOV': filtered_df['TOV'].mean(),
        'TS%': (filtered_df['PTS'].sum() / (2 * (filtered_df['FGA'].sum() + 0.44 * filtered_df['FTA'].sum()))) * 100,
        '3P%': (filtered_df['FG3M'].sum() / filtered_df['FG3A'].sum()) * 100 if filtered_df['FG3A'].sum() > 0 else 0,
        'Win_Rate': (filtered_df['WL'] == 'W').mean() * 100
    }
    return stats, filtered_df


# ==========================================
# 3. SIDEBAR CONTROLS
# ==========================================
st.sidebar.header("🏀 Matchup Selector")

all_teams = get_all_teams()
team_names = [t['full_name'] for t in all_teams]
team_names.sort()

# Sélection Team A et Team B
team_a_name = st.sidebar.selectbox("🏠 Home Team", team_names, index=team_names.index("San Antonio Spurs"))
team_b_name = st.sidebar.selectbox("✈️ Away Team", team_names, index=team_names.index("Denver Nuggets"))

# Récupération des IDs
team_a_id = [t['id'] for t in all_teams if t['full_name'] == team_a_name][0]
team_b_id = [t['id'] for t in all_teams if t['full_name'] == team_b_name][0]

st.sidebar.markdown("---")
filter_games = st.sidebar.selectbox("📅 Timeframe:", ['All Season', 'Last 10 Games', 'Last 5 Games'])
st.sidebar.caption("Note: Stats are fetched live from NBA API.")

# ==========================================
# 4. DASHBOARD LOGIC
# ==========================================

# Loading Data
with st.spinner('Scouting reports loading...'):
    log_a = load_team_data(team_a_id)
    log_b = load_team_data(team_b_id)

    # Pour l'équipe A (Home), on regarde ses stats à domicile si l'utilisateur veut être précis,
    # mais pour simplifier la comparaison globale, on garde les filtres globaux pour l'instant
    stats_a, df_a = calculate_aggregated_stats(log_a, filter_games, 'All')
    stats_b, df_b = calculate_aggregated_stats(log_b, filter_games, 'All')

    players_a = get_top_players(team_a_id)
    players_b = get_top_players(team_b_id)

# Header
col_h1, col_h2, col_h3 = st.columns([1, 2, 1])
with col_h1:
    st.markdown(f"## {team_a_name}")
    st.markdown(f"<h1 style='color:#4CAF50'>{stats_a['Win_Rate']:.1f}% Win</h1>", unsafe_allow_html=True)
with col_h2:
    st.markdown("<h3 style='text-align: center; vertical-align: middle; line-height: 100px;'>VS</h3>",
                unsafe_allow_html=True)
with col_h3:
    st.markdown(f"## {team_b_name}")
    st.markdown(f"<h1 style='color:#FF5722'>{stats_b['Win_Rate']:.1f}% Win</h1>", unsafe_allow_html=True)

st.divider()

# TABS LAYOUT
tab1, tab2, tab3 = st.tabs(["📊 General Stats", "🧠 Advanced Metrics", "🌟 Top Players"])

# --- TAB 1: GENERAL ---
with tab1:
    col1, col2, col3, col4 = st.columns(4)


    def delta_metric(col, label, key, better='high'):
        val_a = stats_a[key]
        val_b = stats_b[key]
        diff = val_a - val_b

        # Gestion des couleurs pour les deltas
        color = "normal"
        if better == 'low':
            color = "inverse"

        col.metric(label, f"{val_a:.1f}", f"{diff:.1f} vs {team_b_name}", delta_color=color)


    with col1: delta_metric(st, "Points / Game", 'PTS')
    with col2: delta_metric(st, "Rebounds", 'REB')
    with col3: delta_metric(st, "Assists", 'AST')
    with col4: delta_metric(st, "Turnovers", 'TOV', better='low')

    st.subheader("Scoring Trend (Last Games)")

    # Graphique combiné
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(x=df_a['GAME_DATE'], y=df_a['PTS'], mode='lines+markers', name=team_a_name))
    fig_trend.add_trace(
        go.Scatter(x=df_b['GAME_DATE'], y=df_b['PTS'], mode='lines+markers', name=team_b_name, line=dict(dash='dash')))
    fig_trend.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified")
    st.plotly_chart(fig_trend, use_container_width=True)

# --- TAB 2: ADVANCED ---
with tab2:
    col_adv1, col_adv2 = st.columns(2)

    with col_adv1:
        st.markdown("### Efficiency & Pace")
        # Radar Chart amélioré
        categories = ['Offensive Rating', 'True Shooting %', '3-Point %', 'Ball Security (Inv TOV)']


        # Normalisation grossière pour le radar (0-1)
        def norm(val, max_val): return min(val / max_val, 1.0)


        r_a = [
            norm(stats_a['ORTG'], 130),
            norm(stats_a['TS%'], 65),
            norm(stats_a['3P%'], 45),
            norm(30 - stats_a['TOV'], 30)
        ]
        r_b = [
            norm(stats_b['ORTG'], 130),
            norm(stats_b['TS%'], 65),
            norm(stats_b['3P%'], 45),
            norm(30 - stats_b['TOV'], 30)
        ]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=r_a, theta=categories, fill='toself', name=team_a_name))
        fig_radar.add_trace(go.Scatterpolar(r=r_b, theta=categories, fill='toself', name=team_b_name))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1])), height=400)
        st.plotly_chart(fig_radar, use_container_width=True)

    with col_adv2:
        st.markdown("### The Pace Factor")
        st.info("Pace estimates the number of possessions per 48 minutes. A higher pace means a faster game.")

        fig_bar = go.Figure(data=[
            go.Bar(name=team_a_name, x=['Pace (Possessions)'], y=[stats_a['POSS']], text=[f"{stats_a['POSS']:.1f}"],
                   textposition='auto'),
            go.Bar(name=team_b_name, x=['Pace (Possessions)'], y=[stats_b['POSS']], text=[f"{stats_b['POSS']:.1f}"],
                   textposition='auto')
        ])
        fig_bar.update_layout(barmode='group', height=400)
        st.plotly_chart(fig_bar, use_container_width=True)

# --- TAB 3: PLAYERS ---
with tab3:
    st.subheader(f"🌟 Top Performers ({season})")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"**{team_a_name} Leaders**")
        if not players_a.empty:
            st.dataframe(
                players_a[['PLAYER_NAME', 'GP', 'PTS', 'AST', 'REB', 'FG_PCT']].style.background_gradient(cmap='Greens',
                                                                                                          subset=[
                                                                                                              'PTS']),
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("Player data unavailable.")

    with c2:
        st.markdown(f"**{team_b_name} Leaders**")
        if not players_b.empty:
            st.dataframe(
                players_b[['PLAYER_NAME', 'GP', 'PTS', 'AST', 'REB', 'FG_PCT']].style.background_gradient(cmap='Blues',
                                                                                                          subset=[
                                                                                                              'PTS']),
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("Player data unavailable.")