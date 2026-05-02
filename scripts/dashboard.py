# -*- coding: utf-8 -*-
"""
IT Risk Engine — Dashboard v5.0
pip install streamlit plotly pandas openpyxl watchdog
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501
"""

import os, json, glob, hashlib, re, secrets, time, warnings
from pathlib import Path
from datetime import datetime, timedelta

# Streamlit uyarılarını sustur (stIconMaterial, use_container_width, DeprecationWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*stIconMaterial.*")
warnings.filterwarnings("ignore", message=".*use_container_width.*")
warnings.filterwarnings("ignore", message=".*container_width.*")
warnings.filterwarnings("ignore", message=".*Icon.*")

import pandas as pd
import streamlit as st
# Cihaz Geçmişi, Şeffaflık ve Tahmin modülü
try:
    import sys as _sys2, os as _os2
    _sys2.path.insert(0, _os2.path.dirname(_os2.path.abspath(__file__)))
    from device_history_engine import gecmis_oku, puan_ozeti, tahmin as risk_tahmin
    DEVHIST_OK = True
except Exception as _dhe:
    DEVHIST_OK = False
    def gecmis_oku(x): return []
    def puan_ozeti(x): return {"aktif_maddeler":[],"pasif_maddeler":[],"ham_sql":0,"carpan":1.0,"bonus":0,"cve_bonus":0,"final":0,"hesaplanan":0}
    def risk_tahmin(x, **kw): return {"yeterli_veri":False,"mesaj":"Modül yüklenemedi.","trend":"bilinmiyor","uyari":None,"guven":"yok","veri_sayisi":0}
# MITRE ve CIS modülleri
try:
    from mitre_mapper import TECHNIQUES, TACTICS, THREAT_TO_TECHNIQUES, df_to_technique_counts, taktik_bazli_ozet
    from compliance_engine import CIS_CONTROLS, cis_hesapla, genel_uyum_skoru
    MITRE_OK = True
except Exception as _e:
    MITRE_OK = False
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
_SUBNET_CONFIG = Path(__file__).parent.parent / "config" / "subnet_city.json"
if _SUBNET_CONFIG.exists():
    with open(_SUBNET_CONFIG, encoding="utf-8") as _f:
        SUBNET_CITY = {k: tuple(v) for k, v in _json.load(_f).items()}
else:
    # Örnek yapı — config/subnet_city.json oluşturun
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
HISTORY_DIR   = PROC_DIR / "history"           # günlük snapshot CSV'leri
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

.kpi-box{border-radius:10px;padding:10px 8px;text-align:center;
  box-shadow:0 4px 14px rgba(0,0,0,.4);transition:all .25s;
  min-height:82px!important;height:82px!important;
  display:flex!important;flex-direction:column!important;
  justify-content:center!important;box-sizing:border-box!important;}
.kpi-box:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(0,0,0,.5);filter:brightness(1.1);}
.kpi-num{font-size:22px!important;font-weight:900;line-height:1;margin:3px 0 1px;}
.kpi-lbl{font-size:8px!important;color:rgba(255,255,255,0.55)!important;text-transform:uppercase;
  font-weight:700;letter-spacing:.05em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.kpi-sub{font-size:10px!important;color:rgba(255,255,255,0.35)!important;margin-top:1px;}

/* Aksiyon kart git butonu */
div[data-testid="stButton"] button {
    background:transparent!important;
    border:1px solid #30363D!important;
    color:#58A6FF!important;
    font-size:12px!important;
    border-radius:6px!important;
    transition:all .2s!important;
}
div[data-testid="stButton"] button:hover {
    background:#21262D!important;
    border-color:#58A6FF!important;
}

.footer{text-align:center;color:#484F58;font-size:11px;padding:20px 0 6px;
  border-top:1px solid #21262D;margin-top:24px;}

/* Tooltip */
.tooltip-wrap{position:relative;display:inline-block;cursor:help;}
.tooltip-wrap:hover .tooltip-txt{visibility:visible;opacity:1;}
.tooltip-txt{visibility:hidden;background:#21262D;color:#C9D1D9;font-size:11px;
  border-radius:6px;padding:8px 12px;position:absolute;z-index:999;bottom:125%;
  left:50%;transform:translateX(-50%);width:220px;border:1px solid #30363D;
  opacity:0;transition:opacity .2s;}

/* ───────────────────────────────────────
   stIconMaterial (Material Design Icons) — metinlerin üstünü kapıyor
   Streamlit içinde native MDI kullanıyor; bunları normalize ediyoruz
   ─────────────────────────────────────── */

/* Genel: tüm stIconMaterial span'larını satır içine al, taşmalarını kapat */
span[data-testid="stIconMaterial"] {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    vertical-align: middle !important;
    font-size: 16px !important;
    line-height: 1 !important;
    overflow: hidden !important;
    width: 20px !important;
    height: 20px !important;
    flex-shrink: 0 !important;
}

/* Selectbox / multiselect dropdown oku — küçük ve hizalı */
[data-baseweb="select"] span[data-testid="stIconMaterial"],
[data-baseweb="select"] ~ div span[data-testid="stIconMaterial"] {
    font-size: 18px !important;
    width: 18px !important;
    height: 18px !important;
    color: #8B949E !important;
    pointer-events: none !important;
}

/* Sidebar radio/nav ikonları */
[data-testid="stSidebar"] span[data-testid="stIconMaterial"] {
    font-size: 14px !important;
    width: 16px !important;
    height: 16px !important;
    color: #8B949E !important;
}

/* Streamlit header/sayfa ikon alanı */
[data-testid="stAppViewContainer"] > header span[data-testid="stIconMaterial"] {
    font-size: 18px !important;
}

/* Expander ok işaretleri */
[data-testid="stExpanderToggleIcon"] span[data-testid="stIconMaterial"] {
    font-size: 20px !important;
    color: #8B949E !important;
}

/* Genel metin akışında yüzen ikonları sabitle */
p span[data-testid="stIconMaterial"],
div span[data-testid="stIconMaterial"],
label span[data-testid="stIconMaterial"] {
    position: relative !important;
    top: 0 !important;
    left: 0 !important;
    float: none !important;
}
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
        n_   = len(df)
        snap = {
            "date":   today,
            "yuksek": int((df["Seviye"] == "YÜKSEK").sum()),
            "orta":   int((df["Seviye"] == "ORTA").sum()),
            "dusuk":  int((df["Seviye"] == "DÜŞÜK").sum()),
            "avg":    round(float(df["Final_Risk_Skoru"].mean()), 1),
            "max":    int(df["Final_Risk_Skoru"].max()),
            "patch":  int((df["Yamasız Gün"] > 60).sum()) if "Yamasız Gün" in df.columns else 0,
            "offline":int((df["Offline Gün"]  > 60).sum()) if "Offline Gün"  in df.columns else 0,
            "admin":  int(df["_RawAdminCount"].gt(0).sum()) if "_RawAdminCount" in df.columns else 0,
            "n":      n_,
            "posture":max(0,min(100,int(100-(
                (df["Seviye"]=="YÜKSEK").sum()/max(n_,1)*50
                +((df["Yamasız Gün"]>60).sum() if "Yamasız Gün" in df.columns else 0)/max(n_,1)*30
                +((df["Offline Gün"]>60).sum()  if "Offline Gün"  in df.columns else 0)/max(n_,1)*20
            )))),
        }
        hist.append(snap)
        hist = hist[-90:]  # 90 gün sakla
        HISTORY_FILE.write_text(json.dumps(hist))

        # History klasörüne günlük CSV kaydet
        try:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            csv_path = HISTORY_DIR / f"snapshot_{today}.csv"
            if not csv_path.exists():
                import csv as _csv
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    w = _csv.DictWriter(f, fieldnames=snap.keys())
                    w.writeheader()
                    w.writerow(snap)
        except Exception:
            pass

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

    # ── AssetID sütun normalizasyonu ──────────────────────────────────────────
    # Lansweeper'dan gelen dosyada sütun adı "AssetID1", "AssetID", "Asset ID",
    # "asset_id" gibi farklı varyantlarda gelebilir.
    import re as _re2
    def _nc(s): return _re2.sub(r"[^a-z0-9]","",s.strip().lower())
    _AID_OK = {"assetid","assetid1","assetid2"}
    _aid_col = next((c for c in df.columns if _nc(c) in _AID_OK), None)
    if _aid_col is None:
        # processed dosyasında zaten "AssetID" olarak kaydedilmiş olabilir
        if "AssetID" in df.columns:
            _aid_col = "AssetID"
    if _aid_col and _aid_col != "AssetID":
        df["AssetID"] = df[_aid_col].copy()

    for col in ["Kullanıcı","AssetName","IPAddress","Sistem","Cihaz_Tipi","Risk Analizi",
                "Kural Dışı Adminler (İsim ve Ünvan)","Riskli Paylaşılan Klasörler",
                "Tespit Edilen Şüpheli Yazılımlar","AssetID","Durum"]:
        if col in df.columns:
            df[col]=df[col].fillna("").astype(str)
        else:
            df[col]=""

    # AssetID'yi integer string olarak temizle: "12345.0" → "12345"
    def _clean_aid(val):
        v = str(val).strip()
        if v in ("","nan","None","NaN","0","0.0"): return ""
        try: return str(int(float(v)))
        except: return v
    df["AssetID"] = df["AssetID"].apply(_clean_aid)

    # Lansweeper linki — SADECE AssetID ile, isim araması YOK
    def _lsw(row):
        aid = row.get("AssetID","")
        if aid:
            return ASSET_URL.format(aid=aid)
        return ""
    df["Lansweeper"] = df.apply(_lsw, axis=1)

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
# margin'siz DARK — update_layout içinde özel margin belirtirken kullan
DARK_M={k:v for k,v in DARK.items() if k!="margin"}
SEV_CLR={"YÜKSEK":"#F85149","ORTA":"#D29922","DÜŞÜK":"#3FB950"}
CRIT_CLR={"Domain Controller":"#F85149","Mail Server":"#FF7B72",
           "Veritabanı Sunucusu":"#FFA657","Sunucu":"#D29922",
           "Sunucu (OS)":"#56D364","Laptop":"#58A6FF","Workstation":"#8B949E"}
SERVER_TYPES=["Domain Controller","Mail Server","Veritabanı Sunucusu","Sunucu","Sunucu (OS)"]

def sec(title, icon="", color="#F85149"):
    st.markdown(f'<div class="sec" style="border-left-color:{color}">'
                f'{"" if not icon else icon+" "}{title}</div>',
                unsafe_allow_html=True)

def kpi(col, value, label, color, sub="", bg="", icon=""):
    """HTML KPI kutusu — eşit boyut, simge, renkli arka plan."""
    bg_style = bg if bg else "linear-gradient(135deg,#161B22,#21262D)"
    _icon_html = f'<span style="font-size:14px;margin-right:3px">{icon}</span>' if icon else ""
    # label ve sub içinde HTML özel karakterleri güvenli hale getir
    _label_safe = str(label).replace("<","&lt;").replace(">","&gt;")
    _sub_safe   = str(sub).replace("<","&lt;").replace(">","&gt;") if sub else ""
    with col:
        st.markdown(f"""
<div class="kpi-box" style="background:{bg_style};border-top:3px solid {color};">
  <div class="kpi-lbl">{_icon_html}{_label_safe}</div>
  <div class="kpi-num" style="color:{color}">{value:,}</div>
  <div class="kpi-sub">{_sub_safe}</div>
</div>""", unsafe_allow_html=True)

def _neden_riskli(ra_str: str) -> str:
    """C) Auto Comment Engine — risk metninden akıllı özet + aksiyon üretir."""
    if not isinstance(ra_str, str) or not ra_str.strip():
        return "✅ Temiz"
    maddeler = [m.strip() for m in ra_str.split("•")
                if m.strip() and m.strip() not in ("Risk Tespit Edilmedi","")]
    if not maddeler:
        return "✅ Temiz"
    sayisi = len(maddeler)
    # Öncelik sırasına göre ana maddeyi seç
    oncelik_map = {
        "EoL":             ("💀 EoL OS","güvenlik yaması yok"),
        "Riskli Paylaşım": ("📁 SMB riski","ransomware yayılma kapısı"),
        "Onaysız Yönetici":("👤 Yetki ihlali","lateral movement riski"),
        "DLP":             ("🔒 Veri sızdırma","DLP eksik"),
        "SEP Eksik":       ("🛡️ AV yok","ransomware hedefi"),
        "Antivirüs":       ("🛡️ AV sorunu","koruma zayıf"),
        "CVE":             ("🦠 CVE açığı","istismar riski"),
        "Şüpheli":         ("🦠 Şüpheli SW","shadow IT"),
        "Patch":           ("🩹 Yamasız","bilinen CVE'lere açık"),
        "RDP":             ("🖥 RDP açık","brute-force hedefi"),
        "WSUS":            ("🩹 WSUS kopuk","güncelleme gelmiyor"),
        "Disk":            ("💾 Disk kritik","servis çökmesi riski"),
        "WU":              ("🔄 WU kapalı","yamalar durdu"),
        "Offline":         ("📴 Offline","izlenemiyor"),
    }
    for kw, (etiket, aciklama) in oncelik_map.items():
        for m in maddeler:
            if kw.lower() in m.lower():
                if sayisi == 1:
                    return f"{etiket} — {aciklama}"
                return f"{etiket} +{sayisi-1} sorun daha"
    # Fallback
    if sayisi == 1:
        return f"⚠ {maddeler[0][:40]}"
    return f"⚠ {maddeler[0][:30]} (+{sayisi-1})"


def show_table(dfs, height=500, sort_col=None, text_cols=None, link_col="Lansweeper",
               add_neden_riskli=True):
    if sort_col and sort_col in dfs.columns:
        dfs = dfs.sort_values(sort_col, ascending=False)
    # Neden Riskli sütunu: Risk Analizi varsa otomatik ekle
    if add_neden_riskli and "Risk Analizi" in dfs.columns and "Neden Riskli" not in dfs.columns:
        dfs = dfs.copy()
        dfs.insert(dfs.columns.get_loc("Risk Analizi"), "Neden Riskli",
                   dfs["Risk Analizi"].apply(_neden_riskli))
    cfg = {}
    if link_col and link_col in dfs.columns:
        # Gerçekten URL içeren satır var mı kontrol et
        has_links = dfs[link_col].astype(str).str.strip().str.match(r'^https?://').any()
        if has_links:
            try:
                cfg[link_col] = st.column_config.LinkColumn(
                    "🔗 Lansweeper",
                    help="Cihazı Lansweeper'da açmak için tıklayın",
                    display_text="🔗 Aç",
                )
            except TypeError:
                # Eski Streamlit sürümü — display_text parametresi yok
                try:
                    cfg[link_col] = st.column_config.LinkColumn("🔗 Lansweeper")
                except Exception:
                    pass
        else:
            # Tüm URL'ler boş — AssetID verisinin olmadığını belirt
            cfg[link_col] = st.column_config.TextColumn(
                "Lansweeper (AssetID Yok)", width="small"
            )
    for tc in (text_cols or []):
        if tc in dfs.columns:
            cfg[tc] = st.column_config.TextColumn(tc, width="large")
    if "Neden Riskli" in dfs.columns and "Neden Riskli" not in (text_cols or []):
        cfg["Neden Riskli"] = st.column_config.TextColumn("🤖 Neden Riskli", width="medium")
    st.dataframe(dfs, use_container_width=True, height=height,
                 column_config=cfg or None, hide_index=True)

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

def _render_alert_panel(df):
    """Canlı Alert Paneli — kritik durum kartları."""
    n   = len(df)
    ra  = df.get("Risk Analizi", pd.Series("",index=df.index)).fillna("").astype(str)
    alerts = []
    def _chk(mask, ikon, msg, renk, onc):
        cnt = int(mask.sum()) if hasattr(mask,"sum") else int(mask)
        if cnt>0: alerts.append({"ikon":ikon,"msg":msg.format(n=cnt,pct=round(cnt/max(n,1)*100,1)),"renk":renk,"onc":onc,"cnt":cnt})
    _chk(ra.str.contains("Antivirüs (SEP) Eksik",na=False,regex=False),"🛡️","{n} cihazda Antivirüs eksik (%{pct})","#F85149",1)
    _chk(ra.str.contains("Onaysız Yönetici",na=False,regex=False),"👤","{n} cihazda yetkisiz admin (%{pct})","#F85149",1)
    _chk(ra.str.contains("Riskli Paylaşım",na=False,regex=False),"📁","{n} cihazda riskli SMB paylaşımı","#F85149",1)
    _chk(ra.str.contains("Desteklenmeyen OS",na=False,regex=False),"💀","{n} cihaz EoL OS","#F85149",1)
    _chk(ra.str.contains("DLP Yüklü Değil",na=False,regex=False),"🔒","{n} cihazda DLP eksik","#D29922",2)
    _chk((df["Yamasız Gün"]>60).fillna(False) if "Yamasız Gün" in df.columns else pd.Series(False,index=df.index),"🩹","{n} cihaz 60+ gün yamasız","#D29922",2)
    _chk((df["Yamasız Gün"]>180).fillna(False) if "Yamasız Gün" in df.columns else pd.Series(False,index=df.index),"⚠️","{n} cihaz 180+ gün yamasız","#FF7B72",1)
    _chk(ra.str.contains("Şüpheli Yazılım",na=False,regex=False),"🦠","{n} cihazda şüpheli yazılım","#D29922",2)
    _chk((df["% Boş"]<10).fillna(False) if "% Boş" in df.columns else pd.Series(False,index=df.index),"💾","{n} cihazda disk kritik","#FFA657",3)
    _chk((df["Offline Gün"]>60).fillna(False) if "Offline Gün" in df.columns else pd.Series(False,index=df.index),"📴","{n} cihaz 60+ gün offline","#8B949E",3)
    _chk(df["_RawUpdateStop"].gt(0).fillna(False) if "_RawUpdateStop" in df.columns else pd.Series(False,index=df.index),"🔄","{n} cihazda WU kapalı","#FFA657",3)
    sw_path = Path(__file__).parent.parent/"data"/"processed"/"software_changes.json"
    if sw_path.exists():
        try:
            sw = json.loads(sw_path.read_text(encoding="utf-8"))
            n_s = len(sw.get("suphe_yeni",[]))
            if n_s>0: alerts.append({"ikon":"🚨","msg":f"{n_s} şüpheli yazılım YENİ kuruldu!","renk":"#8B1A1A","onc":0,"cnt":n_s})
        except Exception: pass
    if not alerts: return
    alerts.sort(key=lambda x:(x["onc"],-x["cnt"]))
    ncols = min(len(alerts),4)
    cols_a = st.columns(ncols)
    for i,a in enumerate(alerts[:8]):
        clr=a["renk"]
        with cols_a[i%ncols]:
            st.markdown(f"""<div style="background:{clr}14;border:1px solid {clr}55;border-left:3px solid {clr};
border-radius:6px;padding:6px 10px;margin:2px 0;display:flex;align-items:center;gap:6px">
  <span style="font-size:14px">{a["ikon"]}</span>
  <div style="font-size:10px;font-weight:700;color:{clr}">{a["msg"]}</div>
</div>""",unsafe_allow_html=True)


def footer():
    st.markdown("""<div class="footer">
    Designed by <b>hsaldiran</b> &nbsp;·&nbsp; IT Risk Engine v6.2 &nbsp;·&nbsp;
    IT Risk Intelligence Platform v5.0</div>""", unsafe_allow_html=True)

def page_anomali(df):
    st.title("🔬 Anomali Tespiti — Z-Score Analizi")
    st.markdown("""<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
padding:12px 16px;margin:4px 0 14px 0;font-size:12px;color:#C9D1D9;line-height:1.7">
  <b style="color:#8957E5">Z-Score Anomali Tespiti Nedir?</b> —
  Her metrik için tüm filodaki ortalama ve standart sapma hesaplanır.
  Bir cihaz o metrikte ortalamanın <b>2.5 standart sapma</b> (Z≥2.5) ötesindeyse anormal sayılır.
  2+ metrikte anormal olan cihazlar işaretlenir. Kural motorunun gözden kaçırdığı riskleri ortaya çıkarır.<br>
  <b style="color:#FFA657">Örnek:</b> Yaması tam, admin sayısı normal — ama disk kullanımı filonun
  3.2σ üstünde ve CVE bonusu alışılmadık yüksek → sistem bu cihaza 🚨 ANOMALİ basar.
</div>""", unsafe_allow_html=True)

    n = len(df)
    has_anomali = "Anomali_Skoru" in df.columns and "Anomali_Flag" in df.columns

    if not has_anomali:
        st.warning("⚠ Anomali verileri henüz hesaplanmamış.")
        st.markdown("""<div style="background:#161B22;border:1px solid #D29922;border-radius:8px;
padding:14px 16px;font-size:12px;color:#C9D1D9">
  <b style="color:#D29922">Nasıl Aktif Edilir?</b><br><br>
  <b>Yöntem 1 — risk_engine ile entegre:</b><br>
  risk_engine_v62.py sonuna şu satırları ekle:<br>
  <pre style="background:#0D1117;padding:8px;border-radius:4px;margin:6px 0;font-size:11px">
from anomaly_engine import anomali_hesapla
df = anomali_hesapla(df)
df.to_excel(CLEAN_DATA, index=False)</pre>
  <b>Yöntem 2 — Tek seferlik çalıştır:</b><br>
  <code style="background:#0D1117;padding:3px 8px;border-radius:4px">python scripts/anomaly_engine.py</code>
</div>""", unsafe_allow_html=True)
        footer(); return

    anomaliler = df[df["Anomali_Flag"]].sort_values("Anomali_Skoru", ascending=False)
    n_anomali  = len(anomaliler)
    n_yuksek   = int((anomaliler["Anomali_Skoru"] > 40).sum()) if n_anomali > 0 else 0
    n_orta     = int(((anomaliler["Anomali_Skoru"] > 20) & (anomaliler["Anomali_Skoru"] <= 40)).sum()) if n_anomali > 0 else 0
    oran       = round(n_anomali / max(n, 1) * 100, 1)

    _a_lbl, _a_clr, _a_icon = ("KRİTİK","#F85149","🔴") if n_yuksek>=10 else                                ("YÜKSEK","#D29922","🟡") if n_anomali>0 else ("TEMİZ","#3FB950","🟢")
    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_a_clr};border-left:5px solid {_a_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_a_clr};font-weight:700;text-transform:uppercase">🤖 AI Anomali Değerlendirmesi</div>
    <div style="background:{_a_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_a_icon} {_a_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{n}</b> cihazın <b>{n_anomali}</b>i (%{oran}) kural motorunun dışında istatistiksel anormallik gösteriyor.
    Bunların <b>{n_yuksek}</b>i yüksek anomali skoru (>40) taşıyor.
    {"Bu cihazlar kural tabanlı sistemde yeşilde görünse de istatistiksel olarak şüpheli — manuel inceleme önerilir." if n_anomali>0 else
     "Şu an istatistiksel olarak anormal cihaz tespit edilmedi."}
  </div>
  <div style="font-size:11px;color:{_a_clr};font-weight:600;margin-top:6px">
    ⚡ {"Yüksek anomali cihazlarını kural motoru bulamadı — özellikle sağ alt kadrandakilere bak." if n_yuksek>0 else "Rutin izleme yeterli."}
  </div>
</div>""", unsafe_allow_html=True)

    _ak = st.columns(5)
    kpi(_ak[0], n,             "Toplam Cihaz",    "#58A6FF","",          "linear-gradient(135deg,#0d2137,#162e4d)","🖥️")
    kpi(_ak[1], n_anomali,     "Anomali Cihazı",  "#8957E5",f"%{oran}", "linear-gradient(135deg,#2d1a4d,#3d2466)","🚨")
    kpi(_ak[2], n_yuksek,      "Yüksek (>40)",    "#F85149","",          "linear-gradient(135deg,#3d0000,#5c0a0a)","🔴")
    kpi(_ak[3], n_orta,        "Orta (20-40)",     "#D29922","",          "linear-gradient(135deg,#3d2200,#5c3300)","🟡")
    kpi(_ak[4], n-n_anomali,   "Normal Cihaz",    "#3FB950","",          "linear-gradient(135deg,#0d2e14,#1a4a23)","✅")
    st.markdown("---")

    if n_anomali == 0:
        st.info("✅ Z-Score anomalisi yok. Ani değişim tespiti aşağıda devam ediyor.")

    # ── ANİ DEĞİŞİM TESPİTİ (Gün-üstü) ─────────────────────────
    if DEVHIST_OK:
        st.markdown("---")
        sec("🚨 Ani Risk Değişimleri — Dünden Bugüne")
        st.caption("📌 Son iki ölçüm arasında risk skoru 15+ puan artan cihazlar. '7 gün önce 12, bugün 80' → sistem anında işaretler.")
        _ani_rows = []
        for _, _drow in df.iterrows():
            _an = str(_drow.get("AssetName",""))
            _gh = gecmis_oku(_an)
            if len(_gh) >= 2:
                _prev, _curr = _gh[-2]["skor"], _gh[-1]["skor"]
                _delta = _curr - _prev
                if abs(_delta) >= 15:
                    _ani_rows.append({
                        "AssetName":   _an,
                        "Kullanıcı":   _drow.get("Kullanıcı",""),
                        "Önceki Skor": _prev,
                        "Güncel Skor": _curr,
                        "Değişim":     f"{'+'if _delta>0 else ''}{_delta}",
                        "Yön":         "🔴 Yükseli" if _delta>0 else "🟢 Düşüş",
                        "Cihaz_Tipi":  _drow.get("Cihaz_Tipi",""),
                        "Seviye":      _drow.get("Seviye",""),
                        "Lansweeper":  _drow.get("Lansweeper",""),
                    })
        if _ani_rows:
            _ani_df = pd.DataFrame(_ani_rows).sort_values("Değişim",ascending=False,key=lambda x: x.str.replace("+","").astype(float,errors="ignore"))
            _anc1, _anc2 = st.columns([1,3])
            with _anc1:
                _n_yuk = sum(1 for r in _ani_rows if int(r["Değişim"].replace("+","").replace("−","")) > 0)
                _n_dus = len(_ani_rows) - _n_yuk
                kpi(st.container(), _n_yuk, "Ani Yükseliş", "#F85149","",
                    "linear-gradient(135deg,#3d0000,#5c0a0a)","🔴")
            with _anc2:
                _ai_ani = f"{_n_yuk} cihaz son ölçümde 15+ puan artış gösterdi." if _n_yuk else "Kritik yükseliş yok."
                st.markdown(f"""<div style="background:#0D1117;border-left:4px solid #F85149;
border-radius:6px;padding:10px 14px;font-size:12px;color:#C9D1D9">
  🤖 <b style="color:#F85149">AI:</b> {_ai_ani}
  {"Ani skor artışları yeni bir saldırı vektörü veya yazılım kurulumuna işaret edebilir. Bu cihazları öncelikle incele." if _n_yuk>0 else ""}
</div>""", unsafe_allow_html=True)
            show_table(_ani_df, height=320)
            _csv_ani = _ani_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ Ani Değişimler CSV", _csv_ani,
                               f"ani_degisim_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
        else:
            st.success("✅ Son iki ölçüm arasında 15+ puan değişim gösteren cihaz yok.")
            st.caption("Geçmiş birikince (min 2 ölçüm) bu bölüm otomatik aktif olur.")

    _g1, _g2 = st.columns(2)
    with _g1:
        sec("Anomali Skoru Dağılımı")
        st.caption("📌 Skor = kaç metrikte anormal olduğu × Z-Score büyüklüğünün bileşik fonksiyonu. Yüksek skor = daha alışılmadık profil.")
        _bins_a = [0,10,20,40,60,101]
        _lbls_a = ["1-10 (Hafif)","11-20","21-40 (Orta)","41-60 (Yüksek)","60+ (Kritik)"]
        _a_cut  = pd.cut(anomaliler["Anomali_Skoru"],bins=_bins_a,labels=_lbls_a,right=True)
        _a_vc   = _a_cut.value_counts().reindex(_lbls_a,fill_value=0).reset_index()
        _a_vc.columns=["Aralik","Cihaz"]
        _fig_ad=go.Figure(go.Bar(
            x=_a_vc["Aralik"],y=_a_vc["Cihaz"],
            marker_color=["#3FB950","#D29922","#FF9F43","#F85149","#8B1A1A"][:len(_a_vc)],
            text=_a_vc["Cihaz"],textposition="outside",textfont=dict(color="#C9D1D9"),
            hovertemplate="<b>%{x}</b><br>%{y} cihaz<extra></extra>",
        ))
        _fig_ad.update_layout(**DARK,height=280,showlegend=False)
        st.plotly_chart(_fig_ad,use_container_width=True)

    with _g2:
        sec("Anomali vs Final Risk Skoru")
        st.caption("📌 Sol üst = kural motoru düşük risk dedi ama anomali yüksek → en kritik köşe. Sağ üst = hem kural hem anomali yüksek → kesinlikle incelenmeli.")
        if "Final_Risk_Skoru" in anomaliler.columns:
            _hov_a={c:True for c in ["AssetName","Anomali_Detay"] if c in anomaliler.columns}
            _fig_sc=px.scatter(anomaliler,x="Final_Risk_Skoru",y="Anomali_Skoru",
                color="Anomali_Skoru",color_continuous_scale=["#3FB950","#D29922","#F85149","#8B1A1A"],
                size="Anomali_Skoru",size_max=18,hover_data=_hov_a,opacity=0.85,
                text="AssetName" if len(anomaliler)<=25 else None)
            _fig_sc.add_hline(y=40,line_dash="dash",line_color="#F85149",annotation_text="Yüksek Anomali (40)")
            _fig_sc.add_vline(x=50,line_dash="dash",line_color="#D29922",annotation_text="Yüksek Risk (50)")
            _fig_sc.update_layout(**DARK,height=280,xaxis_title="Final Risk Skoru",
                                   yaxis_title="Anomali Skoru",coloraxis_showscale=False)
            if len(anomaliler)<=25:
                _fig_sc.update_traces(textposition="top center",textfont=dict(color="#C9D1D9",size=8))
            st.plotly_chart(_fig_sc,use_container_width=True)

    _gizli = anomaliler[anomaliler["Final_Risk_Skoru"]<50].sort_values("Anomali_Skoru",ascending=False)
    if len(_gizli)>0:
        sec("🔍 Kural Motorunun Kaçırdığı Anomaliler",color="#8957E5")
        st.caption("📌 Final Risk Skoru <50 ama Z-Score analizi anormallik buldu. Özellikle dikkat: kural tabanlı sistemde görünmez, bu liste olmasa atlanırdı.")
        _cols_g=[c for c in ["Lansweeper","AssetName","Kullanıcı","Cihaz_Tipi",
                               "Final_Risk_Skoru","Anomali_Skoru","Anomali_Detay","Seviye"]
                 if c in _gizli.columns]
        show_table(_gizli[_cols_g],height=320,text_cols=["Anomali_Detay"])

    sec("Tüm Anomali Cihazları")
    _cols_a=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Cihaz_Tipi",
                          "Final_Risk_Skoru","Seviye","Anomali_Skoru","Anomali_Detay"]
             if c in anomaliler.columns]
    show_table(anomaliler[_cols_a],height=480,text_cols=["Anomali_Detay"])
    _csv_a=anomaliler[_cols_a].to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ Anomali Listesi CSV",_csv_a,
                       f"anomali_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
    footer()


# ═══════════════════════════════════════════════════════════
# SAYFA: MITRE ATT&CK
# ═══════════════════════════════════════════════════════════
def page_mitre(df):
    st.title("⚔️ MITRE ATT&CK Tehdit Çerçevesi")

    if not MITRE_OK:
        st.error("mitre_mapper.py bulunamadı. scripts/ klasörüne kopyalandığından emin ol.")
        footer(); return

    # ── Nedir kutusu ──────────────────────────────────────
    with st.expander("📖 MITRE ATT&CK Nedir? — Okumak için tıkla", expanded=False):
        st.markdown("""
<div style="font-size:13px;color:#C9D1D9;line-height:1.9">

### 🏛️ MITRE ATT&CK Nedir?

**MITRE Corporation** (ABD merkezli, kâr amacı gütmeyen araştırma kuruluşu) tarafından
geliştirilen **dünya standardı siber saldırı bilgi tabanıdır**.

ATT&CK = **A**dversarial **T**actics, **T**echniques & **C**ommon **K**nowledge

Gerçek dünyada gerçekleşmiş saldırıların incelenmesiyle oluşturulmuştur.
FBI, NSA, Microsoft, Google ve dünyanın en büyük SOC ekipleri bu çerçeveyi kullanmaktadır.

---

### 🎯 Ne İşe Yarar?

1. **Ortak dil sağlar** — "Yetkisiz admin var" demek yerine "T1078 tespit edildi" demek,
   uluslararası güvenlik ekipleriyle aynı dili konuşmaktır.

2. **Saldırıyı haritalandırır** — Bir tehdit tespit edildiğinde "saldırgan şu an hangi
   aşamada?" sorusuna yanıt verir.

3. **Savunma önceliğini belirler** — Hangi taktiklere karşı savunmasız olduğunu gösterir.

4. **Uyum belgelerinde kullanılır** — ISO 27001, NIST CSF, SOC 2 denetimlerinde MITRE
   referansları kabul görmektedir.

---

### 🗂️ Yapısı Nasıl?

```
14 TAKTİK (Saldırının amacı/aşaması)
  └── 190+ TEKNİK (Amaca ulaşmak için kullanılan yöntem)
        └── Alt-Teknikler (Tekniğin spesifik varyantı)
```

**Örnek:**
- Taktik: TA0004 — Privilege Escalation (Yetki Yükseltme)
- Teknik: T1078 — Valid Accounts (Geçerli Hesap Kötüye Kullanımı)
- Sistem bulgumuz: "Onaysız Yönetici Yetkisi" → Bu tam olarak T1078'dir

</div>""", unsafe_allow_html=True)

    n = len(df)
    tech_df = df_to_technique_counts(df)
    aktif_tech = tech_df[tech_df["Etkilenen"] > 0]
    taktik_ozet = taktik_bazli_ozet(df)

    # ── AI Genel Yorum ────────────────────────────────────
    n_kritik_tech  = int((aktif_tech["Risk"] == "Kritik").sum()) if len(aktif_tech) > 0 else 0
    n_aktif_tak    = sum(1 for v in taktik_ozet.values() if v["etkilenen"] > 0)
    max_etkilenen  = int(aktif_tech["Etkilened"].max()) if "Etkilened" in aktif_tech.columns else (int(aktif_tech["Etkilenen"].max()) if len(aktif_tech) > 0 else 0)
    _m_lbl, _m_clr, _m_icon = ("KRİTİK","#F85149","🔴") if n_kritik_tech >= 3 else                                ("YÜKSEK","#D29922","🟡") if n_aktif_tak >= 4 else ("ORTA","#FFA657","🟠")

    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_m_clr};border-left:5px solid {_m_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 16px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_m_clr};font-weight:700;text-transform:uppercase">🤖 AI MITRE ATT&CK Değerlendirmesi</div>
    <div style="background:{_m_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_m_icon} {_m_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.8">
    Sistemde <b>{len(aktif_tech)}</b> aktif MITRE tekniği tespit edildi, bunların <b>{n_kritik_tech}</b>i kritik risk sınıfında.
    <b>{n_aktif_tak}</b> farklı taktik aşamasında saldırı vektörü mevcut.
    {"Saldırgan altyapıya girerse birden fazla taktik aşamasında hareket edebilir — derinlemesine savunma gerekli." if n_aktif_tak >= 4 else
     "Mevcut bulgular saldırı zincirinin erken aşamalarını işaret ediyor." if len(aktif_tech) > 0 else
     "Aktif MITRE tekniği tespit edilmedi."}
  </div>
  <div style="font-size:11px;color:{_m_clr};font-weight:600;margin-top:6px">
    ⚡ {"Kritik tekniklere (T1078, T1562, T1486, T1021) öncelik ver — bunlar ransomware zincirinin yapı taşları." if n_kritik_tech >= 2 else
       "Aktif tekniklerin öneri adımlarını sırayla uygula." if len(aktif_tech) > 0 else "İzleme devam etmeli."}
  </div>
</div>""", unsafe_allow_html=True)

    # ── KPI: Taktik Heatmap ───────────────────────────────
    sec("🗺️ MITRE ATT&CK Taktik Haritası — Hangi Aşamada Tehdidimiz Var?")
    st.caption("📌 Her kart bir MITRE taktiğini (saldırı aşamasını) temsil eder. Kırmızı = etkilenen cihaz var. Sayı = o taktikle ilişkili etkilenen cihaz sayısı.")

    _tak_listesi = list(taktik_ozet.items())
    for _row_start in range(0, len(_tak_listesi), 7):
        _row_cols = st.columns(7)
        for _ci, (tak_id, tak) in enumerate(_tak_listesi[_row_start:_row_start+7]):
            _etk = tak["etkilenen"]
            _bg  = "linear-gradient(135deg,#3d0000,#5c0a0a)" if _etk > 0 else "linear-gradient(135deg,#0d2e14,#1a4a23)"
            _clr = "#F85149" if _etk > 0 else "#3FB950"
            _row_cols[_ci].markdown(f"""<div style="background:{_bg};border:1px solid {_clr}33;
border-top:3px solid {_clr};border-radius:8px;padding:8px 6px;text-align:center;min-height:72px">
  <div style="font-size:14px">{tak["emoji"]}</div>
  <div style="font-size:8px;color:{_clr};font-weight:700;text-transform:uppercase;line-height:1.2;margin:2px 0">{tak["tr"]}</div>
  <div style="font-size:16px;font-weight:900;color:{_clr}">{_etk if _etk > 0 else "✓"}</div>
  <div style="font-size:7px;color:rgba(255,255,255,0.3)">{tak_id}</div>
</div>""", unsafe_allow_html=True)
    st.markdown("")

    # ── Teknik Detay Bar Grafiği ──────────────────────────
    if len(aktif_tech) > 0:
        st.markdown("---")
        sec("⚔️ Tespit Edilen MITRE Teknikleri — Etkilenen Cihaz Sayısı")
        st.caption("📌 Her çubuk bir MITRE tekniğidir. Kırmızı = Kritik risk, Sarı = Yüksek risk. ID'ye tıklayarak MITRE'nin resmi sayfasına gidebilirsin.")

        _tc1, _tc2 = st.columns([3, 2])
        with _tc1:
            _aktif = aktif_tech.sort_values("Etkilenen", ascending=True)
            _bar_clrs = _aktif["Renk"].tolist()
            _fig_m = go.Figure(go.Bar(
                y=[f"{r['ID']} — {r['Türkçe']}" for _, r in _aktif.iterrows()],
                x=_aktif["Etkilenen"],
                orientation="h",
                marker_color=_bar_clrs,
                text=[f"{r['Etkilenen']} cihaz  ({r['Risk']})" for _, r in _aktif.iterrows()],
                textposition="outside",
                textfont=dict(color="#C9D1D9", size=10),
                hovertemplate="<b>%{y}</b><br>%{x} cihaz<extra></extra>",
            ))
            _fig_m.update_layout(**DARK, height=max(320, len(aktif_tech) * 44),
                                  showlegend=False,
                                  xaxis=dict(range=[0, aktif_tech["Etkilenen"].max() * 1.45]))
            st.plotly_chart(_fig_m, use_container_width=True)

        with _tc2:
            sec("Taktik Dağılımı")
            # Aktif taktiklerin pasta grafiği
            _tak_data = [(t["tr"], t["etkilenen"]) for t in taktik_ozet.values() if t["etkilenen"] > 0] if "etkilenen" in list(taktik_ozet.values())[0] else [(t["tr"], t["etkilenen"]) for t in taktik_ozet.values() if t["etkilenen"] > 0]
            if _tak_data:
                _tak_labels = [d[0] for d in _tak_data]
                _tak_vals   = [d[1] for d in _tak_data]
                _fig_tp = go.Figure(go.Pie(
                    labels=_tak_labels, values=_tak_vals, hole=0.42,
                    textinfo="label+percent",
                    textfont=dict(color="#E6EDF3", size=9),
                    marker=dict(
                        colors=["#F85149","#FF7B72","#D29922","#FFA657","#3FB950","#58A6FF","#D2A8FF","#A5D6FF"][:len(_tak_data)],
                        line=dict(color="#0D1117", width=2),
                    ),
                ))
                _fig_tp.update_layout(**DARK, height=300, showlegend=False)
                st.plotly_chart(_fig_tp, use_container_width=True)

            # Risk özeti kutuları
            for risk, clr in [("Kritik","#F85149"),("Yüksek","#D29922"),("Orta","#FFA657")]:
                _rc = int((aktif_tech["Risk"] == risk).sum())
                if _rc > 0:
                    st.markdown(f"""<div style="background:{clr}18;border-left:3px solid {clr};
border-radius:6px;padding:6px 10px;margin:3px 0;font-size:11px">
  <span style="color:{clr};font-weight:700">{risk}:</span>
  <span style="color:#C9D1D9"> {_rc} teknik aktif</span>
</div>""", unsafe_allow_html=True)

    # ── Teknik Açıklamaları (Expander) ───────────────────
    st.markdown("---")
    sec("📘 Tespit Edilen Teknikler — Detaylı Açıklamalar ve Öneriler")
    st.caption("📌 Her expander bir MITRE tekniğini açıklar. ID rozetine tıklayarak MITRE'nin resmi dökümantasyonuna erişebilirsiniz.")

    for _, row in aktif_tech.sort_values("Etkilenen", ascending=False).iterrows():
        _ec = row["Renk"]
        _eth = int(row["Etkilened"]) if "Etkilened" in row else int(row["Etkilenen"])
        with st.expander(f"[{row['ID']}] {row['Türkçe']} ({row['Teknik']}) — {_eth} cihaz"):
            _dc1, _dc2 = st.columns([2, 1])
            with _dc1:
                st.markdown(f"""<div style="background:#161B22;border-left:4px solid {_ec};
border-radius:8px;padding:12px 16px;margin-bottom:8px">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
    <a href="{row['URL']}" target="_blank" style="background:{_ec};color:#fff;font-size:10px;
    font-weight:700;padding:3px 10px;border-radius:4px;text-decoration:none">{row['ID']}</a>
    <span style="color:{_ec};font-size:11px;font-weight:700">{row['Risk']} Risk</span>
    <span style="color:#8B949E;font-size:10px">{row['Taktikler']}</span>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">{row['Açıklama']}</div>
</div>
<div style="background:#0D1117;border-left:3px solid #3FB950;border-radius:6px;padding:10px 14px">
  <div style="font-size:9px;color:#3FB950;font-weight:700;text-transform:uppercase;margin-bottom:4px">⚡ Öneri</div>
  <div style="font-size:12px;color:#C9D1D9">{row['Öneri']}</div>
</div>""", unsafe_allow_html=True)
            with _dc2:
                # Bu teknikle eşleşen etkilenen cihazlar
                ra = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)
                _mask = pd.Series(False, index=df.index)
                for tehdit in [t for t, techs in THREAT_TO_TECHNIQUES.items() if row["ID"] in techs]:
                    _mask |= ra.str.contains(tehdit, na=False, regex=False)
                # Raw sütunlar
                if row["ID"] in ("T1078","T1098") and "_RawAdminCount" in df.columns:
                    _mask |= df["_RawAdminCount"].gt(0)
                if row["ID"] == "T1021" and "Riskli Paylaşılan Klasörler" in df.columns:
                    _mask |= df["Riskli Paylaşılan Klasörler"].ne("").fillna(False)
                _aff = df[_mask]
                if len(_aff) > 0:
                    _cc = [c for c in ["Lansweeper","AssetName","Kullanıcı","Final_Risk_Skoru","Seviye"] if c in _aff.columns]
                    show_table(_aff[_cc].sort_values("Final_Risk_Skoru", ascending=False), height=220)
                else:
                    st.info("Risk Analizi metninde doğrudan eşleşme bulunamadı.")

    if len(aktif_tech) == 0:
        st.success("✅ Şu an aktif MITRE tekniği tespit edilmedi.")
    footer()


# ═══════════════════════════════════════════════════════════
# SAYFA: CIS CONTROLS UYUM SKORU
# ═══════════════════════════════════════════════════════════
def page_cis(df):
    st.title("📋 CIS Controls v8 Uyum Skoru")

    if not MITRE_OK:
        st.error("compliance_engine.py bulunamadı. scripts/ klasörüne kopyalandığından emin ol.")
        footer(); return

    # ── Nedir kutusu ──────────────────────────────────────
    with st.expander("📖 CIS Controls Nedir? — Okumak için tıkla", expanded=False):
        st.markdown("""
<div style="font-size:13px;color:#C9D1D9;line-height:1.9">

### 🛡️ CIS Controls Nedir?

**Center for Internet Security (CIS)**, dünyanın önde gelen güvenlik kuruluşlarından biri olan
ABD merkezli, kâr amacı gütmeyen bir organizasyondur.

**CIS Controls**, siber saldırıların %80'ini engelleyebilecek **18 güvenlik kontrolünden**
oluşan bir çerçevedir. İlk kez 2008'de yayımlandı, günümüzde v8 sürümü geçerlidir.

---

### 🎯 Neden Önemli?

1. **Pratik** — Teorik değil, uygulanabilir kontroller
2. **Önceliklendirilmiş** — Neyi önce yapman gerektiğini söyler
3. **Ölçülebilir** — "Uyuyoruz / uyumuyoruz" net cevabı verir
4. **Evrensel kabul** — ISO 27001, NIST CSF, SOC 2 ile örtüşür

---

### 📊 Uygulama Grupları (IG)

| Grup | Kapsam | Sistemimiz |
|------|--------|-----------|
| **IG1** | Temel — Her kurum uygulamalı | ✅ Ölçülüyor |
| **IG2** | Orta — Ek kaynak gerektiren | ✅ Ölçülüyor |
| **IG3** | İleri — Kritik altyapı | ⏳ İleride |

---

### 📈 Skor Yorumu

- **75-100** → İYİ — Kontroller büyük ölçüde uygulanmış
- **50-74** → GELİŞTİRİLEBİLİR — Temel eksiklikler giderilmeli
- **0-49** → KRİTİK — Acil müdahale gerekiyor

</div>""", unsafe_allow_html=True)

    n = len(df)
    cis_sonuc = cis_hesapla(df)
    ozet      = genel_uyum_skoru(cis_sonuc)

    # ── AI Genel Yorum ────────────────────────────────────
    _c_lbl, _c_clr = ozet["lbl"], ozet["renk"]
    _c_icon = "🟢" if _c_lbl == "İYİ" else "🟡" if _c_lbl == "GELİŞTİRİLEBİLİR" else "🔴"
    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_c_clr};border-left:5px solid {_c_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 16px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_c_clr};font-weight:700;text-transform:uppercase">🤖 AI CIS Uyum Değerlendirmesi</div>
    <div style="background:{_c_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_c_icon} {_c_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.8">
    Genel CIS uyum skoru: <b style="color:{_c_clr}">{ozet["genel_skor"]}/100</b>.
    Temel kontroller (IG1) skoru: <b>{ozet["ig1_skor"]}/100</b>.
    <b>{ozet["uyumlu"]}</b> kontrol uyumlu, <b>{ozet["kismen"]}</b> kısmen uyumlu, <b>{ozet["uyumsuz"]}</b> uyumsuz.
    {"Kritik güvenlik kontrolleri eksik — bu durum denetçilere ve yöneticilere raporlanmalı." if ozet["genel_skor"] < 50 else
     "Temel kontroller büyük ölçüde uygulanmış, eksikleri kapatarak skoru artırabilirsin." if ozet["genel_skor"] < 75 else
     "Güçlü uyum profili. IG2/IG3 kontrollerini güçlendirmeye odaklan."}
  </div>
  <div style="font-size:11px;color:{_c_clr};font-weight:600;margin-top:6px">
    ⚡ {"IG1 kontrollerini öncelikle tamamla — bunlar 'temel hijyen' kabul edilir." if ozet["ig1_skor"] < 70 else
       "IG2 kontrollerini güçlendir ve bu raporu yöneticiye sun." if ozet["genel_skor"] < 75 else
       "Mevcut durumu belgele, IG3 için yol haritası hazırla."}
  </div>
</div>""", unsafe_allow_html=True)

    # ── Özet KPI ─────────────────────────────────────────
    _ck = st.columns(5)
    kpi(_ck[0], ozet["genel_skor"],  "Genel Uyum Skoru",   ozet["renk"],  "/100",       f"linear-gradient(135deg,{ozet['renk']}22,#0D1117)", "📊")
    kpi(_ck[1], ozet["ig1_skor"],    "IG1 Temel Skor",      "#58A6FF",     "Temel",      "linear-gradient(135deg,#0d2137,#162e4d)", "🏗️")
    kpi(_ck[2], ozet["uyumlu"],      "Uyumlu Kontrol",      "#3FB950",     f"/{ozet['toplam']}", "linear-gradient(135deg,#0d2e14,#1a4a23)", "✅")
    kpi(_ck[3], ozet["kismen"],      "Kısmen Uyumlu",       "#D29922",     "",            "linear-gradient(135deg,#3d2200,#5c3300)", "⚠️")
    kpi(_ck[4], ozet["uyumsuz"],     "Uyumsuz Kontrol",     "#F85149",     "",            "linear-gradient(135deg,#3d0000,#5c0a0a)", "❌")
    st.markdown("---")

    # ── Uyum Radar / Çubuk Grafiği ────────────────────────
    _cg1, _cg2 = st.columns([3, 2])
    with _cg1:
        sec("Kontrol Bazında Uyum Skoru")
        st.caption("📌 Her çubuk bir CIS kontrolüdür. 80+ yeşil = uyumlu, 50-79 sarı = geliştirilmeli, 50 altı kırmızı = uyumsuz.")
        _kontrol_listesi = [(f"CIS {no}: {v['baslik'][:40]}", v["puan"], v["durum"], v["renk"], v["ig"]) for no, v in cis_sonuc.items()]
        _kontrol_listesi.sort(key=lambda x: x[1])
        _bar_clrs_c = ["#F85149" if p < 50 else "#D29922" if p < 80 else "#3FB950" for _, p, _, _, _ in _kontrol_listesi]
        _fig_cis = go.Figure(go.Bar(
            y=[k[0] for k in _kontrol_listesi],
            x=[k[1] for k in _kontrol_listesi],
            orientation="h",
            marker_color=_bar_clrs_c,
            text=[f"{k[1]}/100  {k[4]}" for k in _kontrol_listesi],
            textposition="outside",
            textfont=dict(color="#C9D1D9", size=10),
            hovertemplate="<b>%{y}</b><br>Skor: %{x}/100<extra></extra>",
        ))
        _fig_cis.add_vline(x=80, line_dash="dash", line_color="#3FB950", annotation_text="Uyumlu (80)")
        _fig_cis.add_vline(x=50, line_dash="dot",  line_color="#F85149", annotation_text="Kritik (50)")
        _fig_cis.update_layout(**DARK, height=max(350, len(_kontrol_listesi) * 38),
                                showlegend=False, xaxis=dict(range=[0, 115]))
        st.plotly_chart(_fig_cis, use_container_width=True)

    with _cg2:
        sec("Uyum Durumu Dağılımı")
        _pie_data = [
            ("✅ Uyumlu",    ozet["uyumlu"],  "#3FB950"),
            ("⚠️ Kısmen",   ozet["kismen"],  "#D29922"),
            ("❌ Uyumsuz",  ozet["uyumsuz"], "#F85149"),
        ]
        _fig_pie = go.Figure(go.Pie(
            labels=[d[0] for d in _pie_data],
            values=[d[1] for d in _pie_data],
            hole=0.48,
            marker=dict(colors=[d[2] for d in _pie_data], line=dict(color="#0D1117", width=2)),
            textinfo="label+value+percent",
            textfont=dict(color="#E6EDF3", size=11),
        ))
        _fig_pie.add_annotation(text=f"<b>{ozet['genel_skor']}</b><br>/100",
                                 x=0.5, y=0.5, showarrow=False,
                                 font=dict(size=14, color=ozet["renk"]))
        _fig_pie.update_layout(**DARK, height=280, showlegend=False)
        st.plotly_chart(_fig_pie, use_container_width=True)

        # Skor çubuğu
        st.markdown(f"""<div style="background:#161B22;border-radius:8px;padding:12px 14px;margin-top:8px">
  <div style="font-size:9px;color:#8B949E;text-transform:uppercase;margin-bottom:6px">Genel Uyum İlerleme Çubuğu</div>
  <div style="background:#21262D;border-radius:6px;height:14px;overflow:hidden">
    <div style="width:{ozet['genel_skor']}%;background:linear-gradient(90deg,{ozet['renk']},{ozet['renk']}99);
    height:100%;border-radius:6px;transition:width .5s"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:9px;color:#484F58;margin-top:3px">
    <span>0 (Kritik)</span><span>50</span><span>75</span><span>100 (İyi)</span>
  </div>
</div>""", unsafe_allow_html=True)

    # ── Kontrol Detayları ─────────────────────────────────
    st.markdown("---")
    sec("📋 Kontrol Detayları ve Aksiyon Önerileri")
    st.caption("📌 Her kart bir CIS kontrolüdür. Kırmızı kenarlı = uyumsuz (acil). Sarı = geliştirilmeli. Yeşil = uyumlu.")

    for no, v in sorted(cis_sonuc.items()):
        _vc = v["renk"]
        _border_clr = "#F85149" if v["durum"] == "UYUMSUZ" else "#D29922" if v["durum"] == "KISMEN" else "#3FB950"
        _icon_d = "❌" if v["durum"] == "UYUMSUZ" else "⚠️" if v["durum"] == "KISMEN" else "✅"
        with st.expander(f"{_icon_d}  CIS {no} — {v['baslik']}  |  Skor: {v['puan']}/100  |  {v['ig']}"):
            st.markdown(f"""<div style="background:#161B22;border-left:4px solid {_border_clr};
border-radius:8px;padding:12px 16px;margin-bottom:10px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div>
      <div style="font-size:9px;color:{_vc};text-transform:uppercase;font-weight:700;margin-bottom:4px">{v['emoji']} Nedir?</div>
      <div style="font-size:12px;color:#C9D1D9;line-height:1.6">{v['aciklama']}</div>
    </div>
    <div>
      <div style="font-size:9px;color:#F85149;text-transform:uppercase;font-weight:700;margin-bottom:4px">⚠ Neden Önemli?</div>
      <div style="font-size:12px;color:#C9D1D9;line-height:1.6">{v['neden']}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

            # Ölçütler
            for olcut in v["olcutler"]:
                _oc = "#3FB950" if olcut["gecerli"] else "#F85149"
                _oi = "✅" if olcut["gecerli"] else "❌"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid {_oc}33;border-left:3px solid {_oc};
border-radius:6px;padding:8px 12px;margin:4px 0">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:10px;font-weight:700;color:{_oc}">{_oi} {olcut['id']}: {olcut['kural']}</span><br>
      <span style="font-size:11px;color:#8B949E">{olcut['aciklama']}</span>
    </div>
    <div style="text-align:right;min-width:120px">
      <div style="font-size:11px;color:{_oc};font-weight:700">{olcut['detay']}</div>
      <div style="background:#21262D;border-radius:4px;height:5px;margin-top:4px;overflow:hidden">
        <div style="width:{olcut['puan']}%;background:{_oc};height:100%;border-radius:4px"></div>
      </div>
      <div style="font-size:9px;color:#484F58;margin-top:1px">{olcut['puan']}/100 puan</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

            if not all(o["gecerli"] for o in v["olcutler"]):
                st.markdown(f"""<div style="background:rgba(248,81,73,.06);border-left:3px solid #3FB950;
border-radius:6px;padding:8px 12px;margin-top:6px;font-size:11px;color:#C9D1D9">
  <b style="color:#3FB950">⚡ Önerilen Adımlar:</b><br>
  {"<br>".join(f"• {o['kural']}" for o in v['olcutler'] if not o['gecerli'])}
</div>""", unsafe_allow_html=True)
    footer()


# ═══════════════════════════════════════════════════════════
# TÜRKİYE HARİTASI
# ═══════════════════════════════════════════════════════════
def turkey_map(df):
    """Türkiye risk haritası — büyük, renkli, detaylı, AI yorumlu."""
    # Geçerli lokasyon filtresi: boş isim, "None", tek karakter, nan → hariç tut
    map_df = df[
        df["Lat"].notna() &
        df["Lon"].notna() &
        df["Sehir"].notna() &
        (df["Sehir"].astype(str).str.strip() != "") &
        (df["Sehir"].astype(str).str.strip() != "None") &
        (df["Sehir"].astype(str).str.strip() != "nan") &
        (df["Sehir"].astype(str).str.len() > 1)
    ].copy()
    if len(map_df) == 0:
        st.info("Harita icin IP-Sehir eslestirmesi bulunamadi. SUBNET_CITY sozlugunu guncelleyin.")
        return

    city_risk = map_df.groupby(["Sehir","Lat","Lon"]).agg(
        Cihaz    = ("Final_Risk_Skoru", "count"),
        Ort_Risk = ("Final_Risk_Skoru", "mean"),
        Max_Risk = ("Final_Risk_Skoru", "max"),
        Yuksek   = ("Seviye", lambda x: (x == "YÜKSEK").sum()),
        Orta     = ("Seviye", lambda x: (x == "ORTA").sum()),
        Dusuk    = ("Seviye", lambda x: (x == "DÜŞÜK").sum()),
        Max_Yama = ("Yamasız Gün",      "max") if "Yamasız Gün" in map_df.columns else ("Final_Risk_Skoru","max"),
    ).reset_index()
    city_risk["Ort_Risk"]  = city_risk["Ort_Risk"].round(1)
    city_risk["Yuksek_Oran"] = (city_risk["Yuksek"] / city_risk["Cihaz"] * 100).round(1)

    # Renk: yüksek risk oranına göre (kırmızı→turuncu→yeşil)
    def _risk_color(row):
        oran = row["Yuksek_Oran"]
        if oran >= 30:   return "#F85149"
        elif oran >= 15: return "#FF7B72"
        elif oran >= 5:  return "#D29922"
        else:            return "#3FB950"

    city_risk["Renk"]  = city_risk.apply(_risk_color, axis=1)
    # Baloncuk boyutu: cihaz sayısına göre (min 16, max 52)
    _mx = city_risk["Cihaz"].max()
    city_risk["Boyut"] = ((city_risk["Cihaz"] / _mx) * 36 + 16).round(0)

    # ── Harita ─────────────────────────────────────────────────
    fig = go.Figure()

    # Kritik şehirler için ekstra hale (glow effect)
    kritik_sehirler = city_risk[city_risk["Yuksek_Oran"] >= 20]
    for _, r in kritik_sehirler.iterrows():
        fig.add_trace(go.Scattergeo(
            lon=[r["Lon"]], lat=[r["Lat"]],
            mode="markers",
            marker=dict(size=r["Boyut"] * 1.9, color=r["Renk"], opacity=0.18,
                        line=dict(width=0)),
            showlegend=False, hoverinfo="skip",
        ))

    # Ana noktalar
    for _, r in city_risk.iterrows():
        pct_h = r["Yuksek_Oran"]
        risk_lbl = "🔴 Kritik" if pct_h >= 30 else "🟠 Yüksek" if pct_h >= 15 else "🟡 Orta" if pct_h >= 5 else "🟢 İyi"
        fig.add_trace(go.Scattergeo(
            lon=[r["Lon"]], lat=[r["Lat"]],
            mode="markers+text",
            marker=dict(
                size=r["Boyut"]*1.1, color=r["Renk"], opacity=0.95,
                line=dict(color="#0D1117", width=2.5),
                symbol="circle",
            ),
            text=[f"<b>{r['Sehir']}</b>"],
            textposition="top center",
            textfont=dict(color="#E6EDF3", size=10, family="Inter"),
            name=r["Sehir"],
            showlegend=False,
            hovertemplate=(
                f"<b>{r['Sehir']}</b> {risk_lbl}<br>"
                f"━━━━━━━━━━━━━━━━<br>"
                f"🖥️ Toplam Cihaz: <b>{int(r['Cihaz'])}</b><br>"
                f"📊 Ort. Risk Skoru: <b>{r['Ort_Risk']}</b>/100<br>"
                f"🔴 Yüksek Riskli: <b>{int(r['Yuksek'])}</b> (%{pct_h:.1f})<br>"
                f"🟡 Orta Riskli:   <b>{int(r['Orta'])}</b><br>"
                f"🟢 Düşük Riskli:  <b>{int(r['Dusuk'])}</b><br>"
                f"⚠ Max Risk Skoru: <b>{int(r['Max_Risk'])}</b>"
                "<extra></extra>"
            ),
        ))

    # Gerçek legend: sadece label trace'leri (harita dışında görünmez nokta)
    # Deniz ortasında değil — sadece legend kaydı için invisible trace
    for clr, lbl in [
        ("#F85149","🔴 Kritik (>%30 yüksek risk)"),
        ("#D29922","🟡 Yüksek (%5-30)"),
        ("#3FB950","🟢 İyi (<%5)"),
    ]:
        fig.add_trace(go.Scattergeo(
            lon=[None], lat=[None], mode="markers",
            marker=dict(size=10, color=clr, opacity=0.9),
            name=lbl, showlegend=True,
        ))

    fig.update_geos(
        scope="asia",
        center=dict(lon=35, lat=39),
        projection_scale=5.8,
        showland=True,        landcolor="#1C2B3A",
        showocean=True,       oceancolor="#061020",
        showcoastlines=True,  coastlinecolor="#3A6E8E", coastlinewidth=1.5,
        showcountries=True,   countrycolor="#3A6E8E",   countrywidth=0.8,
        showlakes=True,       lakecolor="#0A2030",
        showrivers=True,      rivercolor="#152840",     riverwidth=0.5,
        showframe=False,
        bgcolor="#061020",
        showsubunits=True,    subunitcolor="#243A4E",   subunitwidth=0.5,
        resolution=50,
    )
    # DARK dict'teki margin'i override et — çakışmayı önle
    _map_layout = {k: v for k, v in DARK.items() if k != "margin"}
    _map_layout.update(dict(
        height=720,
        showlegend=False,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(
            orientation="h", yanchor="bottom", y=0.01,
            xanchor="center", x=0.5,
            font=dict(color="#C9D1D9", size=11),
            bgcolor="rgba(13,17,23,0.8)",
            bordercolor="#30363D", borderwidth=1,
        ),
    ))
    fig.update_layout(**_map_layout)
    st.plotly_chart(fig, use_container_width=True)

    # ── İki kolon: KPI + Tablo ─────────────────────────────────
    col_map_a, col_map_b = st.columns([1, 2])

    with col_map_a:
        # En riskli şehir KPI'ları
        top_city     = city_risk.nlargest(1, "Ort_Risk").iloc[0]
        most_devices = city_risk.nlargest(1, "Cihaz").iloc[0]
        st.markdown(f"""
<div style="background:linear-gradient(135deg,#1A0A0A,#2D1010);border:1px solid #F85149;
border-radius:10px;padding:14px;margin:4px 0">
  <div style="font-size:9px;color:#F85149;text-transform:uppercase;font-weight:700">
    ⚠ En Riskli Lokasyon</div>
  <div style="font-size:22px;font-weight:800;color:#F85149">{top_city['Sehir']}</div>
  <div style="font-size:12px;color:#C9D1D9">
    Ort. Risk: <b>{top_city['Ort_Risk']}</b>/100 &nbsp;·&nbsp;
    Yüksek: <b>{int(top_city['Yuksek'])}</b> cihaz</div>
</div>
<div style="background:linear-gradient(135deg,#091020,#0D2040);border:1px solid #58A6FF;
border-radius:10px;padding:14px;margin:4px 0">
  <div style="font-size:9px;color:#58A6FF;text-transform:uppercase;font-weight:700">
    🖥️ En Kalabalık Lokasyon</div>
  <div style="font-size:22px;font-weight:800;color:#58A6FF">{most_devices['Sehir']}</div>
  <div style="font-size:12px;color:#C9D1D9">
    {int(most_devices['Cihaz'])} cihaz &nbsp;·&nbsp;
    Ort. Risk: <b>{most_devices['Ort_Risk']}</b>/100</div>
</div>""", unsafe_allow_html=True)

        # AI Risk Yorumu (kural tabanlı, hızlı)
        _total_cities   = len(city_risk)
        _kritik_c       = int((city_risk["Yuksek_Oran"] >= 30).sum())
        _en_riskli_list = city_risk.nlargest(3, "Ort_Risk")[["Sehir","Yuksek","Cihaz"]].to_dict("records")
        _en_riskli_str  = ", ".join([f"{r['Sehir']} ({int(r['Yuksek'])} yüksek)" for r in _en_riskli_list])

        if _kritik_c >= 3:
            _ai_renk  = "#F85149"
            _ai_icon  = "🔴"
            _ai_ozet  = (f"{_total_cities} lokasyonda {int(city_risk['Yuksek'].sum())} yüksek riskli cihaz dağılmış durumda. "
                         f"{_kritik_c} şehir kritik eşiği (%30+) aştı. "
                         f"En riskli lokasyonlar: **{_en_riskli_str}**. "
                         "Merkezi patch yönetimi ve uzak acil müdahale planı önceliklendirilmeli.")
        elif _kritik_c >= 1:
            _ai_renk  = "#D29922"
            _ai_icon  = "🟡"
            _ai_ozet  = (f"{_kritik_c} lokasyon kritik eşikte. "
                         f"Öne çıkan riskli nokta: {top_city['Sehir']} "
                         f"({top_city['Ort_Risk']} ort. risk). "
                         "Lokasyon bazlı patch önceliklendirmesi önerilir.")
        else:
            _ai_renk  = "#3FB950"
            _ai_icon  = "🟢"
            _ai_ozet  = (f"Tüm {_total_cities} lokasyon kabul edilebilir risk seviyesinde. "
                         f"En yüksek risk {top_city['Sehir']}'de ({top_city['Ort_Risk']}). "
                         "Rutin izleme yeterli.")

        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_ai_renk};
border-left:4px solid {_ai_renk};border-radius:10px;padding:14px;margin:4px 0">
  <div style="font-size:9px;color:{_ai_renk};font-weight:700;text-transform:uppercase;
  margin-bottom:6px">🤖 Lokasyon Risk Analizi</div>
  <div style="font-size:11px;color:#C9D1D9;line-height:1.6">{_ai_icon} {_ai_ozet}</div>
</div>""", unsafe_allow_html=True)

    with col_map_b:
        # Şehir risk tablosu — renkli
        show_cols = city_risk[["Sehir","Cihaz","Ort_Risk","Yuksek","Yuksek_Oran","Orta","Dusuk"]].copy()
        show_cols.columns = ["Şehir","Cihaz","Ort. Risk","Yüksek","% Yüksek","Orta","Düşük"]
        show_cols = show_cols.sort_values("Ort. Risk", ascending=False).reset_index(drop=True)
        st.dataframe(
            show_cols,
            use_container_width=True,
            height=300,
            hide_index=True,
            column_config={
                "Ort. Risk": st.column_config.ProgressColumn(
                    "Ort. Risk", min_value=0, max_value=100, format="%.1f"
                ),
                "% Yüksek": st.column_config.NumberColumn("% Yüksek", format="%.1f%%"),
                "Yüksek": st.column_config.NumberColumn("🔴 Yüksek"),
                "Orta":   st.column_config.NumberColumn("🟡 Orta"),
                "Düşük":  st.column_config.NumberColumn("🟢 Düşük"),
            }
        )

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
    adm  = int(df["_RawAdminCount"].gt(0).sum())   if "_RawAdminCount"  in df.columns else 0
    disk = int((df["% Boş"] < 10).sum())           if "% Boş"           in df.columns else 0
    wu   = int(df["_RawUpdateStop"].gt(0).sum())   if "_RawUpdateStop"  in df.columns else 0
    shd  = int(df["Tespit Edilen Şüpheli Yazılımlar"].ne("").sum())
    share= int(df["Riskli Paylaşılan Klasörler"].ne("").sum()) if "Riskli Paylaşılan Klasörler" in df.columns else 0
    avg  = round(float(df["Final_Risk_Skoru"].mean()),1)
    sc = posture_score(df)
    sc_clr = "#F85149" if sc<40 else "#D29922" if sc<65 else "#3FB950"
    sc_lbl = "Kritik"  if sc<40 else "Orta"    if sc<65 else "Iyi"

    # ── Başlık — dolu, anlamlı ──────────────────────────────────
    # Trend: dünle karşılaştır
    _trend_delta_h = 0; _trend_delta_avg = 0.0; _trend_days = 0
    if len(hist) >= 2:
        _trend_delta_h   = hist[-1]["yuksek"] - hist[-2]["yuksek"]
        _trend_delta_avg = round(hist[-1].get("avg",0) - hist[-2].get("avg",0), 1)
        _trend_days      = len(hist)
    _tr_clr  = "#F85149" if _trend_delta_h > 0 else "#3FB950" if _trend_delta_h < 0 else "#8B949E"
    _tr_icon = "↑" if _trend_delta_h > 0 else "↓" if _trend_delta_h < 0 else "→"
    _tr_msg  = (f"{_tr_icon} Dünden {abs(_trend_delta_h)} {'artış' if _trend_delta_h>0 else 'azalış'}"
                if _trend_delta_h != 0 else "→ Dünle aynı seviye")

    ca, cb, cc = st.columns([4, 2, 2])
    with ca:
        st.markdown(f"""
<div style="padding:6px 0">
  <div style="font-size:22px;font-weight:800;color:#E6EDF3;letter-spacing:-0.5px">
    🛡️ IT Risk Intelligence Platform
  </div>
  <div style="display:flex;gap:16px;margin-top:6px;flex-wrap:wrap">
    <span style="color:#8B949E;font-size:12px">🖥️ <b style="color:#C9D1D9">{n:,}</b> cihaz</span>
    <span style="color:#8B949E;font-size:12px">📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}</span>
    <span style="color:#8B949E;font-size:12px">📊 <b style="color:#C9D1D9">{_trend_days}</b> günlük veri</span>
    <span style="color:{_tr_clr};font-size:12px;font-weight:700">{_tr_msg}</span>
  </div>
</div>""", unsafe_allow_html=True)
    with cb:
        st.markdown(f"""
<div style="background:linear-gradient(135deg,#161B22,#1C2333);border:1px solid {sc_clr}44;
border-left:4px solid {sc_clr};border-radius:10px;padding:12px 14px">
  <div style="font-size:9px;color:#8B949E;text-transform:uppercase;font-weight:700;margin-bottom:6px">
    🛡️ Güvenlik Postür Skoru
    <span class="tooltip-wrap" style="color:#58A6FF;cursor:help;margin-left:4px">?
      <span class="tooltip-txt"><b>Postür Skoru Nedir?</b><br><br>
      0-100 arasında genel siber güvenlik sağlığı.<br><br>
      <b>Hesaplama:</b><br>
      • Yüksek riskli cihazlar (-50%)<br>
      • 60+ gün yamasız sistemler (-30%)<br>
      • 60+ gün offline cihazlar (-20%)<br><br>
      <b>Değerlendirme:</b><br>
      • 80-100 = ✅ İyi &nbsp;&nbsp; • 65-79 = ⚠️ Orta &nbsp;&nbsp; • 0-64 = 🔴 Kritik</span>
    </span>
  </div>
  <div style="display:flex;align-items:baseline;gap:8px">
    <div style="font-size:34px;font-weight:900;color:{sc_clr};line-height:1">{sc}</div>
    <div style="font-size:13px;color:#8B949E">/100</div>
    <div style="background:{sc_clr};color:#fff;font-size:11px;font-weight:700;
    padding:3px 10px;border-radius:20px">{sc_lbl}</div>
  </div>
  <div style="background:#21262D;border-radius:4px;height:5px;margin-top:8px;overflow:hidden">
    <div style="width:{sc}%;background:{sc_clr};height:100%;border-radius:4px"></div>
  </div>
</div>""", unsafe_allow_html=True)
    with cc:
        # Dünkü karşılaştırma kartı
        _prev_sc = hist[-2].get("posture", sc) if len(hist)>=2 else sc
        _sc_diff = sc - _prev_sc
        _sc_diff_clr = "#3FB950" if _sc_diff > 0 else "#F85149" if _sc_diff < 0 else "#8B949E"
        st.markdown(f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px 14px">
  <div style="font-size:9px;color:#8B949E;text-transform:uppercase;font-weight:700;margin-bottom:6px">
    📈 Dün ile Karşılaştırma
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div>
      <div style="font-size:9px;color:#8B949E">Yüksek Risk</div>
      <div style="font-size:18px;font-weight:800;color:#F85149">{nh:,}</div>
      <div style="font-size:10px;color:{_tr_clr};font-weight:600">{_tr_icon}{abs(_trend_delta_h)}</div>
    </div>
    <div>
      <div style="font-size:9px;color:#8B949E">Postür Skoru</div>
      <div style="font-size:18px;font-weight:800;color:{sc_clr}">{sc}</div>
      <div style="font-size:10px;color:{_sc_diff_clr};font-weight:600">
        {"+" if _sc_diff>0 else ""}{_sc_diff:.0f} puan
      </div>
    </div>
  </div>
  <div style="font-size:10px;color:#484F58;margin-top:6px">
    Ort. risk skoru: <b style="color:#8B949E">{avg}</b>/100
    {f' · {"↑" if _trend_delta_avg>0 else "↓"}{abs(_trend_delta_avg)}' if _trend_delta_avg!=0 else ''}
  </div>
</div>""", unsafe_allow_html=True)
    # cd kaldırıldı — Son Tarama bilgisini cc içine dahil et
    # (zaten cc = Dünle Karşılaştırma kartı)

    st.markdown("---")

    # KPI satırı — 2 satır × 6, eşit boyut, simgeli
    _krow1 = st.columns(6)
    kpi(_krow1[0], n,    "Toplam Cihaz",    "#58A6FF", f"Ort:{avg}",        "linear-gradient(135deg,#0d2137,#162e4d)", "🖥️")
    kpi(_krow1[1], nh,   "Yüksek Risk",     "#F85149", f"%{nh/n*100:.1f}",  "linear-gradient(135deg,#3d0000,#5c0a0a)", "🔴")
    kpi(_krow1[2], nm,   "Orta Risk",       "#D29922", f"%{nm/n*100:.1f}",  "linear-gradient(135deg,#3d2200,#5c3300)", "🟡")
    kpi(_krow1[3], nl,   "Düşük Risk",      "#3FB950", f"%{nl/n*100:.1f}",  "linear-gradient(135deg,#0d2e14,#1a4a23)", "🟢")
    kpi(_krow1[4], pc,   "Patch 60g+",      "#FF7B72", f"%{pc/n*100:.1f}",  "linear-gradient(135deg,#3d1500,#5c2200)", "🩹")
    kpi(_krow1[5], oc,   "Offline 60g+",    "#79C0FF", f"%{oc/n*100:.1f}",  "linear-gradient(135deg,#0d1f3d,#152d57)", "📴")
    _krow2 = st.columns(6)
    kpi(_krow2[0], ec,   "EoL OS",          "#D2A8FF", f"%{ec/n*100:.1f}",  "linear-gradient(135deg,#2d1a4d,#3d2466)", "💀")
    kpi(_krow2[1], adm,  "Yetkisiz Admin",  "#FFA657", f"%{adm/n*100:.1f}", "linear-gradient(135deg,#3d2200,#5c3000)", "👤")
    kpi(_krow2[2], disk, "Kritik Disk",     "#E07B54", f"%{disk/n*100:.1f}","linear-gradient(135deg,#3d1a00,#5c2800)", "💾")
    kpi(_krow2[3], wu,   "WU Kapalı",       "#A5D6FF", f"%{wu/n*100:.1f}",  "linear-gradient(135deg,#0a1828,#112238)", "🔄")
    kpi(_krow2[4], share,"Riskli Klasör",   "#FF9F43", f"%{share/n*100:.1f}","linear-gradient(135deg,#3d2800,#5c3c00)", "📂")
    kpi(_krow2[5], shd,  "Şüpheli Yazılım", "#C9D1D9", f"%{shd/n*100:.1f}", "linear-gradient(135deg,#1a1a2e,#24243e)", "🦠")

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
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        sec("📈 Risk Trendi & Gidiş Analizi")
        if len(hist) >= 3:
            _hdf = pd.DataFrame(hist[-21:])  # Son 21 gün
            _hdf["date"] = pd.to_datetime(_hdf["date"])
            _hdf["Gün"] = _hdf["date"].dt.strftime("%d.%m")

            _fig2 = go.Figure()
            # Yüksek — dolgu bar
            _fig2.add_trace(go.Bar(
                x=_hdf["Gün"], y=_hdf["yuksek"], name="🔴 Yüksek",
                marker_color="#F85149", opacity=0.85,
                hovertemplate="<b>%{x}</b><br>Yüksek: %{y} cihaz<extra></extra>"))
            # Orta — bar üstüne
            _fig2.add_trace(go.Bar(
                x=_hdf["Gün"], y=_hdf["orta"], name="🟡 Orta",
                marker_color="#D29922", opacity=0.7,
                hovertemplate="<b>%{x}</b><br>Orta: %{y} cihaz<extra></extra>"))
            # Postür çizgisi — sağ eksen
            if "posture" in _hdf.columns:
                _fig2.add_trace(go.Scatter(
                    x=_hdf["Gün"], y=_hdf["posture"], name="🛡 Postür",
                    line=dict(color="#58A6FF",width=2.5,dash="solid"),
                    mode="lines+markers", marker=dict(size=5,color="#58A6FF"),
                    yaxis="y2",
                    hovertemplate="<b>%{x}</b><br>Postür: %{y}/100<extra></extra>"))
            _fig2.update_layout(
                **DARK, height=280, barmode="stack",
                legend=dict(font=dict(color="#C9D1D9",size=9),
                            orientation="h",y=1.08,x=0),
                yaxis=dict(title="Cihaz Sayısı",gridcolor="#21262D"),
                yaxis2=dict(title="Postür /100", overlaying="y", side="right",
                            range=[0,105], tickfont=dict(color="#58A6FF",size=8),
                            showgrid=False),
                bargap=0.15,
            )
            st.plotly_chart(_fig2, use_container_width=True)

            # AI Trend Yorumu
            _last  = hist[-1]; _prev  = hist[-2]
            _d_h   = _last["yuksek"] - _prev["yuksek"]
            _d_avg = round(_last.get("avg",0) - _prev.get("avg",0), 1)
            _d_pct = round(_d_h / max(_prev["yuksek"],1) * 100, 1) if _prev["yuksek"]>0 else 0
            _wk_trend = sum(h["yuksek"] for h in hist[-7:]) / 7 if len(hist)>=7 else _last["yuksek"]
            _wk_dir   = "artış" if _last["yuksek"] > _wk_trend else "azalış"

            if _d_h < -5:
                _t_clr="#3FB950";_t_icon="📉";_t_lbl="İYİLEŞİYOR"
                _t_msg=f"Yüksek riskli cihaz sayısı dünden %{abs(_d_pct):.1f} azaldı ({abs(_d_h)} cihaz). 7 günlük ortalamayla kıyaslandığında {_wk_dir} eğilimi devam ediyor."
            elif _d_h > 5:
                _t_clr="#F85149";_t_icon="📈";_t_lbl="KÖTÜLEŞIYOR"
                _t_msg=f"Yüksek riskli cihaz sayısı dünden %{abs(_d_pct):.1f} arttı ({_d_h} cihaz). Acil müdahale gerekiyor. 7 günlük {_wk_dir} eğilimi sürmekte."
            elif abs(_d_avg) > 2:
                _t_clr="#D29922";_t_icon="↗" if _d_avg>0 else "↘";_t_lbl="DEĞİŞİYOR"
                _t_msg=f"Cihaz sayısı stabil ancak ortalama risk skoru {'+' if _d_avg>0 else ''}{_d_avg} puan {'yükseldi' if _d_avg>0 else 'düştü'}. Gelişme {'olumsuz' if _d_avg>0 else 'olumlu'}."
            else:
                _t_clr="#8B949E";_t_icon="⟳";_t_lbl="STABİL"
                _t_msg=f"Risk profili dünle neredeyse aynı. Yüksek risk: {_last['yuksek']} · Ort. skor: {_last.get('avg',0):.1f}"

            st.markdown(f"""<div style="background:#0D1117;border-left:4px solid {_t_clr};
border-radius:6px;padding:10px 14px;margin:4px 0">
  <div style="display:flex;justify-content:space-between;margin-bottom:4px">
    <span style="color:{_t_clr};font-size:10px;font-weight:700">🤖 AI Trend Analizi</span>
    <span style="background:{_t_clr};color:#fff;font-size:9px;font-weight:700;padding:1px 8px;border-radius:10px">{_t_icon} {_t_lbl}</span>
  </div>
  <div style="font-size:11px;color:#C9D1D9;line-height:1.6">{_t_msg}</div>
</div>""", unsafe_allow_html=True)
        elif len(hist) == 2:
            _d2 = hist[-1]["yuksek"] - hist[-2]["yuksek"]
            _msg2 = f"Dünden {'↑ '+str(_d2)+' artış' if _d2>0 else '↓ '+str(abs(_d2))+' azalış' if _d2<0 else '→ değişim yok'}. Daha fazla snapshot birikince trend grafiği görünecek."
            st.info(f"📊 {_msg2}")
        else:
            st.markdown("""<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
padding:24px;text-align:center;margin:8px 0">
  <div style="font-size:24px">📊</div>
  <div style="color:#8B949E;font-size:12px;margin-top:8px">Risk engine her çalıştığında<br>otomatik snapshot birikir.</div>
  <div style="color:#484F58;font-size:10px;margin-top:4px">3+ gün sonra trend grafiği aktifleşir.</div>
</div>""", unsafe_allow_html=True)

    with c3:
        sec("Tehdit Türleri — Tam Görünüm")
        # Tüm tehdit vektörlerini kapsamlı göster
        _tmap_full = {
            "Onaysız Yönetici Yetkisi": "Yetkisiz Admin",
            "DLP Yüklü Değil":          "DLP Eksik",
            "Antivirüs (SEP) Eksik":    "AV / SEP Yok",
            "Güvenlik Yamaları Eksik":  "Patch Eksik",
            "Şüpheli Yazılım":          "Shadow IT",
            "Desteklenmeyen OS":        "EoL OS",
            "Update Servisi Kapalı":    "WU Kapalı",
            "Riskli Paylaşım":          "Açık Klasör",
            "Uzun Süredir Offline":     "Offline Cihaz",
            "Sabit Şifreli Admin":      "Sabit Şifre",
            "Disk Kritik":              "Kritik Disk",
            "Firewall":                 "Firewall Kapalı",
            "Antivirüs":                "AV Eksik (Genel)",
        }
        _ra = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)
        _threats = {
            lbl: int(_ra.str.contains(kw, na=False, regex=False).sum())
            for kw, lbl in _tmap_full.items()
        }
        # _Raw sütunlarından gerçek sayılar ekle (Risk Analizi metninde olmayabilir)
        if "_RawDiskError"  in df.columns: _threats["Disk Hatası (_Raw)"]  = int(df["_RawDiskError"].gt(0).sum())
        if "_RawAdminCount" in df.columns: _threats["Admin Fazlalığı (_Raw)"] = int(df["_RawAdminCount"].gt(0).sum())
        if "_RawUpdateStop" in df.columns: _threats["WU Durdurulmuş (_Raw)"]  = int(df["_RawUpdateStop"].gt(0).sum())
        if "Riskli Paylaşılan Klasörler" in df.columns:
            _threats["Riskli Paylaşım (Klasör)"] = int(df["Riskli Paylaşılan Klasörler"].ne("").sum())
        # Yamasız/offline direkt sayı (eşik bazlı)
        if "Yamasız Gün" in df.columns:
            _threats["Yamasız >60g"]  = int((df["Yamasız Gün"] > 60).sum())
            _threats["Yamasız >180g"] = int((df["Yamasız Gün"] > 180).sum())
        if "Offline Gün" in df.columns:
            _threats["Offline >60g"]  = int((df["Offline Gün"] > 60).sum())
        if "% Boş" in df.columns:
            _threats["Disk <10% Boş"] = int((df["% Boş"] < 10).sum())
        # Sıfır olanları filtrele, büyükten küçüğe sırala
        _threats = {k: v for k, v in sorted(_threats.items(), key=lambda x: -x[1]) if v > 0}
        if _threats:
            _tdf = pd.DataFrame(list(_threats.items()), columns=["Tehdit","Sayi"])
            # Her çubuğa risk rengi ver
            def _tclr(v):
                mx = _tdf["Sayi"].max()
                r = v / max(mx, 1)
                if r >= 0.6: return "#F85149"
                if r >= 0.3: return "#D29922"
                return "#3FB950"
            _tdf["Renk"] = _tdf["Sayi"].apply(_tclr)
            _tdf["Oran"] = (_tdf["Sayi"] / n * 100).round(1).astype(str) + "%"
            _fig3 = go.Figure()
            for _, _tr in _tdf.sort_values("Sayi").iterrows():
                _fig3.add_trace(go.Bar(
                    x=[_tr["Sayi"]], y=[_tr["Tehdit"]],
                    orientation="h",
                    marker_color=_tr["Renk"],
                    text=[f"{_tr['Sayi']}  ({_tr['Oran']})"],
                    textposition="outside",
                    textfont=dict(color="#C9D1D9", size=10),
                    showlegend=False,
                    hovertemplate=f"<b>{_tr['Tehdit']}</b><br>{_tr['Sayi']} cihaz · %{_tr['Oran']}<extra></extra>",
                ))
            _h3 = max(300, len(_threats) * 28)
            _fig3.update_layout(**DARK, height=_h3, showlegend=False,
                                xaxis=dict(range=[0, _tdf["Sayi"].max() * 1.35]))
            st.plotly_chart(_fig3, use_container_width=True)
        else:
            st.success("✅ Aktif tehdit vektörü tespit edilmedi")

    # Türkiye Haritası — Aksiyonlar öncesinde
    st.markdown("---")
    sec("🗺️ Cihaz Lokasyon Haritası — Türkiye")
    turkey_map(df)

    # Aksiyon Paneli
    st.markdown("---")
    sec("🚨 Önerilen Aksiyonlar")
    st.caption("⚡ Butona tıklayarak ilgili sayfaya gidin")
    # Aksiyon tanımları: (css_class, mesaj, goto_page, section_key, uid)
    _actions_raw = [
        ("ac-red", f"🔴 {nh} yüksek riskli cihaz — acil müdahale bekliyor",
         "🚨 Önerilen Aksiyonlar", "yuksek_risk",  "high_risk")  if nh>0  else None,
        ("ac-red", f"🔴 {pc} cihaz 60+ gün yamasız — Windows Update acil",
         "🚨 Önerilen Aksiyonlar", "yamasiz",       "patch_crit") if pc>0  else None,
        ("ac-org", f"🟠 {adm} cihazda yetkisiz admin — AD'den kaldır",
         "🚨 Önerilen Aksiyonlar", "yetkisiz_admin","unauth_adm") if adm>0 else None,
        ("ac-org", f"🟠 {oc} cihaz 60+ gün offline — zombi cihaz inceleme",
         "🚨 Önerilen Aksiyonlar", "offline",       "offline_cr") if oc>0  else None,
        ("ac-grn", f"🟡 {shd} cihazda şüpheli yazılım — kaldırma iş emri",
         "🚨 Önerilen Aksiyonlar", "suphe_yazilim", "shadow_sw")  if shd>0 else None,
        ("ac-org", f"🟠 {ec} EoL işletim sistemi — yükseltme planı gerekli",
         "🚨 Önerilen Aksiyonlar", "eol_os",        "eol_os")     if ec>0  else None,
    ]
    _active = [a for a in _actions_raw if a]
    if not _active:
        st.success("✅ Kritik aksiyon gerektiren durum tespit edilmedi.")
    else:
        for _idx, (_css, _msg, _dest, _section, _uid) in enumerate(_active):
            col_card, col_btn = st.columns([5, 1])
            with col_card:
                st.markdown(f'<div class="action-card {_css}" style="cursor:pointer">{_msg}</div>',
                            unsafe_allow_html=True)
            with col_btn:
                st.markdown("<div style='padding-top:6px'></div>", unsafe_allow_html=True)
                if st.button("↗ Git", key=f"actn_{_uid}_{_idx}"):
                    st.session_state["goto_page"]    = _dest
                    st.session_state["action_section"] = _section
                    st.rerun()

    # Patch halka grafiği
    st.markdown("---")
    sec("🩹 Patch Uyum Analizi")
    st.markdown("""<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
padding:10px 14px;margin:4px 0 10px 0;font-size:11px;color:#C9D1D9;line-height:1.6">
  <b style="color:#FF7B72">Patch Uyumu Nedir?</b> — Sistemlerin güvenlik yamalarını ne kadar güncel tuttuğunu ölçer.
  60+ gün yamasız cihazlar bilinen CVE açıklarına karşı savunmasız olur.
  <b style="color:#3FB950">Öneri:</b> CVSS≥7 yamalar 48 saat, standart yamalar 30 gün içinde uygulanmalı.
</div>""", unsafe_allow_html=True)
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
            st.plotly_chart(fig_p, use_container_width=True)
        with cb3:
            st.metric("Uyumlu (60g)",f"{uyumlu}",f"%{uyumlu/n*100:.1f}")
            st.metric("Kritik (60g+)",f"{pc}",f"%{pc/n*100:.1f}",delta_color="inverse")
            st.metric("Ort. Yamasiz",f"{df['Yamasız Gün'].mean():.1f}g")
            _max_patch = int(df["Yamasız Gün"].max())
            st.metric("Max Yamasiz", f"{_max_patch}g")
            # Max yamasız cihaz bilgisi + link
            _max_row = df.loc[df["Yamasız Gün"].idxmax()]
            _max_name = str(_max_row.get("AssetName","?"))
            _max_lsw  = str(_max_row.get("Lansweeper",""))
            _max_user = str(_max_row.get("Kullanıcı",""))
            if _max_lsw:
                st.markdown(f"""<div style="background:rgba(248,81,73,.1);border-left:3px solid #F85149;
border-radius:6px;padding:8px 10px;margin:4px 0;font-size:11px">
  <div style="color:#F85149;font-weight:700">⚠ En Uzun Yamasız</div>
  <div style="color:#E6EDF3">{_max_name}</div>
  <div style="color:#8B949E">{_max_user}</div>
  <a href="{_max_lsw}" target="_blank" style="color:#58A6FF;font-size:11px">🔗 Lansweeper'da Aç</a>
</div>""", unsafe_allow_html=True)
            else:
                st.caption(f"⚠ {_max_name} ({_max_user})")
            # Max offline bilgisi
            if "Offline Gün" in df.columns and df["Offline Gün"].max() > 60:
                _max_off     = int(df["Offline Gün"].max())
                _max_off_row = df.loc[df["Offline Gün"].idxmax()]
                _off_name    = str(_max_off_row.get("AssetName","?"))
                _off_lsw     = str(_max_off_row.get("Lansweeper",""))
                _off_user    = str(_max_off_row.get("Kullanıcı",""))
                st.metric("Max Offline", f"{_max_off}g")
                if _off_lsw:
                    st.markdown(f"""<div style="background:rgba(121,192,255,.08);border-left:3px solid #79C0FF;
border-radius:6px;padding:8px 10px;margin:4px 0;font-size:11px">
  <div style="color:#79C0FF;font-weight:700">📴 En Uzun Offline</div>
  <div style="color:#E6EDF3">{_off_name}</div>
  <div style="color:#8B949E">{_off_user}</div>
  <a href="{_off_lsw}" target="_blank" style="color:#58A6FF;font-size:11px">🔗 Lansweeper'da Aç</a>
</div>""", unsafe_allow_html=True)
                else:
                    st.caption(f"📴 {_off_name} ({_off_user})")

    # Patch Uyum Analizi — Ek grafikler + AI yorum (tek başlık, üsttekine taşındı)
    if "Yamasız Gün" in df.columns and df["Yamasız Gün"].sum() > 0:
        st.markdown("---")

        ca4, cb4 = st.columns(2)

        with ca4:
            sec("Patch Durumu — Risk Seviyesine Göre")
            # Yüksek/Orta/Düşük gruplarında ortalama yamasız gün
            _pgrp = df.groupby("Seviye")["Yamasız Gün"].agg(["mean","median","max"]).reset_index()
            _pgrp.columns = ["Seviye","Ort","Medyan","Maks"]
            _pgrp["Renk"] = _pgrp["Seviye"].map({"YÜKSEK":"#F85149","ORTA":"#D29922","DÜŞÜK":"#3FB950"})
            _pgrp = _pgrp[_pgrp["Seviye"].isin(["YÜKSEK","ORTA","DÜŞÜK"])]
            _fig_pg = go.Figure()
            for _, _r in _pgrp.iterrows():
                _fig_pg.add_trace(go.Bar(
                    name=_r["Seviye"], x=[_r["Seviye"]],
                    y=[_r["Ort"]], marker_color=_r["Renk"], opacity=0.9,
                    text=[f"Ort: {_r['Ort']:.0f}g"],
                    textposition="outside", textfont=dict(color="#C9D1D9"),
                    hovertemplate=f"<b>{_r['Seviye']}</b><br>Ort: {_r['Ort']:.0f}g<br>Medyan: {_r['Medyan']:.0f}g<br>Maks: {_r['Maks']:.0f}g<extra></extra>",
                ))
            _fig_pg.add_hline(y=60, line_dash="dash", line_color="#F85149",
                              annotation_text="Kritik Eşik (60g)", annotation_font_color="#F85149")
            _fig_pg.update_layout(**DARK, height=280, showlegend=False,
                                  yaxis_title="Ortalama Yamasız Gün")
            st.plotly_chart(_fig_pg, use_container_width=True)

        with cb4:
            sec("En Uzun Yamasız Cihazlar — İlk 10")
            _top10p = df.nlargest(10, "Yamasız Gün")[
                ["AssetName","Kullanıcı","Yamasız Gün","Seviye","Lansweeper"]
            ].copy()
            _fig_top = px.bar(
                _top10p.sort_values("Yamasız Gün"),
                x="Yamasız Gün", y="AssetName", orientation="h",
                color="Yamasız Gün",
                color_continuous_scale=["#D29922","#FF7B72","#F85149","#8B1A1A"],
                text="Yamasız Gün",
                hover_data={"Kullanıcı": True, "Seviye": True, "Lansweeper": False},
            )
            _fig_top.add_vline(x=60, line_dash="dash", line_color="#F85149",
                               annotation_text="60g")
            _fig_top.update_layout(**DARK, height=280, showlegend=False,
                                   coloraxis_showscale=False)
            _fig_top.update_traces(textposition="outside",
                                   textfont=dict(color="#C9D1D9"),
                                   texttemplate="%{text:.0f}g")
            st.plotly_chart(_fig_top, use_container_width=True)

        # AI Patch Yorumu — kural tabanlı, anlık
        _uyumlu_p = int((df["Yamasız Gün"] <= 60).sum())
        _kritik_p = int((df["Yamasız Gün"] > 60).sum())
        _cok_kritik_p = int((df["Yamasız Gün"] > 180).sum())
        _max_p   = int(df["Yamasız Gün"].max())
        _ort_p   = round(float(df["Yamasız Gün"].mean()), 1)
        _oran_p  = round(_kritik_p / max(n, 1) * 100, 1)

        if _oran_p >= 80:
            _p_renk = "#F85149"; _p_icon = "🔴"; _p_seviye = "KRİTİK"
            _p_yorum = (f"Patch uyumu **kritik** seviyede. {_oran_p}% cihaz ({_kritik_p} adet) 60+ gün yamasız. "
                        f"Ortalama yamasız süre {_ort_p} gün — bu oran fidye yazılımı saldırıları için "
                        f"doğrudan güvenlik açığı oluşturuyor. {_cok_kritik_p} cihaz 180+ gündür yamasız; "
                        "bunlar WSUS'tan kopmuş olabilir, manuel müdahale gerekli.")
            _p_aksiyon = "Acil: WSUS sağlığını kontrol et, otomatik güncelleme politikası zorla."
        elif _oran_p >= 40:
            _p_renk = "#D29922"; _p_icon = "🟡"; _p_seviye = "YÜKSEK"
            _p_yorum = (f"Patch uyumu **yetersiz**. {_kritik_p} cihaz ({_oran_p}%) 60+ gün yamasız. "
                        f"En uzun yamasız süre {_max_p} gün. "
                        f"{_cok_kritik_p} cihaz 180+ gün ile özellikle risk altında. "
                        "Bu hafta patch operasyonu başlatılmalı.")
            _p_aksiyon = "Önerilen: 180+ gün yamasız cihazları önceliklendir, SCCM/WSUS raporunu gözden geçir."
        else:
            _p_renk = "#3FB950"; _p_icon = "🟢"; _p_seviye = "KABUL EDİLEBİLİR"
            _p_yorum = (f"Patch durumu **kabul edilebilir** seviyede. {_uyumlu_p} cihaz ({100-_oran_p:.1f}%) uyumlu. "
                        f"Kalan {_kritik_p} cihaz için rutin patch döngüsü yeterli.")
            _p_aksiyon = "Rutin izleme ve aylık patch döngüsü sürdürülmeli."

        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_p_renk};
border-left:5px solid {_p_renk};border-radius:10px;padding:14px 18px;margin:8px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_p_renk};font-weight:700;text-transform:uppercase">🤖 AI Patch Risk Analizi</div>
    <div style="background:{_p_renk};color:#fff;font-size:10px;font-weight:700;
    padding:2px 10px;border-radius:20px">{_p_icon} {_p_seviye}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7;margin-bottom:6px">{_p_yorum}</div>
  <div style="font-size:11px;color:{_p_renk};font-weight:600">⚡ {_p_aksiyon}</div>
</div>""", unsafe_allow_html=True)

        # 3. grafik: Patch × Risk Korelasyon Scatter
        st.markdown("---")
        sec("Patch-Risk Korelasyonu — Yamasız Gün vs Final Risk Skoru")
        _sc_col1, _sc_col2 = st.columns([3,1])
        with _sc_col1:
            _hov = {c: True for c in ["AssetName","Kullanıcı","Cihaz_Tipi"] if c in df.columns}
            _fig_sc = px.scatter(
                df, x="Yamasız Gün", y="Final_Risk_Skoru",
                color="Seviye", color_discrete_map=SEV_CLR,
                opacity=0.65, size_max=8,
                hover_data=_hov,
            )
            _fig_sc.add_hline(y=50,  line_dash="dash", line_color="#F85149",
                              annotation_text="Yüksek Risk (50)", annotation_font_color="#F85149")
            _fig_sc.add_vline(x=60,  line_dash="dash", line_color="#D29922",
                              annotation_text="Kritik Patch (60g)", annotation_font_color="#D29922")
            _fig_sc.add_vline(x=180, line_dash="dot",  line_color="#FF7B72",
                              annotation_text="180g", annotation_font_color="#FF7B72")
            _fig_sc.update_layout(**DARK, height=320,
                                  legend=dict(font=dict(color="#C9D1D9")),
                                  xaxis_title="Yamasız Gün",
                                  yaxis_title="Final Risk Skoru")
            st.plotly_chart(_fig_sc, use_container_width=True)
        with _sc_col2:
            # Çeyrek analizi
            _q1 = df[(df["Yamasız Gün"]>60) & (df["Final_Risk_Skoru"]>=50)]
            _q2 = df[(df["Yamasız Gün"]>60) & (df["Final_Risk_Skoru"]<50)]
            _q3 = df[(df["Yamasız Gün"]<=60) & (df["Final_Risk_Skoru"]>=50)]
            _q4 = df[(df["Yamasız Gün"]<=60) & (df["Final_Risk_Skoru"]<50)]
            for _qlbl, _qdf, _qclr, _qdesc in [
                ("⚠ Kritik Bölge",  _q1, "#F85149", "Hem yamasız hem riskli"),
                ("🟡 Patch Öncelik", _q2, "#D29922", "Yamasız ama düşük risk"),
                ("🔷 Risk Öncelik",  _q3, "#79C0FF", "Yamalı ama yüksek risk"),
                ("✅ Güvenli",       _q4, "#3FB950", "Yamalı ve düşük risk"),
            ]:
                st.markdown(f"""<div style="background:#161B22;border-left:3px solid {_qclr};
border-radius:6px;padding:7px 10px;margin:4px 0;font-size:11px">
  <div style="color:{_qclr};font-weight:700">{_qlbl}: {len(_qdf)}</div>
  <div style="color:#8B949E">{_qdesc}</div>
</div>""", unsafe_allow_html=True)

    # ── Disk / WU / Admin Analizi ────────────────────────────────────────────
    st.markdown("---")
    sec("💾 Depolama · 🔄 Windows Update · 👤 Admin — Sistem Sağlık Analizi")
    _sag_c1, _sag_c2, _sag_c3 = st.columns(3)

    with _sag_c1:
        sec("Disk Doluluk Dağılımı", color="#E07B54")
        if "% Boş" in df.columns:
            _dbins = [0, 5, 10, 20, 40, 101]
            _dlbls = ["<5% (Kritik)", "5-10%", "10-20%", "20-40%", ">40% (İyi)"]
            _dcolors = ["#8B1A1A","#F85149","#D29922","#3FB950","#56D364"]
            _ddf = pd.cut(df["% Boş"].clip(0,100), bins=_dbins, labels=_dlbls, right=True)
            _dvc = _ddf.value_counts().reindex(_dlbls, fill_value=0).reset_index()
            _dvc.columns = ["Aralik","Cihaz"]
            _fig_d = go.Figure(go.Bar(
                x=_dvc["Aralik"], y=_dvc["Cihaz"],
                marker_color=_dcolors[:len(_dvc)],
                text=_dvc["Cihaz"], textposition="outside",
                textfont=dict(color="#C9D1D9"),
                hovertemplate="<b>%{x}</b><br>%{y} cihaz<extra></extra>",
            ))
            _fig_d.add_hline(y=0, line_color="#30363D")
            _fig_d.update_layout(**DARK, height=240, showlegend=False)
            st.plotly_chart(_fig_d, use_container_width=True)
            # AI
            _dk = int((df["% Boş"]<10).sum())
            _dk_oran = round(_dk/max(n,1)*100,1)
            _dk_clr  = "#F85149" if _dk_oran>=10 else "#D29922" if _dk_oran>=3 else "#3FB950"
            _dk_icon = "🔴" if _dk_oran>=10 else "🟡" if _dk_oran>=3 else "🟢"
            _dk_msg  = (f"**{_dk}** cihaz (%{_dk_oran}) disk doluluk kritiği (%90+). "
                        "Sistem yavaşlaması ve log kaybı riski." if _dk>0 else
                        "Tüm cihazlarda yeterli disk alanı var.")
            st.markdown(f"""<div style="border-left:3px solid {_dk_clr};background:rgba(0,0,0,.2);
border-radius:6px;padding:8px 10px;font-size:11px">
  <span style="color:{_dk_clr};font-weight:700">{_dk_icon} Disk Durumu</span>
  <div style="color:#C9D1D9;margin-top:3px">{_dk_msg}</div>
  <div style="color:{_dk_clr};font-size:10px;margin-top:4px">
    {'⚡ Acil: Disk temizleme scripti çalıştır.' if _dk_oran>=10 else
     '⚡ İzle: Kritik cihazdaki dosyaları temizle.' if _dk>0 else '✅ İzleme yeterli.'}</div>
</div>""", unsafe_allow_html=True)

    with _sag_c2:
        sec("Windows Update Servisi", color="#A5D6FF")
        if "_RawUpdateStop" in df.columns:
            _wu_on  = int((df["_RawUpdateStop"]==0).sum())
            _wu_off = int(df["_RawUpdateStop"].gt(0).sum())
            _fig_wu = go.Figure(go.Pie(
                labels=["WU Aktif","WU Kapalı"],
                values=[_wu_on, _wu_off], hole=0.48,
                marker=dict(colors=["#3FB950","#F85149"],
                            line=dict(color="#0D1117",width=2)),
                textinfo="label+value+percent",
                textfont=dict(color="#E6EDF3",size=10),
                hovertemplate="<b>%{label}</b><br>%{value} cihaz · %{percent}<extra></extra>",
            ))
            _fig_wu.add_annotation(text=f"<b>{_wu_off}</b><br>kapalı",
                                   x=0.5,y=0.5,showarrow=False,
                                   font=dict(size=12,color="#F85149" if _wu_off>0 else "#3FB950"))
            _fig_wu.update_layout(**DARK, height=240, showlegend=False)
            st.plotly_chart(_fig_wu, use_container_width=True)
            _wu_oran = round(_wu_off/max(n,1)*100,1)
            _wu_clr  = "#F85149" if _wu_oran>=20 else "#D29922" if _wu_oran>=5 else "#3FB950"
            _wu_icon = "🔴" if _wu_oran>=20 else "🟡" if _wu_oran>=5 else "🟢"
            st.markdown(f"""<div style="border-left:3px solid {_wu_clr};background:rgba(0,0,0,.2);
border-radius:6px;padding:8px 10px;font-size:11px">
  <span style="color:{_wu_clr};font-weight:700">{_wu_icon} WU Durumu</span>
  <div style="color:#C9D1D9;margin-top:3px">
    <b>{_wu_off}</b> cihaz (%{_wu_oran}) Windows Update servisi kapalı.</div>
  <div style="color:{_wu_clr};font-size:10px;margin-top:4px">
    {'⚡ GPO ile Windows Update politikasını zorla.' if _wu_off>0 else '✅ Tüm cihazlar WU aktif.'}</div>
</div>""", unsafe_allow_html=True)

    with _sag_c3:
        sec("Admin Hesabı Dağılımı", color="#FFA657")
        if "_RawAdminCount" in df.columns:
            _adm_zero = int((df["_RawAdminCount"]==0).sum())
            _adm_one  = int((df["_RawAdminCount"]==1).sum())
            _adm_multi= int((df["_RawAdminCount"]>1).sum())
            _fig_adm = go.Figure(go.Pie(
                labels=["Normal (0)","1 Ekstra","2+ Ekstra"],
                values=[_adm_zero, _adm_one, _adm_multi], hole=0.48,
                marker=dict(colors=["#3FB950","#D29922","#F85149"],
                            line=dict(color="#0D1117",width=2)),
                textinfo="label+value+percent",
                textfont=dict(color="#E6EDF3",size=10),
                hovertemplate="<b>%{label}</b><br>%{value} cihaz · %{percent}<extra></extra>",
            ))
            _fig_adm.update_layout(**DARK, height=240, showlegend=False)
            st.plotly_chart(_fig_adm, use_container_width=True)
            _adm_oran = round((_adm_one+_adm_multi)/max(n,1)*100,1)
            _adm_clr  = "#F85149" if _adm_oran>=15 else "#D29922" if _adm_oran>=5 else "#3FB950"
            _adm_icon = "🔴" if _adm_oran>=15 else "🟡" if _adm_oran>=5 else "🟢"
            st.markdown(f"""<div style="border-left:3px solid {_adm_clr};background:rgba(0,0,0,.2);
border-radius:6px;padding:8px 10px;font-size:11px">
  <span style="color:{_adm_clr};font-weight:700">{_adm_icon} Admin Durumu</span>
  <div style="color:#C9D1D9;margin-top:3px">
    <b>{_adm_one+_adm_multi}</b> cihaz (%{_adm_oran}) yetkisiz admin içeriyor.</div>
  <div style="color:{_adm_clr};font-size:10px;margin-top:4px">
    {'⚡ Acil: AD grubunu temizle, log al, yöneticiye bildir.' if _adm_oran>=15 else
     '⚡ Bu hafta AD grup üyeliklerini gözden geçir.' if (_adm_one+_adm_multi)>0 else
     '✅ Admin hesapları standart.'}</div>
</div>""", unsafe_allow_html=True)

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
    # Yeni profesyonel filtreler
    if "ip_f" in dir() and ip_f and "IPAddress" in filtered.columns:
        filtered = filtered[filtered["IPAddress"].astype(str).apply(
            lambda ip: any(ip.startswith(p+".") for p in ip_f)
        )]
    if "os_f" in dir() and os_f and "Sistem" in filtered.columns:
        filtered = filtered[filtered["Sistem"].isin(os_f)]
    if "usr_q" in dir() and usr_q and "Kullanıcı" in filtered.columns:
        filtered = filtered[filtered["Kullanıcı"].astype(str).str.contains(usr_q,case=False,na=False)]
    if "min_risk" in dir() and min_risk > 0 and "Final_Risk_Skoru" in filtered.columns:
        filtered = filtered[filtered["Final_Risk_Skoru"] >= min_risk]
    nf = len(filtered)
    st.caption(f"**{nf}** / {n} cihaz — {nf} sonuç")

    tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs([
        "📊 Cihaz Listesi",
        "🚨 Tehdit Analizi",
        "🩹 Patch Uyumu",
        "🦠 CVE Risk",
        "🔑 Admin & Kimlik",
        "🌐 Ağ & Güvenlik",
        "📂 Dosya Paylaşımı",
    ])

    with tab1:
        sec("Cihaz Risk Tablosu")
        st.caption("Lansweeper sütununa tıklayarak cihazı Lansweeper'da açabilirsiniz")
        cols=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem","Cihaz_Tipi",
                           "Risk Skoru","Final_Risk_Skoru","CVE_Bonus","Seviye","Risk Analizi"]
              if c in filtered.columns]
        show_table(filtered[cols].sort_values("Final_Risk_Skoru",ascending=False),
                   height=520,text_cols=["Risk Analizi","Sistem"])
        csv=filtered[cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ CSV İndir",csv,f"risk_{datetime.now().strftime('%Y%m%d_%H%M')}.csv","text/csv")

        # AI: Cihaz listesi analizi
        _t1_nh = int((filtered["Seviye"]=="YÜKSEK").sum())
        _t1_nm = int((filtered["Seviye"]=="ORTA").sum())
        _t1_avg = round(float(filtered["Final_Risk_Skoru"].mean()),1) if nf>0 else 0
        _t1_oran = round(_t1_nh/max(nf,1)*100,1)
        _lbl,_clr,_icon = ("KRİTİK","#F85149","🔴") if _t1_oran>=30 else                           ("YÜKSEK","#D29922","🟡") if _t1_oran>=10 else ("KABUL EDİLEBİLİR","#3FB950","🟢")
        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_clr};border-left:5px solid {_clr};
border-radius:10px;padding:14px 18px;margin:10px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_clr};font-weight:700;text-transform:uppercase">🤖 AI Cihaz Listesi Analizi</div>
    <div style="background:{_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_icon} {_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    Filtrelenmiş <b>{nf}</b> cihazın <b>{_t1_nh}</b>'i (%{_t1_oran}) yüksek risk seviyesinde.
    Ortalama final risk skoru <b>{_t1_avg}</b>/100.
    {"⚠ Bu oran acil müdahale gerektiriyor — önce sunucu/DC tipi cihazları incele." if _t1_oran>=30 else
     "⚠ Yüksek riskli cihazlar önceliklendirilmeli." if _t1_oran>=10 else
     "Rutin izleme yeterli, ancak ORTA risk grubunu takipte tut."}
  </div>
  <div style="font-size:11px;color:{_clr};font-weight:600;margin-top:6px">
    ⚡ {"Acil: Yüksek riskli sunucu ve DC'lere bugün müdahale et." if _t1_oran>=30 else
       "Bu hafta yüksek riskli cihazları CVE ve patch açısından tara." if _t1_oran>=10 else
       "Aylık inceleme döngüsünü sürdür."}
  </div>
</div>""", unsafe_allow_html=True)

        # Grafikler: risk dağılımı + cihaz tipi
        _t1c1, _t1c2 = st.columns(2)
        with _t1c1:
            sec("Risk Skoru — Seviye Dağılımı")
            hov={c:True for c in ["AssetName","Kullanıcı","Cihaz_Tipi","CVE_Bonus"] if c in filtered.columns}
            fig=px.scatter(filtered,x="Yamasız Gün",y="Final_Risk_Skoru",color="Seviye",
                           color_discrete_map=SEV_CLR,hover_data=hov,size_max=10,opacity=0.7)
            fig.add_hline(y=50,line_dash="dash",line_color="#F85149",annotation_text="Yüksek (50)")
            fig.add_vline(x=60,line_dash="dash",line_color="#D29922",annotation_text="Kritik Patch (60g)")
            fig.update_layout(**DARK,height=300,legend=dict(font=dict(color="#C9D1D9")))
            st.plotly_chart(fig, use_container_width=True)
        with _t1c2:
            sec("Cihaz Tipine Göre Ortalama Risk")
            if "Cihaz_Tipi" in filtered.columns:
                _ct = filtered.groupby("Cihaz_Tipi")["Final_Risk_Skoru"].agg(["mean","count"]).reset_index()
                _ct.columns=["Tip","Ort","Sayi"]
                _ct["Renk"]=[CRIT_CLR.get(t,"#8B949E") for t in _ct["Tip"]]
                _ct = _ct.sort_values("Ort",ascending=False)
                _fig_ct=go.Figure(go.Bar(
                    x=_ct["Tip"],y=_ct["Ort"].round(1),
                    marker_color=_ct["Renk"],
                    text=[f"{v:.0f} ({c})" for v,c in zip(_ct["Ort"],_ct["Sayi"])],
                    textposition="outside",textfont=dict(color="#C9D1D9"),
                    hovertemplate="<b>%{x}</b><br>Ort: %{y:.1f}<extra></extra>",
                ))
                _fig_ct.add_hline(y=50,line_dash="dash",line_color="#F85149")
                _fig_ct.update_layout(**DARK,height=300,showlegend=False)
                st.plotly_chart(_fig_ct, use_container_width=True)

    with tab2:
        sec("Tehdit Analizi — Kapsamlı Görünüm")
        # Genişletilmiş tehdit kütüphanesi: kw, kategori, renk, acıklama, öneri
        threat_detail={
            "Onaysız Yönetici Yetkisi": ("Erişim Kontrolü","#F85149",
                "Yetkisiz admin grubu: lateral movement, veri ihlali ve kalıcı erişim riski.",
                "AD'den kaldır, PAM çözümü değerlendir, JIT access uygula."),
            "DLP Yüklü Değil": ("Veri Koruma","#FF7B72",
                "DLP olmadan hassas veri USB/e-posta/bulut ile dışarı sızdırılabilir.",
                "Endpoint DLP deployment planını bu hafta başlat, EDPA politikasını zorla."),
            "Antivirüs (SEP) Eksik": ("Endpoint","#F85149",
                "SEP/AV olmayan cihazlar ransomware, trojan ve 0-day için açık hedeftir.",
                "SCCM/GPO deployment başlat, SEP sunucusu kapsamına al."),
            "Güvenlik Yamaları Eksik": ("Patch","#D29922",
                "Yamasız sistemler bilinen CVE'lerle hızla istismar edilir, CVSS 9+ yamalar 48h içinde uygulanmalı.",
                "WSUS/SCCM'den zorla güncelleme, 180+ gün cihazları manuel müdahaleyle güncelle."),
            "Şüpheli Yazılım Tespit Edildi": ("Shadow IT","#D29922",
                "Kontrolsüz yazılımlar veri kaçağı, C2 kanal kurulumu ve lisans riski oluşturur.",
                "GPO application whitelist, unauthorized software kaldırma scripti çalıştır."),
            "Desteklenmeyen OS (EoL)": ("Platform","#F85149",
                "EoL OS için güvenlik yaması çıkmıyor — sıfır-gün açıkları kalıcı olarak yamalanamaz.",
                "Upgrade takvimi hazırla, EoL cihazları izole ağa al veya ek kontrol uygula."),
            "Update Servisi Kapalı": ("Patch","#D29922",
                "Windows Update servisi kapalı — kritik güvenlik yamaları cihaza ulaşmıyor.",
                "GPO ile WU politikasını zorla, servis başlatma kısıtlamalarını kaldır."),
            "Riskli Paylaşım": ("Ağ","#FF9F43",
                "Açık SMB paylaşımları (Everyone/Domain Users) ransomware lateral movement vektörü.",
                "Paylaşım izinlerini denetle, Everyone erişimini kaldır, NTFS izinleri uygula."),
            "Uzun Süredir Offline": ("Cihaz","#79C0FF",
                "60+ gün offline cihazlar tüm yamalardan mahrum — ağa döndüklerinde tehdit oluşturur.",
                "Envanterden çıkar veya ağa bağlanmadan önce zorunlu patch uygula."),
            "Sabit Şifreli Admin": ("Kimlik","#FF7B72",
                "PasswordNeverExpires flag'li hesaplar credential harvesting ve brute-force hedefidir.",
                "Fine-grained password policy uygula, MFA'yı etkinleştir, şifre süresini sınırla."),
            "Disk Kritik": ("Depolama","#E07B54",
                "Disk %90+ dolu sistemlerde log kaybı, servis çökmesi ve saldırı tespiti zorlaşır.",
                "Temp/log temizleme scripti çalıştır, storage monitoring alarma al."),
            "Firewall": ("Ağ","#F85149",
                "Windows Firewall kapalı sistemler network tabanlı atağa doğrudan açık.",
                "GPO ile domain firewall profilini zorla, exception listesini gözden geçir."),
            "Riskli Paylaşılan Klasör": ("Ağ","#FF9F43",
                "Herkese açık yazma/tam yetki paylaşımlar veri sızıntısı ve şifreli dosya saldırısı riski.",
                "Paylaşım erişimini principle of least privilege ile yeniden yapılandır."),
        }
        ra=filtered.get("Risk Analizi",pd.Series("",index=filtered.index)).astype(str)

        # _Raw sütunlarından da sayılar ekle
        _t2_rows=[]
        for kw,(cat,clr,desc,action) in threat_detail.items():
            cnt=int(ra.str.contains(kw,na=False,regex=False).sum())
            if cnt>0:
                _t2_rows.append({"Tehdit":kw,"Kategori":cat,"Etkilenen":cnt,
                                 "Oran":f"%{cnt/max(nf,1)*100:.1f}",
                                 "Risk Açıklaması":desc,"Öneri":action,"Renk":clr})

        # _Raw ek kaynaklar (Risk Analizi metninde olmayabilir)
        _raw_extra = []
        if "_RawDiskError"  in filtered.columns:
            _rde = int(filtered["_RawDiskError"].gt(0).sum())
            if _rde>0:
                _raw_extra.append({"Tehdit":"Disk Hatası (Raw)","Kategori":"Depolama","Etkilenen":_rde,
                    "Oran":f"%{_rde/max(nf,1)*100:.1f}","Renk":"#E07B54",
                    "Risk Açıklaması":"Disk I/O hatası tespit edilmiş cihazlar — donanım arızası riski.",
                    "Öneri":"S.M.A.R.T. testi yaptır, disk değişimi planla."})
        if "_RawAdminCount" in filtered.columns:
            _rda = int(filtered["_RawAdminCount"].gt(0).sum())
            if _rda>0 and not any(r["Tehdit"]=="Onaysız Yönetici Yetkisi" for r in _t2_rows):
                _raw_extra.append({"Tehdit":"Admin Fazlalığı (Raw)","Kategori":"Erişim Kontrolü","Etkilenen":_rda,
                    "Oran":f"%{_rda/max(nf,1)*100:.1f}","Renk":"#FFA657",
                    "Risk Açıklaması":"Standart dışı admin grubu üyeliği tespit edildi.",
                    "Öneri":"AD group membership audit yap, JIT access değerlendir."})
        if "_RawUpdateStop" in filtered.columns:
            _rwu = int(filtered["_RawUpdateStop"].gt(0).sum())
            if _rwu>0 and not any(r["Tehdit"]=="Update Servisi Kapalı" for r in _t2_rows):
                _raw_extra.append({"Tehdit":"WU Durdurulmuş (Raw)","Kategori":"Patch","Etkilenen":_rwu,
                    "Oran":f"%{_rwu/max(nf,1)*100:.1f}","Renk":"#A5D6FF",
                    "Risk Açıklaması":"Windows Update servisi manuel durdurulmuş.",
                    "Öneri":"GPO ile WU servisini zorla, startup type=Automatic yap."})
        if "Riskli Paylaşılan Klasörler" in filtered.columns:
            _rsh = int(filtered["Riskli Paylaşılan Klasörler"].ne("").sum())
            if _rsh>0 and not any("Riskli Paylaş" in r["Tehdit"] for r in _t2_rows):
                _raw_extra.append({"Tehdit":"Riskli Dosya Paylaşımı","Kategori":"Ağ","Etkilenen":_rsh,
                    "Oran":f"%{_rsh/max(nf,1)*100:.1f}","Renk":"#FF9F43",
                    "Risk Açıklaması":"Herkese açık SMB paylaşımı tespit edildi.",
                    "Öneri":"Erişim izinlerini denetle, Everyone grubunu kaldır."})

        _t2_rows.extend(_raw_extra)
        _t2_rows = sorted(_t2_rows, key=lambda x:-x["Etkilenen"])

        if _t2_rows:
            th_df=pd.DataFrame(_t2_rows).sort_values("Etkilenen",ascending=False)

            # AI Tehdit Analizi yorumu
            _top3 = ", ".join([f"{r['Tehdit']} ({r['Etkilenen']})" for r in _t2_rows[:3]])
            _total_threats = len(_t2_rows)
            _max_cnt = _t2_rows[0]["Etkilenen"] if _t2_rows else 0
            _max_pct = round(_max_cnt/max(nf,1)*100,1)
            _t2_lbl,_t2_clr,_t2_icon = ("KRİTİK","#F85149","🔴") if _total_threats>=8 or _max_pct>=50 else                                         ("YÜKSEK","#D29922","🟡") if _total_threats>=4 or _max_pct>=20 else                                         ("ORTA","#FFA657","🟠")
            st.markdown(f"""<div style="background:#0D1117;border:1px solid {_t2_clr};border-left:5px solid {_t2_clr};
border-radius:10px;padding:14px 18px;margin:10px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_t2_clr};font-weight:700;text-transform:uppercase">🤖 AI Tehdit Analizi</div>
    <div style="background:{_t2_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_t2_icon} {_t2_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{_total_threats}</b> aktif tehdit vektörü tespit edildi. En yaygın tehditler: <b>{_top3}</b>.
    En fazla etkilenen tehdit cihazların <b>%{_max_pct}</b>ini etkiliyor.
    {"Kritik eşik aşıldı — çok yönlü saldırı yüzeyi söz konusu." if _t2_lbl=="KRİTİK" else
     "Öncelikli tehditlere odaklanarak risk azaltma planı başlatılmalı." if _t2_lbl=="YÜKSEK" else
     "Mevcut tehditler kontrol altında tutulmalı."}
  </div>
  <div style="font-size:11px;color:{_t2_clr};font-weight:600;margin-top:6px">
    ⚡ {"Kırmızı renkli tehditleri bugün, sarıları bu hafta ele al." if _t2_lbl in ("KRİTİK","YÜKSEK") else
       "Haftalık inceleme döngüsünü sürdür."}
  </div>
</div>""", unsafe_allow_html=True)

            # Grafik + Tablo
            _t2ca, _t2cb = st.columns([3, 2])
            with _t2ca:
                sec("Tehdit Vektörü Karşılaştırması")
                _fig_t=go.Figure()
                for _,r in th_df.sort_values("Etkilenen").iterrows():
                    _fig_t.add_trace(go.Bar(
                        x=[r["Etkilenen"]], y=[r["Tehdit"]], orientation="h",
                        marker_color=r["Renk"], showlegend=False,
                        text=[f"{r['Etkilenen']}  {r['Oran']}"],
                        textposition="outside", textfont=dict(color="#C9D1D9",size=10),
                        hovertemplate=f"<b>{r['Tehdit']}</b><br>{r['Etkilenen']} cihaz ({r['Oran']})<br>{r['Risk Açıklaması']}<extra></extra>",
                    ))
                _fig_t.update_layout(**DARK, height=max(360,len(_t2_rows)*36),
                                     showlegend=False, barmode="overlay",
                                     xaxis=dict(range=[0, th_df["Etkilenen"].max()*1.40]))
                st.plotly_chart(_fig_t, use_container_width=True)

            with _t2cb:
                sec("Özet Tablo")
                _tbl_show = th_df[["Tehdit","Kategori","Etkilenen","Oran"]].copy()
                st.dataframe(_tbl_show, use_container_width=True, hide_index=True,
                             height=min(600,len(_t2_rows)*42+50),
                             column_config={
                                 "Etkilenen": st.column_config.ProgressColumn(
                                     "Etkilenen", min_value=0, max_value=max(th_df["Etkilenen"]),
                                     format="%d",
                                 ),
                             })
                # Kategori pasta
                _cat_cnt = th_df.groupby("Kategori")["Etkilenen"].sum().reset_index()
                _fig_cat = go.Figure(go.Pie(
                    labels=_cat_cnt["Kategori"], values=_cat_cnt["Etkilenen"], hole=0.42,
                    textinfo="label+percent",
                    textfont=dict(color="#E6EDF3",size=10),
                    marker=dict(colors=["#F85149","#D29922","#FF9F43","#58A6FF","#3FB950","#D2A8FF","#E07B54"],
                                line=dict(color="#0D1117",width=2)),
                ))
                _fig_cat.update_layout(**DARK_M, height=260, showlegend=False,
                                       margin=dict(l=0,r=0,t=10,b=0))
                st.plotly_chart(_fig_cat, use_container_width=True)

            # Tehdit Açıklamaları — genişletilmiş
            sec("Tehdit Açıklamaları ve Etkilenen Cihazlar")
            for _, r in th_df.iterrows():
                _exp_clr = r["Renk"]
                with st.expander(f"{r['Tehdit']} — {r['Etkilenen']} cihaz {r['Oran']}"):
                    _ec1, _ec2 = st.columns([1,2])
                    with _ec1:
                        # D) Smart Action Engine
                        _smart_map = {
                            "Antivirüs":      ("🛡️ SEP Kur","GPO/SCCM ile SEP paketi push. 48 saat içinde tüm cihazlara."),
                            "DLP":            ("🔒 DLP Deploy","EDPA paketini SCCM üzerinden push et. USB politikasını GPO ile zorla."),
                            "Onaysız Yönetici":("👤 AD Temizle","Bu hafta kural dışı hesapları AD'den kaldır. PAM değerlendirmesi başlat."),
                            "Güvenlik Yamaları":("🩹 Patch Op","WSUS'ta zorunlu update policy. 72 saat deadline."),
                            "Riskli Paylaşım":("📁 SMB İzin","Everyone/Domain Users yazma iznini kaldır. NTFS izinleri uygula."),
                            "Desteklenmeyen": ("💀 Upgrade","Win 10/11 upgrade projesi. Geçici VLAN izolasyonu."),
                            "Şüpheli":        ("🦠 GPO Engelle","AppLocker/GPO'ya yasak yazılım listesi ekle."),
                            "Disk":           ("💾 Temizle","Temp/log temizleme scripti çalıştır. Storage monitoring kur."),
                            "Update Servis":  ("🔄 WU Fix","GPO ile wuauserv auto-start zorla."),
                            "RDP":            ("🖥 RDP Kapat","GPO ile workstation RDP'yi devre dışı bırak."),
                        }
                        for _kw,(_stitle,_sdesc) in _smart_map.items():
                            if _kw.lower() in r["Tehdit"].lower():
                                st.markdown(f"""<div style="background:#0D1117;border:1px solid #3FB950;
border-left:4px solid #3FB950;border-radius:6px;padding:7px 10px;margin-bottom:6px">
  <div style="font-size:9px;color:#3FB950;font-weight:700">⚡ SMART AKSİYON</div>
  <div style="font-size:11px;color:#E6EDF3;font-weight:600">{_stitle}</div>
  <div style="font-size:10px;color:#8B949E">{_sdesc}</div>
</div>""", unsafe_allow_html=True)
                                break
                        st.markdown(f"""<div style="background:#161B22;border-left:3px solid {_exp_clr};
border-radius:6px;padding:10px 12px;margin:4px 0">
  <div style="font-size:9px;color:{_exp_clr};text-transform:uppercase;font-weight:700">Kategori</div>
  <div style="color:#E6EDF3;font-weight:700">{r['Kategori']}</div>
</div>
<div style="background:#161B22;border-left:3px solid {_exp_clr};border-radius:6px;padding:10px 12px;margin:4px 0">
  <div style="font-size:9px;color:{_exp_clr};text-transform:uppercase;font-weight:700">Risk Açıklaması</div>
  <div style="color:#C9D1D9;font-size:12px">{r['Risk Açıklaması']}</div>
</div>
<div style="background:#161B22;border-left:3px solid #3FB950;border-radius:6px;padding:10px 12px;margin:4px 0">
  <div style="font-size:9px;color:#3FB950;text-transform:uppercase;font-weight:700">⚡ Öneri</div>
  <div style="color:#C9D1D9;font-size:12px">{r['Öneri']}</div>
</div>""", unsafe_allow_html=True)
                    with _ec2:
                        affected=filtered[ra.str.contains(r["Tehdit"],na=False,regex=False)]
                        if len(affected)==0 and r["Tehdit"].endswith("(Raw)"):
                            # Raw kaynaklı tehdit — sütun bazlı filtre
                            if "Disk" in r["Tehdit"] and "_RawDiskError" in filtered.columns:
                                affected=filtered[filtered["_RawDiskError"].gt(0)]
                            elif "Admin" in r["Tehdit"] and "_RawAdminCount" in filtered.columns:
                                affected=filtered[filtered["_RawAdminCount"].gt(0)]
                            elif "WU" in r["Tehdit"] and "_RawUpdateStop" in filtered.columns:
                                affected=filtered[filtered["_RawUpdateStop"].gt(0)]
                        elif len(affected)==0 and "Riskli Dosya" in r["Tehdit"]:
                            if "Riskli Paylaşılan Klasörler" in filtered.columns:
                                affected=filtered[filtered["Riskli Paylaşılan Klasörler"].ne("")]
                        cols_a=[c for c in ["Lansweeper","AssetName","Kullanıcı","Cihaz_Tipi",
                                             "Final_Risk_Skoru","Seviye","Risk Analizi"]
                                if c in affected.columns]
                        if len(affected)>0:
                            show_table(affected[cols_a].sort_values("Final_Risk_Skoru",ascending=False),
                                      height=220,text_cols=["Risk Analizi"])
                        else:
                            st.info("Etkilenen cihaz tablosu için Risk Analizi sütununu kontrol edin.")
        else:
            st.success("✅ Aktif tehdit vektörü tespit edilmedi")

    with tab3:
        _t3_pc  = int((filtered["Yamasız Gün"]>60).sum())  if "Yamasız Gün" in filtered.columns else 0
        _t3_180 = int((filtered["Yamasız Gün"]>180).sum()) if "Yamasız Gün" in filtered.columns else 0
        _t3_oc  = int((filtered["Offline Gün"]>60).sum())  if "Offline Gün" in filtered.columns else 0
        _t3_oran= round(_t3_pc/max(nf,1)*100,1)
        _t3_ort = round(float(filtered["Yamasız Gün"].mean()),1) if "Yamasız Gün" in filtered.columns and nf>0 else 0
        _t3_lbl,_t3_clr,_t3_icon = ("KRİTİK","#F85149","🔴") if _t3_oran>=70 else                                     ("YÜKSEK","#D29922","🟡") if _t3_oran>=30 else ("KABUL EDİLEBİLİR","#3FB950","🟢")
        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_t3_clr};border-left:5px solid {_t3_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_t3_clr};font-weight:700;text-transform:uppercase">🤖 AI Patch ve Offline Analizi</div>
    <div style="background:{_t3_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_t3_icon} {_t3_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    Filtrelenmiş <b>{nf}</b> cihazin <b>{_t3_pc}</b>i (%{_t3_oran}) 60+ gun yamasiz. Ort. yamasiz sure <b>{_t3_ort}</b> gun.
    <b>{_t3_180}</b> cihaz 180+ gunu asti — WSUS baglantisi kopmus olabilir. Offline tarafta <b>{_t3_oc}</b> cihaz 60+ gundur gorunmuyor.
  </div>
  <div style="font-size:11px;color:{_t3_clr};font-weight:600;margin-top:6px">
    ⚡ {"WSUS sagligini kontrol et, 180+ gun cihazlara manuel mudahale, offline cihaZlari envanterden cikar." if _t3_lbl=="KRİTİK" else
       "Bu hafta patch operasyonu baslat, offline cihazlarin lokasyonunu belirle." if _t3_lbl=="YÜKSEK" else
       "Rutin patch dongusu yeterli, offline cihazlar takipte tutulsun."}
  </div>
</div>""", unsafe_allow_html=True)
        ca,cb=st.columns(2)
        with ca:
            sec("Yamasiz Gun Dagilimi")
            if "Yamasız Gün" in filtered.columns:
                fig6=px.histogram(filtered,x="Yamasız Gün",nbins=25,color_discrete_sequence=["#58A6FF"])
                fig6.add_vline(x=60, line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
                fig6.add_vline(x=180,line_dash="dot", line_color="#FF7B72",annotation_text="180g")
                fig6.add_vline(x=365,line_dash="dot", line_color="#8B1A1A", annotation_text="1 Yil")
                fig6.update_layout(**DARK,height=260)
                st.plotly_chart(fig6, use_container_width=True)
        with cb:
            sec("Offline Gun Dagilimi")
            if "Offline Gün" in filtered.columns:
                fig7=px.histogram(filtered,x="Offline Gün",nbins=25,color_discrete_sequence=["#D29922"])
                fig7.add_vline(x=60, line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
                fig7.add_vline(x=180,line_dash="dot", line_color="#FF7B72",annotation_text="180g")
                fig7.update_layout(**DARK,height=260)
                st.plotly_chart(fig7, use_container_width=True)
        sec("Patch Durumu — Risk Seviyesine Gore")
        if "Yamasız Gün" in filtered.columns:
            _pg=filtered.groupby("Seviye")["Yamasız Gün"].agg(["mean","median","max"]).reset_index()
            _pg.columns=["Seviye","Ort","Medyan","Maks"]
            _pg=_pg[_pg["Seviye"].isin(["YÜKSEK","ORTA","DÜŞÜK"])]
            _pca,_pcb=st.columns(2)
            with _pca:
                _fp=go.Figure()
                for m,lbl in [("Ort","Ort. Gun"),("Medyan","Medyan"),("Maks","Maks")]:
                    _fp.add_trace(go.Bar(name=lbl,x=_pg["Seviye"],y=_pg[m],
                                         text=_pg[m].round(0).astype(int),
                                         textposition="outside",textfont=dict(color="#C9D1D9")))
                _fp.add_hline(y=60,line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
                _fp.update_layout(**DARK,height=280,barmode="group",legend=dict(font=dict(color="#C9D1D9")))
                st.plotly_chart(_fp, use_container_width=True)
            with _pcb:
                _hov2={c:True for c in ["AssetName","Kullanıcı","Cihaz_Tipi"] if c in filtered.columns}
                _fsc=px.scatter(filtered,x="Yamasız Gün",y="Final_Risk_Skoru",
                                color="Seviye",color_discrete_map=SEV_CLR,opacity=0.6,hover_data=_hov2)
                _fsc.add_hline(y=50,line_dash="dash",line_color="#F85149")
                _fsc.add_vline(x=60,line_dash="dash",line_color="#D29922")
                _fsc.update_layout(**DARK,height=280,legend=dict(font=dict(color="#C9D1D9")))
                st.plotly_chart(_fsc, use_container_width=True)
        sec("Kritik Patch Listesi (60g+)")
        p_df=filtered[filtered["Yamasız Gün"]>60].sort_values("Yamasız Gün",ascending=False)              if "Yamasız Gün" in filtered.columns else filtered.head(0)
        cols_p=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem",
                             "Cihaz_Tipi","Yamasız Gün","Offline Gün","Final_Risk_Skoru","Seviye"]
                if c in p_df.columns]
        show_table(p_df[cols_p],height=380)
        if len(p_df)>0:
            _csv3=p_df[cols_p].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ Kritik Patch CSV",_csv3,f"patch_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")

    with tab4:
        sec("🦠 CVE Risk Analizi")
        st.caption("📌 CVE (Common Vulnerabilities & Exposures): Yazılımlardaki bilinen güvenlik açıkları. CVE_Bonus: Bu cihazda CVE içeren yazılım bulunması nedeniyle Final Risk Skoruna eklenen puan.")
        cve_risk = filtered[filtered["CVE_Bonus"]>0].sort_values("CVE_Bonus",ascending=False)                    if "CVE_Bonus" in filtered.columns else filtered.head(0)
        _t4_n    = len(cve_risk)
        _t4_oran = round(_t4_n/max(nf,1)*100,1)
        _t4_max  = int(cve_risk["CVE_Bonus"].max())   if _t4_n>0 else 0
        _t4_avg  = round(cve_risk["CVE_Bonus"].mean(),1) if _t4_n>0 else 0

        if _t4_n > 0:
            _t4_lbl,_t4_clr,_t4_icon = ("KRİTİK","#F85149","🔴") if _t4_oran>=30 else                                         ("YÜKSEK","#D29922","🟡") if _t4_oran>=10 else ("ORTA","#FFA657","🟠")

            # AI yorum
            st.markdown(f"""<div style="background:#0D1117;border:1px solid {_t4_clr};border-left:5px solid {_t4_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_t4_clr};font-weight:700;text-transform:uppercase">🤖 AI CVE Risk Analizi</div>
    <div style="background:{_t4_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_t4_icon} {_t4_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{_t4_n}</b> cihaz (%{_t4_oran}) CVE içeren yazılım barındırıyor.
    Max CVE bonus: <b>+{_t4_max}</b> · Ort. bonus: <b>+{_t4_avg}</b>.
    {"CVE yüzdesi kritik — etkilenen cihazlarda incident response başlat." if _t4_oran>=30 else
     "Yüksek CVE bonuslu cihazlarda bu hafta yazılım güncellemesi yapılmalı." if _t4_oran>=10 else
     "CVE etkilenimi sınırlı, rutin yazılım güncellemesi yeterli."}
  </div>
  <div style="font-size:11px;color:{_t4_clr};font-weight:600;margin-top:6px">
    ⚡ {"CVE'li yazılımları barındıran cihazlarda acil güncelleme/kaldırma." if _t4_n>0 else "CVE izlemesi aktif."}
  </div>
</div>""", unsafe_allow_html=True)

            # KPI rozetleri
            _k4c1,_k4c2,_k4c3,_k4c4 = st.columns(4)
            _k4c1.metric("🦠 CVE Etkili",   _t4_n,    f"%{_t4_oran}")
            _k4c2.metric("🎯 Max Bonus",     f"+{_t4_max}")
            _k4c3.metric("📊 Ort. Bonus",    f"+{_t4_avg}")
            _k4c4.metric("🖥️ Toplam Cihaz",  nf)

            # Grafik 1: Top 15 CVE'li cihaz (horizontal bar — anlamlı)
            _cv_c1, _cv_c2 = st.columns([3, 2])
            with _cv_c1:
                sec("En Yüksek CVE Bonuslu Cihazlar — İlk 15")
                st.caption("📌 Bu grafik CVE içeren yazılım bulunan cihazları bonus puanına göre sıralar. Kırmızı çubuk = yüksek riskli.")
                _top15 = cve_risk.head(15)[["AssetName","CVE_Bonus","Cihaz_Tipi","Final_Risk_Skoru","Seviye"]].copy()                          if "Cihaz_Tipi" in cve_risk.columns else cve_risk.head(15)[["AssetName","CVE_Bonus","Final_Risk_Skoru","Seviye"]].copy()
                _cv_clrs = ["#8B1A1A" if v>=20 else "#F85149" if v>=12 else "#D29922" for v in _top15["CVE_Bonus"]]
                _fig_cv = go.Figure(go.Bar(
                    y=_top15["AssetName"], x=_top15["CVE_Bonus"],
                    orientation="h", marker_color=_cv_clrs,
                    text=[f"+{v}" for v in _top15["CVE_Bonus"]],
                    textposition="outside", textfont=dict(color="#C9D1D9",size=10),
                    hovertemplate="<b>%{y}</b><br>CVE Bonus: +%{x}<br>Final Risk: %{customdata}<extra></extra>",
                    customdata=_top15["Final_Risk_Skoru"],
                ))
                _fig_cv.add_vline(x=20, line_dash="dash", line_color="#F85149",
                                  annotation_text="Kritik (+20)", annotation_font=dict(color="#F85149",size=9))
                _fig_cv.add_vline(x=12, line_dash="dot",  line_color="#D29922",
                                  annotation_text="Yüksek (+12)", annotation_font=dict(color="#D29922",size=9))
                _fig_cv.update_layout(**DARK, height=400, showlegend=False,
                                      xaxis_title="CVE Bonus Puanı")
                st.plotly_chart(_fig_cv, use_container_width=True)

            with _cv_c2:
                sec("CVE Bonus Dağılımı — Aralıklara Göre")
                st.caption("📌 +20 puan = Kritik CVE (CVSS≥9). +12 puan = Yüksek CVE (CVSS≥7). Her çubuk o puan aralığındaki cihaz sayısı.")
                _cvb_counts = cve_risk["CVE_Bonus"].value_counts().reset_index()
                _cvb_counts.columns = ["Bonus","Cihaz"]
                _cvb_counts = _cvb_counts.sort_values("Bonus", ascending=False)
                _cvb_clrs = ["#8B1A1A" if b>=20 else "#F85149" if b>=15 else "#D29922" for b in _cvb_counts["Bonus"]]
                _fig_cvb = go.Figure(go.Bar(
                    x=[f"+{b}" for b in _cvb_counts["Bonus"]], y=_cvb_counts["Cihaz"],
                    marker_color=_cvb_clrs,
                    text=_cvb_counts["Cihaz"], textposition="outside",
                    textfont=dict(color="#C9D1D9"),
                    hovertemplate="<b>CVE Bonus %{x}</b><br>%{y} cihaz<extra></extra>",
                ))
                _fig_cvb.update_layout(**DARK, height=240, showlegend=False,
                                       xaxis_title="CVE Bonus Puanı", yaxis_title="Cihaz Sayısı")
                st.plotly_chart(_fig_cvb, use_container_width=True)

                # Cihaz tipine göre dağılım (kısa tablo değil, pasta)
                if "Cihaz_Tipi" in cve_risk.columns:
                    _cve_ct = cve_risk["Cihaz_Tipi"].value_counts().reset_index()
                    _cve_ct.columns = ["Tip","Sayi"]
                    _fig_cve_pie = go.Figure(go.Pie(
                        labels=_cve_ct["Tip"], values=_cve_ct["Sayi"], hole=0.4,
                        textinfo="label+value",
                        textfont=dict(color="#E6EDF3",size=10),
                        marker=dict(colors=[CRIT_CLR.get(t,"#8B949E") for t in _cve_ct["Tip"]],
                                    line=dict(color="#0D1117",width=2)),
                    ))
                    _fig_cve_pie.update_layout(**DARK_M, height=200, showlegend=False,
                                               margin=dict(l=0,r=0,t=10,b=0),
                                               title=dict(text="Cihaz Tipine Göre",
                                                          font=dict(color="#8B949E",size=11)))
                    st.plotly_chart(_fig_cve_pie, use_container_width=True)

            sec(f"CVE Etkili Cihaz Listesi — {_t4_n} Cihaz")
            st.caption("📌 CVE_Bonus sütunu: Bu cihazda tespit edilen şüpheli yazılımın NIST NVD taramasından aldığı ek puan. Tespit Edilen Şüpheli Yazılımlar: Lansweeper tarafından bulunan risk yazılımları.")
            cols_cve=[c for c in ["Lansweeper","AssetName","Kullanıcı","Sistem","Cihaz_Tipi",
                                   "CVE_Bonus","Final_Risk_Skoru","Seviye","Tespit Edilen Şüpheli Yazılımlar"]
                      if c in cve_risk.columns]
            show_table(cve_risk[cols_cve],height=380,sort_col="CVE_Bonus",
                       text_cols=["Tespit Edilen Şüpheli Yazılımlar"])
            _csv4=cve_risk[cols_cve].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ CVE Listesi CSV",_csv4,f"cve_cihaz_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
        else:
            st.success("✅ Filtrelenmiş cihazlarda CVE'ye sahip yazılım tespit edilmemiştir")
            st.caption("CVE taraması için önce risk_engine_v62.py ardından cve_scanner.py çalıştırın.")

    with tab5:
        sec("🔑 Admin Yetkisi ve Kimlik Riski")
        st.caption("Yetkisiz admin grubu ve kimlik riski analizi")
        admin_risk=filtered[filtered["_RawAdminCount"].gt(0)] if "_RawAdminCount" in filtered.columns else filtered.head(0)
        _t5_n = len(admin_risk)
        _t5_oran = round(_t5_n/max(nf,1)*100,1)
        # AI
        _t5_lbl,_t5_clr,_t5_icon = ("KRİTİK","#F85149","🔴") if _t5_oran>=20 else                                     ("YÜKSEK","#D29922","🟡") if _t5_oran>=5 else ("KABUL EDİLEBİLİR","#3FB950","🟢")
        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_t5_clr};border-left:5px solid {_t5_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_t5_clr};font-weight:700;text-transform:uppercase">🤖 AI Kimlik ve Erisim Analizi</div>
    <div style="background:{_t5_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_t5_icon} {_t5_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{_t5_n}</b> cihaz (%{_t5_oran}) standart disi admin grubu uyeligi iceriyor.
    {"Bu oran lateral movement ve domain compromise riski olusturuyor — acil AD audit gerekli." if _t5_oran>=20 else
     "Yetkisiz admin hesaplari bu hafta AD'den kaldirilmali." if _t5_n>0 else
     "Tum cihazlarda standart admin yapisi mevcut."}
  </div>
  <div style="font-size:11px;color:{_t5_clr};font-weight:600;margin-top:6px">
    ⚡ {"Bugun AD group membership temizle, PAM cozumu degerlendir." if _t5_oran>=20 else
       "Bu hafta kural disi admin hesaplarini AD'den kaldir, log al." if _t5_n>0 else "Rutin izleme yeterli."}
  </div>
</div>""", unsafe_allow_html=True)
        ca3,cb3=st.columns(2)
        with ca3:
            if _t5_n>0:
                admin_counts=admin_risk["_RawAdminCount"].value_counts().head(10)
                fig_admin=px.bar(x=admin_counts.values,y=[str(v) for v in admin_counts.index],
                                orientation="h",color_discrete_sequence=["#FF7B72"],
                                labels={"x":"Cihaz Sayisi","y":"Ekstra Admin Sayisi"},
                                text=admin_counts.values)
                fig_admin.update_layout(**DARK,height=300,showlegend=False)
                fig_admin.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"))
                st.plotly_chart(fig_admin, use_container_width=True)
        with cb3:
            st.metric("👥 Yetkisiz Admin",_t5_n,f"%{_t5_oran}")
            if _t5_n>0:
                st.metric("Ort. Ekstra Admin",f"{admin_risk['_RawAdminCount'].mean():.1f}")
                st.metric("Max Ekstra Admin",int(admin_risk["_RawAdminCount"].max()))
                # Kullaniciya gore toplam
                if "Kullanıcı" in admin_risk.columns:
                    _uc2=admin_risk.groupby("Kullanıcı")["_RawAdminCount"].sum().nlargest(5).reset_index()
                    _uc2.columns=["Kullanici","Toplam Admin"]
                    st.dataframe(_uc2,use_container_width=True,hide_index=True,height=180)
        if _t5_n>0:
            sec("Yetkisiz Admin Grubu Cihazlari")
            cols_admin=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","_RawAdminCount",
                                    "Kural Dışı Adminler (İsim ve Ünvan)","Final_Risk_Skoru","Seviye"]
                        if c in admin_risk.columns]
            show_table(admin_risk[cols_admin],height=360,sort_col="_RawAdminCount",
                       text_cols=["Kural Dışı Adminler (İsim ve Ünvan)"])
            _csv5=admin_risk[cols_admin].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ Admin Listesi CSV",_csv5,f"admin_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
        else:
            st.success("✅ Tum cihazlarda standart admin sayisi var")

    with tab6:
        sec("🌐 Ag ve Guvenlik — DLP, Firewall, AV")
        risk_analysis=filtered.get("Risk Analizi",pd.Series("",index=filtered.index)).astype(str)
        dlp_missing=int(risk_analysis.str.contains("DLP",na=False,regex=False).sum())
        firewall_off=int(risk_analysis.str.contains("Firewall",na=False,regex=False).sum())
        av_missing=int(risk_analysis.str.contains("Antivirüs",na=False,regex=False).sum())
        risky_share=int(risk_analysis.str.contains("Riskli Paylaşım",na=False,regex=False).sum())
        wu_off2=int(risk_analysis.str.contains("Update Servisi Kapalı",na=False,regex=False).sum())

        # AI Ağ Güvenliği
        _t6_total = dlp_missing+firewall_off+av_missing
        _t6_lbl,_t6_clr,_t6_icon = ("KRİTİK","#F85149","🔴") if _t6_total>=int(nf*0.3) else                                     ("YÜKSEK","#D29922","🟡") if _t6_total>0 else ("İYİ","#3FB950","🟢")
        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_t6_clr};border-left:5px solid {_t6_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_t6_clr};font-weight:700;text-transform:uppercase">🤖 AI Ag Guvenlik Analizi</div>
    <div style="background:{_t6_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_t6_icon} {_t6_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    DLP eksik: <b>{dlp_missing}</b> · Firewall kapali: <b>{firewall_off}</b> · AV eksik: <b>{av_missing}</b> cihaz.
    {"Cok katmanli ag guvenligi acigi var — DLP+Firewall+AV ucunun de eksik oldugu cihazlar dogrudan saldiriya acik." if _t6_total>=int(nf*0.3) else
     "Eksikler giderilmeden bu cihazlar veri sizintisi ve network saldirisina karsi savunmasiz." if _t6_total>0 else
     "Ag guvenlik katmanlari yeterli gorunuyor."}
  </div>
  <div style="font-size:11px;color:{_t6_clr};font-weight:600;margin-top:6px">
    ⚡ {"SCCM/GPO ile DLP+AV deployment acil, Firewall policy zorla." if _t6_total>0 else "Rutin izleme yeterli."}
  </div>
</div>""", unsafe_allow_html=True)

        _t6c1,_t6c2,_t6c3,_t6c4,_t6c5 = st.columns(5)
        _t6c1.metric("📱 DLP Eksik",dlp_missing,f"%{dlp_missing/max(nf,1)*100:.1f}")
        _t6c2.metric("🔥 Firewall Kapali",firewall_off,f"%{firewall_off/max(nf,1)*100:.1f}")
        _t6c3.metric("🛡 AV Eksik",av_missing,f"%{av_missing/max(nf,1)*100:.1f}")
        _t6c4.metric("📂 Riskli Paylasim",risky_share)
        _t6c5.metric("🔄 WU Kapali",wu_off2)

        if dlp_missing+firewall_off+av_missing+risky_share+wu_off2 > 0:
            # Grafik: Ag tehditleri karsilastirmasi
            _net_data = {
                "DLP Eksik": (dlp_missing, "#FF7B72"),
                "Firewall Kapali": (firewall_off, "#F85149"),
                "AV Eksik": (av_missing, "#F85149"),
                "Riskli Paylasim": (risky_share, "#FF9F43"),
                "WU Kapali": (wu_off2, "#A5D6FF"),
            }
            _nd = [(k,v,c) for k,(v,c) in _net_data.items() if v>0]
            if _nd:
                _fig_net = go.Figure(go.Bar(
                    x=[v for _,v,_ in _nd], y=[k for k,_,_ in _nd],
                    orientation="h",
                    marker_color=[c for _,_,c in _nd],
                    text=[f"{v} cihaz" for _,v,_ in _nd],
                    textposition="outside", textfont=dict(color="#C9D1D9"),
                ))
                _fig_net.update_layout(**DARK, height=max(200,len(_nd)*50), showlegend=False,
                                        xaxis=dict(range=[0,max(v for _,v,_ in _nd)*1.4]))
                st.plotly_chart(_fig_net, use_container_width=True)

            sec("Ag Tehditleri Detayi")
            _nt_map = {
                "DLP Eksik": ("DLP olmayan cihazlar USB/e-posta ile veri sizintisina acik", "DLP"),
                "Firewall Kapali": ("Windows Firewall kapali sistemler network saldirilarına acik", "Firewall"),
                "AV Eksik": ("AV/SEP olmayan cihazlar ransomware icin hedef", "Antivirüs"),
                "Riskli Paylasim": ("Herkese acik SMB paylasimlar ransomware lateral movement vektoru", "Riskli Paylaşım"),
                "WU Kapali": ("Windows Update kapali — yamalar ulasmıyor", "Update Servisi Kapalı"),
            }
            for tname,(desc,kw) in _nt_map.items():
                cnt = int(risk_analysis.str.contains(kw,na=False,regex=False).sum())
                if cnt>0:
                    _nt_clr = "#F85149" if tname in ("Firewall Kapali","AV Eksik") else "#FF9F43" if tname=="Riskli Paylasim" else "#D29922"
                    _hex = _nt_clr.lstrip("#")
                    r2,g2,b2 = int(_hex[0:2],16),int(_hex[2:4],16),int(_hex[4:6],16)
                    with st.expander(f"{tname} — {cnt} cihaz"):
                        st.markdown(f"""<div style="background:rgba({r2},{g2},{b2},.1);border-left:4px solid {_nt_clr};
border-radius:6px;padding:10px 12px;margin:6px 0">
  <b style="color:{_nt_clr}">{tname}</b> ({cnt} cihaz)<br>
  <span style="font-size:12px;color:#C9D1D9">{desc}</span>
</div>""",unsafe_allow_html=True)
                        _af6 = filtered[risk_analysis.str.contains(kw,na=False,regex=False)]
                        _c6 = [c for c in ["Lansweeper","AssetName","Kullanıcı","Cihaz_Tipi",
                                           "Final_Risk_Skoru","Seviye"] if c in _af6.columns]
                        show_table(_af6[_c6].sort_values("Final_Risk_Skoru",ascending=False),height=200)

    with tab7:
        sec("📂 Riskli Dosya Paylasimi Analizi")
        st.caption("Herkese acik SMB/UNC paylasimlar, NTFS izin sorunlari ve lateral movement riskleri")

        # Veriyi al
        _share_col = "Riskli Paylaşılan Klasörler"
        _ra7 = filtered.get("Risk Analizi",pd.Series("",index=filtered.index)).astype(str)
        _share_df = pd.DataFrame()
        if _share_col in filtered.columns:
            _share_df = filtered[filtered[_share_col].ne("") & filtered[_share_col].notna()].copy()
        _share_ra = filtered[_ra7.str.contains("Riskli Paylaşım",na=False,regex=False)].copy()
        # Her ikisini birleştir (union)
        _share_combined = pd.concat([_share_df, _share_ra]).drop_duplicates()
        _ns = len(_share_combined)
        _ns_oran = round(_ns/max(nf,1)*100,1)

        # AI Yorum
        _t7_lbl,_t7_clr,_t7_icon = ("KRİTİK","#F85149","🔴") if _ns_oran>=20 else                                     ("YÜKSEK","#D29922","🟡") if _ns>0 else ("TEMİZ","#3FB950","🟢")
        st.markdown(f"""<div style="background:#0D1117;border:1px solid {_t7_clr};border-left:5px solid {_t7_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_t7_clr};font-weight:700;text-transform:uppercase">🤖 AI Dosya Paylasim Risk Analizi</div>
    <div style="background:{_t7_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_t7_icon} {_t7_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{_ns}</b> cihaz (%{_ns_oran}) riskli klasor paylasimi iceriyor.
    Acik SMB paylasimlar ransomware lateral movement, veri sizdirma ve yetkisiz erisim icin birincil vektordur.
    {"Kritik esik asildi — bu cihazlardan biri ele gecirilirse tum paylasimlar risk altina girer." if _ns_oran>=20 else
     "Paylasim izinleri bu hafta gozden gecirilmeli." if _ns>0 else
     "Riskli paylasim tespit edilmedi."}
  </div>
  <div style="font-size:11px;color:{_t7_clr};font-weight:600;margin-top:6px">
    ⚡ {"Acil: Everyone/Domain Users yazma yetkisini kaldir, paylasimlari audit et." if _ns_oran>=20 else
       "Bu hafta NTFS izinlerini gozden gecir, gereksiz paylasimi kapat." if _ns>0 else
       "Rutin paylasim izin denetimi surdurul."}
  </div>
</div>""", unsafe_allow_html=True)

        if _ns > 0:
            _s7c1, _s7c2 = st.columns([1,2])
            with _s7c1:
                # KPI kutuları
                st.metric("📂 Riskli Paylaşım", _ns, f"%{_ns_oran}")
                if "Cihaz_Tipi" in _share_combined.columns:
                    _sct = _share_combined["Cihaz_Tipi"].value_counts().reset_index()
                    _sct.columns = ["Tip","Sayi"]
                    _fig_sct = go.Figure(go.Pie(
                        labels=_sct["Tip"], values=_sct["Sayi"], hole=0.4,
                        textinfo="label+value",textfont=dict(color="#E6EDF3",size=10),
                        marker=dict(colors=["#FF9F43","#F85149","#D29922","#3FB950","#58A6FF"],
                                    line=dict(color="#0D1117",width=2)),
                    ))
                    _fig_sct.update_layout(**DARK_M,height=240,showlegend=False,
                                           margin=dict(l=0,r=0,t=10,b=0))
                    st.plotly_chart(_fig_sct, use_container_width=True)
            with _s7c2:
                sec("Paylasim Risk Skoru Dagilimi")
                _fig_sh = px.histogram(_share_combined, x="Final_Risk_Skoru", nbins=15,
                                       color="Seviye", color_discrete_map=SEV_CLR)
                _fig_sh.add_vline(x=50,line_dash="dash",line_color="#F85149",annotation_text="Yuksek (50)")
                _fig_sh.update_layout(**DARK,height=240,legend=dict(font=dict(color="#C9D1D9")))
                st.plotly_chart(_fig_sh, use_container_width=True)

            # Şehre göre dağılım
            if "Sehir" in _share_combined.columns:
                _s_city = _share_combined[_share_combined["Sehir"].notna() & (_share_combined["Sehir"]!="None")]                          .groupby("Sehir").size().nlargest(10).reset_index()
                _s_city.columns = ["Sehir","Cihaz"]
                if len(_s_city)>0:
                    sec("Lokasyona Gore Riskli Paylasim")
                    _fig_sc2=px.bar(_s_city.sort_values("Cihaz"),x="Cihaz",y="Sehir",orientation="h",
                                    color="Cihaz",color_continuous_scale=["#FF9F43","#F85149"],text="Cihaz")
                    _fig_sc2.update_layout(**DARK,height=max(200,len(_s_city)*32),showlegend=False,
                                           coloraxis_showscale=False)
                    _fig_sc2.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"))
                    st.plotly_chart(_fig_sc2, use_container_width=True)

            sec("Riskli Paylasim Cihaz Listesi")
            _cols_sh = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Cihaz_Tipi",
                                     "Riskli Paylaşılan Klasörler","Final_Risk_Skoru","Seviye"]
                        if c in _share_combined.columns]
            show_table(_share_combined[_cols_sh].sort_values("Final_Risk_Skoru",ascending=False),
                       height=420, text_cols=["Riskli Paylaşılan Klasörler"])
            _csv7=_share_combined[_cols_sh].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ Paylasim Listesi CSV",_csv7,
                               f"paylasim_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
        else:
            st.success("✅ Riskli dosya paylasimi tespit edilmedi")

    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: SUNUCU & KRİTİK
# ═══════════════════════════════════════════════════════════
def page_servers(df):
    st.title("🖥️ Kritik Sunucu & Altyapı Analizi")

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

    ns  = len(servers)
    ns_h= int((servers["Seviye"]=="YÜKSEK").sum())
    ns_m= int((servers["Seviye"]=="ORTA").sum())
    ns_l= int((servers["Seviye"]=="DÜŞÜK").sum())
    ns_p= int((servers["Yamasız Gün"]>60).sum()) if "Yamasız Gün" in servers.columns else 0
    ns_avg = round(float(servers["Final_Risk_Skoru"].mean()),1) if ns>0 else 0
    ns_max = int(servers["Final_Risk_Skoru"].max()) if ns>0 else 0
    _dc_n   = int((servers["Cihaz_Tipi"]=="Domain Controller").sum()) if "Cihaz_Tipi" in servers.columns else 0
    _mail_n = int((servers["Cihaz_Tipi"]=="Mail Server").sum()) if "Cihaz_Tipi" in servers.columns else 0

    # Kritik uyarı banner — dinamik
    _srv_lbl = "KRİTİK" if ns_h==ns else "YÜKSEK" if ns_h>0 else "İZLENİYOR"
    _srv_clr = "#F85149" if ns_h==ns else "#D29922" if ns_h>0 else "#3FB950"
    st.markdown(f"""<div style="background:linear-gradient(135deg,rgba(248,81,73,0.08),rgba(13,17,23,0.8));
border:1px solid {_srv_clr};border-left:6px solid {_srv_clr};border-radius:12px;
padding:16px 20px;margin-bottom:16px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <div style="font-size:10px;color:{_srv_clr};font-weight:700;text-transform:uppercase;
      letter-spacing:.08em;margin-bottom:4px">⚠️ Kritik Altyapı Risk Durumu — {_srv_lbl}</div>
      <div style="font-size:13px;color:#E6EDF3">
        <b>{_dc_n}</b> Domain Controller · <b>{_mail_n}</b> Mail Server tespit edildi.
        DC/Mail Server ihlali tüm ağı tehlikeye atar — 7/24 izleme zorunlu.
      </div>
      <div style="font-size:11px;color:#8B949E;margin-top:4px">
        Ortalama risk skoru: <b style="color:{_srv_clr}">{ns_avg}/100</b> · 
        Maksimum: <b style="color:{_srv_clr}">{ns_max}/100</b> · 
        Yamasız (60g+): <b style="color:#FF7B72">{ns_p}</b> sunucu
      </div>
    </div>
    <div style="text-align:center;background:{_srv_clr}22;border-radius:10px;padding:12px 18px">
      <div style="font-size:36px;font-weight:900;color:{_srv_clr}">{ns_h}</div>
      <div style="font-size:9px;color:{_srv_clr};text-transform:uppercase;font-weight:700">Yüksek Riskli</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # KPI satırı — renkli simgeli kartlar
    _sk = st.columns(6)
    kpi(_sk[0], ns,    "Toplam Sunucu",   "#58A6FF", f"Ort:{ns_avg}",      "linear-gradient(135deg,#0d2137,#162e4d)", "🖥️")
    kpi(_sk[1], ns_h,  "Yüksek Risk",     "#F85149", f"%{ns_h/max(ns,1)*100:.0f}", "linear-gradient(135deg,#3d0000,#5c0a0a)", "🔴")
    kpi(_sk[2], ns_m,  "Orta Risk",       "#D29922", f"%{ns_m/max(ns,1)*100:.0f}", "linear-gradient(135deg,#3d2200,#5c3300)", "🟡")
    kpi(_sk[3], ns_l,  "Düşük Risk",      "#3FB950", f"%{ns_l/max(ns,1)*100:.0f}", "linear-gradient(135deg,#0d2e14,#1a4a23)", "🟢")
    kpi(_sk[4], ns_p,  "Yamasız 60g+",    "#FF7B72", f"%{ns_p/max(ns,1)*100:.0f}", "linear-gradient(135deg,#3d1500,#5c2200)", "🩹")
    kpi(_sk[5], _dc_n, "Domain Ctrl.",    "#D2A8FF", str(_mail_n)+" Mail",   "linear-gradient(135deg,#2d1a4d,#3d2466)", "🔑")

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
    st.caption(f"**{len(filtered_srv)}** sunucu gösteriliyor")

    # Grafikler — tüm cihazlar sunucu olduğu için pie/bar yerine daha anlamlılar
    col1,col2=st.columns(2)
    with col1:
        sec("Sunucu Başına Risk Skoru — Sıralı")
        if "Cihaz_Tipi" in servers.columns:
            _srv_top = servers.nlargest(15,"Final_Risk_Skoru")[["AssetName","Final_Risk_Skoru","Cihaz_Tipi","Yamasız Gün"]].copy()
            _srv_colors = [CRIT_CLR.get(t,"#8B949E") for t in _srv_top["Cihaz_Tipi"]]
            _fig_srv = go.Figure(go.Bar(
                y=_srv_top["AssetName"], x=_srv_top["Final_Risk_Skoru"],
                orientation="h",
                marker_color=_srv_colors,
                text=[f"{v}" for v in _srv_top["Final_Risk_Skoru"]],
                textposition="outside", textfont=dict(color="#C9D1D9",size=10),
                hovertemplate="<b>%{y}</b><br>Risk: %{x}<br>Tür: %{customdata}<extra></extra>",
                customdata=_srv_top["Cihaz_Tipi"],
            ))
            _fig_srv.add_vline(x=50,line_dash="dash",line_color="#F85149",annotation_text="Yüksek (50)")
            _fig_srv.add_vline(x=75,line_dash="dot", line_color="#8B1A1A", annotation_text="Kritik (75)")
            _fig_srv.update_layout(**DARK,height=360,showlegend=False,
                                   xaxis=dict(range=[0,105]))
            st.plotly_chart(_fig_srv, use_container_width=True)

    with col2:
        sec("Yamasız Gün — Sunucu Başına Risk Matrisi")
        if "Yamasız Gün" in servers.columns:
            _hov_s = {c:True for c in ["AssetName","Cihaz_Tipi","Final_Risk_Skoru"] if c in servers.columns}
            _fig_mat = px.scatter(
                servers, x="Yamasız Gün", y="Final_Risk_Skoru",
                color="Cihaz_Tipi",
                color_discrete_map=CRIT_CLR,
                size="Final_Risk_Skoru", size_max=20,
                hover_data=_hov_s, opacity=0.85,
                text="AssetName" if len(servers)<=20 else None,
            )
            _fig_mat.add_hline(y=50, line_dash="dash",line_color="#F85149",annotation_text="Yüksek (50)")
            _fig_mat.add_vline(x=60, line_dash="dash",line_color="#D29922",annotation_text="Kritik Patch (60g)")
            _fig_mat.update_layout(**DARK, height=360,
                                   legend=dict(font=dict(color="#C9D1D9",size=9)))
            if len(servers)<=20:
                _fig_mat.update_traces(textposition="top center",textfont=dict(color="#C9D1D9",size=8))
            st.plotly_chart(_fig_mat, use_container_width=True)

    TYPE_INFO={
        "Domain Controller":{"color":"#F85149","risk":"MAKSIMUM","icon":"🔑",
            "desc":"Tüm ağın kimlik doğrulama merkezi. Ele geçirilirse domain çöker.",
            "actions":["DC replikasyon sağlığını kontrol et (dcdiag)","DSRM şifresi belgeli mi?",
                       "Privileged Access Workstation kullan","Son DC yedeklemesini doğrula",
                       "Tier-0 izolasyonu uygulandı mı?"]},
        "Mail Server":{"color":"#FF7B72","risk":"KRİTİK","icon":"📧",
            "desc":"Phishing, veri sızdırma ve MITM saldırılarının birincil hedefi.",
            "actions":["SPF/DKIM/DMARC yapılandırıldı mı?","TLS 1.2+ zorunlu mu?",
                       "Spam filtresi güncel mi?","Ekler sandbox'ta taranıyor mu?"]},
        "Veritabanı Sunucusu":{"color":"#FFA657","risk":"KRİTİK","icon":"🗄️",
            "desc":"Kritik iş verisi deposu. SQL injection ve yetkisiz erişim en büyük tehlikeler.",
            "actions":["SA hesabı devre dışı mı?","Şifreli bağlantı zorunlu mu?",
                       "Audit logging aktif mi?","En az yetkili servis hesapları mı?"]},
        "Sunucu":{"color":"#D29922","risk":"YÜKSEK","icon":"🖥️",
            "desc":"Uygulama/dosya sunucusu. Servis hesapları ve ayrıcalı erişim riski.",
            "actions":["Host firewall aktif mi?","Gereksiz rol/feature kaldırıldı mı?",
                       "Servis hesapları minimum yetkili mi?"]},
        "Sunucu (OS)":{"color":"#56D364","risk":"YÜKSEK","icon":"💻",
            "desc":"Sunucu işletim sistemi algılanan cihaz — rol ataması gerekli.",
            "actions":["Sunucu olduğu teyit edildi mi?","Rol atandı mı?","Patch takibi yapılıyor mu?"]},
    }

    sec("Sunucu Detayları","","#8957E5")
    for _,row in filtered_srv.sort_values("Final_Risk_Skoru",ascending=False).iterrows():
        ctype   = str(row.get("Cihaz_Tipi","Sunucu"))
        info    = TYPE_INFO.get(ctype, TYPE_INFO["Sunucu"])
        sev     = str(row.get("Seviye",""))
        score   = int(row.get("Final_Risk_Skoru",0))
        ham     = int(row.get("Risk Skoru",0))
        yamasiz = int(row.get("Yamasız Gün",0))
        offline = int(row.get("Offline Gün",0))
        cve_b   = int(row.get("CVE_Bonus",0))
        lsw     = str(row.get("Lansweeper",""))
        _sev_clr = "#F85149" if sev=="YÜKSEK" else "#D29922" if sev=="ORTA" else "#3FB950"
        _sev_icon= "🔴" if sev=="YÜKSEK" else "🟡" if sev=="ORTA" else "🟢"
        _score_bg= "#3d0000" if score>=75 else "#3d2200" if score>=50 else "#0d2e14"

        with st.expander(
            f"{_sev_icon} {row.get('AssetName','?')}  ·  {info['icon']} {ctype}  ·  Skor: {score}  ·  {row.get('IPAddress','')}",
            expanded=(sev=="YÜKSEK")):

            # Üst banner — renk kodlu
            st.markdown(f"""<div style="background:linear-gradient(135deg,{info['color']}18,#0D1117);
border:1px solid {info['color']}44;border-left:5px solid {info['color']};
border-radius:10px;padding:12px 16px;margin-bottom:10px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <div style="font-size:11px;color:{info['color']};font-weight:700;margin-bottom:3px">
        {info['icon']} {ctype} — {info['risk']}</div>
      <div style="color:#C9D1D9;font-size:12px">{info['desc']}</div>
      <div style="margin-top:6px;font-size:11px;color:#8B949E">
        👤 {row.get('Kullanıcı','-')} &nbsp;·&nbsp;
        🌐 {row.get('IPAddress','-')} &nbsp;·&nbsp;
        💻 {row.get('Sistem','-')}
      </div>
      {f'<a href="{lsw}" target="_blank" style="color:#58A6FF;font-size:11px;margin-top:4px;display:inline-block">🔗 Lansweeperde Ac</a>' if lsw else ""}
    </div>
    <div style="text-align:center;background:{_score_bg};border-radius:10px;padding:10px 16px;min-width:70px">
      <div style="font-size:30px;font-weight:900;color:{_sev_clr};line-height:1">{score}</div>
      <div style="font-size:8px;color:{_sev_clr};text-transform:uppercase">Final Risk</div>
      <div style="font-size:9px;color:#8B949E;margin-top:2px">Ham: {ham}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

            ca, cb = st.columns(2)
            with ca:
                # Metrik rozetleri
                _badges = [
                    (f"⏱ {yamasiz}g Yamasız",  "#F85149" if yamasiz>60 else "#3FB950"),
                    (f"📴 {offline}g Offline",  "#D29922" if offline>60 else "#3FB950"),
                    (f"🦠 CVE+{cve_b}",         "#8957E5" if cve_b>0 else "#3FB950"),
                ]
                _badge_html = "".join([
                    f'<span style="background:{c}22;border:1px solid {c}44;color:{c};'
                    f'font-size:10px;font-weight:700;padding:3px 9px;border-radius:12px;'
                    f'margin:2px;display:inline-block">{t}</span>'
                    for t,c in _badges
                ])
                st.markdown(f'<div style="margin-bottom:8px">{_badge_html}</div>',
                            unsafe_allow_html=True)

                # Risk Analizi
                ra = str(row.get("Risk Analizi",""))
                if ra.strip():
                    for item in ra.split("•"):
                        if item.strip():
                            st.markdown(f"""<div style="background:rgba(248,81,73,.08);border-left:3px solid #F85149;
border-radius:4px;padding:5px 10px;margin:3px 0;font-size:11px;color:#E6EDF3">⚠ {item.strip()}</div>""",
                                        unsafe_allow_html=True)
                else:
                    st.markdown("""<div style="background:rgba(63,185,80,.08);border-left:3px solid #3FB950;
border-radius:4px;padding:5px 10px;font-size:11px;color:#3FB950">✅ Aktif risk tespiti yok</div>""",
                                unsafe_allow_html=True)
                kd = str(row.get("Kural Dışı Adminler (İsim ve Ünvan)",""))
                if kd.strip():
                    st.markdown(f"""<div style="background:rgba(210,153,34,.1);border-left:3px solid #D29922;
border-radius:4px;padding:5px 10px;margin:3px 0;font-size:11px;color:#D29922">👤 {kd}</div>""",
                                unsafe_allow_html=True)
                sw = str(row.get("Tespit Edilen Şüpheli Yazılımlar",""))
                if sw.strip():
                    st.markdown(f"""<div style="background:rgba(137,87,229,.1);border-left:3px solid #8957E5;
border-radius:4px;padding:5px 10px;margin:3px 0;font-size:11px;color:#D2A8FF">🦠 {sw[:80]}</div>""",
                                unsafe_allow_html=True)

            with cb:
                # Öncelikli aksiyon listesi
                st.markdown(f"""<div style="background:#161B22;border-radius:8px;padding:10px 12px">
  <div style="font-size:9px;color:{info['color']};font-weight:700;text-transform:uppercase;
  margin-bottom:6px">⚡ Öncelikli Aksiyonlar</div>""", unsafe_allow_html=True)
                for i, act in enumerate(info.get("actions",[]), 1):
                    _act_clr = "#F85149" if i==1 else "#D29922" if i==2 else "#8B949E"
                    st.markdown(f"""<div style="display:flex;align-items:flex-start;margin:3px 0">
  <span style="color:{_act_clr};font-size:10px;font-weight:700;min-width:16px">{i}.</span>
  <span style="color:#C9D1D9;font-size:10px;margin-left:4px">{act}</span>
</div>""", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

                # AI kısa yorum
                _ai_act = ("🔴 ACİL: Bu sunucuda yüksek risk tespit edildi — bugün patch uygula!" 
                           if score>=75 and yamasiz>60 else
                           "🟡 YÜKSEK: Yama eksiği ve/veya aktif risk var — bu hafta müdahale et."
                           if score>=50 or yamasiz>60 else
                           "🟢 İZLENİYOR: Aktif kritik risk yok, rutin izleme yeterli.")
                st.markdown(f"""<div style="background:#0D1117;border-left:3px solid {_sev_clr};
border-radius:4px;padding:7px 10px;margin-top:6px;font-size:11px">
  <span style="color:#8B949E">🤖 AI:</span>
  <span style="color:#C9D1D9"> {_ai_act}</span>
</div>""", unsafe_allow_html=True)

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
            st.plotly_chart(fig_g, use_container_width=True)
    footer()


# ═══════════════════════════════════════════════════════════
# SAYFA: KULLANICI RİSKİ
# ═══════════════════════════════════════════════════════════
def page_users(df):
    st.title("Kullanıcı Risk Analizi")
    n = len(df)
    st.caption("Kullanıcı başına cihaz riski ve davranış puanı — yüksek puan = yüksek öncelik.")

    cs,cf=st.columns([2,2])
    with cs: q_u=st.text_input("Kullanıcı ara","",key="usr_q",placeholder="kullanıcı adı...")
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
        +ur.get("Disk",pd.Series(0,index=ur.index))*5
        +ur.get("WU",pd.Series(0,index=ur.index))*5
    ).round(1)
    ur=ur.sort_values("Davranis Puani",ascending=False)
    if q_u: ur=ur[ur["Kullanıcı"].str.contains(q_u,case=False,na=False)]
    nu = len(ur)

    # AI Kullanıcı Risk Yorumu
    _top_user = ur.iloc[0]["Kullanıcı"] if nu>0 else "-"
    _top_puan = ur.iloc[0]["Davranis Puani"] if nu>0 else 0
    _riskli_u = int((ur["Davranis Puani"]>=50).sum()) if nu>0 else 0
    _u_oran   = round(_riskli_u/max(nu,1)*100,1)
    _u_lbl,_u_clr,_u_icon = ("KRİTİK","#F85149","🔴") if _u_oran>=30 else                              ("YÜKSEK","#D29922","🟡") if _u_oran>=10 else ("NORMAL","#3FB950","🟢")
    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_u_clr};border-left:5px solid {_u_clr};
border-radius:10px;padding:14px 18px;margin:8px 0 16px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_u_clr};font-weight:700;text-transform:uppercase">🤖 AI Kullanıcı Risk Analizi</div>
    <div style="background:{_u_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_u_icon} {_u_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{nu}</b> kullanıcı analiz edildi. <b>{_riskli_u}</b>'i (%{_u_oran}) 50+ davranış puanıyla yüksek risk grubunda.
    En riskli kullanıcı: <b>{_top_user}</b> ({_top_puan:.0f} puan).
    {"Bu risk profili, yetkisiz admin erişimi veya birden fazla sorunlu cihaz barındıran kullanıcıları işaret ediyor." if _riskli_u>0 else "Kullanıcı risk profili genel olarak kabul edilebilir seviyede."}
  </div>
  <div style="font-size:11px;color:{_u_clr};font-weight:600;margin-top:6px">
    ⚡ {"Yüksek puanlı kullanıcıların cihazlarını öncelikle incele, AD yetki listesini gözden geçir." if _riskli_u>0 else "Rutin izleme yeterli."}
  </div>
</div>""", unsafe_allow_html=True)

    st.caption(f"**{nu}** kullanıcı")
    _uc1, _uc2 = st.columns([3,2])
    with _uc1:
        sec("En Riskli 15 Kullanıcı — Davranış Puanı")
        fig=px.bar(ur.head(15).sort_values("Davranis Puani"),
                   x="Davranis Puani",y="Kullanıcı",orientation="h",
                   color="Davranis Puani",
                   color_continuous_scale=["#3FB950","#D29922","#F85149","#8B1A1A"],
                   text="Davranis Puani")
        fig.add_vline(x=50,line_dash="dash",line_color="#F85149",annotation_text="Yüksek Risk (50)")
        fig.update_layout(**DARK,height=440,showlegend=False,coloraxis_showscale=False)
        fig.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"),texttemplate="%{text:.0f}")
        st.plotly_chart(fig, use_container_width=True)
    with _uc2:
        sec("Davranış Puanı Dağılımı")
        _u_bins=[0,25,50,75,100,9999]
        _u_lbls=["0-25 (Düşük)","25-50 (Orta)","50-75 (Yüksek)","75-100 (Kritik)","100+ (Alarm)"]
        _u_cut=pd.cut(ur["Davranis Puani"],bins=_u_bins,labels=_u_lbls,right=True)
        _u_vc=_u_cut.value_counts().reindex(_u_lbls,fill_value=0).reset_index()
        _u_vc.columns=["Aralik","Kullanici"]
        _u_colors=["#3FB950","#D29922","#F85149","#8B1A1A","#5C0000"]
        _fig_ud=go.Figure(go.Bar(
            x=_u_vc["Aralik"],y=_u_vc["Kullanici"],
            marker_color=_u_colors[:len(_u_vc)],
            text=_u_vc["Kullanici"],textposition="outside",textfont=dict(color="#C9D1D9"),
            hovertemplate="<b>%{x}</b><br>%{y} kullanıcı<extra></extra>",
        ))
        _fig_ud.update_layout(**DARK,height=280,showlegend=False)
        st.plotly_chart(_fig_ud, use_container_width=True)

        # Admin olan kullanıcı sayısı özeti
        if "Admin" in ur.columns:
            _adm_u = int((ur["Admin"]>0).sum())
            st.markdown(f"""<div style="background:#161B22;border-left:3px solid #FFA657;
border-radius:6px;padding:8px 10px;font-size:11px;margin-top:4px">
  <div style="color:#FFA657;font-weight:700">👤 {_adm_u} kullanıcı yetkisiz admin barındırıyor</div>
  <div style="color:#8B949E">Cihazlarında standart dışı admin grubu üyeliği var.</div>
</div>""", unsafe_allow_html=True)

    _utab1, _utab2 = st.tabs(["📊 Risk Tablosu", "🔍 Profil Detayı"])

    with _utab1:
        # Tablo — açıklamalı sütun başlıkları
        sec("Kullanıcı Risk Tablosu")
        st.caption("📌 Sütun açıklamaları: **Cihaz**=kullanıcıya ait cihaz sayısı · **Ort_Risk**=ortalama final risk skoru · **Max_Risk**=en yüksek risk skoru · **Yuksek**=yüksek riskli cihaz sayısı · **Max_Yamasiz**=en uzun yamasız süre (gün) · **Admin**=yetkisiz admin toplam · **Disk**=disk hatası sayısı · **WU**=WU kapalı cihaz · **Davranis Puani**=bileşik risk skoru")
        # Kullanıcı Lansweeper linki ekle
        _ur_display = ur.copy()
        _DOMAIN = "dunyagoz"
        _ur_display.insert(0, "Lansweeper",
            _ur_display["Kullanıcı"].apply(
                lambda u: f"http://LANSWEEPER_HOST:81/user.aspx?username={u}&userdomain={_DOMAIN}"
                          if isinstance(u, str) and u not in ("Sahipsiz","") else ""
            )
        )
        _ur_col_cfg = {
            "Lansweeper": st.column_config.LinkColumn(
                "🔗 Profil", help="Lansweeper'da kullanıcı profilini aç",
                display_text="🔗 Aç"
            ),
            "Davranis Puani": st.column_config.ProgressColumn(
                "🎯 Davranış Puanı", min_value=0, max_value=max(int(ur["Davranis Puani"].max()),1) if nu>0 else 100, format="%.0f"
            ),
            "Ort_Risk":    st.column_config.NumberColumn("📊 Ort. Risk",  format="%.1f", help="Kullanıcının cihazlarının ortalama final risk skoru"),
            "Max_Risk":    st.column_config.NumberColumn("⬆ Max Risk",   format="%d",   help="Kullanıcının en yüksek riskli cihazının skoru"),
            "Cihaz":       st.column_config.NumberColumn("🖥 Cihaz",      format="%d",   help="Kullanıcıya ait toplam cihaz sayısı"),
            "Yuksek":      st.column_config.NumberColumn("🔴 Yüksek",     format="%d",   help="Yüksek risk seviyesindeki cihaz sayısı"),
            "Max_Yamasiz": st.column_config.NumberColumn("📅 Max Yamasız",format="%d g", help="Kullanıcının en uzun yamasız gün sayısı"),
        }
        if "Admin" in _ur_display.columns:
            _ur_col_cfg["Admin"] = st.column_config.NumberColumn("👤 Admin",format="%d",help="Yetkisiz admin grubu üyesi toplam cihaz")
        if "Disk"  in _ur_display.columns:
            _ur_col_cfg["Disk"]  = st.column_config.NumberColumn("💾 Disk", format="%d",help="Disk hatası (_RawDiskError>0) olan cihaz sayısı")
        if "WU"    in _ur_display.columns:
            _ur_col_cfg["WU"]    = st.column_config.NumberColumn("🔄 WU",   format="%d",help="Windows Update servisi kapalı cihaz sayısı")
        st.dataframe(_ur_display, use_container_width=True, height=440, hide_index=True,
                     column_config=_ur_col_cfg)
        _csv_u=ur.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ Kullanıcı Listesi CSV",_csv_u,f"kullanici_risk_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")

        if q_u and len(ur)==1:
            sec("Kullanıcı Cihazları")
            ud=df[df["Kullanıcı"].str.contains(q_u,case=False,na=False)]
            cols=[c for c in ["Lansweeper","AssetName","IPAddress","Sistem","Cihaz_Tipi",
                               "Final_Risk_Skoru","Seviye","Risk Analizi"] if c in ud.columns]
            show_table(ud[cols],height=300,sort_col="Final_Risk_Skoru",text_cols=["Risk Analizi"])

            # Seçili kullanıcı AI yorumu
            if len(ud)>0:
                _su_nh = int((ud["Seviye"]=="YÜKSEK").sum())
                _su_avg= round(float(ud["Final_Risk_Skoru"].mean()),1)
                _su_max= int(ud["Yamasız Gün"].max()) if "Yamasız Gün" in ud.columns else 0
                _su_clr="#F85149" if _su_nh/max(len(ud),1)>=0.5 else "#D29922" if _su_nh>0 else "#3FB950"
                st.markdown(f"""<div style="background:#0D1117;border-left:4px solid {_su_clr};
    border-radius:8px;padding:12px 16px;margin:8px 0;font-size:12px">
      <div style="color:{_su_clr};font-weight:700;margin-bottom:4px">🤖 {q_u} — Profil Özeti</div>
      <div style="color:#C9D1D9">{len(ud)} cihaz · Ort. risk: <b>{_su_avg}</b> · Yüksek riskli: <b>{_su_nh}</b> · Max yamasız: <b>{_su_max}g</b></div>
      <div style="color:{_su_clr};font-size:11px;margin-top:4px">
        ⚡ {"Kullanıcının yüksek riskli cihazları acil inceleme gerektiriyor." if _su_nh/max(len(ud),1)>=0.5 else "Cihazlarında patch ve admin denetimi yapılmalı." if _su_nh>0 else "Rutin izleme yeterli."}
      </div>
    </div>""", unsafe_allow_html=True)

    with _utab2:
        # ── KULLANICI PROFİL DRILLDOWN ─────────────────────────────
        st.markdown("---")
        sec("🔍 Kullanıcı Profil Detayı")
        st.caption("📌 Bir kullanıcı seç → kaç cihazı var, en riskli cihazı, hangi tehditler tekrarlıyor, trend + Lansweeper'da kullanıcı profili.")
        if "Kullanıcı" in df.columns and len(df) > 0:
            # Duplicate önleme: her kullanıcı bir kez listele, cihaz sayısıyla
            _usr_counts = df.groupby("Kullanıcı")["Final_Risk_Skoru"].agg(
                count="count", max_risk="max"
            ).reset_index()
            _usr_counts.columns = ["Kullanıcı","Cihaz","MaxRisk"]
            _usr_counts = _usr_counts.sort_values("MaxRisk",ascending=False)
            # Label: "hsaldiran (3 cihaz, max 72)"
            _usr_labels = {
                row["Kullanıcı"]: f"{row['Kullanıcı']}  ({row['Cihaz']} cihaz · max {row['MaxRisk']})"
                for _, row in _usr_counts.iterrows()
            }
            _usr_opts   = list(_usr_labels.keys())
            _prof_label = st.selectbox(
                "👤 Kullanıcı seç:",
                options=_usr_opts,
                format_func=lambda x: _usr_labels.get(x,x),
                key="ur_drilldown"
            )
            _prof_u     = _prof_label  # seçilen gerçek kullanıcı adı
            _u_cihazlar = df[df["Kullanıcı"] == _prof_u]

            if len(_u_cihazlar) > 0:
                _u_n   = len(_u_cihazlar)
                _u_avg = round(float(_u_cihazlar["Final_Risk_Skoru"].mean()), 1)
                _u_max = int(_u_cihazlar["Final_Risk_Skoru"].max())
                _u_yuk = int((_u_cihazlar["Seviye"] == "YÜKSEK").sum())
                _u_clr = "#F85149" if _u_max >= 50 else "#D29922" if _u_max >= 25 else "#3FB950"

                # Lansweeper kullanıcı linki
                _lsw_user_url = f"http://LANSWEEPER_HOST:81/user.aspx?username={_prof_u}&userdomain=dunyagoz"

                # Profil banner
                st.markdown(f"""<div style="background:linear-gradient(135deg,#161B22,#21262D);
    border:1px solid {_u_clr}44;border-left:5px solid {_u_clr};
    border-radius:10px;padding:14px 20px;margin:8px 0">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:18px;font-weight:800;color:#E6EDF3">👤 {_prof_u}</div>
          <div style="font-size:11px;color:#8B949E;margin-top:4px">
            {_u_n} cihaz &nbsp;·&nbsp; Ort. risk: {_u_avg} &nbsp;·&nbsp; {_u_yuk} yüksek riskli
          </div>
          <a href="{_lsw_user_url}" target="_blank"
             style="font-size:11px;color:#58A6FF;text-decoration:none;margin-top:6px;display:inline-block">
             🔗 Lansweeper'da Kullanıcı Profilini Aç
          </a>
        </div>
        <div style="text-align:center;background:{_u_clr}22;border-radius:8px;padding:10px 18px">
          <div style="font-size:36px;font-weight:900;color:{_u_clr};line-height:1">{_u_max}</div>
          <div style="font-size:9px;color:{_u_clr};text-transform:uppercase">Max Risk</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

                # AI kullanıcı yorum
                _u_tehditler = []
                _u_ra_all = _u_cihazlar.get("Risk Analizi", pd.Series("",index=_u_cihazlar.index)).astype(str)
                for _tt in ["Antivirüs (SEP) Eksik","DLP Yüklü Değil","Onaysız Yönetici",
                            "Güvenlik Yamaları Eksik","Riskli Paylaşım","Şüpheli Yazılım",
                            "Desteklenmeyen OS","Update Servisi Kapalı","RDP Açık"]:
                    if _u_ra_all.str.contains(_tt,na=False,regex=False).any():
                        _u_tehditler.append(_tt)
                _u_en_tehdit = _u_tehditler[0] if _u_tehditler else None
                _ai_u_clr    = "#F85149" if _u_yuk >= _u_n//2 else "#D29922" if _u_yuk>0 else "#3FB950"
                _ai_u_msg    = (
                    f"{_u_n} cihazın {_u_yuk}'i yüksek risk. "
                    + (f"En kritik sorun: **{_u_en_tehdit}** — {_u_ra_all.str.contains(_u_en_tehdit,na=False,regex=False).sum()} cihazda tekrarlıyor." if _u_en_tehdit else "")
                    + (" Öncelikle en yüksek skorlu cihazdan başla." if _u_yuk > 0 else " Genel profil kabul edilebilir.")
                )
                st.markdown(f"""<div style="background:#0D1117;border-left:4px solid {_ai_u_clr};
    border-radius:6px;padding:10px 14px;margin:4px 0 10px 0;font-size:12px">
      <span style="color:{_ai_u_clr};font-weight:700">🤖 AI Kullanıcı Profil Yorumu:</span>
      <span style="color:#C9D1D9;margin-left:6px">{_ai_u_msg}</span>
    </div>""", unsafe_allow_html=True)

                _up1, _up2 = st.columns([3,2])
                with _up1:
                    sec(f"Cihazlar ({_u_n})")
                    # Neden Riskli sütunu ekle
                    _u_show = _u_cihazlar.copy()
                    _u_show["Neden Riskli"] = _u_show.get("Risk Analizi", pd.Series("",index=_u_show.index)).astype(str).str.replace("•","⚠",regex=False).str[:80]
                    _u_cols = [c for c in ["Lansweeper","AssetName","Cihaz_Tipi",
                                            "Final_Risk_Skoru","Seviye","Yamasız Gün","Neden Riskli"]
                               if c in _u_show.columns]
                    show_table(_u_show[_u_cols].sort_values("Final_Risk_Skoru",ascending=False),
                               height=280, text_cols=["Neden Riskli"])

                with _up2:
                    sec("Risk Profil Radar")
                    # Radar/spider chart — daha işlevsel
                    _tehdit_cats = {
                        "Kimlik":    ["Onaysız Yönetici","Sabit Şifreli Admin"],
                        "Endpoint":  ["Antivirüs (SEP) Eksik","DLP Yüklü Değil","Şüpheli Yazılım"],
                        "Patch":     ["Güvenlik Yamaları Eksik","Update Servisi Kapalı","WSUS"],
                        "Ağ":        ["Riskli Paylaşım","RDP Açık"],
                        "OS/Donanım":["Desteklenmeyen OS","Disk"],
                    }
                    _radar_vals  = []
                    _radar_cats  = []
                    for _cat, _keywords in _tehdit_cats.items():
                        _score = 0
                        for _kw in _keywords:
                            _score += int(_u_ra_all.str.contains(_kw,na=False,regex=False).sum())
                        _radar_vals.append(min(_score, _u_n))
                        _radar_cats.append(_cat)
                    _fig_rad = go.Figure(go.Scatterpolar(
                        r=_radar_vals + [_radar_vals[0]],
                        theta=_radar_cats + [_radar_cats[0]],
                        fill="toself",
                        fillcolor=(f"rgba({int(_u_clr[1:3],16)},{int(_u_clr[3:5],16)},{int(_u_clr[5:7],16)},0.2)" if _u_clr.startswith("#") and len(_u_clr)==7 else "rgba(248,81,73,0.2)"),
                        line=dict(color=_u_clr,width=2),
                        marker=dict(size=6,color=_u_clr),
                        hovertemplate="%{theta}: %{r} cihaz<extra></extra>",
                    ))
                    _fig_rad.update_layout(
                        **DARK, height=270,
                        polar=dict(
                            radialaxis=dict(visible=True,range=[0,max(_u_n,1)],
                                            tickfont=dict(color="#8B949E",size=8),
                                            gridcolor="#21262D",linecolor="#30363D"),
                            angularaxis=dict(tickfont=dict(color="#C9D1D9",size=10),
                                             gridcolor="#21262D",linecolor="#30363D"),
                            bgcolor="#0D1117",
                        ),
                        showlegend=False,
                    )
                    st.plotly_chart(_fig_rad, use_container_width=True)

                # Trend (device_history)
                if DEVHIST_OK:
                    _en_riskli = _u_cihazlar.sort_values("Final_Risk_Skoru",ascending=False).iloc[0]
                    _en_asset  = str(_en_riskli.get("AssetName",""))
                    _gecmis_u  = gecmis_oku(_en_asset)
                    if len(_gecmis_u) >= 2:
                        sec(f"📈 En Riskli Cihaz Trendi — {_en_asset}")
                        _gdf_u = pd.DataFrame(_gecmis_u)
                        _fig_ut = go.Figure(go.Scatter(
                            x=_gdf_u["tarih"], y=_gdf_u["skor"],
                            mode="lines+markers", line=dict(color=_u_clr,width=2.5),
                            marker=dict(size=7,color=_u_clr),
                            hovertemplate="%{x}: %{y}<extra></extra>",
                        ))
                        _fig_ut.add_hline(y=50,line_dash="dash",line_color="#F85149",
                                          annotation_text="Yüksek Eşik (50)")
                        _fig_ut.update_layout(**DARK,height=200,
                                              xaxis_title="Tarih",yaxis=dict(range=[0,105]))
                        st.plotly_chart(_fig_ut, use_container_width=True)
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: ASSET CRİTİCALİTY
# ═══════════════════════════════════════════════════════════
def page_criticality(df):
    st.title("Asset Criticality Analizi")
    st.caption("Cihaz tipine göre risk çarpanı uygulaması — sunucular ve DC'ler daha yüksek öncelik alır.")
    n = len(df)
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
    nac = len(filtered_ac)

    ct=df.groupby("Cihaz_Tipi").agg(
        Sayi=("Final_Risk_Skoru","count"),Ort_Final=("Final_Risk_Skoru","mean"),
        Ort_Ham=("Risk Skoru","mean"),Yuksek=("Seviye",lambda x:(x=="YÜKSEK").sum()),
        Crit_Mult=("Crit_Multiplier","mean") if "Crit_Multiplier" in df.columns else ("Final_Risk_Skoru","count"),
    ).reset_index().sort_values("Ort_Final",ascending=False)
    ct["Yuksek_Oran"] = (ct["Yuksek"]/ct["Sayi"]*100).round(1)

    # AI Criticality Yorumu
    _srv_types = ["Domain Controller","Mail Server","Veritabanı Sunucusu","Sunucu","Sunucu (OS)"]
    _srv_df = df[df["Cihaz_Tipi"].isin(_srv_types)] if "Cihaz_Tipi" in df.columns else df.head(0)
    _srv_h = int((_srv_df["Seviye"]=="YÜKSEK").sum()) if len(_srv_df)>0 else 0
    _srv_n = len(_srv_df)
    _promoted = int((df["Final_Risk_Skoru"]>df["Risk Skoru"]).sum()) if "Risk Skoru" in df.columns else 0
    _ac_lbl,_ac_clr,_ac_icon = ("KRİTİK","#F85149","🔴") if _srv_h>0 else                                 ("YÜKSEK","#D29922","🟡") if _promoted>int(n*0.3) else ("NORMAL","#3FB950","🟢")
    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_ac_clr};border-left:5px solid {_ac_clr};
border-radius:10px;padding:14px 18px;margin:8px 0 16px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_ac_clr};font-weight:700;text-transform:uppercase">🤖 AI Asset Criticality Analizi</div>
    <div style="background:{_ac_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_ac_icon} {_ac_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{_srv_n}</b> sunucu/kritik varlık tespit edildi. Bunların <b>{_srv_h}</b>i yüksek risk seviyesinde.
    Criticality çarpanı uygulamasıyla <b>{_promoted}</b> cihaz risk skoru yukarı çıktı.
    {"Kritik sunucularda yüksek risk: Domain'in tamamı tehdit altında olabilir." if _srv_h>0 else
     f"Sunucular şu an yüksek risk grubunda değil ancak {_promoted} cihaz çarpan nedeniyle skoru yükseltildi." if _promoted>0 else
     "Criticality profili genel olarak kabul edilebilir."}
  </div>
  <div style="font-size:11px;color:{_ac_clr};font-weight:600;margin-top:6px">
    ⚡ {"Kritik sunuculara 7/24 izleme, PAM çözümü ve ayrı patch önceliği uygula." if _srv_h>0 else "Sunucu patch takvimini DC > Mail > DB sırasıyla önceliklendir."}
  </div>
</div>""", unsafe_allow_html=True)

    col1,col2=st.columns(2)
    with col1:
        sec("Cihaz Tipi Dağılımı")
        fig_p=go.Figure(go.Pie(values=ct["Sayi"],labels=ct["Cihaz_Tipi"],hole=0.4,
            marker=dict(colors=[CRIT_CLR.get(t,"#8B949E") for t in ct["Cihaz_Tipi"]],
                        line=dict(color="#0D1117",width=2)),
            textinfo="label+percent+value",textfont=dict(color="#E6EDF3",size=11),
            hovertemplate="<b>%{label}</b><br>%{value} cihaz · %{percent} · Ort. Risk: %{customdata}<extra></extra>",
            customdata=ct["Ort_Final"].round(1)))
        fig_p.update_layout(**DARK,height=320,showlegend=False)
        st.plotly_chart(fig_p, use_container_width=True)
    with col2:
        sec("Ham vs Final Risk Skoru (Criticality Etkisi)")
        fig_b=go.Figure()
        fig_b.add_trace(go.Bar(name="Ham (Lansweeper)",x=ct["Cihaz_Tipi"],y=ct["Ort_Ham"].round(1),
            marker_color="#3498DB",opacity=0.85,text=ct["Ort_Ham"].round(1),
            textposition="outside",textfont=dict(color="#C9D1D9"),
            hovertemplate="<b>%{x}</b><br>Ham: %{y}<extra></extra>"))
        fig_b.add_trace(go.Bar(name="Final (Criticality Uygulandı)",x=ct["Cihaz_Tipi"],y=ct["Ort_Final"].round(1),
            marker_color="#F85149",opacity=0.85,text=ct["Ort_Final"].round(1),
            textposition="outside",textfont=dict(color="#C9D1D9"),
            hovertemplate="<b>%{x}</b><br>Final: %{y}<extra></extra>"))
        fig_b.add_hline(y=50,line_dash="dash",line_color="#D29922",annotation_text="Yüksek (50)")
        fig_b.update_layout(**DARK,height=320,barmode="group",legend=dict(font=dict(color="#C9D1D9")))
        st.plotly_chart(fig_b, use_container_width=True)

    # Ek grafikler
    col3,col4=st.columns(2)
    with col3:
        sec("Cihaz Tipine Göre Yüksek Risk Oranı (%)")
        _fig_yor=px.bar(ct.sort_values("Yuksek_Oran",ascending=False),
                        x="Cihaz_Tipi",y="Yuksek_Oran",
                        color="Yuksek_Oran",
                        color_continuous_scale=["#3FB950","#D29922","#F85149"],
                        text="Yuksek_Oran",
                        hover_data={"Sayi":True,"Yuksek":True})
        _fig_yor.add_hline(y=30,line_dash="dash",line_color="#F85149",annotation_text="Kritik (%30)")
        _fig_yor.update_layout(**DARK,height=280,showlegend=False,coloraxis_showscale=False,
                               yaxis_title="Yüksek Risk %")
        _fig_yor.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"),texttemplate="%{text:.1f}%")
        st.plotly_chart(_fig_yor, use_container_width=True)
    with col4:
        sec("Risk Skoru Scatter — Cihaz Tipi")
        if "Cihaz_Tipi" in filtered_ac.columns:
            _hov_ac={c:True for c in ["AssetName","Kullanıcı","Final_Risk_Skoru"] if c in filtered_ac.columns}
            _fig_sc=px.strip(filtered_ac,x="Cihaz_Tipi",y="Final_Risk_Skoru",
                             color="Seviye",color_discrete_map=SEV_CLR,
                             hover_data=_hov_ac)
            _fig_sc.add_hline(y=50,line_dash="dash",line_color="#F85149")
            _fig_sc.update_layout(**DARK,height=280,legend=dict(font=dict(color="#C9D1D9")))
            st.plotly_chart(_fig_sc, use_container_width=True)

    # AI Tablo yorumu
    _top_crit = ct.iloc[0]["Cihaz_Tipi"] if len(ct)>0 else "-"
    _top_final = ct.iloc[0]["Ort_Final"] if len(ct)>0 else 0
    st.markdown(f"""<div style="background:#161B22;border-left:3px solid #8957E5;
border-radius:6px;padding:10px 14px;margin:8px 0;font-size:11px">
  <span style="color:#8957E5;font-weight:700">🤖 Tablo Analizi:</span>
  <span style="color:#C9D1D9"> En kritik cihaz tipi <b>{_top_crit}</b> ({_top_final:.0f} ort. final skor).
  Crit_Multiplier sütunu hangi cihazların skora ek çarpan aldığını gösterir — 1.0 = çarpansız (workstation/laptop), >1.0 = sunucu sınıfı.</span>
</div>""", unsafe_allow_html=True)

    cols_c=[c for c in ["Lansweeper","AssetName","Kullanıcı","Sistem","Cihaz_Tipi",
                         "Crit_Multiplier","Risk Skoru","Final_Risk_Skoru","CVE_Bonus","Seviye"]
            if c in filtered_ac.columns]
    show_table(filtered_ac[cols_c].sort_values(["Cihaz_Tipi","Final_Risk_Skoru"],ascending=[True,False]),
               height=460)
    _csv_ac=filtered_ac[cols_c].to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ Criticality CSV",_csv_ac,f"criticality_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: PATCH & OFFLİNE
# ═══════════════════════════════════════════════════════════
def page_patch(df):
    st.title("Patch & Offline Analizi")
    n=len(df)
    pc  = int((df["Yamasız Gün"]>60).sum())  if "Yamasız Gün" in df.columns else 0
    p180= int((df["Yamasız Gün"]>180).sum()) if "Yamasız Gün" in df.columns else 0
    oc  = int((df["Offline Gün"]>60).sum())  if "Offline Gün" in df.columns else 0
    o180= int((df["Offline Gün"]>180).sum()) if "Offline Gün" in df.columns else 0
    p_oran = round(pc/max(n,1)*100,1)
    o_oran = round(oc/max(n,1)*100,1)
    p_ort  = round(float(df["Yamasız Gün"].mean()),1) if "Yamasız Gün" in df.columns else 0
    p_max  = int(df["Yamasız Gün"].max()) if "Yamasız Gün" in df.columns else 0

    # AI Patch Yorumu
    _pp_lbl,_pp_clr,_pp_icon = ("KRİTİK","#F85149","🔴") if p_oran>=70 else                                 ("YÜKSEK","#D29922","🟡") if p_oran>=30 else ("KABUL EDİLEBİLİR","#3FB950","🟢")
    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_pp_clr};border-left:5px solid {_pp_clr};
border-radius:10px;padding:14px 18px;margin:8px 0 16px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_pp_clr};font-weight:700;text-transform:uppercase">🤖 AI Patch & Offline Analizi</div>
    <div style="background:{_pp_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_pp_icon} {_pp_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{pc}</b> cihaz (%{p_oran}) 60+ gün yamasız, <b>{p180}</b> cihaz 180+ günü aşmış.
    Ortalama yamasız süre <b>{p_ort}</b> gün, maksimum <b>{p_max}</b> gün.
    Offline tarafta <b>{oc}</b> cihaz (%{o_oran}) 60+ gündür görünmüyor, <b>{o180}</b> tanesi 180+ gün.
    {"WSUS'tan kopmuş cihazlar var — bu cihazlar tüm kritik yamalardan mahrum." if p180>10 else
     "Patch uyumsuzluğu yüksek — fidye yazılımı riski artıyor." if p_oran>=30 else
     "Patch durumu genel olarak kabul edilebilir seviyede."}
  </div>
  <div style="font-size:11px;color:{_pp_clr};font-weight:600;margin-top:6px">
    ⚡ {"WSUS sağlığını kontrol et, 180+ gün cihazlara manuel müdahale, GPO ile WU zorla." if p_oran>=70 else
       "Bu hafta patch operasyonu başlat, offline cihazların envanterini güncelle." if p_oran>=30 else
       "Rutin patch döngüsü ve aylık offline cihaz kontrolü yeterli."}
  </div>
</div>""", unsafe_allow_html=True)

    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("Patch Kritik 60g+",  pc,   f"%{p_oran}",  delta_color="inverse")
    c2.metric("Patch Kritik 180g+", p180, f"%{p180/max(n,1)*100:.1f}", delta_color="inverse")
    c3.metric("Ort. Yamasız",       f"{p_ort}g")
    c4.metric("Max Yamasız",        f"{p_max}g")
    c5.metric("Offline Kritik 60g+",oc,   f"%{o_oran}")
    c6.metric("Offline 180g+",      o180)

    ca,cb=st.columns(2)
    with ca:
        sec("Yamasız Gün Dağılımı")
        if "Yamasız Gün" in df.columns:
            fig=px.histogram(df,x="Yamasız Gün",nbins=30,color_discrete_sequence=["#58A6FF"])
            fig.add_vline(x=60, line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
            fig.add_vline(x=180,line_dash="dot", line_color="#FF7B72",annotation_text="180g")
            fig.add_vline(x=365,line_dash="dot", line_color="#8B1A1A",annotation_text="1 Yıl")
            fig.update_layout(**DARK,height=260)
            st.plotly_chart(fig, use_container_width=True)
    with cb:
        sec("Offline Gün Dağılımı")
        if "Offline Gün" in df.columns:
            fig2=px.histogram(df,x="Offline Gün",nbins=30,color_discrete_sequence=["#D29922"])
            fig2.add_vline(x=60, line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
            fig2.add_vline(x=180,line_dash="dot", line_color="#FF7B72",annotation_text="180g")
            fig2.update_layout(**DARK,height=260)
            st.plotly_chart(fig2, use_container_width=True)

    # Ek: Cihaz tipine göre patch ve OS scatter
    cc,_cd_unused=st.columns(2)
    with cc:
        sec("Patch Durumu — Risk Seviyesine Göre Ort. Süre")
        if "Yamasız Gün" in df.columns:
            _pg=df.groupby("Seviye")["Yamasız Gün"].agg(["mean","median","max"]).reset_index()
            _pg.columns=["Seviye","Ort","Medyan","Maks"]
            _pg=_pg[_pg["Seviye"].isin(["YÜKSEK","ORTA","DÜŞÜK"])]
            _fp=go.Figure()
            for m,lbl,clr in [("Ort","Ort. Gün","#58A6FF"),("Medyan","Medyan","#D29922"),("Maks","Maks","#F85149")]:
                _fp.add_trace(go.Bar(name=lbl,x=_pg["Seviye"],y=_pg[m],
                                     marker_color=clr,opacity=0.85,
                                     text=_pg[m].round(0).astype(int),
                                     textposition="outside",textfont=dict(color="#C9D1D9")))
            _fp.add_hline(y=60,line_dash="dash",line_color="#F85149",annotation_text="Kritik (60g)")
            _fp.update_layout(**DARK,height=260,barmode="group",legend=dict(font=dict(color="#C9D1D9")))
            st.plotly_chart(_fp, use_container_width=True)
    with cc:
        sec("Yamasız Cihaz — Şehre Göre Top 10")
        if "Yamasız Gün" in df.columns and "Sehir" in df.columns:
            _city_p=df[df["Yamasız Gün"]>60]                    [df["Sehir"].notna() & (df["Sehir"]!="None")]                    .groupby("Sehir").size().nlargest(10).reset_index()
            _city_p.columns=["Sehir","Cihaz"]
            if len(_city_p)>0:
                _fcp=px.bar(_city_p.sort_values("Cihaz"),x="Cihaz",y="Sehir",orientation="h",
                            color="Cihaz",color_continuous_scale=["#D29922","#F85149"],text="Cihaz")
                _fcp.update_layout(**DARK,height=260,showlegend=False,coloraxis_showscale=False)
                _fcp.update_traces(textposition="outside",textfont=dict(color="#C9D1D9"))
                st.plotly_chart(_fcp, use_container_width=True)

    sec("Kritik Patch Listesi (60g+)")
    p_df=df[df["Yamasız Gün"]>60].sort_values("Yamasız Gün",ascending=False) if "Yamasız Gün" in df.columns else df.head(0)
    cols_p=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem","Cihaz_Tipi",
                         "Yamasız Gün","Offline Gün","Final_Risk_Skoru","Seviye"] if c in p_df.columns]
    show_table(p_df[cols_p],height=360)

    # AI Patch Listesi Yorumu
    if len(p_df)>0:
        _p_srv = p_df[p_df["Cihaz_Tipi"].isin(["Domain Controller","Mail Server","Veritabanı Sunucusu"])] if "Cihaz_Tipi" in p_df.columns else p_df.head(0)
        st.markdown(f"""<div style="background:#161B22;border-left:3px solid #FF7B72;
border-radius:6px;padding:10px 14px;margin:6px 0;font-size:11px">
  <span style="color:#FF7B72;font-weight:700">🤖 Patch Liste Analizi:</span>
  <span style="color:#C9D1D9"> {len(p_df)} kritik cihazın <b>{len(_p_srv)}</b>i DC/Mail/DB sınıfında — bu cihazlar <b>en yüksek öncelik</b> almalı.
  {'⚠ DC veya Mail Server yamasız: Tüm domain güvenliği risk altında!' if len(_p_srv)>0 else 'Sunucu sınıfı cihazlar uyumlu.'}</span>
</div>""", unsafe_allow_html=True)
        _csv_p=p_df[cols_p].to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ Patch Listesi CSV",_csv_p,f"patch_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")

    sec("Kritik Offline Listesi (60g+)")
    o_df=df[df["Offline Gün"]>60].sort_values("Offline Gün",ascending=False) if "Offline Gün" in df.columns else df.head(0)
    cols_o=[c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sehir","Offline Gün",
                         "Yamasız Gün","Final_Risk_Skoru","Seviye"] if c in o_df.columns]
    show_table(o_df[cols_o],height=300)
    if len(o_df)>0:
        st.markdown(f"""<div style="background:#161B22;border-left:3px solid #79C0FF;
border-radius:6px;padding:10px 14px;margin:6px 0;font-size:11px">
  <span style="color:#79C0FF;font-weight:700">🤖 Offline Liste Analizi:</span>
  <span style="color:#C9D1D9"> {len(o_df)} offline cihazın <b>{o180}</b>i 180+ gündür görünmüyor.
  Bu cihazlar zombi statüsünde — envanterden çıkarılmalı veya ağa bağlanmadan önce zorunlu patch uygulanmalı.</span>
</div>""", unsafe_allow_html=True)
        _csv_o=o_df[cols_o].to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ Offline Listesi CSV",_csv_o,f"offline_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: CVE
# ═══════════════════════════════════════════════════════════
def page_cve(df,cve_data,cve_meta):
    st.title("CVE & Zafiyet İstihbaratı")
    if not cve_data:
        st.warning("CVE verisi yok. Risk engine çalıştırıldığında otomatik oluşur.")
        st.code("python scripts/cve_scanner.py")
        return

    # KPI
    n_taranan = cve_meta.get("toplam_tarama",0)
    n_acik    = cve_meta.get("vuln_yazilim",0)
    n_cve     = cve_meta.get("toplam_cve",0)
    n_kritik  = cve_meta.get("kritik",0)
    n_yuksek  = cve_meta.get("yuksek",0)
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("🔍 Taranan Yazılım", n_taranan)
    c2.metric("⚠ Açık Bulunan",    n_acik)
    c3.metric("📋 Toplam CVE",      n_cve)
    c4.metric("🔴 Kritik (≥9.0)",   n_kritik)
    c5.metric("🟡 Yüksek (≥7.0)",   n_yuksek)

    # AI CVE Genel Yorumu
    _cv_oran = round(n_acik/max(n_taranan,1)*100,1)
    _cv_lbl,_cv_clr,_cv_icon = ("KRİTİK","#F85149","🔴") if n_kritik>=5 or _cv_oran>=40 else                                 ("YÜKSEK","#D29922","🟡") if n_kritik>=1 or n_acik>=3 else ("NORMAL","#3FB950","🟢")
    st.markdown(f"""<div style="background:#0D1117;border:1px solid {_cv_clr};border-left:5px solid {_cv_clr};
border-radius:10px;padding:14px 18px;margin:8px 0 16px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_cv_clr};font-weight:700;text-transform:uppercase">🤖 AI CVE İstihbarat Analizi</div>
    <div style="background:{_cv_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">{_cv_icon} {_cv_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    Taranan <b>{n_taranan}</b> yazılımın <b>{n_acik}</b>i (%{_cv_oran}) bilinen CVE içeriyor.
    <b>{n_kritik}</b> kritik (CVSS≥9.0) ve <b>{n_yuksek}</b> yüksek (CVSS≥7.0) seviye açık tespit edildi.
    {"Kritik CVE sayısı yüksek — bu yazılımlar aktif exploit kampanyalarının hedefinde olabilir." if n_kritik>=5 else
     "Kritik açıklar mevcut — ilgili yazılımlar bu hafta güncellenmeli." if n_kritik>=1 else
     "CVE profili yönetilebilir seviyede."}
  </div>
  <div style="font-size:11px;color:{_cv_clr};font-weight:600;margin-top:6px">
    ⚡ {"Kritik CVE'li yazılımları barındıran cihazlarda acil güncelleme/kaldırma operasyonu başlat." if n_kritik>=1 else "CVSS≥7 yazılımları bu sprint'te güncelle."}
  </div>
</div>""", unsafe_allow_html=True)

    # cve_results xlsx'ten detay verisi yükle (varsa)
    _cve_detail_map = {}  # yazılım_adı → {açıklama, cve_ids, vb.}
    import glob as _glob2
    _cve_xlsx = sorted(_glob2.glob(str(Path(__file__).parent.parent / "data" / "processed" / "cve_results_*.xlsx")), reverse=True)
    if _cve_xlsx:
        try:
            _detail_df = pd.read_excel(_cve_xlsx[0])
            _detail_df.columns = _detail_df.columns.str.strip()
            # Yazılım adını normalize et, açıklama ve CVE ID'lerini al
            _sw_col  = next((c for c in _detail_df.columns if "software" in c.lower() or "yazilim" in c.lower() or "name" in c.lower()), None)
            _desc_col= next((c for c in _detail_df.columns if "desc" in c.lower() or "aciklama" in c.lower() or "summary" in c.lower()), None)
            _id_col  = next((c for c in _detail_df.columns if "cve" in c.lower() and "id" in c.lower()), None)
            if _sw_col:
                for _, row in _detail_df.iterrows():
                    sw_key = str(row[_sw_col]).strip().lower()
                    if sw_key not in _cve_detail_map:
                        _cve_detail_map[sw_key] = {"desc": "", "ids": []}
                    if _desc_col and pd.notna(row.get(_desc_col,"")):
                        _cve_detail_map[sw_key]["desc"] = str(row[_desc_col])[:200]
                    if _id_col and pd.notna(row.get(_id_col,"")):
                        _cve_detail_map[sw_key]["ids"].append(str(row[_id_col]))
        except Exception:
            pass

    def _get_detail(sw_name):
        """Yazılım için xlsx'ten açıklama al, yoksa WHY dict'e düş."""
        key = sw_name.strip().lower()
        if key in _cve_detail_map and _cve_detail_map[key]["desc"]:
            ids = ", ".join(_cve_detail_map[key]["ids"][:3])
            desc = _cve_detail_map[key]["desc"]
            return f"{desc[:150]}{'...' if len(desc)>150 else ''}" + (f" [{ids}]" if ids else "")
        # WHY kütüphanesi
        WHY = {
            "anydesk":"Uzak masaüstü — RCE ve kimlik doğrulama bypass CVE'leri (CVE-2024-12754 vb.)",
            "teamviewer":"Uzak masaüstü — kimlik bypass ve ayrıcalık yükseltme açıkları",
            "wireshark":"Ağ analizi — kötü amaçlı paket ayrıştırması üzerinden RCE",
            "nmap":"Port tarama aracı — kötüye kullanım ve keşif saldırıları",
            "chrome":"Chromium/Chrome — V8 motoru RCE, sandbox bypass CVE'leri",
            "firefox":"Mozilla Firefox — use-after-free ve bellek bozulması CVE'leri",
            "java":"Oracle JRE/JDK — deserialization, RCE ve sandbox bypass",
            "adobe":"Adobe Acrobat/Flash — PDF/SWF tabanlı RCE açıkları",
            "office":"Microsoft Office — makro/OLE tabanlı RCE, CVE-2017-11882 vb.",
            "vlc":"VLC Media Player — medya ayrıştırma bellek taşması",
            "7-zip":"7-Zip — arşiv ayrıştırma yığın taşması güvenlik açığı",
            "winrar":"WinRAR — ACE path traversal (CVE-2018-20250) ve benzeri",
            "zoom":"Zoom — ara bellek güvenlik açıkları, otomatik yükleme zafiyetleri",
            "telegram":"Telegram Desktop — medya işleme RCE açıkları",
            "whatsapp":"WhatsApp Desktop — medya dosyası işleme güvenlik açıkları",
            "steam":"Steam Client — yerel ayrıcalık yükseltme güvenlik açıkları",
            "putty":"PuTTY SSH — RSA/DSA anahtar açıkları (CVE-2024-31497)",
            "openssh":"OpenSSH — authentication bypass ve RCE (CVE-2024-6387)",
            "python":"Python interpreter — çeşitli güvenlik açıkları",
            "nodejs":"Node.js — prototype pollution ve path traversal",
        }
        for kw, desc in WHY.items():
            if kw in key:
                return desc
        return f"{sw_name} — NIST NVD veritabanında kayıtlı açıklar mevcut. Sürüm güncellemesi önerilir."

    def _ai_tavsiye(cvss, sw_name):
        """CVSS skoru ve yazılım adına göre AI tabanlı tavsiye üret."""
        if cvss >= 9:
            return f"🔴 ACİL (48h): {sw_name} derhal güncelle veya kaldır. Aktif exploit riski yüksek."
        elif cvss >= 7:
            return f"🟡 Bu Hafta: {sw_name} güncellemesini bu sprint'e al. CVSS {cvss:.1f} kritik eşiğe yakın."
        else:
            return f"🟢 Planlı: Bir sonraki maintenance penceresinde {sw_name} güncelle."

    def cvss_lbl(s): return "Kritik" if s>=9 else("Yüksek" if s>=7 else "Orta")

    rows=[{"Yazılım":k,
           "Max CVSS":round(float(v.get("max_cvss",0)),1),
           "CVE Sayısı":int(v.get("cve_sayisi",0)),
           "Risk Bonusu":int(v.get("bonus",0)),
           "Kritiklik":cvss_lbl(float(v.get("max_cvss",0))),
           "Risk Açıklaması":_get_detail(k),
           "AI Tavsiye":_ai_tavsiye(float(v.get("max_cvss",0)),k)}
          for k,v in cve_data.items()]
    cve_df=pd.DataFrame(rows).sort_values("Max CVSS",ascending=False)

    # CVE nedir? — Kullanıcı bilgilendirme
    st.markdown("""<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
padding:12px 16px;margin:4px 0 14px 0;font-size:12px;color:#C9D1D9;line-height:1.7">
  <b style="color:#8957E5">CVE (Common Vulnerabilities and Exposures) Nedir?</b> —
  MITRE Corporation tarafından yönetilen uluslararası güvenlik açığı veritabanıdır.
  Her CVE; bir yazılımdaki spesifik güvenlik açığını, saldırı vektörünü ve etkisini belgeler.
  <b>CVSS (Common Vulnerability Scoring System)</b> skoru 0-10 arası bir şiddet puanıdır:
  <b style="color:#F85149">9.0-10.0 = Kritik</b> · <b style="color:#D29922">7.0-8.9 = Yüksek</b> ·
  <b style="color:#FFA657">4.0-6.9 = Orta</b> · <b style="color:#3FB950">0-3.9 = Düşük</b><br>
  <b style="color:#58A6FF">Kaynak:</b> Tüm CVE verileri
  <a href="https://nvd.nist.gov" target="_blank" style="color:#58A6FF">NIST NVD (National Vulnerability Database)</a>
  üzerinden otomatik taranmıştır. Her taramada kuruluşunuzdaki yazılımlar NIST ile eşleştirilir.
</div>""", unsafe_allow_html=True)

    # ── Grafik 1: CVSS Skoruna Göre Yazılım Listesi (grouped bar + risk marker) ──
    col1,col2=st.columns([3,2])
    with col1:
        sec("Yazılım Risk Profili — CVSS × CVE Sayısı")
        _top20 = cve_df.head(20).sort_values("Max CVSS", ascending=False)
        _colors_bar = ["#8B1A1A" if v>=9 else "#F85149" if v>=8 else "#D29922" if v>=7 else "#3FB950"
                       for v in _top20["Max CVSS"]]
        _fig_bar = go.Figure()
        _fig_bar.add_trace(go.Bar(
            name="Max CVSS", x=_top20["Max CVSS"], y=_top20["Yazılım"],
            orientation="h", marker_color=_colors_bar,
            text=[f"CVSS:{v:.1f}  ({c} CVE)" for v,c in zip(_top20["Max CVSS"],_top20["CVE Sayısı"])],
            textposition="outside", textfont=dict(color="#C9D1D9",size=10),
            hovertemplate="<b>%{y}</b><br>Max CVSS: %{x}<br>%{text}<extra></extra>",
        ))
        _fig_bar.add_vline(x=9,line_dash="dash",line_color="#8B1A1A",annotation_text="Kritik (9.0)",
                           annotation_font=dict(color="#F85149",size=10))
        _fig_bar.add_vline(x=7,line_dash="dot", line_color="#D29922",annotation_text="Yüksek (7.0)",
                           annotation_font=dict(color="#D29922",size=10))
        _fig_bar.update_layout(**DARK, height=min(520, max(320,len(_top20)*26)),
                               showlegend=False, xaxis=dict(range=[0,11]))
        st.plotly_chart(_fig_bar, use_container_width=True)
    with col2:
        sec("Kritiklik Dağılımı")
        kc=cve_df["Kritiklik"].value_counts().reset_index()
        kc.columns=["Seviye","Adet"]
        _kc_colors={"Kritik":"#F85149","Yüksek":"#D29922","Orta":"#3FB950"}
        fig2=go.Figure(go.Pie(labels=kc["Seviye"],values=kc["Adet"],hole=0.45,
            marker=dict(colors=[_kc_colors.get(s,"#8B949E") for s in kc["Seviye"]],
                        line=dict(color="#0D1117",width=2)),
            textinfo="label+value+percent",textfont=dict(color="#E6EDF3",size=11),
            hovertemplate="<b>%{label}</b><br>%{value} yazılım · %{percent}<extra></extra>"))
        fig2.add_annotation(text=f"<b>{len(cve_df)}</b><br>yazılım",
                            x=0.5,y=0.5,showarrow=False,font=dict(size=12,color="#E6EDF3"))
        fig2.update_layout(**DARK,height=260,showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

        # Risk Bonusu özeti
        st.markdown(f"""<div style="background:#161B22;border-left:3px solid #8957E5;
border-radius:6px;padding:10px 12px;font-size:11px;margin-top:4px">
  <div style="color:#8957E5;font-weight:700">📊 Risk Bonusu Sistemi</div>
  <div style="color:#C9D1D9;margin-top:4px">
    🔴 Kritik (CVSS≥9.0) → <b>+20 puan</b><br>
    🟡 Yüksek (CVSS≥7.0) → <b>+12 puan</b><br>
    Bonus doğrudan Final Risk Skoru'na eklenir.
  </div>
</div>""", unsafe_allow_html=True)

    # ── Tüm Açık Yazılımlar Tablosu ──
    sec("Tüm Açık Yazılımlar")
    ca2,cb2=st.columns([2,1])
    with ca2: q_cv=st.text_input("Yazılım ara","",key="cvs_q")
    with cb2:
        sev_cv=st.multiselect("Kritiklik",["Kritik","Yüksek","Orta"],
                              default=["Kritik","Yüksek","Orta"],key="cvsev")
    cve_df_f=cve_df.copy()
    if q_cv: cve_df_f=cve_df_f[cve_df_f["Yazılım"].str.contains(q_cv,case=False,na=False)]
    if sev_cv: cve_df_f=cve_df_f[cve_df_f["Kritiklik"].isin(sev_cv)]
    st.dataframe(cve_df_f,use_container_width=True,height=440,hide_index=True,
                 column_config={
                     "Max CVSS":     st.column_config.NumberColumn("⚠ Max CVSS", format="%.1f",
                                     help="En yüksek CVSS skoru — 9.0+ kritik, 7.0+ yüksek"),
                     "CVE Sayısı":   st.column_config.NumberColumn("📋 CVE Sayısı",
                                     help="Bu yazılımda bulunan toplam CVE adedi"),
                     "Risk Bonusu":  st.column_config.NumberColumn("🎯 Bonus",
                                     help="Final Risk Skoru'na eklenen puan (+20 kritik, +12 yüksek)"),
                     "Kritiklik":    st.column_config.TextColumn("🏷 Kritiklik",
                                     help="CVSS skoruna göre: Kritik≥9.0 / Yüksek≥7.0 / Orta<7.0"),
                     "Risk Açıklaması": st.column_config.TextColumn("🔍 Risk Açıklaması", width="large",
                                     help="CVE detay veritabanından çekilen açıklama"),
                     "AI Tavsiye":   st.column_config.TextColumn("🤖 AI Tavsiye", width="large",
                                     help="CVSS skoru ve yazılım tipine göre otomatik üretilen aksiyon tavsiyesi"),
                 })

    # AI CVE Tablo Yorumu
    _kritik_sw = cve_df[cve_df["Kritiklik"]=="Kritik"]
    if len(_kritik_sw)>0:
        _top_sw = _kritik_sw.iloc[0]
        st.markdown(f"""<div style="background:#0D1117;border-left:4px solid #F85149;
border-radius:6px;padding:10px 14px;margin:8px 0;font-size:11px">
  <span style="color:#F85149;font-weight:700">🤖 En Kritik Yazılım Analizi:</span>
  <span style="color:#C9D1D9"> <b>{_top_sw['Yazılım']}</b> — CVSS {_top_sw['Max CVSS']}, {_top_sw['CVE Sayısı']} CVE.
  {_top_sw['Risk Açıklaması'][:120]}{'...' if len(str(_top_sw['Risk Açıklaması']))>120 else ''}
  <b>Tavsiye:</b> {_top_sw['AI Tavsiye']}</span>
</div>""", unsafe_allow_html=True)

    if "Tespit Edilen Şüpheli Yazılımlar" in df.columns:
        rk=[k.lower() for k in cve_data.keys()]
        at_risk=df[df["Tespit Edilen Şüpheli Yazılımlar"].apply(
            lambda c: isinstance(c,str) and any(k in c.lower() for k in rk))]
        if len(at_risk)>0:
            sec(f"CVE'li Yazılım Barındıran Cihazlar — {len(at_risk)} cihaz")
            cr=[c for c in ["Lansweeper","AssetName","Kullanıcı","Cihaz_Tipi","Final_Risk_Skoru",
                             "CVE_Bonus","Seviye","Tespit Edilen Şüpheli Yazılımlar"] if c in at_risk.columns]
            show_table(at_risk[cr].sort_values("CVE_Bonus",ascending=False),height=340,
                       sort_col="CVE_Bonus",text_cols=["Tespit Edilen Şüpheli Yazılımlar"])

            # AI Cihaz Bazlı Yorum
            _top_cve_dev = at_risk.nlargest(1,"CVE_Bonus").iloc[0] if len(at_risk)>0 else None
            if _top_cve_dev is not None:
                _tcd_lsw = str(_top_cve_dev.get("Lansweeper",""))
                st.markdown(f"""<div style="background:#161B22;border-left:3px solid #8957E5;
border-radius:6px;padding:10px 14px;margin:6px 0;font-size:11px">
  <span style="color:#8957E5;font-weight:700">🤖 En Riskli CVE Cihazı:</span>
  <span style="color:#C9D1D9"> <b>{_top_cve_dev.get('AssetName','?')}</b> — CVE Bonus: +{int(_top_cve_dev['CVE_Bonus'])} puan.
  Yazılım: {str(_top_cve_dev.get('Tespit Edilen Şüpheli Yazılımlar',''))[:80]}. </span>
  {f'<a href="{_tcd_lsw}" target="_blank" style="color:#58A6FF;font-size:11px">🔗 Lansweeper</a>' if _tcd_lsw else ""}
</div>""", unsafe_allow_html=True)

    csv=cve_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ CVE Tablosu CSV",csv,f"cve_{datetime.now().strftime('%Y%m%d')}.csv","text/csv")
    footer()

# ═══════════════════════════════════════════════════════════
# SAYFA: ÖNERİLEN AKSİYONLAR
# ═══════════════════════════════════════════════════════════
def page_actions(df):
    st.title("🚨 Önerilen Aksiyonlar")
    st.caption("Her kart için ilgili cihaz listesi ve analiz aşağıda yer almaktadır.")

    n   = len(df)
    nh  = int((df["Seviye"] == "YÜKSEK").sum())
    pc  = int((df["Yamasız Gün"] > 60).sum())  if "Yamasız Gün"  in df.columns else 0
    oc  = int((df["Offline Gün"] > 60).sum())  if "Offline Gün"  in df.columns else 0
    adm = int(df["_RawAdminCount"].gt(0).sum()) if "_RawAdminCount" in df.columns else 0
    shd = int(df["Tespit Edilen Şüpheli Yazılımlar"].ne("").sum())
    ec  = int(df["Sistem"].str.contains("Win 7|2008|8.1|XP|2012", na=False).sum()) if "Sistem" in df.columns else 0
    ra  = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)

    # Hangi bölüme gidileceğini session_state'ten al
    _section = st.session_state.pop("action_section", "yuksek_risk")

    # Tab sırası: her aksiyona bir tab
    _tab_labels = []
    _tab_data   = []  # (label, section_key, count, color)
    if nh  > 0: _tab_data.append(("🔴 Yüksek Riskli",   "yuksek_risk",   nh,  "#F85149"))
    if pc  > 0: _tab_data.append(("🩹 Yamasız Cihazlar", "yamasiz",       pc,  "#FF7B72"))
    if adm > 0: _tab_data.append(("👤 Yetkisiz Admin",   "yetkisiz_admin",adm, "#D29922"))
    if oc  > 0: _tab_data.append(("📴 Offline",          "offline",       oc,  "#79C0FF"))
    if shd > 0: _tab_data.append(("🦠 Şüpheli Yazılım",  "suphe_yazilim", shd, "#D2A8FF"))
    if ec  > 0: _tab_data.append(("💀 EoL OS",           "eol_os",        ec,  "#FFA657"))

    if not _tab_data:
        st.success("✅ Tüm sistemler uyumlu. Kritik aksiyon gerektiren durum yok.")
        footer()
        return

    # Varsayılan tab indeksi — session_state'ten gelen section'a göre
    _default_tab = 0
    for _i, (_lbl, _key, _cnt, _clr) in enumerate(_tab_data):
        if _key == _section:
            _default_tab = _i
            break

    # Tab başlıkları
    _tabs = st.tabs([f"{lbl} ({cnt})" for lbl, key, cnt, clr in _tab_data])

    # ── TAB: YÜKSEK RİSKLİ CİHAZLAR ───────────────────────────
    for _ti, (_tab_obj, (_lbl, _key, _cnt, _clr)) in enumerate(zip(_tabs, _tab_data)):
        with _tab_obj:

            if _key == "yuksek_risk":
                _hdf = df[df["Seviye"] == "YÜKSEK"].sort_values("Final_Risk_Skoru", ascending=False)
                _h_srv = int(_hdf["Cihaz_Tipi"].isin(["Domain Controller","Mail Server","Veritabanı Sunucusu"]).sum()) if "Cihaz_Tipi" in _hdf.columns else 0
                _h_avg = round(float(_hdf["Final_Risk_Skoru"].mean()),1) if len(_hdf)>0 else 0

                # AI Yorumu
                _h_lbl = "KRİTİK" if _h_srv>0 else "ACİL" if len(_hdf)>50 else "YÜKSEK"
                _h_clr = "#F85149"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid #F85149;border-left:5px solid #F85149;
border-radius:10px;padding:14px 18px;margin:8px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:#F85149;font-weight:700;text-transform:uppercase">🤖 AI Yüksek Risk Analizi</div>
    <div style="background:#F85149;color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">🔴 {_h_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{len(_hdf)}</b> yüksek riskli cihaz tespit edildi. Ortalama risk skoru: <b>{_h_avg}/100</b>.
    {f"⚠️ Kritik: <b>{_h_srv}</b> sunucu/DC sınıfı cihaz yüksek risk grubunda — domain güvenliği tehdit altında." if _h_srv>0 else
     "Yüksek riskli cihazlar fidye yazılımı ve APT saldırılarına karşı savunmasız."}
    Önce sunucu/DC tipindeki cihazları ele al, ardından patch ve admin denetimi yap.
  </div>
  <div style="font-size:11px;color:#F85149;font-weight:600;margin-top:6px">
    ⚡ {"BUGÜN: DC/Mail/DB sunucularına acil patch + 7/24 izleme. AD'yi denetle." if _h_srv>0 else "Bu hafta: Tüm yüksek riskli cihazlara patch uygula, admin listesini gözden geçir."}
  </div>
</div>""", unsafe_allow_html=True)

                # Grafikler — net renkler, anlamlı
                _ct_col1, _ct_col2 = st.columns(2)
                with _ct_col1:
                    sec("Cihaz Tipine Göre Yüksek Risk Sayısı", color="#F85149")
                    st.caption("📌 Her çubuk bir cihaz tipini gösterir. DC/Mail/DB öncelikli ele alınmalı.")
                    if "Cihaz_Tipi" in _hdf.columns:
                        _ct2 = _hdf["Cihaz_Tipi"].value_counts().reset_index()
                        _ct2.columns = ["Tip","Sayi"]
                        # Cihaz tipine göre sabit renkler — karışıklık önlenir
                        _tip_clr = [CRIT_CLR.get(t,"#8B949E") for t in _ct2["Tip"]]
                        _fg = go.Figure(go.Bar(
                            x=_ct2["Tip"], y=_ct2["Sayi"],
                            marker_color=_tip_clr,
                            text=_ct2["Sayi"], textposition="outside",
                            textfont=dict(color="#C9D1D9"),
                            hovertemplate="<b>%{x}</b><br>%{y} yüksek riskli cihaz<extra></extra>",
                        ))
                        _fg.update_layout(**DARK, height=260, showlegend=False)
                        st.plotly_chart(_fg, use_container_width=True)
                with _ct_col2:
                    sec("Risk Skoru Dağılımı — Yüksek Risk Grubu", color="#F85149")
                    st.caption("📌 50-74 arası yüksek risk, 75+ kritik risk. Sütun yüksekliği cihaz sayısını gösterir.")
                    _bins_r = [50,60,70,75,80,90,101]
                    _lbls_r = ["50-59","60-69","70-74","75-79","80-89","90+"]
                    _hdf["_rb"] = pd.cut(_hdf["Final_Risk_Skoru"].clip(50,100), bins=_bins_r, labels=_lbls_r, right=False)
                    _rb = _hdf["_rb"].value_counts().reindex(_lbls_r, fill_value=0).reset_index()
                    _rb.columns = ["Aralik","Cihaz"]
                    _colors_r = ["#D29922","#F85149","#F85149","#8B1A1A","#8B1A1A","#5C0000"]
                    _fg2 = go.Figure(go.Bar(
                        x=_rb["Aralik"], y=_rb["Cihaz"],
                        marker_color=_colors_r[:len(_rb)],
                        text=_rb["Cihaz"], textposition="outside",
                        textfont=dict(color="#C9D1D9"),
                        hovertemplate="<b>Skor %{x}</b><br>%{y} cihaz<extra></extra>",
                    ))
                    _fg2.update_layout(**DARK, height=260, showlegend=False)
                    st.plotly_chart(_fg2, use_container_width=True)

                sec(f"Yüksek Riskli Cihaz Listesi — {len(_hdf)} Cihaz", color="#F85149")
                st.caption("📌 Final_Risk_Skoru = Lansweeper ham skoru × Criticality çarpanı + CVE bonusu. Sütuna tıklayarak sıralayabilirsiniz.")
                _cols_h = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem",
                                        "Cihaz_Tipi","Final_Risk_Skoru","CVE_Bonus","Seviye","Risk Analizi"]
                           if c in _hdf.columns]
                show_table(_hdf[_cols_h], height=460, sort_col="Final_Risk_Skoru",
                           text_cols=["Risk Analizi"])
                _csv = _hdf[_cols_h].to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Listeyi İndir (CSV)", _csv,
                                   f"yuksek_risk_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

            elif _key == "yamasiz":
                _pdf = df[df["Yamasız Gün"] > 60].sort_values("Yamasız Gün", ascending=False)                     if "Yamasız Gün" in df.columns else df.head(0)
                _max_g   = int(_pdf["Yamasız Gün"].max()) if len(_pdf) else 0
                _p180    = int((_pdf["Yamasız Gün"]>180).sum()) if len(_pdf) else 0
                _p_oran  = round(len(_pdf)/max(n,1)*100,1)
                _yp_lbl  = "KRİTİK" if _p_oran>=70 else "YÜKSEK" if _p_oran>=30 else "İZLE"
                _yp_clr  = "#F85149" if _yp_lbl=="KRİTİK" else "#D29922" if _yp_lbl=="YÜKSEK" else "#3FB950"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid {_yp_clr};border-left:5px solid {_yp_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_yp_clr};font-weight:700;text-transform:uppercase">🤖 AI Patch Analizi</div>
    <div style="background:{_yp_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">🩹 {_yp_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{len(_pdf)}</b> cihaz (%{_p_oran}) 60+ gün yamasız. En uzun: <b>{_max_g} gün</b>.
    <b>{_p180}</b> cihaz 180+ günü aşmış — WSUS bağlantısı kopmuş olabilir.
    Yamasız sistemler bilinen CVE'lerle istismar edilmeye açık.
  </div>
  <div style="font-size:11px;color:{_yp_clr};font-weight:600;margin-top:6px">
    ⚡ {"180+ gün cihazlara manuel müdahale, WSUS sağlığını kontrol et." if _p180>0 else "WSUS/SCCM'den zorla güncelleme politikası uygula."}
  </div>
</div>""", unsafe_allow_html=True)

                _pa_col1, _pa_col2 = st.columns(2)
                with _pa_col1:
                    sec("Yamasız Gün Dağılımı", color="#FF7B72")
                    _bins = [60,90,180,365,730,9999]
                    _lbls = ["61-90g","91-180g","181-365g","1-2 Yıl","2+ Yıl"]
                    _pdf["_pb2"] = pd.cut(_pdf["Yamasız Gün"], bins=_bins, labels=_lbls, right=True)
                    _pb2 = _pdf["_pb2"].value_counts().reindex(_lbls, fill_value=0).reset_index()
                    _pb2.columns = ["Aralik","Cihaz"]
                    _fgp = px.bar(_pb2, x="Aralik", y="Cihaz",
                                  color="Cihaz", color_continuous_scale=["#D29922","#F85149","#8B1A1A"],
                                  text="Cihaz")
                    _fgp.update_layout(**DARK, height=260, showlegend=False, coloraxis_showscale=False)
                    _fgp.update_traces(textposition="outside", textfont=dict(color="#C9D1D9"))
                    st.plotly_chart(_fgp, use_container_width=True)
                with _pa_col2:
                    sec("En Uzun Yamasız İlk 10", color="#FF7B72")
                    _top10 = _pdf.nlargest(10, "Yamasız Gün")
                    _fgt = px.bar(_top10, x="Yamasız Gün", y="AssetName", orientation="h",
                                  color="Yamasız Gün",
                                  color_continuous_scale=["#D29922","#F85149","#8B1A1A"],
                                  text="Yamasız Gün")
                    _fgt.update_layout(**DARK, height=260, showlegend=False, coloraxis_showscale=False)
                    _fgt.update_traces(textposition="outside", textfont=dict(color="#C9D1D9"),
                                       texttemplate="%{text:.0f}g")
                    st.plotly_chart(_fgt, use_container_width=True)

                sec(f"Yamasız Cihaz Listesi — {len(_pdf)} Cihaz", color="#FF7B72")
                _cols_p = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem",
                                        "Cihaz_Tipi","Yamasız Gün","Final_Risk_Skoru","Seviye"]
                           if c in _pdf.columns]
                show_table(_pdf[_cols_p], height=440, sort_col="Yamasız Gün")
                _csv = _pdf[_cols_p].to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Listeyi İndir (CSV)", _csv,
                                   f"yamasiz_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

            elif _key == "yetkisiz_admin":
                _adf = df[df["_RawAdminCount"].gt(0)].sort_values("_RawAdminCount", ascending=False)                     if "_RawAdminCount" in df.columns else df.head(0)

                # _RawAdminCount açıklama
                st.markdown("""<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;
padding:10px 14px;margin:4px 0 10px 0;font-size:11px">
  <b style="color:#FFA657">ℹ _RawAdminCount Nedir?</b>
  <span style="color:#C9D1D9"> Lansweeper'ın her cihazda tespit ettiği <b>standart dışı admin grubu üyesi sayısı</b>dır.
  Sıfır (0) = sadece varsayılan admin hesabı var, normal durum.
  1+ = ek yetkili hesap var, AD'de doğrulama gerekli.
  Bu metrik yüksekse lateral movement ve domain privilege escalation riski artar.</span>
</div>""", unsafe_allow_html=True)

                # AI Yorumu
                _a_multi = int((_adf["_RawAdminCount"]>2).sum()) if len(_adf)>0 else 0
                _a_avg   = round(float(_adf["_RawAdminCount"].mean()),1) if len(_adf)>0 else 0
                _a_lbl   = "KRİTİK" if _a_multi>10 or len(_adf)>int(n*0.2) else "YÜKSEK" if len(_adf)>0 else "TEMİZ"
                _a_clr   = "#F85149" if _a_lbl=="KRİTİK" else "#D29922" if _a_lbl=="YÜKSEK" else "#3FB950"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid {_a_clr};border-left:5px solid {_a_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_a_clr};font-weight:700;text-transform:uppercase">🤖 AI Yetkisiz Admin Analizi</div>
    <div style="background:{_a_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">👤 {_a_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{len(_adf)}</b> cihazda standart dışı admin üyeliği var. Ortalama ekstra admin: <b>{_a_avg}</b>.
    {f"<b>{_a_multi}</b> cihazda 2'den fazla ekstra admin — bu hesaplar aktif tehdit oluşturur." if _a_multi>0 else ""}
    Yetkisiz admin hesapları AD'de lateral movement için kullanılabilir.
  </div>
  <div style="font-size:11px;color:{_a_clr};font-weight:600;margin-top:6px">
    ⚡ {"Bugün AD Group Membership Audit başlat, 2+ adminli hesapları önce temizle." if _a_lbl=="KRİTİK" else "Bu hafta AD'den kaldır, log al, yöneticiye bildir."}
  </div>
</div>""", unsafe_allow_html=True)

                _aa_col1, _aa_col2 = st.columns(2)
                with _aa_col1:
                    sec("Admin Sayısı Dağılımı", color="#D29922")
                    st.caption("📌 X ekseni: bir cihazdaki ekstra admin sayısı. Y ekseni: o sayıya sahip cihaz adedi. 1=az riskli, 3+=yüksek riskli.")
                    _ac = _adf["_RawAdminCount"].value_counts().head(10).reset_index()
                    _ac.columns = ["Admin Sayısı","Cihaz"]
                    _ac_colors = ["#D29922" if v<=1 else "#F85149" if v<=3 else "#8B1A1A" for v in _ac["Admin Sayısı"]]
                    _fga = go.Figure(go.Bar(
                        x=_ac["Admin Sayısı"], y=_ac["Cihaz"],
                        marker_color=_ac_colors,
                        text=_ac["Cihaz"], textposition="outside",
                        textfont=dict(color="#C9D1D9"),
                        hovertemplate="<b>%{x} ekstra admin</b><br>%{y} cihaz<extra></extra>",
                    ))
                    _fga.update_layout(**DARK, height=260, showlegend=False,
                                       xaxis_title="Ekstra Admin Sayısı (_RawAdminCount)",
                                       yaxis_title="Cihaz Adedi")
                    st.plotly_chart(_fga, use_container_width=True)
                with _aa_col2:
                    sec("Kullanıcıya Göre Toplam Admin Riski", color="#D29922")
                    st.caption("📌 Kullanıcının tüm cihazlarındaki toplam ekstra admin sayısı. Yüksek = o kullanıcının cihazları özellikle riskli.")
                    if "Kullanıcı" in _adf.columns:
                        _uc = _adf.groupby("Kullanıcı")["_RawAdminCount"].sum().nlargest(10).reset_index()
                        _uc_colors = ["#8B1A1A" if v>5 else "#F85149" if v>2 else "#D29922" for v in _uc["_RawAdminCount"]]
                        _fgu = go.Figure(go.Bar(
                            x=_uc["_RawAdminCount"], y=_uc["Kullanıcı"], orientation="h",
                            marker_color=_uc_colors,
                            text=_uc["_RawAdminCount"], textposition="outside",
                            textfont=dict(color="#C9D1D9"),
                            hovertemplate="<b>%{y}</b><br>Toplam ekstra admin: %{x}<extra></extra>",
                        ))
                        _fgu.update_layout(**DARK, height=260, showlegend=False,
                                           xaxis_title="Toplam Ekstra Admin (_RawAdminCount)")
                        st.plotly_chart(_fgu, use_container_width=True)
                        _fgu_placeholder = True

                sec(f"Yetkisiz Admin Cihaz Listesi — {len(_adf)} Cihaz", color="#D29922")
                st.caption("📌 _RawAdminCount: Cihazdaki ekstra admin grubu üyesi sayısı. 'Kural Dışı Adminler' sütunu AD'den çekilen hesap isimlerini gösterir.")
                _cols_a = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress",
                                        "_RawAdminCount","Kural Dışı Adminler (İsim ve Ünvan)",
                                        "Final_Risk_Skoru","Seviye"]
                           if c in _adf.columns]
                show_table(_adf[_cols_a], height=440, sort_col="_RawAdminCount",
                           text_cols=["Kural Dışı Adminler (İsim ve Ünvan)"])
                _csv = _adf[_cols_a].to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Listeyi İndir (CSV)", _csv,
                                   f"yetkisiz_admin_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

            elif _key == "offline":
                _odf = df[df["Offline Gün"] > 60].sort_values("Offline Gün", ascending=False)                     if "Offline Gün" in df.columns else df.head(0)
                _max_off = int(_odf["Offline Gün"].max()) if len(_odf) else 0
                _o180    = int((_odf["Offline Gün"]>180).sum()) if len(_odf) else 0
                _o_oran  = round(len(_odf)/max(n,1)*100,1)
                _op_lbl  = "KRİTİK" if _o180>20 else "YÜKSEK" if len(_odf)>0 else "TEMİZ"
                _op_clr  = "#F85149" if _op_lbl=="KRİTİK" else "#79C0FF"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid {_op_clr};border-left:5px solid {_op_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_op_clr};font-weight:700;text-transform:uppercase">🤖 AI Offline Analizi</div>
    <div style="background:{_op_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">📴 {_op_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{len(_odf)}</b> cihaz (%{_o_oran}) 60+ gün offline. En uzun: <b>{_max_off} gün</b>.
    <b>{_o180}</b> cihaz 180+ gündür görünmüyor — bu cihazlar zombi statüsünde veya kaybolmuş olabilir.
    Ağa döndüklerinde tüm yamalardan mahrum ve tehlikeli durumda olacaklar.
  </div>
  <div style="font-size:11px;color:{_op_clr};font-weight:600;margin-top:6px">
    ⚡ {"180+ gün cihazları envanterden çıkar veya lokasyonunu belirle." if _o180>0 else "Offline cihazların ağa bağlanmadan önce zorunlu patch uygulaması yap."}
  </div>
</div>""", unsafe_allow_html=True)

                _oo_col1, _oo_col2 = st.columns(2)
                with _oo_col1:
                    sec("Offline Gün Dağılımı", color="#79C0FF")
                    _obins = [60,90,180,365,730,9999]
                    _oblbs = ["61-90g","91-180g","181-365g","1-2 Yıl","2+ Yıl"]
                    _odf["_ob"] = pd.cut(_odf["Offline Gün"], bins=_obins, labels=_oblbs, right=True)
                    _ob = _odf["_ob"].value_counts().reindex(_oblbs, fill_value=0).reset_index()
                    _ob.columns = ["Aralik","Cihaz"]
                    _fgo = px.bar(_ob, x="Aralik", y="Cihaz",
                                  color="Cihaz", color_continuous_scale=["#79C0FF","#58A6FF","#1F6FEB"],
                                  text="Cihaz")
                    _fgo.update_layout(**DARK, height=260, showlegend=False, coloraxis_showscale=False)
                    _fgo.update_traces(textposition="outside", textfont=dict(color="#C9D1D9"))
                    st.plotly_chart(_fgo, use_container_width=True)
                with _oo_col2:
                    sec("Şehre Göre Offline Cihaz", color="#79C0FF")
                    if "Sehir" in _odf.columns:
                        _oc2 = _odf[_odf["Sehir"].notna() & (_odf["Sehir"] != "None")]                               .groupby("Sehir").size().nlargest(10).reset_index()
                        _oc2.columns = ["Sehir","Cihaz"]
                        _fgoc = px.bar(_oc2, x="Cihaz", y="Sehir", orientation="h",
                                       color="Cihaz",
                                       color_continuous_scale=["#58A6FF","#1F6FEB"],
                                       text="Cihaz")
                        _fgoc.update_layout(**DARK, height=260, showlegend=False, coloraxis_showscale=False)
                        _fgoc.update_traces(textposition="outside", textfont=dict(color="#C9D1D9"))
                        st.plotly_chart(_fgoc, use_container_width=True)

                sec(f"Offline Cihaz Listesi — {len(_odf)} Cihaz", color="#79C0FF")
                _cols_o = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem",
                                        "Cihaz_Tipi","Offline Gün","Final_Risk_Skoru","Seviye"]
                           if c in _odf.columns]
                show_table(_odf[_cols_o], height=440, sort_col="Offline Gün")
                _csv = _odf[_cols_o].to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Listeyi İndir (CSV)", _csv,
                                   f"offline_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

            elif _key == "suphe_yazilim":
                _sdf = df[df["Tespit Edilen Şüpheli Yazılımlar"].ne("")]                       .sort_values("Final_Risk_Skoru", ascending=False)
                _s_oran = round(len(_sdf)/max(n,1)*100,1)
                _sp_lbl = "KRİTİK" if _s_oran>=20 else "YÜKSEK" if len(_sdf)>0 else "TEMİZ"
                _sp_clr = "#F85149" if _sp_lbl=="KRİTİK" else "#D2A8FF"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid {_sp_clr};border-left:5px solid {_sp_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_sp_clr};font-weight:700;text-transform:uppercase">🤖 AI Şüpheli Yazılım Analizi</div>
    <div style="background:{_sp_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">🦠 {_sp_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{len(_sdf)}</b> cihaz (%{_s_oran}) şüpheli/yasaklı yazılım barındırıyor.
    TeamViewer, AnyDesk, torrent, cracking araçları veri sızıntısı ve C2 kanal riski oluşturur.
    GPO application whitelist ile bu yazılımların çalışmasını engelle.
  </div>
  <div style="font-size:11px;color:{_sp_clr};font-weight:600;margin-top:6px">
    ⚡ GPO/SCCM ile uzaktan kaldırma scripti çalıştır, application whitelist politikası uygula.
  </div>
</div>""", unsafe_allow_html=True)

                # En çok hangi yazılımlar
                if "Tespit Edilen Şüpheli Yazılımlar" in _sdf.columns:
                    from collections import Counter as _Ctr
                    _all_sw = []
                    for _cell in _sdf["Tespit Edilen Şüpheli Yazılımlar"].dropna():
                        _all_sw.extend([s.strip() for s in str(_cell).split("|") if s.strip()])
                    if _all_sw:
                        _sw_cnt = _Ctr(_all_sw).most_common(12)
                        _sw_df  = pd.DataFrame(_sw_cnt, columns=["Yazılım","Cihaz"])
                        _sw_col1, _sw_col2 = st.columns([3, 2])
                        with _sw_col1:
                            sec("En Yaygın Şüpheli Yazılımlar", color="#D2A8FF")
                            _fgsw = px.bar(_sw_df.sort_values("Cihaz"), x="Cihaz", y="Yazılım",
                                           orientation="h",
                                           color="Cihaz",
                                           color_continuous_scale=["#8957E5","#D2A8FF"],
                                           text="Cihaz")
                            _fgsw.update_layout(**DARK, height=320, showlegend=False,
                                                coloraxis_showscale=False)
                            _fgsw.update_traces(textposition="outside", textfont=dict(color="#C9D1D9"))
                            st.plotly_chart(_fgsw, use_container_width=True)
                        with _sw_col2:
                            sec("Özet", color="#D2A8FF")
                            st.metric("Etkilenen Cihaz", len(_sdf))
                            st.metric("Farklı Yazılım", len(set(_all_sw)))
                            st.metric("En Yaygın", _sw_cnt[0][0] if _sw_cnt else "-")

                sec(f"Şüpheli Yazılım Cihaz Listesi — {len(_sdf)} Cihaz", color="#D2A8FF")
                _cols_s = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Cihaz_Tipi",
                                        "Final_Risk_Skoru","Seviye","Tespit Edilen Şüpheli Yazılımlar"]
                           if c in _sdf.columns]
                show_table(_sdf[_cols_s], height=440, sort_col="Final_Risk_Skoru",
                           text_cols=["Tespit Edilen Şüpheli Yazılımlar"])
                _csv = _sdf[_cols_s].to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Listeyi İndir (CSV)", _csv,
                                   f"suphe_yazilim_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

            elif _key == "eol_os":
                _edf = df[df["Sistem"].str.contains("Win 7|2008|8.1|XP|2012", na=False)]                       .sort_values("Final_Risk_Skoru", ascending=False)                        if "Sistem" in df.columns else df.head(0)
                _e_oran = round(len(_edf)/max(n,1)*100,1)
                _ep_lbl = "KRİTİK" if _e_oran>=10 else "YÜKSEK" if len(_edf)>0 else "TEMİZ"
                _ep_clr = "#F85149" if _ep_lbl=="KRİTİK" else "#FFA657"
                st.markdown(f"""<div style="background:#0D1117;border:1px solid {_ep_clr};border-left:5px solid {_ep_clr};
border-radius:10px;padding:14px 18px;margin:4px 0 14px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div style="font-size:10px;color:{_ep_clr};font-weight:700;text-transform:uppercase">🤖 AI EoL OS Analizi</div>
    <div style="background:{_ep_clr};color:#fff;font-size:10px;font-weight:700;padding:2px 10px;border-radius:20px">💀 {_ep_lbl}</div>
  </div>
  <div style="font-size:12px;color:#C9D1D9;line-height:1.7">
    <b>{len(_edf)}</b> cihaz (%{_e_oran}) End-of-Life işletim sistemi kullanıyor (Win 7/2008/8.1/XP/2012).
    Bu sistemler için Microsoft artık güvenlik yaması yayımlamıyor — tüm sıfır-gün açıkları kalıcı.
    Bu cihazlar ağda izole edilmeli veya acilen yükseltilmeli.
  </div>
  <div style="font-size:11px;color:{_ep_clr};font-weight:600;margin-top:6px">
    ⚡ Upgrade takvimi hazırla: Windows 10/11/Server 2019+. İzolasyon mümkünse VLAN ayır.
  </div>
</div>""", unsafe_allow_html=True)

                _eo_col1, _eo_col2 = st.columns(2)
                with _eo_col1:
                    sec("EoL OS Dağılımı", color="#FFA657")
                    _os_cnt = _edf["Sistem"].value_counts().reset_index()
                    _os_cnt.columns = ["OS","Cihaz"]
                    _fgeos = px.pie(_os_cnt, values="Cihaz", names="OS", hole=0.4,
                                    color_discrete_sequence=["#FFA657","#F85149","#D29922","#FF7B72"])
                    _fgeos.update_layout(**DARK, height=260, showlegend=True,
                                         legend=dict(font=dict(color="#C9D1D9",size=9)))
                    st.plotly_chart(_fgeos, use_container_width=True)
                with _eo_col2:
                    sec("EoL Cihaz Risk Skoru Dağılımı", color="#FFA657")
                    _fgeoh = px.histogram(_edf, x="Final_Risk_Skoru", nbins=15,
                                          color_discrete_sequence=["#FFA657"])
                    _fgeoh.add_vline(x=50, line_dash="dash", line_color="#F85149",
                                     annotation_text="Yüksek (50)")
                    _fgeoh.update_layout(**DARK, height=260)
                    st.plotly_chart(_fgeoh, use_container_width=True)

                sec(f"EoL OS Cihaz Listesi — {len(_edf)} Cihaz", color="#FFA657")
                _cols_e = [c for c in ["Lansweeper","AssetName","Kullanıcı","IPAddress","Sistem",
                                        "Cihaz_Tipi","Final_Risk_Skoru","Yamasız Gün","Seviye"]
                           if c in _edf.columns]
                show_table(_edf[_cols_e], height=440, sort_col="Final_Risk_Skoru")
                _csv = _edf[_cols_e].to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Listeyi İndir (CSV)", _csv,
                                   f"eol_os_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

    # ── B) RİSK TAHMİNİ — "Patlayacak Cihazlar" ────────────────────
    if DEVHIST_OK:
        st.markdown("---")
        sec("🔮 Risk Tahmini — 14 Gün İçinde Kritik Seviyeye Ulaşacak Cihazlar")
        st.caption("📌 Mevcut hızla devam ederse 14 gün içinde risk skoru 50'yi aşacak cihazlar. Önleyici aksiyon için ideal liste.")
        _pred_rows = []
        for _, _pr in df[df["Final_Risk_Skoru"] < 50].iterrows():
            _pan = str(_pr.get("AssetName",""))
            _ph  = gecmis_oku(_pan)
            _pt  = risk_tahmin(_ph, ileri_gun=14)
            if _pt["yeterli_veri"] and _pt["tahmin_seviye"] == "YÜKSEK" and _pt["trend"] == "yukseliyor":
                _pred_rows.append({
                    "Lansweeper":      _pr.get("Lansweeper",""),
                    "AssetName":       _pan,
                    "Kullanıcı":       _pr.get("Kullanıcı",""),
                    "Cihaz_Tipi":      _pr.get("Cihaz_Tipi",""),
                    "Mevcut Skor":     int(_pr.get("Final_Risk_Skoru",0)),
                    "14g Tahmini":     _pt["tahmin_skor"],
                    "Günlük Artış":    f"+{_pt['trend_hiz']:.1f}",
                    "Güven":           _pt["guven"],
                    "Seviye":          _pr.get("Seviye",""),
                })
        if _pred_rows:
            _pred_df = pd.DataFrame(_pred_rows).sort_values("14g Tahmini", ascending=False)
            n_pred = len(_pred_rows)
            st.markdown(f"""<div style="background:#0D1117;border-left:5px solid #8957E5;
border-radius:8px;padding:12px 16px;margin:6px 0 12px 0;font-size:12px;color:#C9D1D9">
  🔮 <b style="color:#8957E5">{n_pred} cihaz</b> mevcut trend devam ederse 14 gün içinde YÜKSEK risk seviyesine ulaşacak.
  Bu cihazlarda <b>şimdi önleyici aksiyon</b> alınması, kritik hale geldikten sonra müdahaleden çok daha kolaydır.
</div>""", unsafe_allow_html=True)
            show_table(_pred_df, height=380)
        else:
            st.info("Şu an için 14 günlük tahmininde YÜKSEK'e ulaşacak cihaz tespit edilmedi. Geçmiş verisi biriktikçe bu bölüm dolacak.")

    footer()


# ═══════════════════════════════════════════════════════════
# ANA UYGULAMA
# ═══════════════════════════════════════════════════════════
PAGES=[
    "📊 Executive Dashboard",
    "🚨 Önerilen Aksiyonlar",
    "🔒 Security Operations",
    "🖥️ Sunucu & Kritik",
    "💻 Cihaz Detay",
    "👤 Kullanıcı Riski",
    "⚠️ Asset Criticality",
    "🩹 Patch & Offline",
    "🦠 CVE İstihbaratı",
    "🔬 Anomali Tespiti",
    "⚔️ MITRE ATT&CK",
    "📋 CIS Uyum Skoru",
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
  <br>Designed by <b style="color:#484F58">hsaldiran</b>
</div>""", unsafe_allow_html=True)

        st.markdown(f"""
<div style="background:#161B22;border:1px solid #21262D;border-radius:8px;
padding:8px 10px;margin:6px 0;text-align:center">
  <div style="font-size:8px;color:#484F58;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">
    👁️ Ziyaret Sayısı</div>
  <div style="display:flex;justify-content:space-around;align-items:center">
    <div style="text-align:center">
      <div style="font-size:18px;font-weight:800;color:#58A6FF">{counter.get('total',0)}</div>
      <div style="font-size:8px;color:#484F58">Toplam</div>
    </div>
    <div style="width:1px;height:28px;background:#21262D"></div>
    <div style="text-align:center">
      <div style="font-size:18px;font-weight:800;color:#3FB950">{counter.get('today',0)}</div>
      <div style="font-size:8px;color:#484F58">Bugün</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # Sayfa yönlendirme
    if   page=="📊 Executive Dashboard":   page_executive(df,hist,counter,session_info)
    elif page=="🚨 Önerilen Aksiyonlar":   page_actions(df)
    elif page=="🔒 Security Operations":   page_security_ops(df,cve_data,cve_meta)
    elif page=="🖥️ Sunucu & Kritik":       page_servers(df)
    elif page=="💻 Cihaz Detay":           page_device(df)
    elif page=="👤 Kullanıcı Riski":       page_users(df)
    elif page=="⚠️ Asset Criticality":     page_criticality(df)
    elif page=="🩹 Patch & Offline":       page_patch(df)
    elif page=="🦠 CVE İstihbaratı":         page_cve(df,cve_data,cve_meta)
    elif page=="🔬 Anomali Tespiti":          page_anomali(df)
    elif page=="⚔️ MITRE ATT&CK":             page_mitre(df)
    elif page=="📋 CIS Uyum Skoru":            page_cis(df)

if __name__=="__main__":
    main()
