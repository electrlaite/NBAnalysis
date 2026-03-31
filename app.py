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
    teamgamelog, leaguedashplayerstats, shotchartdetail,
    leaguegamefinder, boxscoresummaryv2, boxscoretraditionalv3,
)
from nba_api.stats.static import teams
import time

# ================================================================
# 1. PAGE CONFIG & STYLING
# ================================================================
st.set_page_config(page_title="NBA Scouting Report Pro", layout="wide",
                   page_icon="🏀", initial_sidebar_state="expanded")

C_A = "#4CAF50"; C_B = "#2196F3"; ACCENT = "#FEC524"
BG = "#0e1117"; CARD = "#1a1d23"

st.markdown(f"""<style>
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
.player-card {{
    text-align:center; background:{CARD}; border-radius:14px;
    padding:1.2rem; border:1px solid #333;
}}
.player-card img {{ border-radius:10px; width:180px; height:auto; }}
.player-card h3 {{ margin:.5rem 0 0; }}
</style>""", unsafe_allow_html=True)

PLT = dict(
    template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ccc', size=11),
    margin=dict(l=40, r=40, t=40, b=40),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
)

HEADSHOT_URL = "https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"


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
    poss = log['FGA'] + 0.44*log['FTA'] - log['OREB'] + log['TOV']
    log['POSS'] = poss
    log['ORTG'] = (log['PTS'] / poss.replace(0,1)) * 100
    log['eFG%'] = ((log['FGM'] + 0.5*log['FG3M']) / log['FGA'].replace(0,1)) * 100
    log['TOV%'] = (log['TOV'] / poss.replace(0,1)) * 100
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
        df['2P%'] = (df['2PM'] / df['2PA'].replace(0,1)*100).round(1)
        df['3P%'] = (df['FG3_PCT']*100).round(1)
        df['FT%'] = (df['FT_PCT']*100).round(1)
        df['FG%'] = (df['FG_PCT']*100).round(1)
        df['FTr'] = (df['FTA'] / df['FGA'].replace(0,1)).round(3)
        df['TS%'] = (df['PTS'] / (2*(df['FGA']+0.44*df['FTA']).replace(0,1))*100).round(1)
        return df.sort_values('PTS', ascending=False)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_shot_chart(team_id, season, player_id=0, game_id=''):
    time.sleep(0.6)
    try:
        return shotchartdetail.ShotChartDetail(
            team_id=team_id, player_id=player_id,
            season_nullable=season, context_measure_simple='FGA',
            season_type_all_star='Regular Season',
            game_id_nullable=game_id,
        ).get_data_frames()[0]
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_head_to_head(team_id, vs_team_id):
    time.sleep(0.6)
    try:
        df = leaguegamefinder.LeagueGameFinder(
            team_id_nullable=team_id, vs_team_id_nullable=vs_team_id,
            season_type_nullable='Regular Season', league_id_nullable='00'
        ).get_data_frames()[0]
        df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
        for c in ['PTS','AST','REB','FGM','FGA','FG3M','FG3A','FTM','FTA','TOV','STL','BLK','PLUS_MINUS']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('GAME_DATE', ascending=False)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_game_summary(game_id):
    """Fetch game summary with V2→V3 fallback. Normalizes column names."""
    time.sleep(0.6)
    result = {'summary': pd.DataFrame(), 'line_score': pd.DataFrame(), 'other_stats': pd.DataFrame()}

    # Try V2 first (works for seasons <= 2024-25)
    try:
        bs = boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id)
        dfs = bs.get_data_frames()
        # DF indices: 0=AvailableVideo 1=GameInfo 2=GameSummary
        #   3=InactivePlayers 4=LastMeeting 5=LineScore 6=Officials 7=OtherStats
        result['summary'] = dfs[2] if len(dfs) > 2 else pd.DataFrame()
        result['line_score'] = dfs[5] if len(dfs) > 5 else pd.DataFrame()
        result['other_stats'] = dfs[7] if len(dfs) > 7 else pd.DataFrame()
        if not result['line_score'].empty:
            return result
    except Exception:
        pass

    # Fallback: try V3 (for 2025-26+)
    try:
        from nba_api.stats.endpoints import boxscoresummaryv3
        bs3 = boxscoresummaryv3.BoxScoreSummaryV3(game_id=game_id)
        dfs3 = bs3.get_data_frames()
        # V3: 0=GameSummary 1=GameInfo 2=ArenaInfo 3=Officials
        #     4=LineScore 5=InactivePlayers 6=LastFiveMeetings 7=OtherStats
        ls = dfs3[4] if len(dfs3) > 4 else pd.DataFrame()
        os = dfs3[7] if len(dfs3) > 7 else pd.DataFrame()

        # Normalize V3 LineScore columns to V2 names
        if not ls.empty:
            rename_ls = {
                'period1Score':'PTS_QTR1','period2Score':'PTS_QTR2',
                'period3Score':'PTS_QTR3','period4Score':'PTS_QTR4',
                'score':'PTS','teamTricode':'TEAM_ABBREVIATION',
            }
            ls = ls.rename(columns={k:v for k,v in rename_ls.items() if k in ls.columns})

        # Normalize V3 OtherStats columns to V2 names
        if not os.empty:
            rename_os = {
                'teamTricode':'TEAM_ABBREVIATION',
                'pointsInThePaint':'PTS_PAINT','pointsSecondChance':'PTS_2ND_CHANCE',
                'pointsFastBreak':'PTS_FB','pointsFromTurnovers':'PTS_OFF_TO',
                'biggestLead':'LARGEST_LEAD','leadChanges':'LEAD_CHANGES','timesTied':'TIMES_TIED',
            }
            os = os.rename(columns={k:v for k,v in rename_os.items() if k in os.columns})

        result['line_score'] = ls
        result['other_stats'] = os
    except Exception:
        pass

    return result


@st.cache_data(ttl=600, show_spinner=False)
def get_game_boxscore(game_id):
    time.sleep(0.6)
    try:
        bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        dfs = bs.get_data_frames()
        return {
            'players': dfs[0] if len(dfs) > 0 else pd.DataFrame(),
            'teams': dfs[2] if len(dfs) > 2 else pd.DataFrame(),
        }
    except Exception:
        return {'players': pd.DataFrame(), 'teams': pd.DataFrame()}


def filter_games(df, span, loc='All'):
    f = df.copy()
    if loc == 'Home':   f = f[f['MATCHUP'].str.contains(' vs. ')]
    elif loc == 'Away': f = f[f['MATCHUP'].str.contains(' @ ')]
    if "Last" in span:
        try:
            n = int([s for s in span.split() if s.isdigit()][0])
            f = f.head(n)
        except (IndexError, ValueError): pass
    return f


def agg(df):
    if df.empty:
        return {k: 0 for k in ['PTS','REB','AST','STL','BLK','TOV','FGM','FGA',
            'FG3M','FG3A','FTM','FTA','POSS','ORTG','eFG%','TS%','3P%','FG%',
            'FT%','TOV%','FTr','OREB','DREB','PLUS_MINUS','Win_Rate','Games','2PM','2PA','2P%']}
    fga=df['FGA'].sum() or 1; fta=df['FTA'].sum() or 1
    fg3a=df['FG3A'].sum() or 1; tpa=df['2PA'].sum() or 1
    return {
        'PTS':df['PTS'].mean(),'REB':df['REB'].mean(),'AST':df['AST'].mean(),
        'STL':df['STL'].mean(),'BLK':df['BLK'].mean(),'TOV':df['TOV'].mean(),
        'FGM':df['FGM'].mean(),'FGA':df['FGA'].mean(),
        'FG3M':df['FG3M'].mean(),'FG3A':df['FG3A'].mean(),
        'FTM':df['FTM'].mean(),'FTA':df['FTA'].mean(),
        'OREB':df['OREB'].mean(),'DREB':df['DREB'].mean(),
        '2PM':df['2PM'].mean(),'2PA':df['2PA'].mean(),
        '2P%':df['2PM'].sum()/tpa*100,'POSS':df['POSS'].mean(),
        'ORTG':df['ORTG'].mean(),
        'eFG%':(df['FGM'].sum()+.5*df['FG3M'].sum())/fga*100,
        'TS%':df['PTS'].sum()/(2*(fga+.44*fta))*100,
        '3P%':df['FG3M'].sum()/fg3a*100,'FG%':df['FGM'].sum()/fga*100,
        'FT%':df['FTM'].sum()/fta*100,
        'TOV%':df['TOV'].sum()/(df['POSS'].sum() or 1)*100,
        'FTr':fta/fga,
        'PLUS_MINUS':df['PLUS_MINUS'].mean() if 'PLUS_MINUS' in df.columns else 0,
        'Win_Rate':(df['WL']=='W').mean()*100, 'Games':len(df),
    }


# ================================================================
# 3. COURT DRAWING
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
    ax.set_xlim(-260,260); ax.set_ylim(-60,440); ax.set_aspect('equal'); ax.axis('off')


def plot_shot_chart(shots_df, title_text, bg=BG, color_made='#44ff44', color_miss='#fc0303'):
    fig,ax = plt.subplots(figsize=(6,5.5), facecolor=bg)
    ax.set_facecolor(bg)
    draw_court(ax)
    if shots_df.empty:
        ax.text(0,200,"No shot data",ha='center',va='center',fontsize=14,color='#888')
    else:
        missed = shots_df[shots_df['SHOT_MADE_FLAG']==0]
        made   = shots_df[shots_df['SHOT_MADE_FLAG']==1]
        ax.scatter(missed['LOC_X'],missed['LOC_Y'],c=color_miss,marker='o',s=10,alpha=.35,linewidths=.6,label='Missed')
        ax.scatter(made['LOC_X'],made['LOC_Y'],c=color_made,marker='o',s=12,alpha=.45,edgecolors='none',label='Made')
        total=len(shots_df); mc=len(made); pct=mc/total*100 if total else 0
        ax.legend(loc='upper right',fontsize=8,framealpha=.3,labelcolor='white',facecolor='#222')
        ax.set_title(f"{title_text}  —  {mc}/{total} ({pct:.1f}%)",color='white',fontsize=11,fontweight='bold',pad=10)
    plt.tight_layout(); return fig


# ================================================================
# 4. SIDEBAR
# ================================================================

st.sidebar.markdown("## 🏀 NBA Scouting Pro")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navigate", [
    "📊 Overview", "🧠 Advanced Metrics", "🌟 Top Players & Shooters",
    "🎯 Shot Chart & Positions", "📈 Game Analysis",
    "⚔️ Head-to-Head History", "👤 Player Comparison", "🏟️ Single Game Breakdown",
], label_visibility="collapsed")

st.sidebar.markdown("---"); st.sidebar.subheader("Matchup")
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

st.sidebar.markdown("---"); st.sidebar.subheader("Filters")
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
sa = agg(df_a); sb = agg(df_b)


def header():
    c1,c2,c3 = st.columns([2,1,2])
    with c1:
        st.markdown(f"<div class='thdr'><h2 style='color:{C_A}'>{team_a_name}</h2>"
            f"<div class='wr' style='color:{C_A}'>{sa['Win_Rate']:.1f}%</div>"
            f"<div style='color:#999'>{sa['Games']:.0f} games · Win Rate</div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='vs'>VS</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='thdr'><h2 style='color:{C_B}'>{team_b_name}</h2>"
            f"<div class='wr' style='color:{C_B}'>{sb['Win_Rate']:.1f}%</div>"
            f"<div style='color:#999'>{sb['Games']:.0f} games · Win Rate</div></div>", unsafe_allow_html=True)
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
        d=sa[k]-sb[k]; col.metric(label,f"{sa[k]:.1f}",f"{d:+.1f}",delta_color="inverse" if b=='l' else "normal")

    left,right = st.columns([3,2])
    with left:
        st.markdown("### Scoring Trend")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_a['GAME_DATE'],y=df_a['PTS'],mode='lines+markers',
            name=team_a_abbr,line=dict(color=C_A,width=2),marker=dict(size=4)))
        fig.add_trace(go.Scatter(x=df_b['GAME_DATE'],y=df_b['PTS'],mode='lines+markers',
            name=team_b_abbr,line=dict(color=C_B,width=2,dash='dash'),marker=dict(size=4)))
        fig.update_layout(**PLT,height=370,hovermode='x unified')
        st.plotly_chart(fig,use_container_width=True)

    with right:
        st.markdown("### Scoring Breakdown")
        labs=['2PT FG','3PT FG','Free Throws']
        v_a=[(sa['FGM']-sa['FG3M'])*2,sa['FG3M']*3,sa['FTM']]
        v_b=[(sb['FGM']-sb['FG3M'])*2,sb['FG3M']*3,sb['FTM']]
        fig=make_subplots(1,2,specs=[[{"type":"pie"},{"type":"pie"}]],subplot_titles=[team_a_abbr,team_b_abbr])
        fig.add_trace(go.Pie(labels=labs,values=v_a,marker_colors=['#66bb6a','#43a047','#2e7d32'],textinfo='percent',hole=.4),1,1)
        fig.add_trace(go.Pie(labels=labs,values=v_b,marker_colors=['#42a5f5','#1e88e5','#1565c0'],textinfo='percent',hole=.4),1,2)
        fig.update_layout(**PLT,height=370,showlegend=True)
        st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Home vs Away Performance")
    ha=agg(filter_games(log_a,game_span,'Home')); aa=agg(filter_games(log_a,game_span,'Away'))
    hb=agg(filter_games(log_b,game_span,'Home')); ab_=agg(filter_games(log_b,game_span,'Away'))
    ms=['PTS','REB','AST','ORTG']
    fig=make_subplots(1,len(ms),subplot_titles=ms)
    for i,m in enumerate(ms,1):
        s=(i==1)
        fig.add_trace(go.Bar(name=f'{team_a_abbr} Home' if s else None,x=[m],y=[ha[m]],marker_color=C_A,showlegend=s,legendgroup='ah'),1,i)
        fig.add_trace(go.Bar(name=f'{team_a_abbr} Away' if s else None,x=[m],y=[aa[m]],marker_color=C_A,opacity=.5,showlegend=s,legendgroup='aa'),1,i)
        fig.add_trace(go.Bar(name=f'{team_b_abbr} Home' if s else None,x=[m],y=[hb[m]],marker_color=C_B,showlegend=s,legendgroup='bh'),1,i)
        fig.add_trace(go.Bar(name=f'{team_b_abbr} Away' if s else None,x=[m],y=[ab_[m]],marker_color=C_B,opacity=.5,showlegend=s,legendgroup='ba'),1,i)
    fig.update_layout(**PLT,height=350,barmode='group')
    st.plotly_chart(fig,use_container_width=True)


# ================================================================
# PAGE 2 — ADVANCED METRICS
# ================================================================

def pg_advanced():
    header()
    cols = st.columns(6)
    for col,(label,k,b,s) in zip(cols,[
        ("Off. Rating",'ORTG','h',''),("True Shooting",'TS%','h','%'),("eFG%",'eFG%','h','%'),
        ("3P%",'3P%','h','%'),("Pace (Poss)",'POSS','h',''),("TOV Rate",'TOV%','l','%')]):
        d=sa[k]-sb[k]; col.metric(label,f"{sa[k]:.1f}{s}",f"{d:+.1f}",delta_color="inverse" if b=='l' else "normal")

    left,right = st.columns(2)
    with left:
        st.markdown("### Efficiency Radar")
        cats=['Off. Rating','True Shooting','eFG%','3-Point %','Free Throw Rate','Ball Security']
        def n(v,lo,hi): return max(0,min((v-lo)/(hi-lo),1))
        r_a=[n(sa['ORTG'],90,125),n(sa['TS%'],45,65),n(sa['eFG%'],42,58),n(sa['3P%'],28,42),n(sa['FTr'],.15,.35),n(100-sa['TOV%'],80,92)]
        r_b=[n(sb['ORTG'],90,125),n(sb['TS%'],45,65),n(sb['eFG%'],42,58),n(sb['3P%'],28,42),n(sb['FTr'],.15,.35),n(100-sb['TOV%'],80,92)]
        fig=go.Figure()
        fig.add_trace(go.Scatterpolar(r=r_a+[r_a[0]],theta=cats+[cats[0]],fill='toself',name=team_a_abbr,fillcolor='rgba(76,175,80,.2)',line_color=C_A))
        fig.add_trace(go.Scatterpolar(r=r_b+[r_b[0]],theta=cats+[cats[0]],fill='toself',name=team_b_abbr,fillcolor='rgba(33,150,243,.2)',line_color=C_B))
        fig.update_layout(**PLT,height=420,polar=dict(bgcolor='rgba(0,0,0,0)',radialaxis=dict(visible=True,range=[0,1],showticklabels=False,gridcolor='#333'),angularaxis=dict(gridcolor='#333')))
        st.plotly_chart(fig,use_container_width=True)

    with right:
        st.markdown("### Four Factors (Dean Oliver)")
        st.caption("eFG%, Turnover Rate, Offensive Rebounds, Free Throw Rate.")
        fk=['eFG%','TOV%','OREB','FTr']; fl=['eFG%','Turnover %','Off. Rebounds','FT Rate']
        fig=go.Figure()
        fig.add_trace(go.Bar(y=fl,x=[sa[f] for f in fk],orientation='h',name=team_a_abbr,marker_color=C_A,text=[f"{sa[f]:.1f}" for f in fk],textposition='auto'))
        fig.add_trace(go.Bar(y=fl,x=[sb[f] for f in fk],orientation='h',name=team_b_abbr,marker_color=C_B,text=[f"{sb[f]:.1f}" for f in fk],textposition='auto'))
        fig.update_layout(**PLT,height=420,barmode='group')
        st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Shooting Splits")
    ss=['FG%','2P%','3P%','FT%','TS%','eFG%']
    fig=go.Figure()
    fig.add_trace(go.Bar(x=ss,y=[sa[s] for s in ss],name=team_a_abbr,marker_color=C_A,text=[f"{sa[s]:.1f}%" for s in ss],textposition='outside'))
    fig.add_trace(go.Bar(x=ss,y=[sb[s] for s in ss],name=team_b_abbr,marker_color=C_B,text=[f"{sb[s]:.1f}%" for s in ss],textposition='outside'))
    fig.update_layout(**PLT,height=350,barmode='group',yaxis=dict(range=[0,max(sa['FT%'],sb['FT%'])+12]))
    st.plotly_chart(fig,use_container_width=True)


# ================================================================
# PAGE 3 — TOP PLAYERS & SHOOTERS
# ================================================================

def pg_players():
    header()
    with st.spinner("Loading player stats…"):
        pa=get_players(team_a_id,sel_season); pb=get_players(team_b_id,sel_season)

    st.markdown("### 🏆 Top Scorers")
    c1,c2=st.columns(2)
    bcols=['PLAYER_NAME','GP','PTS','AST','REB','STL','BLK','FG%']
    for col,p,name in [(c1,pa,team_a_name),(c2,pb,team_b_name)]:
        with col:
            st.markdown(f"**{name}**")
            if not p.empty:
                sc=[c for c in bcols if c in p.columns]; st.dataframe(p.head(8)[sc],use_container_width=True,hide_index=True)
            else: st.warning("Data unavailable.")
    if pa.empty or pb.empty: return

    # 3PT Shooters
    st.markdown("### 🎯 Best 3-Point Shooters (min 1 3PA/game)")
    c1,c2=st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            sh=p[p['FG3A']>=1].sort_values('FG3_PCT',ascending=False).head(5)
            if not sh.empty:
                fig=go.Figure(go.Bar(y=sh['PLAYER_NAME'],x=sh['3P%'],orientation='h',marker_color=color,
                    text=sh.apply(lambda r:f"{r['3P%']:.1f}% ({r['FG3M']:.1f}/{r['FG3A']:.1f})",axis=1),textposition='outside'))
                fig.update_layout(**PLT,height=280,title=dict(text=f'{abbr} — 3PT Leaders',font_size=13),xaxis=dict(range=[0,sh['3P%'].max()+15]),yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig,use_container_width=True)

    # TS% Leaders
    st.markdown("### 🔥 Most Efficient Scorers (True Shooting %)")
    c1,c2=st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            eff=p[p['FGA']>=3].sort_values('TS%',ascending=False).head(5)
            if not eff.empty:
                fig=go.Figure(go.Bar(y=eff['PLAYER_NAME'],x=eff['TS%'],orientation='h',marker_color=color,
                    text=eff['TS%'].apply(lambda x:f"{x:.1f}%"),textposition='outside'))
                fig.update_layout(**PLT,height=280,title=dict(text=f'{abbr} — TS%',font_size=13),xaxis=dict(range=[0,eff['TS%'].max()+12]),yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig,use_container_width=True)

    # Rebounders
    st.markdown("### 💪 Top Rebounders")
    c1,c2=st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            reb=p.sort_values('REB',ascending=False).head(5)
            if not reb.empty and 'OREB' in reb.columns:
                fig=go.Figure()
                fig.add_trace(go.Bar(y=reb['PLAYER_NAME'],x=reb['OREB'],orientation='h',name='Off.',marker_color=color))
                fig.add_trace(go.Bar(y=reb['PLAYER_NAME'],x=reb['DREB'],orientation='h',name='Def.',marker_color=color,opacity=.5))
                fig.update_layout(**PLT,height=280,barmode='stack',title=dict(text=f'{abbr} — Rebounds',font_size=13),yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig,use_container_width=True)

    # 2P%
    st.markdown("### 🔢 2-Point FG% (min 2 2PA/game)")
    c1,c2=st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            tp=p[p['2PA']>=2].sort_values('2P%',ascending=False).head(5)
            if not tp.empty:
                fig=go.Figure(go.Bar(y=tp['PLAYER_NAME'],x=tp['2P%'],orientation='h',marker_color=color,
                    text=tp.apply(lambda r:f"{r['2P%']:.1f}% ({r['2PM']:.1f}/{r['2PA']:.1f})",axis=1),textposition='outside'))
                fig.update_layout(**PLT,height=280,title=dict(text=f'{abbr} — 2PT%',font_size=13),xaxis=dict(range=[0,tp['2P%'].max()+15]),yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig,use_container_width=True)

    # FT Rate
    st.markdown("### 🎪 Free Throw Rate (FTA / FGA)")
    st.caption("Higher = draws more fouls relative to shot attempts.")
    c1,c2=st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            ft=p[p['FGA']>=2].sort_values('FTr',ascending=False).head(6)
            if not ft.empty:
                fig=go.Figure(go.Bar(y=ft['PLAYER_NAME'],x=ft['FTr'],orientation='h',marker_color=color,
                    text=ft.apply(lambda r:f"{r['FTr']:.3f} ({r['FTM']:.1f}/{r['FTA']:.1f} FT)",axis=1),textposition='outside'))
                fig.update_layout(**PLT,height=300,title=dict(text=f'{abbr} — FT Rate',font_size=13),xaxis=dict(range=[0,ft['FTr'].max()+.15]),yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig,use_container_width=True)

    # FT%
    st.markdown("### 🏹 Free Throw Accuracy (min 1 FTA/game)")
    c1,c2=st.columns(2)
    for col,p,abbr,color in [(c1,pa,team_a_abbr,C_A),(c2,pb,team_b_abbr,C_B)]:
        with col:
            ftp=p[p['FTA']>=1].sort_values('FT_PCT',ascending=False).head(6)
            if not ftp.empty:
                fig=go.Figure(go.Bar(y=ftp['PLAYER_NAME'],x=ftp['FT%'],orientation='h',marker_color=color,
                    text=ftp['FT%'].apply(lambda x:f"{x:.1f}%"),textposition='outside'))
                fig.update_layout(**PLT,height=300,title=dict(text=f'{abbr} — FT%',font_size=13),xaxis=dict(range=[0,105]),yaxis=dict(autorange='reversed'))
                st.plotly_chart(fig,use_container_width=True)

    # Star Radar
    st.markdown("### ⭐ Star Player Comparison")
    star_a=pa.iloc[0]; star_b=pb.iloc[0]
    cats=['Points','Assists','Rebounds','Steals','Blocks']; keys=['PTS','AST','REB','STL','BLK']
    mx={'PTS':35,'AST':12,'REB':14,'STL':3,'BLK':3.5}
    def nr(row): return [min(row[k]/mx[k],1) if k in row.index else 0 for k in keys]
    ra=nr(star_a); rb=nr(star_b)
    fig=go.Figure()
    fig.add_trace(go.Scatterpolar(r=ra+[ra[0]],theta=cats+[cats[0]],fill='toself',name=star_a.get('PLAYER_NAME','?'),fillcolor='rgba(76,175,80,.2)',line_color=C_A))
    fig.add_trace(go.Scatterpolar(r=rb+[rb[0]],theta=cats+[cats[0]],fill='toself',name=star_b.get('PLAYER_NAME','?'),fillcolor='rgba(33,150,243,.2)',line_color=C_B))
    fig.update_layout(**PLT,height=420,polar=dict(bgcolor='rgba(0,0,0,0)',radialaxis=dict(visible=True,range=[0,1],showticklabels=False,gridcolor='#333'),angularaxis=dict(gridcolor='#333')))
    st.plotly_chart(fig,use_container_width=True)


# ================================================================
# PAGE 4 — SHOT CHART & POSITIONS
# ================================================================

def pg_shots():
    header()
    st.subheader(f"Shot Chart — {sel_season}")
    with st.spinner("Loading shot data…"):
        shots_a=get_shot_chart(team_a_id,sel_season); shots_b=get_shot_chart(team_b_id,sel_season)

    c1,c2=st.columns(2)
    with c1: f=plot_shot_chart(shots_a,team_a_name); st.pyplot(f); plt.close(f)
    with c2: f=plot_shot_chart(shots_b,team_b_name); st.pyplot(f); plt.close(f)

    if shots_a.empty and shots_b.empty:
        st.warning("No shot data available."); return

    st.markdown("### Shot Zone Breakdown")
    c1,c2=st.columns(2)
    for col,shots,name,color in [(c1,shots_a,team_a_name,C_A),(c2,shots_b,team_b_name,C_B)]:
        with col:
            if not shots.empty and 'SHOT_ZONE_BASIC' in shots.columns:
                zs=shots.groupby('SHOT_ZONE_BASIC').agg(Att=('SHOT_MADE_FLAG','count'),Made=('SHOT_MADE_FLAG','sum')).reset_index()
                zs['Pct']=(zs['Made']/zs['Att']*100).round(1); zs=zs.sort_values('Att',ascending=True)
                fig=go.Figure()
                fig.add_trace(go.Bar(y=zs['SHOT_ZONE_BASIC'],x=zs['Att'],orientation='h',name='Attempts',marker_color=color,opacity=.35,text=zs['Att'],textposition='inside'))
                fig.add_trace(go.Bar(y=zs['SHOT_ZONE_BASIC'],x=zs['Made'],orientation='h',name='Makes',marker_color=color,text=zs.apply(lambda r:f"{r['Made']} ({r['Pct']}%)",axis=1),textposition='inside'))
                fig.update_layout(**PLT,height=350,barmode='overlay',title=dict(text=name,font_size=13))
                st.plotly_chart(fig,use_container_width=True)

    st.markdown("### 🎯 Preferred Shooting Positions by Player")
    with st.spinner("Loading player stats…"):
        pa=get_players(team_a_id,sel_season); pb=get_players(team_b_id,sel_season)
    c1,c2=st.columns(2)
    for col,shots,players,name in [(c1,shots_a,pa,team_a_name),(c2,shots_b,pb,team_b_name)]:
        with col:
            if not players.empty and not shots.empty and 'PLAYER_NAME' in shots.columns and 'SHOT_ZONE_BASIC' in shots.columns:
                top5=players.head(5)['PLAYER_NAME'].tolist()
                ps=shots[shots['PLAYER_NAME'].isin(top5)]
                if not ps.empty:
                    pz=ps.groupby(['PLAYER_NAME','SHOT_ZONE_BASIC']).agg(Att=('SHOT_MADE_FLAG','count')).reset_index()
                    fig=px.bar(pz,y='PLAYER_NAME',x='Att',color='SHOT_ZONE_BASIC',orientation='h',
                        title=f'{name} — Shot Zones',color_discrete_sequence=px.colors.sequential.Teal)
                    fig.update_layout(**PLT,height=380,barmode='stack',yaxis=dict(autorange='reversed'))
                    st.plotly_chart(fig,use_container_width=True)

    # Distance distribution
    st.markdown("### Shot Distance Distribution")
    has_dist = (not shots_a.empty and 'SHOT_DISTANCE' in shots_a.columns) and (not shots_b.empty and 'SHOT_DISTANCE' in shots_b.columns)
    if has_dist:
        fig=go.Figure()
        fig.add_trace(go.Histogram(x=shots_a['SHOT_DISTANCE'],nbinsx=30,name=team_a_abbr,marker_color=C_A,opacity=.6))
        fig.add_trace(go.Histogram(x=shots_b['SHOT_DISTANCE'],nbinsx=30,name=team_b_abbr,marker_color=C_B,opacity=.6))
        fig.update_layout(**PLT,height=350,barmode='overlay',xaxis_title='Distance (ft)',yaxis_title='Frequency')
        st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Accuracy by Distance")
    c1,c2=st.columns(2)
    for col,shots,abbr,color in [(c1,shots_a,team_a_abbr,C_A),(c2,shots_b,team_b_abbr,C_B)]:
        with col:
            if not shots.empty and 'SHOT_DISTANCE' in shots.columns:
                bins=[0,3,10,16,22,28,50]; labels_d=['0-3ft','3-10ft','10-16ft','16-22ft','22-28ft','28+ft']
                sc=shots.copy(); sc['db']=pd.cut(sc['SHOT_DISTANCE'],bins=bins,labels=labels_d,right=False)
                dg=sc.groupby('db',observed=True).agg(Att=('SHOT_MADE_FLAG','count'),Made=('SHOT_MADE_FLAG','sum')).reset_index()
                dg['Pct']=(dg['Made']/dg['Att'].replace(0,1)*100).round(1)
                fig=go.Figure(go.Bar(x=dg['db'],y=dg['Pct'],marker_color=color,text=dg.apply(lambda r:f"{r['Pct']}%\n({r['Made']}/{r['Att']})",axis=1),textposition='outside'))
                fig.update_layout(**PLT,height=300,title=dict(text=f'{abbr} — FG% by Distance',font_size=13),yaxis=dict(range=[0,100]))
                st.plotly_chart(fig,use_container_width=True)


# ================================================================
# PAGE 5 — GAME ANALYSIS
# ================================================================

def pg_analysis():
    header()
    st.markdown("### Point Differential per Game")
    for df,abbr,color in [(df_a,team_a_abbr,C_A),(df_b,team_b_abbr,C_B)]:
        if 'PLUS_MINUS' in df.columns and not df.empty:
            cs=[color if v>=0 else '#ff5252' for v in df['PLUS_MINUS']]
            fig=go.Figure(go.Bar(x=df['GAME_DATE'],y=df['PLUS_MINUS'],marker_color=cs,name=abbr))
            fig.update_layout(**PLT,height=250,title=dict(text=abbr,font_size=13))
            st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Rolling Averages (5-game)")
    c1,c2=st.columns(2)
    for col,df,abbr in [(c1,df_a,team_a_abbr),(c2,df_b,team_b_abbr)]:
        with col:
            if len(df)>=5:
                ds=df.sort_values('GAME_DATE'); fig=go.Figure()
                for stat,dash in [('PTS','solid'),('REB','dash'),('AST','dot')]:
                    fig.add_trace(go.Scatter(x=ds['GAME_DATE'],y=ds[stat].rolling(5,min_periods=2).mean(),mode='lines',name=stat,line=dict(dash=dash,width=2)))
                fig.update_layout(**PLT,height=350,title=dict(text=f'{abbr}',font_size=13))
                st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Win/Loss Sequence")
    c1,c2=st.columns(2)
    for col,df,abbr,color in [(c1,df_a,team_a_abbr,C_A),(c2,df_b,team_b_abbr,C_B)]:
        with col:
            if not df.empty:
                ds=df.sort_values('GAME_DATE')
                sv=[1 if w=='W' else -1 for w in ds['WL']]; cs=[color if v>0 else '#ff5252' for v in sv]
                fig=go.Figure(go.Bar(x=ds['GAME_DATE'],y=sv,marker_color=cs))
                fig.update_layout(**PLT,height=250,title=dict(text=f'{abbr}',font_size=13),yaxis=dict(tickvals=[-1,1],ticktext=['L','W']))
                st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Consistency (Lower = More Consistent)")
    cstats=['PTS','REB','AST','TOV']
    std_a=[df_a[s].std() if not df_a.empty else 0 for s in cstats]
    std_b=[df_b[s].std() if not df_b.empty else 0 for s in cstats]
    fig=go.Figure()
    fig.add_trace(go.Bar(x=cstats,y=std_a,name=team_a_abbr,marker_color=C_A,text=[f"{v:.1f}" for v in std_a],textposition='outside'))
    fig.add_trace(go.Bar(x=cstats,y=std_b,name=team_b_abbr,marker_color=C_B,text=[f"{v:.1f}" for v in std_b],textposition='outside'))
    fig.update_layout(**PLT,height=350,barmode='group',yaxis_title='Std Dev')
    st.plotly_chart(fig,use_container_width=True)


# ================================================================
# PAGE 6 — HEAD-TO-HEAD
# ================================================================

def pg_h2h():
    header()
    st.subheader(f"⚔️ {team_a_name} vs {team_b_name} — All-Time Regular Season")
    with st.spinner("Loading head-to-head…"):
        h2h=get_head_to_head(team_a_id,team_b_id)
    if h2h.empty: st.warning("No data found."); return

    wins=(h2h['WL']=='W').sum(); losses=(h2h['WL']=='L').sum(); total=len(h2h)
    c1,c2,c3=st.columns(3)
    c1.metric("Total Games",total); c2.metric(f"{team_a_abbr} Wins",wins); c3.metric(f"{team_a_abbr} Losses",losses)

    left,right=st.columns([1,2])
    with left:
        fig=go.Figure(go.Pie(labels=[team_a_abbr,team_b_abbr],values=[wins,losses],marker_colors=[C_A,C_B],hole=.5,textinfo='label+value+percent'))
        fig.update_layout(**PLT,height=320,title=dict(text='All-Time Record',font_size=14),showlegend=False)
        st.plotly_chart(fig,use_container_width=True)
    with right:
        st.markdown("### Average Stats in Matchups")
        ak=['PTS','AST','REB','STL','BLK','TOV']; vals=[h2h[k].mean() for k in ak if k in h2h.columns]
        labs=[k for k in ak if k in h2h.columns]
        fig=go.Figure(go.Bar(x=labs,y=vals,marker_color=C_A,text=[f"{v:.1f}" for v in vals],textposition='outside'))
        fig.update_layout(**PLT,height=320,title=dict(text=f'{team_a_abbr} avg vs {team_b_abbr}',font_size=13))
        st.plotly_chart(fig,use_container_width=True)

    if 'SEASON_ID' in h2h.columns:
        st.markdown("### Season-by-Season Record")
        szn=h2h.copy(); szn['Season']=szn['SEASON_ID'].astype(str).str[-4:].astype(int)
        szn['SL']=szn['Season'].apply(lambda y:f"{y}-{str(y+1)[-2:]}")
        bs=szn.groupby('SL').agg(G=('WL','count'),W=('WL',lambda x:(x=='W').sum())).reset_index()
        bs['L']=bs['G']-bs['W']; bs=bs.sort_values('SL').tail(15)
        fig=go.Figure()
        fig.add_trace(go.Bar(x=bs['SL'],y=bs['W'],name='Wins',marker_color=C_A))
        fig.add_trace(go.Bar(x=bs['SL'],y=bs['L'],name='Losses',marker_color='#ff5252'))
        fig.update_layout(**PLT,height=350,barmode='stack')
        st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Point Differential in Matchups")
    r=h2h.head(30).sort_values('GAME_DATE')
    if not r.empty and 'PLUS_MINUS' in r.columns:
        cs=[C_A if v>=0 else '#ff5252' for v in r['PLUS_MINUS']]
        fig=go.Figure(go.Bar(x=r['GAME_DATE'],y=r['PLUS_MINUS'],marker_color=cs))
        fig.update_layout(**PLT,height=300,title=dict(text=f'{team_a_abbr} +/- (last 30)',font_size=13))
        st.plotly_chart(fig,use_container_width=True)

    st.markdown("### Recent Match Results")
    d=h2h.head(20).copy()
    sc=['GAME_DATE','MATCHUP','WL','PTS','REB','AST','FGM','FGA','FG3M','FG3A','FTM','FTA','PLUS_MINUS']
    sc=[c for c in sc if c in d.columns]; d['GAME_DATE']=d['GAME_DATE'].dt.strftime('%Y-%m-%d')
    st.dataframe(d[sc],use_container_width=True,hide_index=True)


# ================================================================
# PAGE 7 — PLAYER COMPARISON (NEW)
# ================================================================

def pg_player_compare():
    header()
    st.subheader("👤 Player-vs-Player Comparison")

    with st.spinner("Loading rosters…"):
        pa = get_players(team_a_id, sel_season)
        pb = get_players(team_b_id, sel_season)

    if pa.empty or pb.empty:
        st.warning("Player data unavailable for one or both teams.")
        return

    # Player selectors
    c1, c2 = st.columns(2)
    with c1:
        names_a = pa['PLAYER_NAME'].tolist()
        sel_a = st.selectbox(f"Select {team_a_abbr} player", names_a, index=0, key='pa')
    with c2:
        names_b = pb['PLAYER_NAME'].tolist()
        sel_b = st.selectbox(f"Select {team_b_abbr} player", names_b, index=0, key='pb')

    p_a = pa[pa['PLAYER_NAME'] == sel_a].iloc[0]
    p_b = pb[pb['PLAYER_NAME'] == sel_b].iloc[0]
    pid_a = int(p_a['PLAYER_ID'])
    pid_b = int(p_b['PLAYER_ID'])

    # ---- Player Cards with Photos ----
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""<div class='player-card'>
            <img src='{HEADSHOT_URL.format(pid=pid_a)}' onerror="this.src='https://cdn.nba.com/headshots/nba/latest/1040x760/fallback.png'">
            <h3 style='color:{C_A}'>{sel_a}</h3>
            <div style='color:#999'>{team_a_name}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class='player-card'>
            <img src='{HEADSHOT_URL.format(pid=pid_b)}' onerror="this.src='https://cdn.nba.com/headshots/nba/latest/1040x760/fallback.png'">
            <h3 style='color:{C_B}'>{sel_b}</h3>
            <div style='color:#999'>{team_b_name}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ---- KPI Comparison ----
    st.markdown("### Key Stats Comparison")
    kpis = [
        ('GP', 'Games Played', 'h'),
        ('PTS', 'Points', 'h'),
        ('AST', 'Assists', 'h'),
        ('REB', 'Rebounds', 'h'),
        ('STL', 'Steals', 'h'),
        ('BLK', 'Blocks', 'h'),
        ('TOV', 'Turnovers', 'l'),
        ('FG%', 'FG%', 'h'),
        ('3P%', '3PT%', 'h'),
        ('FT%', 'FT%', 'h'),
        ('2P%', '2PT%', 'h'),
        ('TS%', 'True Shooting %', 'h'),
        ('FTr', 'Free Throw Rate', 'h'),
    ]

    # 4-column layout: name_a | val_a | val_b | name_b
    rows = st.columns(4)
    rows[0].markdown(f"**{sel_a}**"); rows[1].markdown("**Stat**")
    rows[2].markdown("**Stat**"); rows[3].markdown(f"**{sel_b}**")

    for k, label, better in kpis:
        va = p_a[k] if k in p_a.index else 0
        vb = p_b[k] if k in p_b.index else 0

        fmt = f"{va:.1f}" if isinstance(va, float) else str(va)
        fmt_b = f"{vb:.1f}" if isinstance(vb, float) else str(vb)

        # Color winner
        if better == 'h':
            c_a = C_A if va > vb else '#666'
            c_b = C_B if vb > va else '#666'
        else:
            c_a = C_A if va < vb else '#666'
            c_b = C_B if vb < va else '#666'

        c1, c2, c3, c4 = st.columns([2,2,2,2])
        c1.markdown(f"<span style='color:{c_a};font-size:1.2rem;font-weight:700'>{fmt}</span>", unsafe_allow_html=True)
        c2.markdown(f"<span style='color:#999'>{label}</span>", unsafe_allow_html=True)
        c3.markdown(f"<span style='color:#999'>{label}</span>", unsafe_allow_html=True)
        c4.markdown(f"<span style='color:{c_b};font-size:1.2rem;font-weight:700'>{fmt_b}</span>", unsafe_allow_html=True)

    # ---- Radar ----
    st.markdown("### Player Radar")
    cats = ['Points','Assists','Rebounds','Steals','Blocks','TS%']
    keys = ['PTS','AST','REB','STL','BLK','TS%']
    maxes = {'PTS':35,'AST':12,'REB':14,'STL':3,'BLK':3.5,'TS%':70}
    def nr(row):
        return [min((row[k] if k in row.index else 0)/maxes[k],1) for k in keys]
    ra = nr(p_a); rb = nr(p_b)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=ra+[ra[0]], theta=cats+[cats[0]], fill='toself',
        name=sel_a, fillcolor='rgba(76,175,80,.2)', line_color=C_A))
    fig.add_trace(go.Scatterpolar(r=rb+[rb[0]], theta=cats+[cats[0]], fill='toself',
        name=sel_b, fillcolor='rgba(33,150,243,.2)', line_color=C_B))
    fig.update_layout(**PLT, height=420,
        polar=dict(bgcolor='rgba(0,0,0,0)',
            radialaxis=dict(visible=True,range=[0,1],showticklabels=False,gridcolor='#333'),
            angularaxis=dict(gridcolor='#333')))
    st.plotly_chart(fig, use_container_width=True)

    # ---- Shot Charts ----
    st.markdown("### Shot Placement")
    with st.spinner("Loading individual shot charts…"):
        shots_pa = get_shot_chart(team_a_id, sel_season, player_id=pid_a)
        shots_pb = get_shot_chart(team_b_id, sel_season, player_id=pid_b)

    c1, c2 = st.columns(2)
    with c1:
        f = plot_shot_chart(shots_pa, sel_a, color_made='#66bb6a', color_miss='#fc0303')
        st.pyplot(f); plt.close(f)
    with c2:
        f = plot_shot_chart(shots_pb, sel_b, color_made='#42a5f5', color_miss='#fc0303')
        st.pyplot(f); plt.close(f)

    # Zone comparison
    if not shots_pa.empty and not shots_pb.empty and 'SHOT_ZONE_BASIC' in shots_pa.columns:
        st.markdown("### Shot Zone Comparison")
        c1, c2 = st.columns(2)
        for col, shots, name, color in [(c1,shots_pa,sel_a,C_A),(c2,shots_pb,sel_b,C_B)]:
            with col:
                zs = shots.groupby('SHOT_ZONE_BASIC').agg(
                    Att=('SHOT_MADE_FLAG','count'), Made=('SHOT_MADE_FLAG','sum')).reset_index()
                zs['Pct'] = (zs['Made']/zs['Att']*100).round(1)
                zs = zs.sort_values('Att', ascending=True)
                fig = go.Figure()
                fig.add_trace(go.Bar(y=zs['SHOT_ZONE_BASIC'],x=zs['Att'],orientation='h',
                    name='Attempts',marker_color=color,opacity=.35))
                fig.add_trace(go.Bar(y=zs['SHOT_ZONE_BASIC'],x=zs['Made'],orientation='h',
                    name='Makes',marker_color=color,
                    text=zs.apply(lambda r:f"{r['Made']} ({r['Pct']}%)",axis=1),textposition='inside'))
                fig.update_layout(**PLT,height=320,barmode='overlay',title=dict(text=name,font_size=13))
                st.plotly_chart(fig,use_container_width=True)


# ================================================================
# PAGE 8 — SINGLE GAME BREAKDOWN (NEW)
# ================================================================

def pg_single_game():
    header()
    st.subheader("🏟️ Single Game Breakdown")

    # Build list of recent games from both teams
    game_list = []
    for df, abbr in [(df_a, team_a_abbr), (df_b, team_b_abbr)]:
        if not df.empty and 'Game_ID' in df.columns:
            for _, row in df.head(15).iterrows():
                gid = row['Game_ID']
                date = row['GAME_DATE'].strftime('%Y-%m-%d')
                matchup = row.get('MATCHUP', '')
                wl = row.get('WL', '')
                pts = row.get('PTS', 0)
                label = f"{date} | {matchup} | {wl} {pts:.0f}pts"
                game_list.append({'label': label, 'game_id': gid, 'date': date, 'team': abbr})

    if not game_list:
        st.warning("No games available. The Game_ID column may be missing.")
        return

    # Dropdown to select a game
    labels = [g['label'] for g in game_list]
    # Remove duplicates while preserving order
    seen = set()
    unique_games = []
    for g in game_list:
        if g['game_id'] not in seen:
            seen.add(g['game_id'])
            unique_games.append(g)
    unique_labels = [g['label'] for g in unique_games]

    selected_label = st.selectbox("Select a game to analyze", unique_labels, index=0)
    sel_game = next(g for g in unique_games if g['label'] == selected_label)
    game_id = sel_game['game_id']

    st.info(f"📋 Game ID: {game_id}")

    # ---- Load game data ----
    with st.spinner("Loading game details…"):
        summary_data = get_game_summary(game_id)
        boxscore_data = get_game_boxscore(game_id)

    line_score = summary_data.get('line_score', pd.DataFrame())
    other_stats = summary_data.get('other_stats', pd.DataFrame())
    players_bs = boxscore_data.get('players', pd.DataFrame())
    teams_bs = boxscore_data.get('teams', pd.DataFrame())

    # ---- Quarter-by-Quarter Scores ----
    if not line_score.empty:
        st.markdown("### 📊 Quarter-by-Quarter Scores")

        qcols = ['PTS_QTR1','PTS_QTR2','PTS_QTR3','PTS_QTR4']
        ot_cols = [c for c in line_score.columns if c.startswith('PTS_OT') and line_score[c].sum() > 0]
        all_q = qcols + ot_cols
        q_labels = ['Q1','Q2','Q3','Q4'] + [c.replace('PTS_','') for c in ot_cols]

        # Ensure numeric
        for c in all_q:
            if c in line_score.columns:
                line_score[c] = pd.to_numeric(line_score[c], errors='coerce').fillna(0)
        if 'PTS' in line_score.columns:
            line_score['PTS'] = pd.to_numeric(line_score['PTS'], errors='coerce').fillna(0)

        if len(line_score) >= 2:
            t1 = line_score.iloc[0]
            t2 = line_score.iloc[1]
            t1_name = t1.get('TEAM_ABBREVIATION', 'Team 1')
            t2_name = t2.get('TEAM_ABBREVIATION', 'Team 2')

            # Score table
            score_data = {'Quarter': q_labels + ['TOTAL']}
            score_data[t1_name] = [int(t1.get(c, 0)) for c in all_q] + [int(t1.get('PTS', 0))]
            score_data[t2_name] = [int(t2.get(c, 0)) for c in all_q] + [int(t2.get('PTS', 0))]
            st.dataframe(pd.DataFrame(score_data), use_container_width=True, hide_index=True)

            # Quarter bar chart
            t1_vals = [float(t1.get(c, 0)) for c in all_q]
            t2_vals = [float(t2.get(c, 0)) for c in all_q]

            fig = go.Figure()
            fig.add_trace(go.Bar(x=q_labels, y=t1_vals, name=t1_name, marker_color=C_A,
                text=[f"{v:.0f}" for v in t1_vals], textposition='outside'))
            fig.add_trace(go.Bar(x=q_labels, y=t2_vals, name=t2_name, marker_color=C_B,
                text=[f"{v:.0f}" for v in t2_vals], textposition='outside'))
            fig.update_layout(**PLT, height=350, barmode='group',
                title=dict(text='Points by Quarter', font_size=14))
            st.plotly_chart(fig, use_container_width=True)

            # Cumulative score flow
            st.markdown("### 📈 Score Flow")
            cum1 = np.cumsum(t1_vals)
            cum2 = np.cumsum(t2_vals)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=q_labels, y=cum1, mode='lines+markers+text',
                name=t1_name, line=dict(color=C_A, width=3), marker=dict(size=10),
                text=[f"{v:.0f}" for v in cum1], textposition='top center'))
            fig.add_trace(go.Scatter(x=q_labels, y=cum2, mode='lines+markers+text',
                name=t2_name, line=dict(color=C_B, width=3), marker=dict(size=10),
                text=[f"{v:.0f}" for v in cum2], textposition='bottom center'))
            fig.update_layout(**PLT, height=350, title=dict(text='Cumulative Score', font_size=14))
            st.plotly_chart(fig, use_container_width=True)

            # Quarter differential
            st.markdown("### Quarter Differential")
            diffs = [t1_vals[i] - t2_vals[i] for i in range(len(q_labels))]
            cs = [C_A if d >= 0 else C_B for d in diffs]
            fig = go.Figure(go.Bar(x=q_labels, y=diffs, marker_color=cs,
                text=[f"{d:+.0f}" for d in diffs], textposition='outside'))
            fig.update_layout(**PLT, height=300,
                title=dict(text=f'{t1_name} margin by quarter', font_size=14),
                yaxis_title='Point Differential')
            st.plotly_chart(fig, use_container_width=True)

    # ---- Other Stats (paint, fastbreak, etc.) ----
    if not other_stats.empty and len(other_stats) >= 2:
        st.markdown("### 🎨 Game Flow Stats")
        o1 = other_stats.iloc[0]; o2 = other_stats.iloc[1]
        o1n = o1.get('TEAM_ABBREVIATION','Team 1'); o2n = o2.get('TEAM_ABBREVIATION','Team 2')
        flow_stats = [
            ('PTS_PAINT','Points in Paint'),('PTS_2ND_CHANCE','2nd Chance Pts'),
            ('PTS_FB','Fast Break Pts'),('PTS_OFF_TO','Pts off Turnovers'),
            ('LARGEST_LEAD','Largest Lead'),('LEAD_CHANGES','Lead Changes'),
            ('TIMES_TIED','Times Tied'),
        ]
        available = [(k,l) for k,l in flow_stats if k in o1.index]
        if available:
            labels_f = [l for _,l in available]
            v1 = [float(o1.get(k,0)) for k,_ in available]
            v2 = [float(o2.get(k,0)) for k,_ in available]
            fig = go.Figure()
            fig.add_trace(go.Bar(y=labels_f, x=v1, orientation='h', name=o1n, marker_color=C_A,
                text=[f"{v:.0f}" for v in v1], textposition='auto'))
            fig.add_trace(go.Bar(y=labels_f, x=v2, orientation='h', name=o2n, marker_color=C_B,
                text=[f"{v:.0f}" for v in v2], textposition='auto'))
            fig.update_layout(**PLT, height=380, barmode='group',
                title=dict(text='Game Flow Stats', font_size=14))
            st.plotly_chart(fig, use_container_width=True)

    # ---- Player Box Score ----
    if not players_bs.empty:
        st.markdown("### 📋 Player Box Score")

        # Map column names (V3 uses camelCase)
        col_map = {
            'firstName':'First','familyName':'Last','teamTricode':'Team',
            'minutes':'MIN','points':'PTS','assists':'AST','reboundsTotal':'REB',
            'reboundsOffensive':'OREB','reboundsDefensive':'DREB',
            'steals':'STL','blocks':'BLK','turnovers':'TOV',
            'fieldGoalsMade':'FGM','fieldGoalsAttempted':'FGA',
            'threePointersMade':'3PM','threePointersAttempted':'3PA',
            'freeThrowsMade':'FTM','freeThrowsAttempted':'FTA',
            'plusMinusPoints':'±',
        }
        display_bs = players_bs.copy()
        # Rename available columns
        rename_dict = {k: v for k, v in col_map.items() if k in display_bs.columns}
        display_bs = display_bs.rename(columns=rename_dict)

        show_cols = ['First','Last','Team','MIN','PTS','AST','REB','OREB','DREB',
                     'STL','BLK','TOV','FGM','FGA','3PM','3PA','FTM','FTA','±']
        show_cols = [c for c in show_cols if c in display_bs.columns]

        if show_cols:
            st.dataframe(display_bs[show_cols], use_container_width=True, hide_index=True, height=500)

    # ---- Shot chart for this specific game ----
    st.markdown("### 🎯 Shot Chart for This Game")
    with st.spinner("Loading game shot chart…"):
        game_shots_a = get_shot_chart(team_a_id, sel_season, game_id=game_id)
        game_shots_b = get_shot_chart(team_b_id, sel_season, game_id=game_id)

    c1, c2 = st.columns(2)
    with c1:
        f = plot_shot_chart(game_shots_a, team_a_name, color_made='#66bb6a')
        st.pyplot(f); plt.close(f)
    with c2:
        f = plot_shot_chart(game_shots_b, team_b_name, color_made='#42a5f5')
        st.pyplot(f); plt.close(f)


# ================================================================
# 7. PAGE ROUTING
# ================================================================

routes = {
    "📊 Overview": pg_overview,
    "🧠 Advanced Metrics": pg_advanced,
    "🌟 Top Players & Shooters": pg_players,
    "🎯 Shot Chart & Positions": pg_shots,
    "📈 Game Analysis": pg_analysis,
    "⚔️ Head-to-Head History": pg_h2h,
    "👤 Player Comparison": pg_player_compare,
    "🏟️ Single Game Breakdown": pg_single_game,
}
routes.get(page, pg_overview)()