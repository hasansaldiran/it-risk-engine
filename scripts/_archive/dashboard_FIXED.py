# -*- coding: utf-8 -*-
"""
IT Risk Engine — Dashboard v5.0
pip install streamlit plotly pandas openpyxl watchdog
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501
"""

import os, json, glob, hashlib, re, secrets, time
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ═══════════════════════════════════════════════════════════
# KONFİGÜRASYON
# ═══════════════════════════════════════════════════════════
CREDENTIALS     = {"admin": hashlib.sha256("S3cur!ty".encode()).hexdigest()}
SESSION_TIMEOUT = 480          # dakika — 8 saat
SESSION_FILE    = Path(__file__).parent.parent / "data" / "processed" / "sessions.json"

# Lansweeper — SADECE AssetID ile direkt link
LANSWEEPER_BASE = os.getenv("LANSWEEPER_HOST", "http://LANSWEEPER_HOST:81")
# Lansweeper versiyonuna göre birini kullan:
ASSET_URL       = LANSWEEPER_BASE + "/asset.aspx?AssetID={aid}"
# ASSET_URL     = LANSWEEPER_BASE + "/web/Asset/AssetDetail.aspx?AssetID={aid}"

# Şehir-subnet eşlemesi harici config dosyasından yüklenir
# Gerçek eşleme: config/subnet_city.json (bu dosya .gitignore ile korunur)
import json as _json
_SUBNET_CONFIG = Path(__file__).parent.parent.parent / "config" / "subnet_city.json"
if _SUBNET_CONFIG.exists():
    with open(_SUBNET_CONFIG, encoding="utf-8") as _f:
        SUBNET_CITY = {k: tuple(v) for k, v in _json.load(_f).items()}
else:
    SUBNET_CITY = {
        "10.0":   ("Lokasyon-A", 0.0, 0.0),
        "10.1":   ("Lokasyon-B", 0.0, 0.0),
        "172":    ("Çağrı Merkezi", 0.0, 0.0),
    }
GEBZE_DEFAULT = ("Varsayılan Lokasyon", 0.0, 0.0)

# ═══════════════════════════════════════════════════════════
# YOLLAR
# ═══════════════════════════════════════════════════════════
BASE_DIR      = Path(__file__).parent.parent
PROC_DIR      = BASE_DIR / "data" / "processed"
CLEAN_DATA    = PROC_DIR / "risk_data_current.xlsx"
RAW_DATA      = BASE_DIR / "data" / "raw" / "lansweeper_risk.xlsx"
COUNTER_FILE  = PROC_DIR / "visitor_counter.json"
HISTORY_FILE  = PROC_DIR / "risk_history.json"

# ═══════════════════════════════════════════════════════════
# SAYFA KURULUMU
# ═══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="IT Risk Intelligence Platform",
    page_icon="🛡️", layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
*{font-family:'Inter',sans-serif!important;}
.stApp{background:#0D1117;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0D1117,#161B22);border-right:1px solid #21262D;}
[data-testid="stSidebar"] *{color:#8B949E!important;}
[data-testid="stSidebar"] .stRadio label{color:#C9D1D9!important;}
h1,h2,h3,h4{color:#E6EDF3!important;}
p,span,label,div{color:#C9D1D9;}

/* Metric kartları */
div[data-testid="metric-container"]{
  background:linear-gradient(135deg,#161B22,#21262D);
  border:1px solid #30363D;border-radius:12px;padding:16px 20px;
  box-shadow:0 4px 12px rgba(0,0,0,.3);transition:all .25s;
}
div[data-testid="metric-container"]:hover{
  border-color:#58A6FF;transform:translateY(-2px);
  box-shadow:0 8px 24px rgba(88,166,255,.15);
}
div[data-testid="metric-container"] label{color:#8B949E!important;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{color:#E6EDF3!important;font-size:24px;font-weight:800;}

.sec{background:linear-gradient(90deg,#161B22,#0D1117);padding:9px 16px;
  border-left:3px solid #F85149;border-radius:5px;margin:18px 0 8px;
  color:#E6EDF3!important;font-size:14px;font-weight:700;}

.action-card{background:#161B22;border:2px solid #30363D;border-radius:9px;
  padding:16px 16px;margin:8px 0;transition:all .3s;cursor:pointer;
  box-shadow:0 2px 8px rgba(0,0,0,.2);display:flex;align-items:center;
  font-weight:600;font-size:15px;}
.action-card:hover{
  border-color:#58A6FF;transform:translateX(4px) translateY(-2px);
  box-shadow:0 6px 16px rgba(88,166,255,.2);
  background:linear-gradient(135deg,#161B22,#21262D);
}
.ac-red{border-left:5px solid #F85149!important;background:linear-gradient(90deg,rgba(248,81,73,.08),transparent);}
.ac-red:hover{background:linear-gradient(90deg,rgba(248,81,73,.15),rgba(24,23,23,0.5));}
.ac-org{border-left:5px solid #D29922!important;background:linear-gradient(90deg,rgba(210,153,34,.08),transparent);}
.ac-org:hover{background:linear-gradient(90deg,rgba(210,153,34,.15),rgba(24,23,23,0.5));}
.ac-grn{border-left:5px solid #3FB950!important;background:linear-gradient(90deg,rgba(63,185,80,.08),transparent);}
.ac-grn:hover{background:linear-gradient(90deg,rgba(63,185,80,.15),rgba(24,23,23,0.5));}

.kpi-box{background:linear-gradient(135deg,#161B22,#21262D);border:1px solid #30363D;
  border-radius:12px;padding:14px 10px;text-align:center;
  box-shadow:0 4px 12px rgba(0,0,0,.3);transition:all .25s;}
.kpi-box:hover{border-color:#58A6FF;transform:translateY(-2px);box-shadow:0 8px 24px rgba(88,166,255,.15);}
.kpi-num{font-size:28px;font-weight:800;line-height:1.1;margin:6px 0 2px;}
.kpi-lbl{font-size:9px;color:#8B949E;text-transform:uppercase;font-weight:700;letter-spacing:.06em;}
.kpi-sub{font-size:11px;color:#8B949E;margin-top:2px;}

.footer{text-align:center;color:#484F58;font-size:11px;padding:20px 0 6px;
  border-top:1px solid #21262D;margin-top:24px;}

/* Tooltip */
.tooltip-wrap{position:relative;display:inline-block;cursor:help;}
.tooltip-wrap:hover .tooltip-txt{visibility:visible;opacity:1;}
.tooltip-txt{visibility:hidden;background:#21262D;color:#C9D1D9;font-size:11px;
  border-radius:6px;padding:8px 12px;position:absolute;z-index:999;bottom:125%;
  left:50%;transform:translateX(-50%);width:220px;border:1px solid #30363D;
  opacity:0;transition:opacity .2s;}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# SESSION YÖNETİMİ — F5'e dayanıklı
# ═══════════════════════════════════════════════════════════
def _load_sessions() -> dict:
    try:
        if SESSION_FILE.exists():
            return json.loads(SESSION_FILE.read_text())
    except Exception:
        pass
    return {}

def _save_sessions(data: dict):
    try:
        SESSION_FILE.write_text(json.dumps(data))
    except Exception:
        pass

def _cleanup_sessions(sessions: dict) -> dict:
    now = time.time()
    return {k: v for k, v in sessions.items()
            if now - v.get("created", 0) < SESSION_TIMEOUT * 60}

def create_session(username: str) -> str:
    token = secrets.token_hex(32)
    sessions = _cleanup_sessions(_load_sessions())
    sessions[token] = {"username": username, "created": time.time(),
                       "login_time": datetime.now().strftime("%H:%M")}
    _save_sessions(sessions)
    return token

def validate_session(token: str) -> dict | None:
    if not token:
        return None
    sessions = _cleanup_sessions(_load_sessions())
    _save_sessions(sessions)
    return sessions.get(token)

def destroy_session(token: str):
    sessions = _load_sessions()
    sessions.pop(token, None)
    _save_sessions(sessions)

def get_session_token() -> str:
    """URL query param'dan token al."""
    try:
        return st.query_params.get("t", "")
    except Exception:
        return ""

def set_session_token(token: str):
    try:
        st.query_params["t"] = token
    except Exception:
        pass

def clear_session_token():
    try:
        st.query_params.clear()
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
# ZIYARETÇI SAYACI
# ═══════════════════════════════════════════════════════════
def get_counter() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        data = json.loads(COUNTER_FILE.read_text()) if COUNTER_FILE.exists() else {}
        if data.get("today_date") != today:
            data["today"] = 0
            data["today_date"] = today
        data["total"] = data.get("total", 0) + 1
        data["today"] = data.get("today", 0) + 1
        COUNTER_FILE.write_text(json.dumps(data))
        return data
    except Exception:
        return {"total": 0, "today": 0}

# ═══════════════════════════════════════════════════════════
# TARİHÇE / SNAPSHOT
# ═══════════════════════════════════════════════════════════
def append_snapshot(df):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        hist = json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []
        if hist and hist[-1]["date"] == today:
            return hist
        hist.append({
            "date":   today,
            "yuksek": int((df["Seviye"] == "YÜKSEK").sum()),
            "orta":   int((df["Seviye"] == "ORTA").sum()),
            "dusuk":  int((df["Seviye"] == "DÜŞÜK").sum()),
            "avg":    round(float(df["Final_Risk_Skoru"].mean()), 1),
            "patch":  int((df["Yamasız Gün"] > 60).sum()) if "Yamasız Gün" in df.columns else 0,
        })
        hist = hist[-60:]
        HISTORY_FILE.write_text(json.dumps(hist))
        return hist
    except Exception:
        return []

# ═══════════════════════════════════════════════════════════
# LOGİN
# ═══════════════════════════════════════════════════════════
def login_page():
    st.markdown("""
    <div style="text-align:center;padding:40px 0 20px">
      <div style="font-size:54px">🛡️</div>
      <h1 style="font-size:24px;font-weight:800;color:#E6EDF3;margin:8px 0 4px">
        IT Risk Intelligence Platform</h1>
      <p style="color:#8B949E;font-size:13px">Yetkili personel girişi</p>
    </div>""", unsafe_allow_html=True)

    _, c, _ = st.columns([1, 2, 1])
    with c:
        with st.form("login_form", clear_on_submit=False):
            user = st.text_input("Kullanıcı Adı", placeholder="Kullanıcı adı")
            pw   = st.text_input("Şifre", type="password", placeholder="Şifre")
            submitted = st.form_submit_button("Giriş Yap", use_container_width=True)

        if submitted:
            if not user or not pw:
                st.error("Kullanıcı adı ve şifre gerekli")
            else:
                pw_hash = hashlib.sha256(pw.encode("utf-8")).hexdigest()
                if CREDENTIALS.get(user.strip()) == pw_hash:
                    token = create_session(user.strip())
                    set_session_token(token)
                    st.rerun()
                else:
                    st.error("Hatalı kullanıcı adı veya şifre")

        st.markdown("""<div style="text-align:center;color:#484F58;font-size:11px;margin-top:16px">
            IT Risk Engine v6.2 — Sadece yetkili personel</div>""",
                    unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# VERİ YÜKLEME
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=120)
def load_data():
    src = CLEAN_DATA if CLEAN_DATA.exists() else RAW_DATA
    if not src.exists():
        return None, None, None, str(src)

    df = pd.read_excel(src)
    df.columns = df.columns.str.strip()

    for col in ["% Boş","Offline Gün","Yamasız Gün","Risk Skoru",
                "Final_Risk_Skoru","CVE_Bonus","Crit_Multiplier",
                "_RawDiskError","_RawAdminCount","_RawUpdateStop"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "Final_Risk_Skoru" not in df.columns or "Cihaz_Tipi" not in df.columns:
        RULES = [
            (r"(?i)\bDC\b|\bDC\d+\b|DOMAIN.CTRL|-DC-",r"(?i)Server","Domain Controller",1.6,25),
            (r"(?i)EXCH|MAIL.SRV|-EX\d",r"(?i)Server","Mail Server",1.5,20),
            (r"(?i)SQL|DB.SRV|-DB\d",r"(?i)Server","Veritabanı Sunucusu",1.5,20),
            (r"(?i)SRV|SVR|SERVER",r"","Sunucu",1.4,15),
            (r"",r"(?i)Server","Sunucu (OS)",1.35,10),
            (r"(?i)LAP|NTB|NOTEBOOK",r"","Laptop",1.0,0),
            (r"",r"","Workstation",1.0,0),
        ]
        def _cr(an,sv):
            an=str(an) if pd.notna(an) else ""; sv=str(sv) if pd.notna(sv) else ""
            for pn,ps,lbl,m,b in RULES:
                mn=bool(pn and re.search(pn,an)); ms=bool(ps and re.search(ps,sv))
                if pn and ps:
                    if mn and ms: return lbl,m,b
                elif pn:
                    if mn: return lbl,m,b
                elif ps:
                    if ms: return lbl,m,b
                else: return lbl,m,b
            return "Workstation",1.0,0
        cr=df.apply(lambda r:_cr(r.get("AssetName",""),r.get("Sistem","")),axis=1)
        df["Cihaz_Tipi"]=cr.apply(lambda x:x[0])
        df["Crit_Multiplier"]=cr.apply(lambda x:x[1])
        df["Final_Risk_Skoru"]=(
            df.get("Risk Skoru",pd.Series(0,index=df.index))*cr.apply(lambda x:x[1])
            +cr.apply(lambda x:x[2])
        ).clip(upper=100).round(0).astype(int)

    sev_map={"YUKSEK":"YÜKSEK","DUSUK":"DÜŞÜK","Yüksek":"YÜKSEK","Orta":"ORTA","Düşük":"DÜŞÜK"}
    if "Seviye" in df.columns:
        df["Seviye"]=df["Seviye"].astype(str).str.strip().replace(sev_map)
    else:
        df["Seviye"]=df["Final_Risk_Skoru"].apply(
            lambda x:"YÜKSEK" if x>=50 else("ORTA" if x>=25 else "DÜŞÜK"))

    for col in ["Kullanıcı","AssetName","IPAddress","Sistem","Cihaz_Tipi","Risk Analizi",
                "Kural Dışı Adminler (İsim ve Ünvan)","Riskli Paylaşılan Klasörler",
                "Tespit Edilen Şüpheli Yazılımlar","AssetID","Durum"]:
        if col in df.columns:
            df[col]=df[col].fillna("").astype(str)
        else:
            df[col]=""

    # Lansweeper linki — SADECE AssetID
    def _lsw(row):
        aid = str(row.get("AssetID","")).strip()
        if aid and aid not in ("","nan","None","0"):
            return ASSET_URL.format(aid=aid)
        return ""
    df["Lansweeper"]=df.apply(_lsw, axis=1)

    # IP → Şehir (ilk iki oktet)
    def _city(ip):
        if not ip or ip in ("","nan"): return None,None,None
        parts = str(ip).split(".")
        if len(parts) < 2: return None,None,None
        two = f"{parts[0]}.{parts[1]}"
        three = f"{parts[0]}.{parts[1]}.{parts[2]}" if len(parts)>2 else ""
        if two in SUBNET_CITY:
            return SUBNET_CITY[two]
        if parts[0] == "172":
            return SUBNET_CITY.get("172", GEBZE_DEFAULT)
        # Bilinmeyen 10.x.x → Gebze
        if parts[0] == "10":
            return GEBZE_DEFAULT
        return None,None,None
    locs=df["IPAddress"].apply(_city)
    df["Sehir"]=locs.apply(lambda x:x[0])
    df["Lat"]  =locs.apply(lambda x:x[1])
    df["Lon"]  =locs.apply(lambda x:x[2])

    # CVE
    cve_data,cve_meta={},{}
    cve_jsons=sorted(glob.glob(str(PROC_DIR/"cve_summary_*.json")),reverse=True)
    if cve_jsons:
        try:
            raw=json.loads(Path(cve_jsons[0]).read_text(encoding="utf-8"))
            cve_data=raw.get("sw_risk",{})
            cve_meta={k:v for k,v in raw.items() if k!="sw_risk"}
        except Exception: pass

    return df, cve_data, cve_meta, str(src)

# ═══════════════════════════════════════════════════════════
# YARDIMCILAR
# ═══════════════════════════════════════════════════════════
DARK=dict(paper_bgcolor="#0D1117",plot_bgcolor="#161B22",
          font=dict(color="#C9D1D9",family="Inter"),
          margin=dict(l=10,r=10,t=40,b=10))
SEV_CLR={"YÜKSEK":"#F85149","ORTA":"#D29922","DÜŞÜK":"#3FB950"}
CRIT_CLR={"Domain Controller":"#F85149","Mail Server":"#FF7B72",
           "Veritabanı Sunucusu":"#FFA657","Sunucu":"#D29922",
           "Sunucu (OS)":"#56D364","Laptop":"#58A6FF","Workstation":"#8B949E"}
SERVER_TYPES=["Domain Controller","Mail Server","Veritabanı Sunucusu","Sunucu","Sunucu (OS)"]

def sec(title, icon="", color="#F85149"):
    st.markdown(f'<div class="sec" style="border-left-color:{color}">'
                f'{"" if not icon else icon+" "}{title}</div>',
                unsafe_allow_html=True)

def kpi(col, value, label, color, sub=""):
    """Gerçek st.metric alternatifi — HTML ile renkli, hover'lı."""
    with col:
        st.markdown(f"""
<div class="kpi-box">
  <div class="kpi-lbl">{label}</div>
  <div class="kpi-num" style="color:{color}">{value:,}</div>
  <div class="kpi-sub">{sub}</div>
</div>""", unsafe_allow_html=True)

def show_table(dfs, height=500, sort_col=None, text_cols=None, link_col="Lansweeper"):
    if sort_col and sort_col in dfs.columns:
        dfs=dfs.sort_values(sort_col,ascending=False)
    cfg={}
    if link_col and link_col in dfs.columns:
        # LinkColumn'u emojili başlık ile göster
        cfg[link_col]=st.column_config.LinkColumn(link_col,display_text="🔗 Aç")
    for tc in (text_cols or []):
        if tc in dfs.columns:
            cfg[tc]=st.column_config.TextColumn(tc,width="large")
    st.dataframe(dfs,use_container_width=True,height=height,
                 column_config=cfg or None,hide_index=True)

def sbar(df, key, cols=None):
    q=st.text_input("Ara (cihaz / kullanici / IP)","",key=key,
                    placeholder="cihaz adi, kullanici veya IP...")
    if q:
        sc=cols or ["AssetName","Kullanıcı","IPAddress"]
        mask=pd.Series(False,index=df.index)
        for c in sc:
            if c in df.columns:
                mask|=df[c].astype(str).str.contains(q,case=False,na=False)
        df=df[mask]
    return df

def posture_score(df)->int:
    n=len(df)
    if n==0: return 0
    nh=int((df["Seviye"]=="YÜKSEK").sum())
    pc=int((df["Yamasız Gün"]>60).sum()) if "Yamasız Gün" in df.columns else 0
    oc=int((df["Offline Gün"]>60).sum())  if "Offline Gün" in df.columns else 0
    return max(0,min(100,int(100-(nh/n*50+pc/n*30+oc/n*20))))

def footer():
    st.markdown("""<div class="footer">
    Designed by <b>hsaldiran</b> &nbsp;·&nbsp; IT Risk Engine v6.2 &nbsp;·&nbsp;
    IT Risk Intelligence Platform v5.0</div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TÜRKİYE HARİTASI
# ═══════════════════════════════════════════════════════════
def turkey_map(df):
    map_df=df[df["Lat"].notna()&df["Sehir"].notna()&(df["Sehir"]!="None")].copy()
    if len(map_df)==0:
        st.info("Harita icin IP-Sehir eslestirmesi bulunamadi. "
                "SUBNET_CITY sozlugunu guncelleyin.")
        return

    city_risk=map_df.groupby(["Sehir","Lat","Lon"]).agg(
        Cihaz=("Final_Risk_Skoru","count"),
        Ort_Risk=("Final_Risk_Skoru","mean"),
        Yuksek=("Seviye",lambda x:(x=="YÜKSEK").sum()),
        Orta=("Seviye",lambda x:(x=="ORTA").sum()),
    ).reset_index()
    city_risk["Ort_Risk"]=city_risk["Ort_Risk"].round(1)
    city_risk["Renk"]=city_risk["Ort_Risk"].apply(
        lambda x:"#F85149" if x>=50 else("#D29922" if x>=25 else "#3FB950"))
    city_risk["Boyut"]=(city_risk["Cihaz"]/city_risk["Cihaz"].max()*35+12).round(0)

    fig=go.Figure()
    for _,r in city_risk.iterrows():
        fig.add_trace(go.Scattergeo(
            lon=[r["Lon"]],lat=[r["Lat"]],
            mode="markers+text",
            marker=dict(size=r["Boyut"],color=r["Renk"],opacity=0.85,
                        line=dict(color="#0D1117",width=2),
                        symbol="circle"),
            text=[f"{r['Sehir']}<br>{int(r['Cihaz'])} cihaz"],
            textposition="top center",
            textfont=dict(color="#E6EDF3",size=9),
            name=r["Sehir"],
            showlegend=False,
            hovertemplate=(
                f"<b>{r['Sehir']}</b><br>"
                f"Toplam: {int(r['Cihaz'])} cihaz<br>"
                f"Ort. Risk: {r['Ort_Risk']}<br>"
                f"Yuksek: {int(r['Yuksek'])} · Orta: {int(r['Orta'])}"
                "<extra></extra>"
            ),
        ))

    fig.update_geos(
        scope="asia",
        center=dict(lon=35,lat=39),
        projection_scale=5,
        showland=True,    landcolor="#1C2333",
        showocean=True,   oceancolor="#0D1117",
        showcoastlines=True, coastlinecolor="#30363D",
        showcountries=True, countrycolor="#30363D",
        showlakes=False,  showrivers=False,
        showframe=True,   framecolor="#30363D", bgcolor="#0D1117",
        showsubunits=True,subunitcolor="#21262D",
    )
    fig.update_layout(**DARK,height=420,showlegend=False,
                      geo_bgcolor="#0D1117")
    st.plotly_chart(fig,use_container_width=True)

    # Şehir özet tablosu
    show_cols=city_risk[["Sehir","Cihaz","Ort_Risk","Yuksek","Orta"]].copy()
    show_cols.columns=["Sehir","Cihaz","Ort. Risk","Yuksek","Orta"]
    show_cols=show_cols.sort_values("Ort. Risk",ascending=False)
    st.dataframe(show_cols,use_container_width=True,height=200,hide_index=True)

# ═══════════════════════════════════════════════════════════
# SAYFA: EXECUTIVE DASHBOARD
# ═══════════════════════════════════════════════════════════
def page_executive(df, hist, counter, session_info):
    n  = len(df)
    nh = int((df["Seviye"]=="YÜKSEK").sum())
    nm = int((df["Seviye"]=="ORTA").sum())
    nl = int((df["Seviye"]=="DÜŞÜK").sum())
    pc = int((df["Yamasız Gün"]>60).sum())  if "Yamasız Gün" in df.columns else 0
    oc = int((df["Offline Gün"]>60).sum())  if "Offline Gün" in df.columns else 0
    ec = int(df["Sistem"].str.contains("Win 7|2008|8.1|XP|2012",na=False).sum()) if "Sistem" in df.columns else 0
    adm= int(df["_RawAdminCount"].gt(0).sum()) if "_RawAdminCount" in df.columns else 0
    shd= int(df["Tespit Edilen Şüpheli Yazılımlar"].ne("").sum())
    avg= round(float(df["Final_Risk_Skoru"].mean()),1)
    sc = posture_score(df)
    sc_clr = "#F85149" if sc<40 else "#D29922" if sc<65 else "#3FB950"
    sc_lbl = "Kritik"  if sc<40 else "Orta"    if sc<65 else "Iyi"

    # Başlık satırı
    ca,cb,cc = st.columns([3,2,1])
    with ca:
        st.markdown("## IT - Risk Engine")
        st.caption(f"{n} cihaz analiz edildi · {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    with cb:
        # Postür açıklaması ile detaylı tooltip
        st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px 16px">
  <div style="font-size:10px;color:#8B949E;text-transform:uppercase;font-weight:700;margin-bottom:4px">
    🛡️ Güvenlik Postürü Skoru
    <span class="tooltip-wrap" style="color:#58A6FF;cursor:help;margin-left:4px">?
      <span class="tooltip-txt"><b>Postür Skoru Nedir?</b><br><br>
      Kuruluşunuzun genel siber güvenlik sağlığını 0-100 arasında ölçen metriktir.<br><br>
      <b>Hesaplama:</b><br>
      • Yüksek riskli cihazlar (-50%)<br>
      • 60+ gün yamasız sistemler (-30%)<br>
      • 60+ gün offline cihazlar (-20%)<br><br>
      <b>Değerlendirme:</b><br>
      • 80-100 = ✅ İyi<br>
      • 65-79 = ⚠️ Orta<br>
      • 0-64 = 🔴 Kritik</span>
    </span>
  </div>
  <div style="font-size:28px;font-weight:800;color:{sc_clr}">{sc}<span style="font-size:14px">/100</span>
    <span style="font-size:11px;background:{sc_clr};color:#fff;padding:2px 8px;
    border-radius:4px;margin-left:8px">{sc_lbl}</span>
  </div>
</div>""", unsafe_allow_html=True)
        st.progress(sc/100)
    with cc:
        st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:10px;
padding:12px;text-align:center">
  <div style="font-size:9px;color:#8B949E;text-transform:uppercase">Ziyaret</div>
  <div style="font-size:24px;font-weight:800;color:#58A6FF">{counter.get('total',0)}</div>
  <div style="font-size:10px;color:#8B949E">Bugun: {counter.get('today',0)}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # KPI satırı — gerçek HTML (JS yok, renk var)
    cols=st.columns(8)
    kpi(cols[0], n,   "Toplam Cihaz",   "#58A6FF", f"Ort:{avg}")
    kpi(cols[1], nh,  "Yuksek Risk",    "#F85149", f"%{nh/n*100:.1f}")
    kpi(cols[2], nm,  "Orta Risk",      "#D29922", f"%{nm/n*100:.1f}")
    kpi(cols[3], nl,  "Dusuk Risk",     "#3FB950", f"%{nl/n*100:.1f}")
    kpi(cols[4], pc,  "Patch 60g+",     "#FF7B72", f"%{pc/n*100:.1f}")
    kpi(cols[5], oc,  "Offline 60g+",   "#79C0FF", "")
    kpi(cols[6], ec,  "EoL Isletim",    "#D2A8FF", "")
    kpi(cols[7], adm, "Yetkisiz Admin", "#FFA657", "")

    st.markdown("---")
    c1,c2,c3=st.columns(3)

    with c1:
        sec("Risk Dagilimi")
        fig=go.Figure(go.Pie(
            labels=["Yuksek","Orta","Dusuk"],
            values=[nh,nm,nl], hole=0.48,
            marker=dict(colors=["#F85149","#D29922","#3FB950"],
                        line=dict(color="#0D1117",width=2)),
            textinfo="label+percent+value",
            textfont=dict(color="#E6EDF3",size=11),
            hovertemplate="<b>%{label}</b><br>%{value} cihaz · %{percent}<extra></extra>",
        ))
        fig.add_annotation(text=f"<b>{n}</b><br>cihaz",
                           x=0.5,y=0.5,showarrow=False,
                           font=dict(size=13,color="#E6EDF3"))
        fig.update_layout(**DARK,height=280,showlegend=False)
        st.plotly_chart(fig,use_container_width=True)

    with c2:
        sec("Gunluk Risk Trendi")
        if len(hist)>1:
            hdf=pd.DataFrame(hist)
            hdf["date"]=pd.to_datetime(hdf["date"])
            fig2=go.Figure()
            fig2.add_trace(go.Scatter(x=hdf["date"],y=hdf["yuksek"],name="Yuksek",
                line=dict(color="#F85149",width=2.5),fill="tozeroy",
                fillcolor="rgba(248,81,73,.1)",
                hovertemplate="%{y} cihaz · %{x|%d.%m}<extra>Yuksek</extra>"))
            fig2.add_trace(go.Scatter(x=hdf["date"],y=hdf["orta"],name="Orta",
                line=dict(color="#D29922",width=2),
                hovertemplate="%{y} cihaz · %{x|%d.%m}<extra>Orta</extra>"))
            fig2.update_layout(**DARK,height=280,
                               legend=dict(font=dict(color="#C9D1D9")))
            st.plotly_chart(fig2,use_container_width=True)
            d=hist[-1]["yuksek"]-hist[-2]["yuksek"]
            if d<0: st.success(f"Yuksek risk {abs(d)} azaldi — iyilesiyor")
            elif d>0: st.error(f"Yuksek risk {d} artti — mudahale gerekiyor")
            else: st.info("Risk seviyesi stabil")
        else:
            st.info("Trend verisi biriktirilmekte. Risk engine her calistiginda snapshot alinir.")

    with c3:
        sec("Tehdit Turleri")
        tmap={"Onaysız Yönetici Yetkisi":"Yetkisiz Admin",
              "DLP Yüklü Değil":"DLP Eksik",
              "Antivirüs (SEP) Eksik":"AV Yok",
              "Güvenlik Yamaları Eksik":"Patch Eksik",
              "Şüpheli Yazılım":"Shadow IT",
              "Desteklenmeyen OS":"EoL OS",
              "Update Servisi Kapalı":"WU Kapali",
              "Riskli Paylaşım":"Acik Klasor",
              "Uzun Süredir Offline":"Offline",
              "Sabit Şifreli Admin":"Sabit Sifre"}
        ra=df.get("Risk Analizi",pd.Series("",index=df.index)).astype(str)
        threats={lbl:int(ra.str.contains(kw,na=False,regex=False).sum())
                 for kw,lbl in tmap.items()}
        threats={k:v for k,v in sorted(threats.items(),key=lambda x:-x[1]) if v>0}
        if threats:
            tdf=pd.DataFrame(list(threats.items()),columns=["Tehdit","Sayi"])
            fig3=px.bar(tdf.sort_values("Sayi"),x="Sayi",y="Tehdit",orientation="h",
                        color="Sayi",color_continuous_scale=["#3FB950","#D29922","#F85149"],
                        text="Sayi")
            fig3.update_layout(**DARK,height=280,showlegend=False,coloraxis_showscale=False)
            fig3.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"),
                               hovertemplate="<b>%{y}</b><br>%{x} cihaz<extra></extra>")
            st.plotly_chart(fig3,use_container_width=True)

    # Aksiyon Paneli
    st.markdown("---")
    sec("🚨 Önerilen Aksiyonlar")
    st.caption("⚡ Kartı tıklayarak ilgili sayfaya gidin")
    actions=[
        ("ac-red",  f"🔴 {nh} yüksek riskli cihaz — acil müdahale bekliyor",    "🔒 Security Operations") if nh>0 else None,
        ("ac-red",  f"🔴 {pc} cihaz 60+ gün yamasız — Windows Update acil",   "🩹 Patch & Offline")     if pc>0 else None,
        ("ac-org",  f"🟠 {adm} cihazda yetkisiz admin — AD'den kaldır",       "🔒 Security Operations") if adm>0 else None,
        ("ac-org",  f"🟠 {oc} cihaz 60+ gün offline — zombi cihaz inceleme",  "🩹 Patch & Offline")     if oc>0 else None,
        ("ac-grn",  f"🟡 {shd} cihazda şüpheli yazılım — kaldırma iş emri",     "🔒 Security Operations") if shd>0 else None,
        ("ac-org",  f"🟠 {ec} EoL işletim sistemi — yükseltme planı gerekli", "🖥️ Sunucu & Kritik")      if ec>0 else None,
    ]
    for item in [a for a in actions if a]:
        css, msg, dest = item
        # Kartın tamamı tıklanabilir hale geldi
        st.markdown(f"""
<div class="action-card {css}" style="cursor:pointer;" onclick="
    const btn = document.querySelector('[data-action=\"{dest}\"]');
    if(btn) btn.click();
">
    {msg}
</div>""",unsafe_allow_html=True)
        # Hidden button (görünmez ama JavaScript tarafından çalışır)
        if st.button(dest, key=f"act_nav_{dest}", label_visibility="collapsed"):
            st.session_state["goto_page"]=dest
            st.rerun()

    # Patch halka grafiği
    st.markdown("---")
    sec("Patch Uyum Analizi")
    if "Yamasız Gün" in df.columns and df["Yamasız Gün"].sum()>0:
        ca3,cb3=st.columns([2,1])
        with ca3:
            bins=[0,7,30,60,90,180,9999]
            lbls=["0-7g","8-30g","31-60g","61-90g","91-180g","180g+"]
            df["_pb"]=pd.cut(df["Yamasız Gün"].clip(lower=0),bins=bins,labels=lbls,right=True)
            pd_=df["_pb"].value_counts().reindex(lbls,fill_value=0).reset_index()
            pd_.columns=["Aralik","Cihaz"]
            uyumlu=int((df["Yamasız Gün"]<=60).sum())
            fig_p=go.Figure(go.Pie(
                labels=pd_["Aralik"],values=pd_["Cihaz"],hole=0.52,
                marker=dict(colors=["#3FB950","#56D364","#D29922","#FFA657","#F85149","#8B1A1A"],
                            line=dict(color="#0D1117",width=2)),
                textinfo="label+value",
                textfont=dict(color="#E6EDF3",size=10),
                direction="clockwise",sort=False,
                hovertemplate="<b>%{label}</b><br>%{value} cihaz · %{percent}<extra></extra>",
            ))
            fig_p.add_annotation(text=f"<b>{uyumlu}</b><br>uyumlu",
                                 x=0.5,y=0.5,showarrow=False,
                                 font=dict(size=13,color="#3FB950"))
            fig_p.update_layout(**DARK,height=300,showlegend=True,
                                legend=dict(font=dict(color="#C9D1D9")))
            st.plotly_chart(fig_p,use_container_width=True)
        with cb3:
            st.metric("Uyumlu (60g)",f"{uyumlu}",f"%{uyumlu/n*100:.1f}")
            st.metric("Kritik (60g+)",f"{pc}",f"%{pc/n*100:.1f}",delta_color="inverse")
            st.metric("Ort. Yamasiz",f"{df['Yamasız Gün'].mean():.1f}g")
            st.metric("Max Yamasiz",f"{int(df['Yamasız Gün'].max())}g")

    # Türkiye Haritası
    st.markdown("---")
    sec("Cihaz Lokasyon Haritasi — Turkiye")
    turkey_map(df)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: SECURITY OPERATIONS
# ═══════════════════════════════════════════════════════════
def page_security_ops(df, cve_data, cve_meta):
    st.title("Security Operations Center")
    n=len(df)
    c1,c2,c3,c4=st.columns(4)
    with c1: filtered=sbar(df,"so_s")
    with c2: sev_f=st.multiselect("Risk Seviyesi",["YÜKSEK","ORTA","DÜŞÜK"],default=["YÜKSEK","ORTA","DÜŞÜK"],key="so_sev")
    with c3: s0,s1=st.slider("Risk Skoru",0,100,(0,100),key="so_sc")
    with c4:
        ctypes=sorted(df["Cihaz_Tipi"].unique().tolist()) if "Cihaz_Tipi" in df.columns else []
        ct_f=st.multiselect("Cihaz Tipi",ctypes,default=ctypes,key="so_ct")
    if sev_f: filtered=filtered[filtered["Seviye"].isin(sev_f)]
    filtered=filtered[(filtered["Final_Risk_Skoru"]>=s0)&(filtered["Final_Risk_Skoru"]<=s1)]
    if ct_f and "Cihaz_Tipi" in filtered.columns:
        filtered=filtered[filtered["Cihaz_Tipi"].isin(ct_f)]
    st.caption(f"**{len(filtered)}** / {n} cihaz")

    tab1,tab2,tab3,tab4,tab5,tab6=st.tabs([
        "📊 Cihaz Listesi",
        "🚨 Tehdit Analizi", 
        "🩹 Patch Uyumu",
        "🦠 CVE Risk",
        "🔑 Admin & Kimlik",
        "🌐 Ağ & Güvenlik"
    ])

    with tab1:
        sec("Cihaz Risk Tablosu")
        st.caption("Lansweeper sutununa tiklayarak cihazi Lansweeper'da acabilirsiniz")
        cols=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem","Cihaz_Tipi",
                           "Risk Skoru","Final_Risk_Skoru","CVE_Bonus","Seviye","Risk Analizi"]
              if c in filtered.columns]
        show_table(filtered[cols].sort_values("Final_Risk_Skoru",ascending=False),
                   height=520,text_cols=["Risk Analizi","Sistem"])
        csv=filtered[cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV Indir",csv,f"risk_{datetime.now().strftime('%Y%m%d_%H%M')}.csv","text/csv")

        sec("Risk Skoru Dagilimi")
        hov={c:True for c in ["AssetName","Kullanıcı","Cihaz_Tipi","CVE_Bonus"] if c in filtered.columns}
        fig=px.scatter(filtered,x="Yamasız Gün",y="Final_Risk_Skoru",color="Seviye",
                       color_discrete_map=SEV_CLR,hover_data=hov,size_max=10,opacity=0.7)
        fig.add_hline(y=50,line_dash="dash",line_color="#F85149",annotation_text="Yuksek (50)")
        fig.add_vline(x=60,line_dash="dash",line_color="#D29922",annotation_text="Kritik Patch (60g)")
        fig.update_layout(**DARK,height=360,legend=dict(font=dict(color="#C9D1D9")))
        st.plotly_chart(fig,use_container_width=True)

    with tab2:
        sec("Tehdit Analizi")
        threat_detail={
            "Onaysız Yönetici Yetkisi":("Erisim Kontrolu","#F85149","Yetkisiz admin grubu: lateral movement ve veri ihlali riski"),
            "DLP Yüklü Değil":("Veri Koruma","#FF7B72","DLP olmadan hassas veri USB/e-posta ile sizdirilebilir"),
            "Antivirüs (SEP) Eksik":("Endpoint","#F85149","SEP olmayan cihazlar ransomware icin acik hedeftir"),
            "Güvenlik Yamaları Eksik":("Patch","#D29922","Yamasiz sistemler bilinen CVE'lerle hizlica istismar edilir"),
            "Şüpheli Yazılım Tespit Edildi":("Shadow IT","#D29922","Kontrol disi yazilimlar veri kacagi ve C2 kanal riski"),
            "Desteklenmeyen OS (EoL)":("Platform","#F85149","EoL OS icin guvenlik yamasi yok — sifir-gun aciklari yamalanmaz"),
            "Update Servisi Kapalı":("Patch","#D29922","Windows Update kapali — kritik yamalar gelmiyor"),
            "Riskli Paylaşım":("Ag","#D29922","Acik SMB paylasimlar ransomware lateral movement vektoru"),
            "Uzun Süredir Offline":("Cihaz","#8B949E","60+ gun offline cihazlar yamalardan mahrum donuyor"),
            "Sabit Şifreli Admin":("Kimlik","#FF7B72","PasswordNeverExpires flag'li hesaplar credential harvesting hedefi"),
        }
        ra=filtered.get("Risk Analizi",pd.Series("",index=filtered.index)).astype(str)
        rows=[]
        for kw,(cat,clr,desc) in threat_detail.items():
            cnt=int(ra.str.contains(kw,na=False,regex=False).sum())
            if cnt>0:
                rows.append({"Tehdit":kw,"Kategori":cat,"Etkilenen":cnt,
                             "Oran":f"%{cnt/len(filtered)*100:.1f}",
                             "Risk Aciklamasi":desc,"Renk":clr})
        if rows:
            th_df=pd.DataFrame(rows).sort_values("Etkilenen",ascending=False)
            ca,cb=st.columns([2,1])
            with ca:
                fig_t=go.Figure()
                for _,r in th_df.iterrows():
                    fig_t.add_trace(go.Bar(
                        x=[r["Etkilenen"]],y=[r["Tehdit"]],orientation="h",
                        marker_color=r["Renk"],
                        text=[f"{r['Etkilenen']} cihaz  {r['Oran']}"],
                        textposition="outside",textfont=dict(color="#C9D1D9",size=11),
                        name=r["Tehdit"],showlegend=False,
                        hovertemplate=f"<b>{r['Tehdit']}</b><br>{r['Etkilenen']} cihaz ({r['Oran']})<br>{r['Risk Aciklamasi']}<extra></extra>",
                    ))
                fig_t.update_layout(**DARK,height=max(320,len(th_df)*38),
                                    showlegend=False,barmode="overlay")
                fig_t.update_xaxes(range=[0,th_df["Etkilenen"].max()*1.35])
                st.plotly_chart(fig_t,use_container_width=True)
            with cb:
                st.dataframe(th_df[["Tehdit","Kategori","Etkilenen","Oran"]],
                             use_container_width=True,hide_index=True,height=350)

            sec("Tehdit Aciklamalari")
            for _,r in th_df.iterrows():
                with st.expander(f"{r['Tehdit']} — {r['Etkilenen']} cihaz ({r['Oran']})"):
                    st.markdown(f"""
- **Kategori:** {r['Kategori']}
- **Risk:** {r['Risk Aciklamasi']}
                    """)
                    affected=filtered[ra.str.contains(r["Tehdit"],na=False,regex=False)]
                    cols_a=[c for c in ["Lansweeper","AssetName","Kullanıcı","Cihaz_Tipi","Final_Risk_Skoru","Seviye"]
                            if c in affected.columns]
                    show_table(affected[cols_a].sort_values("Final_Risk_Skoru",ascending=False),height=200)

    with tab3:
        ca,cb=st.columns(2)
        with ca:
            if "Yamasız Gün" in filtered.columns:
                fig6=px.histogram(filtered,x="Yamasız Gün",nbins=25,color_discrete_sequence=["#58A6FF"],
                                  title="Yamasiz Gun Dagilimi")
                fig6.add_vline(x=60,line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
                fig6.update_layout(**DARK,height=280)
                st.plotly_chart(fig6,use_container_width=True)
        with cb:
            if "Offline Gün" in filtered.columns:
                fig7=px.histogram(filtered,x="Offline Gün",nbins=25,color_discrete_sequence=["#D29922"],
                                  title="Offline Gun Dagilimi")
                fig7.add_vline(x=60,line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
                fig7.update_layout(**DARK,height=280)
                st.plotly_chart(fig7,use_container_width=True)
        sec("Kritik Patch Listesi (60g+)")
        p_df=filtered[filtered["Yamasız Gün"]>60].sort_values("Yamasız Gün",ascending=False) \
             if "Yamasız Gün" in filtered.columns else filtered.head(0)
        cols_p=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem",
                             "Cihaz_Tipi","Yamasız Gün","Final_Risk_Skoru","Seviye"]
                if c in p_df.columns]
        show_table(p_df[cols_p],height=360)

    with tab4:
        sec("🦠 CVE Risk Analizi")
        st.caption("CVE'ye sahip yazılımlar ve bunların risk katkısı")
        cve_risk=filtered[filtered["CVE_Bonus"]>0].sort_values("CVE_Bonus",ascending=False) if "CVE_Bonus" in filtered.columns else filtered.head(0)
        if len(cve_risk)>0:
            ca2,cb2=st.columns([2,1])
            with ca2:
                cve_counts=cve_risk["CVE_Bonus"].value_counts().head(10)
                fig_cve=px.bar(x=cve_counts.index,y=cve_counts.values,
                              color=cve_counts.values,color_continuous_scale=["#3FB950","#D29922","#F85149"],
                              labels={"x":"CVE Bonus Puanı","y":"Cihaz Sayısı"},
                              title="CVE Bonus Dağılımı")
                fig_cve.update_layout(**DARK,height=300,showlegend=False)
                st.plotly_chart(fig_cve,use_container_width=True)
            with cb2:
                st.metric("🦠 CVE'li Cihaz",len(cve_risk))
                avg_bonus=cve_risk["CVE_Bonus"].mean()
                st.metric("Ort. Bonus Puanı",f"+{avg_bonus:.1f}")
                max_bonus=cve_risk["CVE_Bonus"].max()
                st.metric("Max Bonus",f"+{max_bonus:.0f}")
            
            sec("CVE'li Cihazlar")
            cols_cve=[c for c in ["Lansweeper","AssetName","Kullanıcı","Sistem","CVE_Bonus","Final_Risk_Skoru","Seviye"]
                      if c in cve_risk.columns]
            show_table(cve_risk[cols_cve],height=400,sort_col="CVE_Bonus")
        else:
            st.info("✅ CVE'ye sahip yazılım tespit edilmemiştir")

    with tab5:
        sec("🔑 Admin Yetkisi & Kimlik Riski")
        st.caption("Yetkisiz admin grubu ve sabit şifreli hesaplar")
        admin_risk=filtered[filtered["_RawAdminCount"].gt(0)] if "_RawAdminCount" in filtered.columns else filtered.head(0)
        
        ca3,cb3=st.columns(2)
        with ca3:
            if len(admin_risk)>0:
                admin_counts=admin_risk["_RawAdminCount"].value_counts().head(8)
                fig_admin=px.bar(x=admin_counts.values,y=admin_counts.index,orientation="h",
                               color_discrete_sequence=["#FF7B72"],
                               labels={"x":"Ekstra Admin Sayısı","y":"Cihaz"},
                               title="Cihaz Başına Admin Üyeliği")
                fig_admin.update_layout(**DARK,height=320)
                st.plotly_chart(fig_admin,use_container_width=True)
        with cb3:
            st.metric("👥 Yetkisiz Admin",len(admin_risk))
            if len(admin_risk)>0:
                avg_admins=admin_risk["_RawAdminCount"].mean()
                st.metric("Ort. Admin Sayısı",f"{avg_admins:.1f}")
        
        if len(admin_risk)>0:
            sec("Yetkisiz Admin Grubu Cihazları")
            cols_admin=[c for c in ["Lansweeper","AssetName","Kullanıcı","_RawAdminCount","Final_Risk_Skoru","Seviye"]
                        if c in admin_risk.columns]
            show_table(admin_risk[cols_admin],height=350)
        else:
            st.success("✅ Tüm cihazlarda standart admin sayısı var")

    with tab6:
        sec("🌐 Ağ & Güvenlik")
        st.caption("Riskli paylaşımlar, DLP ve firewall durumu")
        
        ca4,cb4,cc4=st.columns(3)
        
        risk_analysis=filtered.get("Risk Analizi",pd.Series("",index=filtered.index)).astype(str)
        
        dlp_missing=int(risk_analysis.str.contains("DLP",na=False,regex=False).sum())
        firewall_off=int(risk_analysis.str.contains("Firewall",na=False,regex=False).sum())
        risky_share=int(risk_analysis.str.contains("Riskli Paylaşım",na=False,regex=False).sum())
        
        with ca4:
            st.metric("📱 DLP Eksik",dlp_missing)
        with cb4:
            st.metric("🔥 Firewall Kapali",firewall_off)
        with cc4:
            st.metric("📂 Riskli Paylaşım",risky_share)
        
        # Ağ tehditleri özet
        if dlp_missing + firewall_off + risky_share > 0:
            sec("Ağ Tehditleri Detayı")
            net_threats={
                "DLP Eksik": ("Endpoint DLP olmayan cihazlar USB/email ile veri sızıntısına açık",dlp_missing,"#FF7B72"),
                "Firewall Kapali": ("Windows Firewall kapalı sistemler network atağına açık",firewall_off,"#F85149"),
                "Riskli Paylaşım": ("SMB paylaşımı herkese açık — ransomware lateral movement vektörü",risky_share,"#D29922"),
            }
            nt_rows=[]
            for threat_name, (desc,cnt,clr) in net_threats.items():
                if cnt>0:
                    nt_rows.append({"Tehdit":threat_name,"Cihaz":cnt,"Açıklama":desc,"Renk":clr})
            
            if nt_rows:
                for row in nt_rows:
                    st.markdown(f"""
<div style="background:rgba({int(row['Renk'][1:3],16)},{int(row['Renk'][3:5],16)},{int(row['Renk'][5:],16)},.1);
border-left:4px solid {row['Renk']};border-radius:6px;padding:10px 12px;margin:6px 0">
  <b style="color:{row['Renk']}">{row['Tehdit']}</b> ({row['Cihaz']} cihaz)<br>
  <span style="font-size:12px;color:#C9D1D9">{row['Açıklama']}</span>
</div>""",unsafe_allow_html=True)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: SUNUCU & KRİTİK
# ═══════════════════════════════════════════════════════════
def page_servers(df):
    st.title("Kritik Sunucu & Altyapi Analizi")
    st.markdown("""
<div style="background:#161B22;border:1px solid #F85149;border-radius:10px;
padding:14px 18px;margin-bottom:16px">
<b style="color:#F85149">Kritik Varlik Uyarisi:</b>
<span style="color:#C9D1D9"> Domain Controller veya Mail Server ihlali tum agi tehlikeye atar.
Bu cihazlara ozel patch onceligi ve 7/24 izleme zorunludur.</span>
</div>""", unsafe_allow_html=True)

    # Sunucu tespiti
    if "Cihaz_Tipi" in df.columns:
        servers=df[df["Cihaz_Tipi"].isin(SERVER_TYPES)].copy()
    else:
        mask=(df.get("AssetName","").str.contains(r"(?i)SRV|SVR|SERVER|DC|SQL|EXCH|MAIL",na=False)
              |df.get("Sistem","").str.contains(r"(?i)Server",na=False))
        servers=df[mask].copy()

    if len(servers)==0:
        st.info("Sunucu tipinde cihaz bulunamadi. Cihaz isimlendirmesini kontrol edin (SRV/SVR/DC/SQL/EXCH).")
        return

    ns=len(servers); ns_h=int((servers["Seviye"]=="YÜKSEK").sum())
    ns_m=int((servers["Seviye"]=="ORTA").sum()); ns_l=int((servers["Seviye"]=="DÜŞÜK").sum())
    ns_p=int((servers["Yamasız Gün"]>60).sum()) if "Yamasız Gün" in servers.columns else 0

    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("Toplam Sunucu",ns); c2.metric("Yuksek",ns_h)
    c3.metric("Orta",ns_m); c4.metric("Dusuk",ns_l); c5.metric("Yamasiz (60g+)",ns_p)
    st.markdown("---")

    # Filtreler
    c1,c2,c3=st.columns([2,1,1])
    with c1: filtered_srv=sbar(servers,"srv_s")
    with c2:
        sev_sf=st.multiselect("Risk Seviyesi",["YÜKSEK","ORTA","DÜŞÜK"],
                              default=["YÜKSEK","ORTA","DÜŞÜK"],key="srv_sev")
    with c3:
        avail=sorted(servers["Cihaz_Tipi"].unique().tolist()) if "Cihaz_Tipi" in servers.columns else []
        type_f=st.multiselect("Sunucu Tipi",avail,default=avail,key="srv_t")

    if sev_sf: filtered_srv=filtered_srv[filtered_srv["Seviye"].isin(sev_sf)]
    if type_f and "Cihaz_Tipi" in filtered_srv.columns:
        filtered_srv=filtered_srv[filtered_srv["Cihaz_Tipi"].isin(type_f)]
    st.caption(f"**{len(filtered_srv)}** sunucu gosteriliyor")

    col1,col2=st.columns(2)
    with col1:
        sec("Sunucu Tipi Risk Karsilastirmasi")
        if "Cihaz_Tipi" in servers.columns and len(servers)>0:
            ct_s=servers.groupby("Cihaz_Tipi")["Final_Risk_Skoru"].agg(["mean","count"]).reset_index()
            ct_s.columns=["Tip","Ort_Risk","Adet"]; ct_s["Ort_Risk"]=ct_s["Ort_Risk"].round(1)
            colors_s=[CRIT_CLR.get(t,"#8B949E") for t in ct_s["Tip"]]
            fig=go.Figure(go.Bar(x=ct_s["Tip"],y=ct_s["Ort_Risk"],
                marker=dict(color=colors_s,line=dict(color="#0D1117",width=1)),
                text=[f"{v} ({a})" for v,a in zip(ct_s["Ort_Risk"],ct_s["Adet"])],
                textposition="outside",textfont=dict(color="#C9D1D9"),
                hovertemplate="<b>%{x}</b><br>Ort. Risk: %{y}<extra></extra>"))
            fig.add_hline(y=50,line_dash="dash",line_color="#F85149",annotation_text="Yuksek (50)")
            fig.update_layout(**DARK,height=300,showlegend=False)
            st.plotly_chart(fig,use_container_width=True)
    with col2:
        sec("Sunucu Risk Seviyesi")
        if ns_h+ns_m+ns_l>0:
            fig2=go.Figure(go.Pie(
                labels=["Yuksek","Orta","Dusuk"],values=[ns_h,ns_m,ns_l],hole=0.48,
                marker=dict(colors=["#F85149","#D29922","#3FB950"],
                            line=dict(color="#0D1117",width=2)),
                textinfo="label+value+percent",textfont=dict(color="#E6EDF3"),
                hovertemplate="<b>%{label}</b><br>%{value} sunucu<extra></extra>"))
            fig2.update_layout(**DARK,height=300,showlegend=False)
            st.plotly_chart(fig2,use_container_width=True)

    TYPE_INFO={
        "Domain Controller":{"color":"#F85149","risk":"MAKSIMUM",
            "desc":"Tum agin kimlik dogrulama merkezi. Ele gecirilirse domain coker.",
            "checks":["DC replikasyonu saglikli mi?","DSRM sifresi belgelenmi?",
                      "Privileged Access Workstation kullaniliyor mu?","Son yedekleme kontrol edildi mi?"]},
        "Mail Server":{"color":"#FF7B72","risk":"KRITIK",
            "desc":"Phishing, veri sizdirma ve MITM saldirilarinin birincil hedefi.",
            "checks":["SPF/DKIM/DMARC yapilandirildi mi?","TLS 1.2+ zorunlu mu?",
                      "Spam filtresi guncel mi?","Ekler sandbox'ta taraniyor mu?"]},
        "Veritabanı Sunucusu":{"color":"#FFA657","risk":"KRITIK",
            "desc":"Kritik is verisi deposu. SQL injection ve yetkisiz erisim en buyuk tehlikeler.",
            "checks":["SA hesabi devre disi mi?","Sifreli baglanti zorunlu mu?",
                      "Audit logging aktif mi?","En az yetkili servis hesaplari mi?"]},
        "Sunucu":{"color":"#D29922","risk":"YUKSEK",
            "desc":"Uygulama/dosya sunucusu. Servis hesaplari ve ayricali erisim riski.",
            "checks":["Host firewall aktif mi?","Gereksiz rol/feature kaldirildi mi?",
                      "Servis hesaplari minimum yetkili mi?"]},
        "Sunucu (OS)":{"color":"#56D364","risk":"YUKSEK",
            "desc":"Sunucu isletim sistemi algilanan cihaz.",
            "checks":["Sunucu oldugu teyit edildi mi?","Rol atanmis mi?","Patch takibi yapiliyor mu?"]},
    }

    sec("Sunucu Detaylari","","#8957E5")
    for _,row in filtered_srv.sort_values("Final_Risk_Skoru",ascending=False).iterrows():
        ctype=str(row.get("Cihaz_Tipi","Sunucu"))
        info=TYPE_INFO.get(ctype,TYPE_INFO["Sunucu"])
        sev=str(row.get("Seviye",""))
        score=int(row.get("Final_Risk_Skoru",0))
        yamasiz=int(row.get("Yamasız Gün",0))
        lsw=str(row.get("Lansweeper",""))
        icon="Yuksek" if sev=="YÜKSEK" else "Orta" if sev=="ORTA" else "Dusuk"

        with st.expander(
            f"[{icon}] {row.get('AssetName','?')} · Skor: {score} · {ctype} · {row.get('IPAddress','')}",
            expanded=(sev=="YÜKSEK")):
            ca,cb,cc=st.columns([2,2,1])
            with ca:
                st.markdown(f"""
**Tip:** {ctype} — **{info['risk']}**

**Kullanici:** {row.get('Kullanıcı','-')}
**IP:** {row.get('IPAddress','-')}
**OS:** {row.get('Sistem','-')}

_{info['desc']}_
""")
                if lsw: st.markdown(f"[Lansweeper'da Ac]({lsw})")
            with cb:
                ra=str(row.get("Risk Analizi",""))
                if ra.strip():
                    for item in ra.split("•"):
                        if item.strip(): st.error(f"• {item.strip()}")
                else:
                    st.success("Aktif risk tespiti yok")
                kd=str(row.get("Kural Dışı Adminler (İsim ve Ünvan)",""))
                if kd.strip(): st.warning(f"Yetkisiz Admin: {kd}")
                sw=str(row.get("Tespit Edilen Şüpheli Yazılımlar",""))
                if sw.strip(): st.error(f"Suphe Yazilim: {sw}")
                st.markdown("**Kontrol Listesi:**")
                for chk in info.get("checks",[]):
                    st.checkbox(chk,key=f"chk_{row.get('AssetName','')}_{chk[:12]}")
            with cc:
                st.metric("Final",score); st.metric("Ham",int(row.get("Risk Skoru",0)))
                st.metric("CVE+",int(row.get("CVE_Bonus",0)))
                st.metric("Yamasiz",f"{yamasiz}g","KRİTİK" if yamasiz>60 else "Normal",
                          delta_color="inverse" if yamasiz>60 else "normal")

    sec("Sunucu Tablosu")
    cols_s=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem","Cihaz_Tipi",
                         "Risk Skoru","Final_Risk_Skoru","CVE_Bonus","Seviye"]
            if c in filtered_srv.columns]
    show_table(filtered_srv[cols_s].sort_values("Final_Risk_Skoru",ascending=False),height=400)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: CİHAZ DETAY
# ═══════════════════════════════════════════════════════════
def page_device(df):
    st.title("Cihaz Detay Analizi")
    st.caption("Tum cihazlar listelenir. Dropdown'dan bir cihaz secin tam profilini goruntuleyin.")

    c1,c2,c3=st.columns([2,1,1])
    with c1: q=st.text_input("Cihaz ara","",key="dd_q",placeholder="cihaz adi veya IP...")
    with c2:
        sev_d=st.multiselect("Risk Seviyesi",["YÜKSEK","ORTA","DÜŞÜK"],
                             default=["YÜKSEK","ORTA","DÜŞÜK"],key="dd_sev")
    with c3:
        ctypes=sorted(df["Cihaz_Tipi"].unique().tolist()) if "Cihaz_Tipi" in df.columns else []
        ct_d=st.multiselect("Cihaz Tipi",ctypes,default=ctypes,key="dd_ct")

    filtered_d=df.copy()
    if q:
        mask=pd.Series(False,index=filtered_d.index)
        for col in ["AssetName","IPAddress","Kullanıcı"]:
            if col in filtered_d.columns:
                mask|=filtered_d[col].astype(str).str.contains(q,case=False,na=False)
        filtered_d=filtered_d[mask]
    if sev_d: filtered_d=filtered_d[filtered_d["Seviye"].isin(sev_d)]
    if ct_d and "Cihaz_Tipi" in filtered_d.columns:
        filtered_d=filtered_d[filtered_d["Cihaz_Tipi"].isin(ct_d)]

    st.caption(f"**{len(filtered_d)}** cihaz")
    all_cols=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem","Cihaz_Tipi",
                           "Risk Skoru","Final_Risk_Skoru","CVE_Bonus","Seviye"]
              if c in filtered_d.columns]
    show_table(filtered_d[all_cols].sort_values("Final_Risk_Skoru",ascending=False),height=320)

    st.markdown("---")
    if "AssetName" in filtered_d.columns and len(filtered_d)>0:
        sel_opts=filtered_d.sort_values("Final_Risk_Skoru",ascending=False)["AssetName"].tolist()
        selected=st.selectbox("Profil goster:",sel_opts,key="dd_sel")
        row=filtered_d[filtered_d["AssetName"]==selected].iloc[0]

        sev=str(row.get("Seviye","")); score=int(row.get("Final_Risk_Skoru",0))
        sc_clr="#F85149" if sev=="YÜKSEK" else "#D29922" if sev=="ORTA" else "#3FB950"
        lsw=str(row.get("Lansweeper",""))

        st.markdown(f"""
<div style="background:linear-gradient(135deg,#161B22,#21262D);
border:1px solid #30363D;border-left:4px solid {sc_clr};
border-radius:12px;padding:20px 24px;margin:12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <h2 style="color:#E6EDF3;margin:0">{row.get('AssetName','?')}</h2>
      <span style="color:#8B949E;font-size:13px">
        {row.get('Kullanıcı','-')} · {row.get('IPAddress','-')} ·
        {row.get('Sistem','-')} · {row.get('Cihaz_Tipi','?')}</span>
    </div>
    <div style="text-align:right">
      <div style="font-size:52px;font-weight:900;color:{sc_clr};line-height:1">{score}</div>
      <div style="font-size:12px;color:#8B949E">Final Risk Skoru</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

        c1,c2,c3,c4,c5,c6=st.columns(6)
        c1.metric("Final",score); c2.metric("Ham",int(row.get("Risk Skoru",0)))
        c3.metric("CVE+",int(row.get("CVE_Bonus",0)))
        y=int(row.get("Yamasız Gün",0))
        c4.metric("Yamasiz",f"{y}g","KRITIK" if y>60 else "Normal",delta_color="inverse" if y>60 else "normal")
        c5.metric("Offline",f"{int(row.get('Offline Gün',0))}g")
        c6.metric("Disk",f"%{int(row.get('% Boş',0))}")
        if lsw: st.markdown(f"[Lansweeper'da Ac]({lsw})")

        col1,col2=st.columns(2)
        with col1:
            sec("Risk Analizi")
            ra=str(row.get("Risk Analizi",""))
            if ra.strip():
                for item in ra.split("•"):
                    if item.strip(): st.error(f"• {item.strip()}")
            else:
                st.success("Risk tespiti yok")
            kd=str(row.get("Kural Dışı Adminler (İsim ve Ünvan)",""))
            if kd.strip(): st.warning(f"Yetkisiz Admin: {kd}")
            sw=str(row.get("Tespit Edilen Şüpheli Yazılımlar",""))
            if sw.strip(): st.error(f"Suphe Yazilim: {sw}")
        with col2:
            sec("Risk Gauge")
            fig_g=go.Figure(go.Indicator(
                mode="gauge+number+delta",value=score,
                delta={"reference":int(row.get("Risk Skoru",0))},
                title={"text":"Final Risk Skoru","font":{"color":"#C9D1D9","size":12}},
                gauge={"axis":{"range":[0,100],"tickcolor":"#8B949E"},
                       "bar":{"color":sc_clr,"thickness":.25},
                       "bgcolor":"#161B22","bordercolor":"#30363D",
                       "steps":[{"range":[0,25],"color":"#0D3320"},
                                 {"range":[25,50],"color":"#3D2800"},
                                 {"range":[50,100],"color":"#3D0000"}],
                       "threshold":{"value":50,"line":{"color":"#F85149","width":2},"thickness":.75}}
            ))
            fig_g.update_layout(**DARK,height=270)
            st.plotly_chart(fig_g,use_container_width=True)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: KULLANICI RİSKİ
# ═══════════════════════════════════════════════════════════
def page_users(df):
    st.title("Kullanici Risk Analizi")
    cs,cf=st.columns([2,2])
    with cs: q_u=st.text_input("Kullanici ara","",key="usr_q",placeholder="kullanici adi...")
    with cf:
        sev_uf=st.multiselect("Cihaz risk seviyesi",["YÜKSEK","ORTA","DÜŞÜK"],
                              default=["YÜKSEK","ORTA","DÜŞÜK"],key="usev")
    df_u=df[df["Seviye"].isin(sev_uf)] if sev_uf else df
    agg={"Cihaz":("Final_Risk_Skoru","count"),"Ort_Risk":("Final_Risk_Skoru","mean"),
         "Max_Risk":("Final_Risk_Skoru","max"),
         "Yuksek":("Seviye",lambda x:(x=="YÜKSEK").sum()),
         "Max_Yamasiz":("Yamasız Gün","max")}
    for sc_,dst_ in [("_RawAdminCount","Admin"),("_RawDiskError","Disk"),("_RawUpdateStop","WU")]:
        if sc_ in df_u.columns: agg[dst_]=(sc_,"sum")
    ur=df_u.groupby("Kullanıcı").agg(**agg).reset_index()
    ur["Ort_Risk"]=ur["Ort_Risk"].round(1)
    ur["Davranis Puani"]=(ur["Ort_Risk"]
        +ur.get("Admin",pd.Series(0,index=ur.index))*10
        +ur["Max_Yamasiz"].apply(lambda x:20 if x>60 else 0)
    ).round(1)
    ur=ur.sort_values("Davranis Puani",ascending=False)
    if q_u: ur=ur[ur["Kullanıcı"].str.contains(q_u,case=False,na=False)]
    st.caption(f"**{len(ur)}** kullanici")
    fig=px.bar(ur.head(15).sort_values("Davranis Puani"),
               x="Davranis Puani",y="Kullanıcı",orientation="h",
               color="Davranis Puani",
               color_continuous_scale=["#3FB950","#D29922","#F85149","#8B1A1A"],
               text="Davranis Puani")
    fig.update_layout(**DARK,height=420,showlegend=False,coloraxis_showscale=False)
    fig.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"))
    st.plotly_chart(fig,use_container_width=True)
    show_table(ur,height=440,sort_col="Davranis Puani",link_col="")
    if q_u and len(ur)==1:
        sec("Kullanici Cihazlari")
        ud=df[df["Kullanıcı"].str.contains(q_u,case=False,na=False)]
        cols=[c for c in ["Lansweeper","AssetName","IPAddress","Sistem","Cihaz_Tipi",
                           "Final_Risk_Skoru","Seviye","Risk Analizi"] if c in ud.columns]
        show_table(ud[cols],height=280,sort_col="Final_Risk_Skoru",text_cols=["Risk Analizi"])
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: ASSET CRİTİCALİTY
# ═══════════════════════════════════════════════════════════
def page_criticality(df):
    st.title("Asset Criticality Analizi")
    c1,c2,c3=st.columns([2,1,1])
    with c1: filtered_ac=sbar(df,"ac")
    with c2:
        ctypes=sorted(df["Cihaz_Tipi"].unique().tolist()) if "Cihaz_Tipi" in df.columns else []
        ct_f=st.multiselect("Cihaz Tipi",ctypes,default=ctypes,key="act")
    with c3:
        sev_af=st.multiselect("Risk Seviyesi",["YÜKSEK","ORTA","DÜŞÜK"],
                              default=["YÜKSEK","ORTA","DÜŞÜK"],key="asev")
    if ct_f and "Cihaz_Tipi" in filtered_ac.columns:
        filtered_ac=filtered_ac[filtered_ac["Cihaz_Tipi"].isin(ct_f)]
    if sev_af: filtered_ac=filtered_ac[filtered_ac["Seviye"].isin(sev_af)]
    ct=df.groupby("Cihaz_Tipi").agg(
        Sayi=("Final_Risk_Skoru","count"),Ort_Final=("Final_Risk_Skoru","mean"),
        Ort_Ham=("Risk Skoru","mean"),Yuksek=("Seviye",lambda x:(x=="YÜKSEK").sum())
    ).reset_index().sort_values("Ort_Final",ascending=False)
    col1,col2=st.columns(2)
    with col1:
        sec("Cihaz Tipi Dagilimi")
        fig_p=go.Figure(go.Pie(values=ct["Sayi"],labels=ct["Cihaz_Tipi"],hole=0.4,
            marker=dict(colors=[CRIT_CLR.get(t,"#8B949E") for t in ct["Cihaz_Tipi"]],
                        line=dict(color="#0D1117",width=2)),
            textinfo="label+percent+value",textfont=dict(color="#E6EDF3",size=11),
            hovertemplate="<b>%{label}</b><br>%{value} cihaz · %{percent}<extra></extra>"))
        fig_p.update_layout(**DARK,height=320,showlegend=False)
        st.plotly_chart(fig_p,use_container_width=True)
    with col2:
        sec("Ham vs Final Skor")
        fig_b=go.Figure()
        fig_b.add_trace(go.Bar(name="Ham (Lansweeper)",x=ct["Cihaz_Tipi"],y=ct["Ort_Ham"].round(1),
            marker_color="#3498DB",opacity=0.85,text=ct["Ort_Ham"].round(1),
            textposition="outside",textfont=dict(color="#C9D1D9"),
            hovertemplate="<b>%{x}</b><br>Ham: %{y}<extra></extra>"))
        fig_b.add_trace(go.Bar(name="Final (Criticality)",x=ct["Cihaz_Tipi"],y=ct["Ort_Final"].round(1),
            marker_color="#F85149",opacity=0.85,text=ct["Ort_Final"].round(1),
            textposition="outside",textfont=dict(color="#C9D1D9"),
            hovertemplate="<b>%{x}</b><br>Final: %{y}<extra></extra>"))
        fig_b.add_hline(y=50,line_dash="dash",line_color="#D29922",annotation_text="Yuksek (50)")
        fig_b.update_layout(**DARK,height=320,barmode="group",legend=dict(font=dict(color="#C9D1D9")))
        st.plotly_chart(fig_b,use_container_width=True)
    cols_c=[c for c in ["Lansweeper","AssetName","Kullanıcı","Sistem","Cihaz_Tipi",
                         "Crit_Multiplier","Risk Skoru","Final_Risk_Skoru","CVE_Bonus","Seviye"]
            if c in filtered_ac.columns]
    show_table(filtered_ac[cols_c].sort_values(["Cihaz_Tipi","Final_Risk_Skoru"],ascending=[True,False]),height=460)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: PATCH & OFFLİNE
# ═══════════════════════════════════════════════════════════
def page_patch(df):
    st.title("Patch & Offline Analizi")
    n=len(df)
    pc=int((df["Yamasız Gün"]>60).sum()) if "Yamasız Gün" in df.columns else 0
    oc=int((df["Offline Gün"]>60).sum())  if "Offline Gün" in df.columns else 0
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Patch Kritik (60g+)",pc,f"%{pc/n*100:.1f}",delta_color="inverse")
    c2.metric("Offline Kritik (60g+)",oc)
    c3.metric("Ort. Yamasiz",f"{df['Yamasız Gün'].mean():.1f}g" if "Yamasız Gün" in df.columns else "?")
    c4.metric("Max Yamasiz",f"{int(df['Yamasız Gün'].max())}g" if "Yamasız Gün" in df.columns else "?")
    ca,cb=st.columns(2)
    with ca:
        if "Yamasız Gün" in df.columns:
            fig=px.histogram(df,x="Yamasız Gün",nbins=30,color_discrete_sequence=["#58A6FF"])
            fig.add_vline(x=60,line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
            fig.update_layout(**DARK,height=260)
            st.plotly_chart(fig,use_container_width=True)
    with cb:
        if "Offline Gün" in df.columns:
            fig2=px.histogram(df,x="Offline Gün",nbins=30,color_discrete_sequence=["#D29922"])
            fig2.add_vline(x=60,line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
            fig2.update_layout(**DARK,height=260)
            st.plotly_chart(fig2,use_container_width=True)
    sec("Kritik Patch Listesi")
    p_df=df[df["Yamasız Gün"]>60].sort_values("Yamasız Gün",ascending=False) if "Yamasız Gün" in df.columns else df.head(0)
    cols_p=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem","Cihaz_Tipi","Yamasız Gün","Final_Risk_Skoru","Seviye"] if c in p_df.columns]
    show_table(p_df[cols_p],height=360)
    sec("Kritik Offline Listesi")
    o_df=df[df["Offline Gün"]>60].sort_values("Offline Gün",ascending=False) if "Offline Gün" in df.columns else df.head(0)
    cols_o=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Offline Gün","Final_Risk_Skoru","Seviye"] if c in o_df.columns]
    show_table(o_df[cols_o],height=300)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: CVE
# ═══════════════════════════════════════════════════════════
def page_cve(df,cve_data,cve_meta):
    st.title("CVE & Zafiyet Istihbarati")
    if not cve_data:
        st.warning("CVE verisi yok.")
        st.code("python scripts/cve_scanner.py")
        return
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("Taranan",cve_meta.get("toplam_tarama",0))
    c2.metric("Acik Bulunan",cve_meta.get("vuln_yazilim",0))
    c3.metric("Toplam CVE",cve_meta.get("toplam_cve",0))
    c4.metric("Kritik",cve_meta.get("kritik",0))
    c5.metric("Yuksek",cve_meta.get("yuksek",0))
    WHY={"anydesk":"Uzak masaustu — RCE ve kimlik dogrulama bypass CVE'leri",
         "teamviewer":"Uzak masaustu — kimlik bypass ve ayricali yukseltme",
         "wireshark":"Ag analiz — kotu amacli paket ayristirmasi uzerinden RCE",
         "nmap":"Port tarama — kesif saldirilari","chrome":"Tarayici — V8 RCE CVE'leri",
         "firefox":"Tarayici — use-after-free CVE'leri","java":"JRE — deserialization",
         "adobe":"PDF/Flash RCE","office":"Makro/OLE tabanli RCE","vlc":"Medya ayristirma",
         "7-zip":"Arsiv yigin tasmasi","winrar":"ACE path traversal","zoom":"Ara bellek CVE",
         "telegram":"Medya isleme RCE","whatsapp":"Medya dosyasi RCE","steam":"Yerel ayricali"}
    def why(n):
        k=n.lower()
        for key,r in WHY.items():
            if key in k: return r
        return "NIST NVD'de detayli CVE bilgisi mevcut"
    def cvss_lbl(s): return "Kritik" if s>=9 else("Yuksek" if s>=7 else "Orta")
    rows=[{"Yazilim":k,"Max CVSS":round(float(v.get("max_cvss",0)),1),
           "CVE Sayisi":int(v.get("cve_sayisi",0)),"Risk Bonusu":int(v.get("bonus",0)),
           "Kritiklik":cvss_lbl(float(v.get("max_cvss",0))),"Neden Riskli":why(k),
           "Tavsiye":"ACIL — hemen yamala" if float(v.get("max_cvss",0))>=9 else "Bu hafta yamala" if float(v.get("max_cvss",0))>=7 else "Sonraki maintenance'ta"}
          for k,v in cve_data.items()]
    cve_df=pd.DataFrame(rows).sort_values("Max CVSS",ascending=False)
    col1,col2=st.columns([2,1])
    with col1:
        sec("En Tehlikeli Yazilimlar")
        fig=px.bar(cve_df.head(20).sort_values("Max CVSS"),x="Max CVSS",y="Yazilim",orientation="h",
                   color="Max CVSS",color_continuous_scale=["#D29922","#F85149","#8B1A1A"],
                   text="Max CVSS",hover_data={"Neden Riskli":True,"CVE Sayisi":True})
        fig.add_vline(x=9,line_dash="dash",line_color="#F85149",annotation_text="Kritik (9.0)")
        fig.add_vline(x=7,line_dash="dot",line_color="#D29922",annotation_text="Yuksek (7.0)")
        fig.update_layout(**DARK,height=500,showlegend=False,coloraxis_showscale=False)
        fig.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"))
        st.plotly_chart(fig,use_container_width=True)
    with col2:
        sec("Kritiklik")
        kc=cve_df["Kritiklik"].value_counts().reset_index()
        kc.columns=["Seviye","Adet"]
        fig2=go.Figure(go.Pie(labels=kc["Seviye"],values=kc["Adet"],hole=0.4,
            marker=dict(colors=["#F85149","#D29922","#D2A8FF"],line=dict(color="#0D1117",width=2)),
            textinfo="label+value+percent",textfont=dict(color="#E6EDF3"),
            hovertemplate="<b>%{label}</b><br>%{value} yazilim · %{percent}<extra></extra>"))
        fig2.update_layout(**DARK,height=260,showlegend=False)
        st.plotly_chart(fig2,use_container_width=True)
        st.markdown("**Bonus:**\n- Kritik → +20 puan\n- Yuksek → +12 puan")
    sec("Tum Acik Yazilimlar")
    ca2,cb2=st.columns([2,1])
    with ca2: q_cv=st.text_input("Yazilim ara","",key="cvs_q")
    with cb2:
        sev_cv=st.multiselect("Kritiklik",["Kritik","Yuksek","Orta"],
                              default=["Kritik","Yuksek","Orta"],key="cvsev")
    cve_df_f=cve_df.copy()
    if q_cv: cve_df_f=cve_df_f[cve_df_f["Yazilim"].str.contains(q_cv,case=False,na=False)]
    if sev_cv: cve_df_f=cve_df_f[cve_df_f["Kritiklik"].isin(sev_cv)]
    st.dataframe(cve_df_f,use_container_width=True,height=420,hide_index=True,
                 column_config={"Max CVSS":st.column_config.NumberColumn(format="%.1f"),
                                "Neden Riskli":st.column_config.TextColumn(width="large"),
                                "Tavsiye":st.column_config.TextColumn(width="large")})
    if "Tespit Edilen Şüpheli Yazılımlar" in df.columns:
        rk=[k.lower() for k in cve_data.keys()]
        at_risk=df[df["Tespit Edilen Şüpheli Yazılımlar"].apply(
            lambda c: isinstance(c,str) and any(k in c.lower() for k in rk))]
        st.caption(f"**{len(at_risk)}** cihaz CVE'li yazilim barindiruyor")
        cr=[c for c in ["Lansweeper","AssetName","Kullanıcı","Cihaz_Tipi","Final_Risk_Skoru",
                         "CVE_Bonus","Seviye","Tespit Edilen Şüpheli Yazılımlar"] if c in at_risk.columns]
        show_table(at_risk[cr].sort_values("CVE_Bonus",ascending=False),height=340,
                   sort_col="CVE_Bonus",text_cols=["Tespit Edilen Şüpheli Yazılımlar"])
    csv=cve_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("CVE CSV Indir",csv,f"cve_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
    footer()

# ═══════════════════════════════════════════════════════════
# ANA UYGULAMA
# ═══════════════════════════════════════════════════════════
PAGES=[
    "📊 Executive Dashboard",
    "🔒 Security Operations",
    "🖥️ Sunucu & Kritik",
    "💻 Cihaz Detay",
    "👤 Kullanıcı Riski",
    "⚠️ Asset Criticality",
    "🩹 Patch & Offline",
    "🦠 CVE İstihbarı"
]

def main():
    # F5-dayanıklı session — URL query param'da token saklanıyor
    token = get_session_token()
    session_info = validate_session(token) if token else None

    if not session_info:
        login_page()
        return

    # Sayaç — session başına bir kez
    if "counted" not in st.session_state:
        counter = get_counter()
        st.session_state["counted"] = True
        st.session_state["counter"] = counter
    else:
        counter = st.session_state.get("counter", {"total":0,"today":0})

    # Veri
    with st.spinner("Risk verisi yukleniyor..."):
        df,cve_data,cve_meta,src=load_data()
    if df is None:
        st.error(f"Veri bulunamadi: {src}\nOnce risk_engine_v62.py calistirin.")
        return

    hist=append_snapshot(df)
    if not hist:
        try: hist=json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []
        except: hist=[]

    sc=posture_score(df)
    sc_clr="#F85149" if sc<40 else "#D29922" if sc<65 else "#3FB950"

    # Aksiyon butonundan gelen yönlendirme
    goto=st.session_state.pop("goto_page","")

    with st.sidebar:
        st.markdown(f"""
<div style="padding:10px 0 6px">
  <div style="font-size:19px;font-weight:800;color:#E6EDF3">IT - Risk Engine</div>
  <div style="font-size:9px;color:#484F58;letter-spacing:.08em;text-transform:uppercase">
    Intelligence Platform v5.0</div>
</div>""", unsafe_allow_html=True)

        st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
padding:10px;margin:8px 0;text-align:center">
  <div style="font-size:9px;color:#8B949E;text-transform:uppercase">
    Guvenlik Postur Skoru
    <span title="0-100 araliginda genel guvenlik sagligi. 80+ = Iyi, 65-79 = Orta, 65 alti = Kritik.
    Yuksek riskli cihaz orani, yamalanmamis sistemler ve offline cihazlar bu skoru dusurur."
    style="color:#58A6FF;cursor:help"> ?</span>
  </div>
  <div style="font-size:26px;font-weight:800;color:{sc_clr}">{sc}</div>
  <div style="font-size:9px;color:#8B949E">/100</div>
</div>""", unsafe_allow_html=True)
        st.progress(sc/100)
        st.markdown("---")

        default_idx=0
        if goto and goto in PAGES:
            default_idx=PAGES.index(goto)
        page=st.radio("Menu",PAGES,index=default_idx)

        st.markdown("---")
        if st.button("Veriyi Yenile"):
            st.cache_data.clear(); st.rerun()
        if st.button("Cikis Yap"):
            destroy_session(token)
            clear_session_token()
            st.session_state.clear()
            st.rerun()

        st.markdown(f"""
<div style="font-size:10px;color:#484F58;margin-top:10px;line-height:1.8">
  Kullanici: {session_info.get('username','?')}<br>
  Giris: {session_info.get('login_time','')}<br>
  Ziyaret: {counter.get('today',0)} bugun / {counter.get('total',0)} toplam<br>
  <br>Designed by <b style="color:#30363D">hsaldiran</b>
</div>""", unsafe_allow_html=True)

    # Sayfa yönlendirme
    if   page=="📊 Executive Dashboard":   page_executive(df,hist,counter,session_info)
    elif page=="🔒 Security Operations":   page_security_ops(df,cve_data,cve_meta)
    elif page=="🖥️ Sunucu & Kritik":       page_servers(df)
    elif page=="💻 Cihaz Detay":           page_device(df)
    elif page=="👤 Kullanıcı Riski":       page_users(df)
    elif page=="⚠️ Asset Criticality":     page_criticality(df)
    elif page=="🩹 Patch & Offline":       page_patch(df)
    elif page=="🦠 CVE İstihbarı":       page_cve(df,cve_data,cve_meta)

if __name__=="__main__":
    main()
