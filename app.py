import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc
from nba_api.stats.endpoints import (
    teamgamelog, leaguedashplayerstats, shotchartdetail, leaguegamefinder
)
from nba_api.stats.static import teams
import time

# ================================================================
# 1. PAGE CONFIG & GLOBAL STYLING
# ================================================================
st.set_page_config(
    page_title="NBA Scouting Report Pro",
    layout="wide",
    page_icon="🏀",
    initial_sidebar_state="expanded"
)

C_A = "#4CAF50"   # Team A accent
C_B = "#2196F3"   # Team B accent
ACCENT = "#FEC524"
BG = "#0e1117"
CARD = "#1a1d23"

st.markdown(f"""
<style>
.stApp {{ background-color: {BG}; color: white; }}
div[data-testid="stMetricValue"] {{ font-size: 22px; font-weight: bold; }}
.block-container {{ padding-top: 1.2rem; }}
h1,h2,h3 {{ color: #f0f0f0; }}
.thdr {{
    text-align:center; padding:1rem; border-radius:12px;
    background:linear-gradient(135deg,{CARD},#22262e);
    border:1px solid #333; margin-bottom:.5rem;
}}
.thdr h2 {{ margin:0; font-size:1.4rem; }}
.thdr .wr {{ font-size:2.2rem; font-weight:800; }}
.vs {{ text-align:center; font-size:2rem; font-weight:900; color:{ACCENT}; padding-top:1.8rem; }}
</style>
""", unsafe_allow_html=True)

PLT = dict(
    template='plotly_dark',
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(color='#ccc', size=11),
    margin=dict(l=40, r=40, t=40, b=40),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
)


# ================================================================
# 2. DATA ENGINE
# ================================================================

@st.cache_data(ttl=3600)
def get_all_teams():
    return teams.get_teams()


@st.cache_data(ttl=600, show_spinner=False)
def load_team_log(team_id, season):
    time.sleep(0.6)
    log = teamgamelog.TeamGameLog(team_id=team_id, season=season).get_data_frames()[0]
    nums = ['PTS','FGM','FGA','FG3M','FG3A','FTM','FTA',
            'OREB','DREB','REB','AST','STL','BLK','TOV','PF','PLUS_MINUS']
    for c in nums:
        if c in log.columns:
            log[c] = pd.to_numeric(log[c], errors='coerce')
    log['GAME_DATE'] = pd.to_datetime(log['GAME_DATE'])
    log['POSS'] = log['FGA'] + 0.44*log['FTA'] - log['OREB'] + log['TOV']
    log['ORTG'] = (log['PTS'] / log['POSS'].replace(0,1)) * 100
    log['eFG%'] = ((log['FGM'] + 0.5*log['FG3M']) / log['FGA'].replace(0,1)) * 100
    log['TOV%'] = (log['TOV'] / log['POSS'].replace(0,1)) * 100
    log['FTr']  = log['FTA'] / log['FGA'].replace(0,1)
    log['2PM']  = log['FGM'] - log['FG3M']
    log['2PA']  = log['FGA'] - log['FG3A']
    return log


@st.cache_data(ttl=600, show_spinner=False)
def get_players(team_id, season):
    time.sleep(0.6)
    try:
        df = leaguedashplayerstats.LeagueDashPlayerStats(
            team_id_nullable=team_id, season=season
        ).get_data_frames()[0]
        df['2PM'] = df['FGM'] - df['FG3M']
        df['2PA'] = df['FGA'] - df['FG3A']
        df['2P%'] = (df['2PM'] / df['2PA'].replace(0,1) * 100).round(1)
        df['3P%'] = (df['FG3_PCT'] * 100).round(1)
        df['FT%'] = (df['FT_PCT'] * 100).round(1)
        df['FG%'] = (df['FG_PCT'] * 100).round(1)
        df['FTr'] = (df['FTA'] / df['FGA'].replace(0,1)).round(3)
        return df.sort_values('PTS', ascending=False)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_shot_chart(team_id, season):
    time.sleep(0.6)
    try:
        return shotchartdetail.ShotChartDetail(
            team_id=team_id, player_id=0,
            season_nullable=season,
            context_measure_simple='FGA',
            season_type_all_star='Regular Season'
        ).get_data_frames()[0]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_head_to_head(team_id, vs_team_id):
    time.sleep(0.6)
    try:
        df = leaguegamefinder.LeagueGameFinder(
            team_id_nullable=team_id,
            vs_team_id_nullable=vs_team_id,
            season_type_nullable='Regular Season',
            league_id_nullable='00'
        ).get_data_frames()[0]
        df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
        for c in ['PTS','AST','REB','FGM','FGA','FG3M','FG3A','FTM','FTA','TOV','STL','BLK','PLUS_MINUS']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('GAME_DATE', ascending=False)
    except Exception:
        return pd.DataFrame()


def filter_games(df, span, loc='All'):
    f = df.copy()
    if loc == 'Home':
        f = f[f['MATCHUP'].str.contains(' vs. ')]
    elif loc == 'Away':
        f = f[f['MATCHUP'].str.contains(' @ ')]
    if "Last" in span:
        try:
            n = int([s for s in span.split() if s.isdigit()][0])
            f = f.head(n)
        except (IndexError, ValueError):
            pass
    return f


def agg(df):
    if df.empty:
        return {k: 0 for k in ['PTS','REB','AST','STL','BLK','TOV','FGM','FGA',
            'FG3M','FG3A','FTM','FTA','POSS','ORTG','eFG%','TS%','3P%','FG%',
            'FT%','TOV%','FTr','OREB','DREB','PLUS_MINUS','Win_Rate','Games',
            '2PM','2PA','2P%']}
    fga=df['FGA'].sum() or 1; fta=df['FTA'].sum() or 1
    fg3a=df['FG3A'].sum() or 1; tpa=df['2PA'].sum() or 1
    return {
        'PTS':df['PTS'].mean(), 'REB':df['REB'].mean(), 'AST':df['AST'].mean(),
        'STL':df['STL'].mean(), 'BLK':df['BLK'].mean(), 'TOV':df['TOV'].mean(),
        'FGM':df['FGM'].mean(), 'FGA':df['FGA'].mean(),
        'FG3M':df['FG3M'].mean(), 'FG3A':df['FG3A'].mean(),
        'FTM':df['FTM'].mean(), 'FTA':df['FTA'].mean(),
        'OREB':df['OREB'].mean(), 'DREB':df['DREB'].mean(),
        '2PM':df['2PM'].mean(), '2PA':df['2PA'].mean(),
        '2P%': df['2PM'].sum()/tpa*100,
        'POSS':df['POSS'].mean(), 'ORTG':df['ORTG'].mean(),
        'eFG%':(df['FGM'].sum()+0.5*df['FG3M'].sum())/fga*100,
        'TS%':df['PTS'].sum()/(2*(fga+0.44*fta))*100,
        '3P%':df['FG3M'].sum()/fg3a*100,
        'FG%':df['FGM'].sum()/fga*100,
        'FT%':df['FTM'].sum()/fta*100,
        'TOV%':df['TOV'].sum()/(df['POSS'].sum() or 1)*100,
        'FTr':fta/fga,
        'PLUS_MINUS':df['PLUS_MINUS'].mean() if 'PLUS_MINUS' in df.columns else 0,
        'Win_Rate':(df['WL']=='W').mean()*100,
        'Games':len(df),
    }


# ================================================================
# 3. COURT DRAWING (matplotlib)
# ================================================================

def draw_court(ax, color='#cccccc', lw=1.2):
    ax.add_patch(Circle((0,0),7.5,lw=lw,edgecolor=color,facecolor='none'))
    ax.plot([-30,30],[-7.5,-7.5],lw=lw,color=color)
    ax.add_patch(Rectangle((-80,-47.5),160,190,lw=lw,edgecolor=color,facecolor='none'))
    ax.add_patch(Rectangle((-60,-47.5),120,190,lw=lw,edgecolor=color,facecolor='none'))
    ax.add_patch(Arc((0,142.5),120,120,theta1=0,theta2=180,lw=lw,color=color))
    ax.add_patch(Arc((0,142.5),120,120,theta1=180,theta2=360,lw=lw,color=color,ls='--',alpha=.3))
    ax.add_patch(Arc((0,0),80,80,theta1=0,theta2=180,lw=lw,color=color))
    ax.plot([-220,-220],[-47.5,92.5],lw=lw,color=color)
    ax.plot([220,220],[-47.5,92.5],lw=lw,color=color)
    ax.add_patch(Arc((0,0),475,475,theta1=22,theta2=158,lw=lw,color=color))
    ax.add_patch(Arc((0,422.5),120,120,theta1=180,theta2=0,lw=lw,color=color))
    ax.plot([-250,250],[422.5,422.5],lw=lw,color=color)
    ax.plot([-250,-250],[-47.5,422.5],lw=lw,color=color)
    ax.plot([250,250],[-47.5,422.5],lw=lw,color=color)
    ax.plot([-250,250],[-47.5,-47.5],lw=lw,color=color)
    ax.set_xlim(-260,260); ax.set_ylim(-60,440)
    ax.set_aspect('equal'); ax.axis('off')


def plot_shot_chart(shots_df, team_name, bg=BG):
    fig,ax = plt.subplots(figsize=(6,5.5), facecolor=bg)
    ax.set_facecolor(bg)
    draw_court(ax)
    if shots_df.empty:
        ax.text(0,200,"No shot data available",ha='center',va='center',fontsize=14,color='#888')
    else:
        missed = shots_df[shots_df['SHOT_MADE_FLAG']==0]
        made   = shots_df[shots_df['SHOT_MADE_FLAG']==1]
        ax.scatter(missed['LOC_X'],missed['LOC_Y'],c='#ff4444',marker='x',s=10,alpha=.35,linewidths=.6,label='Missed')
        ax.scatter(made['LOC_X'],made['LOC_Y'],c='#44ff44',marker='o',s=12,alpha=.45,edgecolors='none',label='Made')
        total=len(shots_df); mc=len(made); pct=mc/total*100 if total else 0
        ax.legend(loc='upper right',fontsize=8,framealpha=.3,labelcolor='white',facecolor='#222')
        ax.set_title(f"{team_name}  —  {mc}/{total} ({pct:.1f}%)",color='white',fontsize=12,fontweight='bold',pad=10)
    plt.tight_layout()
    return fig


# ================================================================
# 4. SIDEBAR
# ================================================================

st.sidebar.markdown("## 🏀 NBA Scouting Pro")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", [
    "📊 Overview",
    "🧠 Advanced Metrics",
    "🌟 Top Players & Shooters",
    "🎯 Shot Chart & Positions",
    "📈 Game Analysis",
    "⚔️ Head-to-Head History",
], label_visibility="collapsed")

st.sidebar.markdown("---")
st.sidebar.subheader("Matchup")

all_teams = get_all_teams()
tnames = sorted([t['full_name'] for t in all_teams])

team_a_name = st.sidebar.selectbox("🏠 Home Team", tnames,
    index=tnames.index("San Antonio Spurs") if "San Antonio Spurs" in tnames else 0)
team_b_name = st.sidebar.selectbox("✈️ Away Team", tnames,
    index=tnames.index("Denver Nuggets") if "Denver Nuggets" in tnames else 1)

team_a_id   = next(t['id'] for t in all_teams if t['full_name']==team_a_name)
team_b_id   = next(t['id'] for t in all_teams if t['full_name']==team_b_name)
team_a_abbr = next(t['abbreviation'] for t in all_teams if t['full_name']==team_a_name)
team_b_abbr = next(t['abbreviation'] for t in all_teams if t['full_name']==team_b_name)

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

seasons_list = ['2024-25','2023-24','2022-23','2021-22','2020-21']
sel_season = st.sidebar.selectbox("Season", seasons_list, index=0)
game_span  = st.sidebar.selectbox("Game Span", ['All Season','Last 20 Games','Last 10 Games','Last 5 Games'])
loc_filter = st.sidebar.selectbox("Location", ['All','Home','Away'])

st.sidebar.caption(f"📅 {sel_season} · {game_span} · {loc_filter}")


# ================================================================
# 5. LOAD CORE DATA
# ================================================================

with st.spinner(f'Loading {sel_season} data…'):
    log_a = load_team_log(team_a_id, sel_season)
    log_b = load_team_log(team_b_id, sel_season)

df_a = filter_games(log_a, game_span, loc_filter)
df_b = filter_games(log_b, game_span, loc_filter)
sa = agg(df_a)
sb = agg(df_b)


# ================================================================
# SHARED HEADER
# ================================================================

def header():
    c1,c2,c3 = st.columns([2,1,2])
    with c1:
        st.markdown(f"""<div class='thdr'>
            <h2 style='color:{C_A}'>{team_a_name}</h2>
            <div class='wr' style='color:{C_A}'>{sa['Win_Rate']:.1f}%</div>
            <div style='color:#999'>{sa['Games']:.0f} games · Win Rate</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='vs'>VS</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class='thdr'>
            <h2 style='color:{C_B}'>{team_b_name}</h2>
            <div class='wr' style='color:{C_B}'>{sb['Win_Rate']:.1f}%</div>
            <div style='color:#999'>{sb['Games']:.0f} games · Win Rate</div>
        </div>""", unsafe_allow_html=True)
    st.markdown("---")


# ================================================================
# PAGE 1 — OVERVIEW
# ================================================================

def pg_overview():
    header()
    cols = st.columns(6)
    for col,(label,k,b) in zip(cols,[
        ("Points",'PTS','h'),("Rebounds",'REB','h'),("Assists",'AST','h'),
        ("Steals",'STL','h'),("Blocks",'BLK','h'),("Turnovers",'TOV','l')]):
        d = sa[k]-sb[k]
        col.metric(label, f"{sa[k]:.1f}", f"{d:+.1f}", delta_color="inverse" if b=='l' else "normal")

    left, right = st.columns([3,2])
    with left:
        st.markdown("### Scoring Trend")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_a['GAME_DATE'],y=df_a['PTS'],mode='lines+markers',
            name=team_a_abbr, line=dict(color=C_A,width=2), marker=dict(size=4)))
        fig.add_trace(go.Scatter(x=df_b['GAME_DATE'],y=df_b['PTS'],mode='lines+markers',
            name=team_b_abbr, line=dict(color=C_B,width=2,dash='dash'), marker=dict(size=4)))
        fig.update_layout(**PLT, height=370, hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("### Scoring Breakdown")
        labs = ['2PT FG','3PT FG','Free Throws']
        v_a = [(sa['FGM']-sa['FG3M'])*2, sa['FG3M']*3, sa['FTM']]
        v_b = [(sb['FGM']-sb['FG3M'])*2, sb['FG3M']*3, sb['FTM']]
        fig = make_subplots(1,2,specs=[[{"type":"pie"},{"type":"pie"}]],
                            subplot_titles=[team_a_abbr, team_b_abbr])
        fig.add_trace(go.Pie(labels=labs,values=v_a,marker_colors=['#66bb6a','#43a047','#2e7d32'],
            textinfo='percent',hole=.4), 1,1)
        fig.add_trace(go.Pie(labels=labs,values=v_b,marker_colors=['#42a5f5','#1e88e5','#1565c0'],
            textinfo='percent',hole=.4), 1,2)
        fig.update_layout(**PLT, height=370, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Home vs Away Performance")
    ha = agg(filter_games(log_a,game_span,'Home'))
    aa = agg(filter_games(log_a,game_span,'Away'))
    hb = agg(filter_games(log_b,game_span,'Home'))
    ab_ = agg(filter_games(log_b,game_span,'Away'))
    ms = ['PTS','REB','AST','ORTG']
    fig = make_subplots(1,len(ms),subplot_titles=ms)
    for i,m in enumerate(ms,1):
        show = (i==1)
        fig.add_trace(go.Bar(name=f'{team_a_abbr} Home' if show else None,x=[m],y=[ha[m]],
            marker_color=C_A,showlegend=show,legendgroup='ah'),1,i)
        fig.add_trace(go.Bar(name=f'{team_a_abbr} Away' if show else None,x=[m],y=[aa[m]],
            marker_color=C_A,opacity=.5,showlegend=show,legendgroup='aa'),1,i)
        fig.add_trace(go.Bar(name=f'{team_b_abbr} Home' if show else None,x=[m],y=[hb[m]],
            marker_color=C_B,showlegend=show,legendgroup='bh'),1,i)
        fig.add_trace(go.Bar(name=f'{team_b_abbr} Away' if show else None,x=[m],y=[ab_[m]],
            marker_color=C_B,opacity=.5,showlegend=show,legendgroup='ba'),1,i)
    fig.update_layout(**PLT, height=350, barmode='group')
    st.plotly_chart(fig, use_container_width=True)


# ================================================================
# PAGE 2 — ADVANCED METRICS
# ================================================================

def pg_advanced():
    header()
    cols = st.columns(6)
    for col,(label,k,b,s) in zip(cols,[
        ("Off. Rating",'ORTG','h',''),("True Shooting",'TS%','h','%'),
        ("eFG%",'eFG%','h','%'),("3P%",'3P%','h','%'),
        ("Pace (Poss)",'POSS','h',''),("TOV Rate",'TOV%','l','%')]):
        d = sa[k]-sb[k]
        col.metric(label,f"{sa[k]:.1f}{s}",f"{d:+.1f}",delta_color="inverse" if b=='l' else "normal")

    left, right = st.columns(2)
    with left:
        st.markdown("### Efficiency Radar")
        cats = ['Off. Rating','True Shooting','eFG%','3-Point %','Free Throw Rate','Ball Security']
        def n(v,lo,hi): return max(0,min((v-lo)/(hi-lo),1))
        r_a = [n(sa['ORTG'],90,125),n(sa['TS%'],45,65),n(sa['eFG%'],42,58),
               n(sa['3P%'],28,42),n(sa['FTr'],.15,.35),n(100-sa['TOV%'],80,92)]
        r_b = [n(sb['ORTG'],90,125),n(sb['TS%'],45,65),n(sb['eFG%'],42,58),
               n(sb['3P%'],28,42),n(sb['FTr'],.15,.35),n(100-sb['TOV%'],80,92)]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=r_a+[r_a[0]],theta=cats+[cats[0]],fill='toself',
            name=team_a_abbr,fillcolor='rgba(76,175,80,.2)',line_color=C_A))
        fig.add_trace(go.Scatterpolar(r=r_b+[r_b[0]],theta=cats+[cats[0]],fill='toself',
            name=team_b_abbr,fillcolor='rgba(33,150,243,.2)',line_color=C_B))
        fig.update_layout(**PLT,height=420,
            polar=dict(bgcolor='rgba(0,0,0,0)',
                radialaxis=dict(visible=True,range=[0,1],showticklabels=False,gridcolor='#333'),
                angularaxis=dict(gridcolor='#333')))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("### Four Factors (Dean Oliver)")
        st.caption("The four key factors that determine winning.")
        fk = ['eFG%','TOV%','OREB','FTr']
        fl = ['eFG%','Turnover %','Off. Rebounds','FT Rate']
        fig = go.Figure()
        fig.add_trace(go.Bar(y=fl,x=[sa[f] for f in fk],orientation='h',name=team_a_abbr,
            marker_color=C_A,text=[f"{sa[f]:.1f}" for f in fk],textposition='auto'))
        fig.add_trace(go.Bar(y=fl,x=[sb[f] for f in fk],orientation='h',name=team_b_abbr,
            marker_color=C_B,text=[f"{sb[f]:.1f}" for f in fk],textposition='auto'))
        fig.update_layout(**PLT, height=420, barmode='group')
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Shooting Splits Comparison")
    ss = ['FG%','2P%','3P%','FT%','TS%','eFG%']
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ss,y=[sa[s] for s in ss],name=team_a_abbr,marker_color=C_A,
        text=[f"{sa[s]:.1f}%" for s in ss],textposition='outside'))
    fig.add_trace(go.Bar(x=ss,y=[sb[s] for s in ss],name=team_b_abbr,marker_color=C_B,
        text=[f"{sb[s]:.1f}%" for s in ss],textposition='outside'))
    mx = max(max(sa[s] for s in ss), max(sb[s] for s in ss))
    fig.update_layout(**PLT, height=350, barmode='group', yaxis=dict(range=[0,mx+12]))
    st.plotly_chart(fig, use_container_width=True)


# ================================================================
# PAGE 3 — TOP PLAYERS & SHOOTERS
# ================================================================

def pg_players():
    header()
    with st.spinner("Loading player stats…"):
        pa = get_players(team_a_id, sel_season)
        pb = get_players(team_b_id, sel_season)

    # ---- Top Scorers ----
    st.markdown("### 🏆 Top Scorers")
    c1,c2 = st.columns(2)
    base_cols = ['PLAYER_NAME','GP','PTS','AST','REB','STL','BLK','FG%']
    for col,p,name in [(c1,pa,team_a_name),(c2,pb,team_b_name)]:
        with col:
            st.markdown(f"**{name}**")
            if not p.empty:
                show = [c for c in base_cols if c in p.columns]
                st.dataframe(p.head(8)[show], use_container_width=True, hide_index=True)
            else:
                st.warning("Data unavailable.")

    if pa.empty or pb.empty:
        return

    # ---- Best 3-Point Shooters ----
    st.markdown("### 🎯 Best 3-Point Shooters (min 1 3PA/game)")
    c1,c2 = st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            shooters = p[p['FG3A']>=1].sort_values('FG3_PCT',ascending=False).head(5)
            if not shooters.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=shooters['PLAYER_NAME'], x=shooters['3P%'], orientation='h',
                    marker_color=color, text=shooters.apply(
                        lambda r: f"{r['3P%']:.1f}%  ({r['FG3M']:.1f}/{r['FG3A']:.1f})", axis=1),
                    textposition='outside'))
                fig.update_layout(**PLT, height=280, title=dict(text=f'{abbr} — 3PT Leaders',font_size=13),
                    xaxis=dict(range=[0, shooters['3P%'].max()+15]),
                    yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig, use_container_width=True)

    # ---- Most Efficient Scorers (TS%) ----
    st.markdown("### 🔥 Most Efficient Scorers (True Shooting %)")
    c1,c2 = st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            eff = p[p['FGA']>=3].copy()
            if not eff.empty:
                eff['TS%'] = (eff['PTS'] / (2*(eff['FGA']+0.44*eff['FTA']).replace(0,1))*100).round(1)
                eff = eff.sort_values('TS%',ascending=False).head(5)
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=eff['PLAYER_NAME'], x=eff['TS%'], orientation='h',
                    marker_color=color, text=eff['TS%'].apply(lambda x: f"{x:.1f}%"),
                    textposition='outside'))
                fig.update_layout(**PLT, height=280, title=dict(text=f'{abbr} — TS% Leaders',font_size=13),
                    xaxis=dict(range=[0, eff['TS%'].max()+12]),
                    yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig, use_container_width=True)

    # ---- Top Rebounders ----
    st.markdown("### 💪 Top Rebounders")
    c1,c2 = st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            reb = p.sort_values('REB',ascending=False).head(5)
            if not reb.empty and 'OREB' in reb.columns and 'DREB' in reb.columns:
                fig = go.Figure()
                fig.add_trace(go.Bar(y=reb['PLAYER_NAME'],x=reb['OREB'],orientation='h',
                    name='Offensive',marker_color=color))
                fig.add_trace(go.Bar(y=reb['PLAYER_NAME'],x=reb['DREB'],orientation='h',
                    name='Defensive',marker_color=color,opacity=.5))
                fig.update_layout(**PLT, height=280, barmode='stack',
                    title=dict(text=f'{abbr} — Rebound Leaders',font_size=13),
                    yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig, use_container_width=True)

    # ---- 2-Point FG% by Player ----
    st.markdown("### 🔢 2-Point Field Goal % by Player (min 2 2PA/game)")
    c1,c2 = st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            tp = p[p['2PA']>=2].sort_values('2P%',ascending=False).head(5)
            if not tp.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=tp['PLAYER_NAME'], x=tp['2P%'], orientation='h',
                    marker_color=color,
                    text=tp.apply(lambda r: f"{r['2P%']:.1f}%  ({r['2PM']:.1f}/{r['2PA']:.1f})", axis=1),
                    textposition='outside'))
                fig.update_layout(**PLT, height=280, title=dict(text=f'{abbr} — 2PT% Leaders',font_size=13),
                    xaxis=dict(range=[0, tp['2P%'].max()+15]),
                    yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig, use_container_width=True)

    # ---- Free Throw Rate by Player ----
    st.markdown("### 🎪 Free Throw Rate by Player (FTA / FGA)")
    st.caption("Higher FTr means the player draws more fouls relative to their shot attempts.")
    c1,c2 = st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            ft = p[p['FGA']>=2].sort_values('FTr',ascending=False).head(6)
            if not ft.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=ft['PLAYER_NAME'], x=ft['FTr'], orientation='h',
                    marker_color=color,
                    text=ft.apply(lambda r: f"{r['FTr']:.3f}  ({r['FTM']:.1f}/{r['FTA']:.1f} FT)", axis=1),
                    textposition='outside'))
                fig.update_layout(**PLT, height=300, title=dict(text=f'{abbr} — Free Throw Rate',font_size=13),
                    xaxis=dict(range=[0, ft['FTr'].max()+.15]),
                    yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig, use_container_width=True)

    # ---- Free Throw Accuracy by Player ----
    st.markdown("### 🏹 Free Throw Accuracy by Player (min 1 FTA/game)")
    c1,c2 = st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            ftp = p[p['FTA']>=1].sort_values('FT_PCT',ascending=False).head(6)
            if not ftp.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=ftp['PLAYER_NAME'], x=ftp['FT%'], orientation='h',
                    marker_color=color,
                    text=ftp['FT%'].apply(lambda x: f"{x:.1f}%"), textposition='outside'))
                fig.update_layout(**PLT, height=300, title=dict(text=f'{abbr} — FT% Leaders',font_size=13),
                    xaxis=dict(range=[0, 105]),
                    yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig, use_container_width=True)

    # ---- Star Radar ----
    st.markdown("### ⭐ Star Player Comparison")
    star_a = pa.iloc[0]; star_b = pb.iloc[0]
    cats=['Points','Assists','Rebounds','Steals','Blocks']
    keys=['PTS','AST','REB','STL','BLK']
    maxes = {'PTS':35,'AST':12,'REB':14,'STL':3,'BLK':3.5}
    def nr(row): return [min(row[k]/maxes[k],1) if k in row.index else 0 for k in keys]
    ra=nr(star_a); rb=nr(star_b)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=ra+[ra[0]],theta=cats+[cats[0]],fill='toself',
        name=star_a.get('PLAYER_NAME','?'),fillcolor='rgba(76,175,80,.2)',line_color=C_A))
    fig.add_trace(go.Scatterpolar(r=rb+[rb[0]],theta=cats+[cats[0]],fill='toself',
        name=star_b.get('PLAYER_NAME','?'),fillcolor='rgba(33,150,243,.2)',line_color=C_B))
    fig.update_layout(**PLT,height=420,
        polar=dict(bgcolor='rgba(0,0,0,0)',
            radialaxis=dict(visible=True,range=[0,1],showticklabels=False,gridcolor='#333'),
            angularaxis=dict(gridcolor='#333')))
    st.plotly_chart(fig, use_container_width=True)


# ================================================================
# PAGE 4 — SHOT CHART & POSITIONS
# ================================================================

def pg_shots():
    header()
    st.subheader(f"Shot Chart — {sel_season}")

    with st.spinner("Loading shot data (may take a moment)…"):
        shots_a = get_shot_chart(team_a_id, sel_season)
        shots_b = get_shot_chart(team_b_id, sel_season)

    c1,c2 = st.columns(2)
    with c1:
        f = plot_shot_chart(shots_a, team_a_name); st.pyplot(f); plt.close(f)
    with c2:
        f = plot_shot_chart(shots_b, team_b_name); st.pyplot(f); plt.close(f)

    if shots_a.empty and shots_b.empty:
        st.warning("No shot chart data available for this season.")
        return

    # Zone breakdown
    st.markdown("### Shot Zone Breakdown")
    c1,c2 = st.columns(2)
    for col,shots,name,color in [(c1,shots_a,team_a_name,C_A),(c2,shots_b,team_b_name,C_B)]:
        with col:
            if not shots.empty and 'SHOT_ZONE_BASIC' in shots.columns:
                zs = shots.groupby('SHOT_ZONE_BASIC').agg(
                    Att=('SHOT_MADE_FLAG','count'), Made=('SHOT_MADE_FLAG','sum')).reset_index()
                zs['Pct'] = (zs['Made']/zs['Att']*100).round(1)
                zs = zs.sort_values('Att',ascending=True)
                fig = go.Figure()
                fig.add_trace(go.Bar(y=zs['SHOT_ZONE_BASIC'],x=zs['Att'],orientation='h',
                    name='Attempts',marker_color=color,opacity=.35,text=zs['Att'],textposition='inside'))
                fig.add_trace(go.Bar(y=zs['SHOT_ZONE_BASIC'],x=zs['Made'],orientation='h',
                    name='Makes',marker_color=color,
                    text=zs.apply(lambda r:f"{r['Made']} ({r['Pct']}%)",axis=1),textposition='inside'))
                fig.update_layout(**PLT,height=350,barmode='overlay',title=dict(text=name,font_size=13))
                st.plotly_chart(fig, use_container_width=True)

    # Player preferred shot zones
    st.markdown("### 🎯 Preferred Shooting Positions by Player")
    st.caption("Top 5 scorers — where they take their shots from.")

    with st.spinner("Loading player stats…"):
        pa = get_players(team_a_id, sel_season)
        pb = get_players(team_b_id, sel_season)

    c1,c2 = st.columns(2)
    for col,shots,players,name,color in [
        (c1,shots_a,pa,team_a_name,C_A),(c2,shots_b,pb,team_b_name,C_B)]:
        with col:
            if not players.empty and not shots.empty and 'PLAYER_NAME' in shots.columns and 'SHOT_ZONE_BASIC' in shots.columns:
                top5 = players.head(5)['PLAYER_NAME'].tolist()
                ps = shots[shots['PLAYER_NAME'].isin(top5)]
                if not ps.empty:
                    pz = ps.groupby(['PLAYER_NAME','SHOT_ZONE_BASIC']).agg(
                        Att=('SHOT_MADE_FLAG','count')).reset_index()
                    fig = px.bar(pz, y='PLAYER_NAME', x='Att', color='SHOT_ZONE_BASIC',
                        orientation='h', title=f'{name} — Shot Zone Distribution',
                        color_discrete_sequence=px.colors.sequential.Teal)
                    fig.update_layout(**PLT, height=380, barmode='stack',
                        yaxis=dict(autorange='reversed'))
                    st.plotly_chart(fig, use_container_width=True)

    # Shot distance distribution
    st.markdown("### Shot Distance Distribution")
    has_dist = ('SHOT_DISTANCE' in shots_a.columns if not shots_a.empty else False) and \
               ('SHOT_DISTANCE' in shots_b.columns if not shots_b.empty else False)
    if has_dist:
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=shots_a['SHOT_DISTANCE'],nbinsx=30,
            name=team_a_abbr,marker_color=C_A,opacity=.6))
        fig.add_trace(go.Histogram(x=shots_b['SHOT_DISTANCE'],nbinsx=30,
            name=team_b_abbr,marker_color=C_B,opacity=.6))
        fig.update_layout(**PLT,height=350,barmode='overlay',
            xaxis_title='Distance (ft)',yaxis_title='Frequency')
        st.plotly_chart(fig, use_container_width=True)

    # Accuracy by distance
    st.markdown("### Accuracy by Distance")
    c1,c2 = st.columns(2)
    for col,shots,abbr,color in [(c1,shots_a,team_a_abbr,C_A),(c2,shots_b,team_b_abbr,C_B)]:
        with col:
            if not shots.empty and 'SHOT_DISTANCE' in shots.columns:
                bins = [0,3,10,16,22,28,50]
                labels_d = ['0-3 ft','3-10 ft','10-16 ft','16-22 ft','22-28 ft','28+ ft']
                sc = shots.copy()
                sc['dist_bin'] = pd.cut(sc['SHOT_DISTANCE'],bins=bins,labels=labels_d,right=False)
                dg = sc.groupby('dist_bin',observed=True).agg(
                    Att=('SHOT_MADE_FLAG','count'),Made=('SHOT_MADE_FLAG','sum')).reset_index()
                dg['Pct'] = (dg['Made']/dg['Att'].replace(0,1)*100).round(1)
                fig = go.Figure()
                fig.add_trace(go.Bar(x=dg['dist_bin'],y=dg['Pct'],marker_color=color,
                    text=dg.apply(lambda r:f"{r['Pct']}%\n({r['Made']}/{r['Att']})",axis=1),
                    textposition='outside'))
                fig.update_layout(**PLT,height=300,title=dict(text=f'{abbr} — FG% by Distance',font_size=13),
                    yaxis=dict(range=[0,100]))
                st.plotly_chart(fig, use_container_width=True)


# ================================================================
# PAGE 5 — GAME ANALYSIS
# ================================================================

def pg_analysis():
    header()

    st.markdown("### Point Differential per Game")
    for df,abbr,color in [(df_a,team_a_abbr,C_A),(df_b,team_b_abbr,C_B)]:
        if 'PLUS_MINUS' in df.columns and not df.empty:
            cs = [color if v>=0 else '#ff5252' for v in df['PLUS_MINUS']]
            fig = go.Figure(go.Bar(x=df['GAME_DATE'],y=df['PLUS_MINUS'],marker_color=cs,name=abbr))
            fig.update_layout(**PLT,height=250,title=dict(text=abbr,font_size=13))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Rolling Averages (5-game window)")
    c1,c2 = st.columns(2)
    for col,df,abbr in [(c1,df_a,team_a_abbr),(c2,df_b,team_b_abbr)]:
        with col:
            if len(df)>=5:
                ds = df.sort_values('GAME_DATE')
                fig = go.Figure()
                for stat,dash in [('PTS','solid'),('REB','dash'),('AST','dot')]:
                    fig.add_trace(go.Scatter(x=ds['GAME_DATE'],y=ds[stat].rolling(5,min_periods=2).mean(),
                        mode='lines',name=stat,line=dict(dash=dash,width=2)))
                fig.update_layout(**PLT,height=350,title=dict(text=f'{abbr} — Rolling Avg',font_size=13))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"Not enough games for {abbr}.")

    st.markdown("### Win/Loss Sequence")
    c1,c2 = st.columns(2)
    for col,df,abbr,color in [(c1,df_a,team_a_abbr,C_A),(c2,df_b,team_b_abbr,C_B)]:
        with col:
            if not df.empty:
                ds = df.sort_values('GAME_DATE')
                sv = [1 if w=='W' else -1 for w in ds['WL']]
                cs = [color if v>0 else '#ff5252' for v in sv]
                fig = go.Figure(go.Bar(x=ds['GAME_DATE'],y=sv,marker_color=cs,name=abbr))
                fig.update_layout(**PLT,height=250,title=dict(text=f'{abbr} — W/L',font_size=13),
                    yaxis=dict(tickvals=[-1,1],ticktext=['L','W']))
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Consistency Analysis (Lower = More Consistent)")
    cstats = ['PTS','REB','AST','TOV']
    std_a = [df_a[s].std() if not df_a.empty else 0 for s in cstats]
    std_b = [df_b[s].std() if not df_b.empty else 0 for s in cstats]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=cstats,y=std_a,name=team_a_abbr,marker_color=C_A,
        text=[f"{v:.1f}" for v in std_a],textposition='outside'))
    fig.add_trace(go.Bar(x=cstats,y=std_b,name=team_b_abbr,marker_color=C_B,
        text=[f"{v:.1f}" for v in std_b],textposition='outside'))
    fig.update_layout(**PLT,height=350,barmode='group',yaxis_title='Std Dev')
    st.plotly_chart(fig, use_container_width=True)


# ================================================================
# PAGE 6 — HEAD-TO-HEAD HISTORY
# ================================================================

def pg_h2h():
    header()
    st.subheader(f"⚔️ {team_a_name} vs {team_b_name} — All-Time Regular Season")

    with st.spinner("Loading head-to-head history…"):
        h2h = get_head_to_head(team_a_id, team_b_id)

    if h2h.empty:
        st.warning("No head-to-head data found.")
        return

    wins = (h2h['WL']=='W').sum()
    losses = (h2h['WL']=='L').sum()
    total = len(h2h)

    c1,c2,c3 = st.columns(3)
    c1.metric("Total Games", total)
    c2.metric(f"{team_a_abbr} Wins", wins)
    c3.metric(f"{team_a_abbr} Losses", losses)

    left,right = st.columns([1,2])
    with left:
        fig = go.Figure(go.Pie(
            labels=[team_a_abbr, team_b_abbr], values=[wins, losses],
            marker_colors=[C_A, C_B], hole=.5, textinfo='label+value+percent'))
        fig.update_layout(**PLT, height=320, title=dict(text='All-Time Record',font_size=14),
            showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("### Average Stats in Matchups")
        avg_keys = ['PTS','AST','REB','STL','BLK','TOV']
        vals = [h2h[k].mean() for k in avg_keys if k in h2h.columns]
        labels = [k for k in avg_keys if k in h2h.columns]
        fig = go.Figure(go.Bar(x=labels, y=vals, marker_color=C_A,
            text=[f"{v:.1f}" for v in vals], textposition='outside'))
        fig.update_layout(**PLT, height=320,
            title=dict(text=f'{team_a_abbr} avg when playing {team_b_abbr}',font_size=13))
        st.plotly_chart(fig, use_container_width=True)

    # Season-by-season
    st.markdown("### Season-by-Season Record")
    if 'SEASON_ID' in h2h.columns:
        szn = h2h.copy()
        szn['Season'] = szn['SEASON_ID'].astype(str).str[-4:].astype(int)
        szn['Season_Label'] = szn['Season'].apply(lambda y: f"{y}-{str(y+1)[-2:]}")
        by_season = szn.groupby('Season_Label').agg(
            Games=('WL','count'),
            Wins=('WL', lambda x: (x=='W').sum()),
        ).reset_index()
        by_season['Losses'] = by_season['Games'] - by_season['Wins']
        by_season = by_season.sort_values('Season_Label')
        # Show last 15 seasons
        by_season = by_season.tail(15)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=by_season['Season_Label'],y=by_season['Wins'],name='Wins',marker_color=C_A))
        fig.add_trace(go.Bar(x=by_season['Season_Label'],y=by_season['Losses'],name='Losses',marker_color='#ff5252'))
        fig.update_layout(**PLT,height=350,barmode='stack',xaxis_title='Season',yaxis_title='Games',
            title=dict(text=f'{team_a_abbr} record vs {team_b_abbr} by season',font_size=13))
        st.plotly_chart(fig, use_container_width=True)

    # Scoring trend
    st.markdown("### Scoring Trend Across Matchups")
    recent = h2h.head(30).sort_values('GAME_DATE')
    if not recent.empty and 'PTS' in recent.columns:
        fig = go.Figure()
        colors = [C_A if w=='W' else '#ff5252' for w in recent['WL']]
        fig.add_trace(go.Scatter(x=recent['GAME_DATE'], y=recent['PTS'], mode='lines+markers',
            marker=dict(color=colors, size=8), line=dict(color='#666',width=1),
            text=recent.apply(lambda r: f"{'W' if r['WL']=='W' else 'L'} — {r.get('MATCHUP','')}",axis=1),
            hoverinfo='text+y', name=team_a_abbr))
        fig.update_layout(**PLT, height=350,
            title=dict(text=f'{team_a_abbr} points in matchups (last 30)',font_size=13))
        st.plotly_chart(fig, use_container_width=True)

    # Point differential
    st.markdown("### Point Differential in Matchups")
    recent2 = h2h.head(30).sort_values('GAME_DATE')
    if not recent2.empty and 'PLUS_MINUS' in recent2.columns:
        cs = [C_A if v>=0 else '#ff5252' for v in recent2['PLUS_MINUS']]
        fig = go.Figure(go.Bar(x=recent2['GAME_DATE'],y=recent2['PLUS_MINUS'],marker_color=cs))
        fig.update_layout(**PLT,height=300,
            title=dict(text=f'{team_a_abbr} +/- vs {team_b_abbr} (last 30)',font_size=13))
        st.plotly_chart(fig, use_container_width=True)

    # Results table
    st.markdown("### Recent Match Results")
    display = h2h.head(20).copy()
    show_cols = ['GAME_DATE','MATCHUP','WL','PTS','REB','AST','FGM','FGA','FG3M','FG3A','FTM','FTA','PLUS_MINUS']
    show_cols = [c for c in show_cols if c in display.columns]
    display['GAME_DATE'] = display['GAME_DATE'].dt.strftime('%Y-%m-%d')
    st.dataframe(display[show_cols], use_container_width=True, hide_index=True)


# ================================================================
# 7. PAGE ROUTING
# ================================================================

if page == "📊 Overview":
    pg_overview()
elif page == "🧠 Advanced Metrics":
    pg_advanced()
elif page == "🌟 Top Players & Shooters":
    pg_players()
elif page == "🎯 Shot Chart & Positions":
    pg_shots()
elif page == "📈 Game Analysis":
    pg_analysis()
elif page == "⚔️ Head-to-Head History":
    pg_h2h()