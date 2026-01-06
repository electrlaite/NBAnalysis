# !pip install streamlit nba_api plotly pandas numpy

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nba_api.stats.endpoints import leaguedashplayerstats, teamgamelog, leaguedashteamstats, shotchartdetail
from nba_api.stats.static import teams

# ==========================================
# 1. PAGE CONFIGURATION & STYLING
# ==========================================
st.set_page_config(page_title="Nuggets vs Spurs Analytics", layout="wide", page_icon="🏀")

# Custom CSS to make it look like a pro dashboard
st.markdown("""
    <style>
    .main {
        background-color: #f0f2f6;
    }
    h1 {
        color: #1d428a; /* NBA Blue */
    }
    h2 {
        color: #ce1141; /* NBA Red */
    }
    .stMetric {
        background-color: white;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 2. DATA LOADING FUNCTIONS (Cached)
# ==========================================
@st.cache_data
def load_data(season='2024-25'):
    # Team IDs
    nuggets_id = [x for x in teams.get_teams() if x['full_name'] == 'Denver Nuggets'][0]['id']
    spurs_id = [x for x in teams.get_teams() if x['full_name'] == 'San Antonio Spurs'][0]['id']

    # 1. Player Stats (General)
    player_stats = leaguedashplayerstats.LeagueDashPlayerStats(season=season).get_data_frames()[0]

    # 2. Team Stats (General)
    team_stats = leaguedashteamstats.LeagueDashTeamStats(season=season).get_data_frames()[0]

    # 3. Game Logs (Trends)
    spurs_log = teamgamelog.TeamGameLog(team_id=spurs_id, season=season).get_data_frames()[0]

    # 4. Shot Chart (Spurs)
    # Note: 0 as player_id gets team shots
    shots = shotchartdetail.ShotChartDetail(
        team_id=spurs_id,
        player_id=0,
        context_measure_simple='FGA',
        season_nullable=season
    ).get_data_frames()[0]

    return nuggets_id, spurs_id, player_stats, team_stats, spurs_log, shots


# Load Data
try:
    with st.spinner('Loading NBA Data from API...'):
        NUGGETS_ID, SPURS_ID, df_players, df_teams, df_trends, df_shots = load_data()

    spurs_roster = df_players[df_players['TEAM_ID'] == SPURS_ID]
    nuggets_roster = df_players[df_players['TEAM_ID'] == NUGGETS_ID]
    spurs_team_stats = df_teams[df_teams['TEAM_ID'] == SPURS_ID]
    nuggets_team_stats = df_teams[df_teams['TEAM_ID'] == NUGGETS_ID]

except Exception as e:
    st.error(f"Error connecting to NBA API: {e}. Please refresh or check internet connection.")
    st.stop()


# ==========================================
# 3. HELPER FUNCTIONS (Court Drawing)
# ==========================================
def draw_court(fig, layer='below'):
    # Standard NBA Court Dimensions overlay for Plotly
    court_color = 'rgba(0,0,0,0.5)'
    lw = 1.5

    # Hoop
    fig.add_shape(type="circle", x0=-7.5, y0=-7.5, x1=7.5, y1=7.5, line_color="orange")
    # Lane
    fig.add_shape(type="rect", x0=-80, y0=-47.5, x1=80, y1=142.5, line_color=court_color, line_width=lw)
    # 3-Point Line
    fig.add_shape(type="path", path="M -220 92.5 C -220 300, 220 300, 220 92.5", line_color=court_color, line_width=lw)
    fig.add_shape(type="line", x0=-220, y0=-47.5, x1=-220, y1=92.5, line_color=court_color, line_width=lw)
    fig.add_shape(type="line", x0=220, y0=-47.5, x1=220, y1=92.5, line_color=court_color, line_width=lw)

    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-250, 250]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[400, -50]),  # Inverted Y for basketball
        height=600, width=600,
        plot_bgcolor='white'
    )
    return fig


# ==========================================
# 4. DASHBOARD LAYOUT
# ==========================================

# --- SIDEBAR ---
st.sidebar.image("https://cdn.nba.com/logos/nba/1610612743/primary/L/logo.svg", width=100)
st.sidebar.title("Scouting Report")
st.sidebar.header("Denver Nuggets vs. San Antonio Spurs")
st.sidebar.markdown("---")
analysis_focus = st.sidebar.radio("Go to Section:",
                                  ["1. Team Overview", "2. Key Players", "3. Star Matchup", "4. Shot Selection",
                                   "5. Trends & Weaknesses"])
st.sidebar.info("**Group:** Adam, Taha MI, Cyril, Yuxuan, Vincent")

# --- HEADER ---
st.title(f"📊 Game Prep: Nuggets vs Spurs")
st.markdown("Data Intelligence for the Coaching Staff.")

# --- SECTIONS ---

if analysis_focus == "1. Team Overview":
    st.header("Team Comparison")

    col1, col2, col3, col4 = st.columns(4)

    # Metrics
    with col1:
        st.metric("Spurs PTS/Game", spurs_team_stats['PTS'].values[0],
                  delta=float(spurs_team_stats['PTS'].values[0]) - float(nuggets_team_stats['PTS'].values[0]))
    with col2:
        st.metric("Spurs Rebounds", spurs_team_stats['REB'].values[0],
                  delta=float(spurs_team_stats['REB'].values[0]) - float(nuggets_team_stats['REB'].values[0]))
    with col3:
        st.metric("Spurs Turnovers", spurs_team_stats['TOV'].values[0],
                  delta=-(float(spurs_team_stats['TOV'].values[0]) - float(nuggets_team_stats['TOV'].values[0])),
                  delta_color="inverse")  # Less TOV is better
    with col4:
        st.metric("Spurs 3P%", f"{spurs_team_stats['FG3_PCT'].values[0] * 100:.1f}%")

    st.subheader("Comparison Chart")

    # Preparing data for comparison
    comp_df = pd.concat([spurs_team_stats, nuggets_team_stats])
    comp_df['Team'] = ['Spurs', 'Nuggets']

    fig = go.Figure(data=[
        go.Bar(name='Points', x=comp_df['Team'], y=comp_df['PTS']),
        go.Bar(name='Rebounds', x=comp_df['Team'], y=comp_df['REB']),
        go.Bar(name='Assists', x=comp_df['Team'], y=comp_df['AST'])
    ])
    fig.update_layout(barmode='group', title="Head-to-Head Averages")
    st.plotly_chart(fig, use_container_width=True)

elif analysis_focus == "2. Key Players":
    st.header("Identifying Opponent Threats")

    stat_filter = st.selectbox("Sort Players By:", ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV'])

    top_players = spurs_roster.sort_values(by=stat_filter, ascending=False).head(5)

    fig = px.bar(top_players, x='PLAYER_NAME', y=stat_filter,
                 color=stat_filter, title=f"Top 5 Spurs by {stat_filter}",
                 color_continuous_scale='Viridis')
    st.plotly_chart(fig, use_container_width=True)

    st.write("### Full Roster Stats")
    st.dataframe(
        spurs_roster[['PLAYER_NAME', 'GP', 'MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV']].sort_values(by='PTS',
                                                                                                         ascending=False))

elif analysis_focus == "3. Star Matchup":
    st.header("The Main Event: Jokic vs. Wembanyama")

    # Fetching specific players
    jokic = nuggets_roster[nuggets_roster['PLAYER_NAME'].str.contains("Jokic")]
    wemby = spurs_roster[spurs_roster['PLAYER_NAME'].str.contains("Wembanyama")]

    if not jokic.empty and not wemby.empty:
        p1 = jokic.iloc[0]
        p2 = wemby.iloc[0]

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🃏 Nikola Jokic")
            st.write(f"**PTS:** {p1['PTS']} | **REB:** {p1['REB']} | **AST:** {p1['AST']}")
        with col2:
            st.subheader("👽 Victor Wembanyama")
            st.write(f"**PTS:** {p2['PTS']} | **REB:** {p2['REB']} | **BLK:** {p2['BLK']}")

        # Radar Chart
        categories = ['PTS', 'REB', 'AST', 'STL', 'BLK']

        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[p1[c] for c in categories],
            theta=categories,
            fill='toself',
            name='Jokic'
        ))
        fig.add_trace(go.Scatterpolar(
            r=[p2[c] for c in categories],
            theta=categories,
            fill='toself',
            name='Wembanyama'
        ))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True)), title="Versatility Comparison")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not find data for Jokic or Wembanyama.")

elif analysis_focus == "4. Shot Selection":
    st.header("Spurs Shot Chart Analysis")
    st.markdown("Where do they shoot from? Where are they dangerous?")

    col1, col2 = st.columns([3, 1])

    with col2:
        shot_type = st.radio("Filter Shot Outcome:", ["All", "Made Shot", "Missed Shot"])

    with col1:
        filtered_shots = df_shots.copy()
        if shot_type != "All":
            filtered_shots = filtered_shots[filtered_shots['EVENT_TYPE'] == shot_type]

        fig = px.scatter(filtered_shots, x='LOC_X', y='LOC_Y', color='EVENT_TYPE',
                         color_discrete_map={'Made Shot': '#00AA00', 'Missed Shot': '#FF0000'},
                         opacity=0.5, hover_data=['PLAYER_NAME', 'SHOT_DISTANCE'])

        fig = draw_court(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.info("**Coach's Note:** Look for the density of shots. Are they attacking the rim or settling for mid-range?")

elif analysis_focus == "5. Trends & Weaknesses":
    st.header("Recent Trends & Turnovers")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Last 5 Games: Points Scored")
        # Ensure dates are datetime
        df_trends['GAME_DATE'] = pd.to_datetime(df_trends['GAME_DATE'])
        fig_trend = px.line(df_trends.head(10), x='GAME_DATE', y='PTS', markers=True,
                            title="Scoring Trend (Last 10 Games)")
        st.plotly_chart(fig_trend, use_container_width=True)

    with col2:
        st.subheader("Turnover Vulnerability")
        avg_tov = spurs_team_stats['TOV'].values[0]

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=avg_tov,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Avg Turnovers per Game"},
            gauge={
                'axis': {'range': [None, 20]},
                'bar': {'color': "red" if avg_tov > 14 else "green"},
                'threshold': {'line': {'color': "black", 'width': 4}, 'thickness': 0.75, 'value': 14}
            }
        ))
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.caption("Target: Force more than 14 turnovers.")