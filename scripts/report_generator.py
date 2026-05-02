# -*- coding: utf-8 -*-
"""
report_generator.py — Haftalık Otomatik HTML Raporu
====================================================
risk_engine çalıştıktan sonra otomatik tetiklenir.
Yönetici dostu, tek sayfalık, baskıya hazır HTML çıktısı.

ÇIKTI: output/reports/IT_RISK_HAFTALIK_YYYYMMDD.html

KURULUM:
  risk_engine_v62.py sonuna şu satırı ekle:
    from report_generator import rapor_olustur
    rapor_olustur(df, cve_data, hist)

  veya ayrı çalıştır:
    python scripts/report_generator.py
"""

import os, sys, json
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# ─── YOLLAR ─────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
PROC_DIR      = BASE_DIR / "data" / "processed"
REPORTS_DIR   = BASE_DIR / "output" / "reports"
HISTORY_FILE  = PROC_DIR / "risk_history.json"
CLEAN_DATA    = PROC_DIR / "risk_data_current.xlsx"
CVE_META_FILE = PROC_DIR / "cve_meta.json"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TARIH    = datetime.now().strftime("%Y%m%d")
TARIH_TR = datetime.now().strftime("%d.%m.%Y")
HAFTA    = datetime.now().strftime("Hafta %V — %B %Y")


# ─── RAPORLAMA FONKSİYONU ────────────────────────────────────────────────────

def rapor_olustur(df=None, cve_data=None, hist=None):
    """
    Ana rapor üretici.
    df       : risk_data DataFrame (None ise CLEAN_DATA'dan okur)
    cve_data : dict (None ise atlar)
    hist     : list[dict] (None ise HISTORY_FILE'dan okur)
    """

    # ── 1. Veriyi yükle ──────────────────────────────────────────
    if df is None:
        if not CLEAN_DATA.exists():
            print(f"[RAPOR] Veri bulunamadı: {CLEAN_DATA}")
            return None
        df = pd.read_excel(CLEAN_DATA)

    if hist is None:
        try:
            hist = json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []
        except Exception:
            hist = []

    if cve_data is None:
        try:
            _cf = PROC_DIR / "cve_meta.json"
            cve_data = json.loads(_cf.read_text()) if _cf.exists() else {}
        except Exception:
            cve_data = {}

    # ── 2. Metrikleri hesapla ─────────────────────────────────────
    n     = len(df)
    nh    = int((df["Seviye"] == "YÜKSEK").sum())
    nm    = int((df["Seviye"] == "ORTA").sum())
    nl    = int((df["Seviye"] == "DÜŞÜK").sum())
    avg   = round(float(df["Final_Risk_Skoru"].mean()), 1) if n > 0 else 0
    pc    = int((df["Yamasız Gün"] > 60).sum())  if "Yamasız Gün" in df.columns else 0
    p180  = int((df["Yamasız Gün"] > 180).sum()) if "Yamasız Gün" in df.columns else 0
    oc    = int((df["Offline Gün"] > 60).sum())  if "Offline Gün" in df.columns else 0
    adm   = int(df["_RawAdminCount"].gt(0).sum()) if "_RawAdminCount" in df.columns else 0
    disk  = int((df["% Boş"] < 10).sum())         if "% Boş" in df.columns else 0
    wu    = int(df["_RawUpdateStop"].gt(0).sum())  if "_RawUpdateStop" in df.columns else 0
    ec    = int(df["Sistem"].str.contains("Win 7|2008|8.1|XP|2012", na=False).sum()) if "Sistem" in df.columns else 0
    shd   = int(df["Tespit Edilen Şüpheli Yazılımlar"].ne("").sum()) if "Tespit Edilen Şüpheli Yazılımlar" in df.columns else 0
    p_oran = round(pc / max(n, 1) * 100, 1)
    h_oran = round(nh / max(n, 1) * 100, 1)

    # Postür skoru
    posture = max(0, min(100, int(100 - (
        nh / max(n, 1) * 50 + pc / max(n, 1) * 30 + oc / max(n, 1) * 20
    ))))
    posture_clr = "#e74c3c" if posture < 40 else "#f39c12" if posture < 65 else "#27ae60"
    posture_lbl = "KRİTİK" if posture < 40 else "ORTA" if posture < 65 else "İYİ"

    # Trend — geçen haftayla kıyasla
    trend_html = ""
    if len(hist) >= 2:
        onceki = hist[-2]
        simdi  = hist[-1]
        d_h    = simdi["yuksek"] - onceki["yuksek"]
        d_avg  = round(simdi.get("avg", avg) - onceki.get("avg", avg), 1)
        d_clr  = "#27ae60" if d_h < 0 else "#e74c3c" if d_h > 0 else "#95a5a6"
        d_icon = "↓" if d_h < 0 else "↑" if d_h > 0 else "→"
        trend_html = f"""
        <div class="trend-box">
          <span class="trend-arrow" style="color:{d_clr}">{d_icon} {abs(d_h)}</span>
          yüksek riskli cihaz {'azaldı' if d_h < 0 else 'arttı' if d_h > 0 else 'değişmedi'}
          &nbsp;|&nbsp; Ort. risk: <b style="color:{d_clr}">
            {''+str(d_avg) if d_avg > 0 else str(d_avg)} puan</b>
        </div>"""

    # Trend sparkline (son 14 gün)
    spark_html = ""
    if len(hist) >= 3:
        recent = hist[-14:] if len(hist) >= 14 else hist
        vals   = [h["yuksek"] for h in recent]
        mx     = max(vals) or 1
        bars   = ""
        for i, v in enumerate(vals):
            h_pct  = max(4, int(v / mx * 40))
            clr    = "#e74c3c" if v == mx else "#f39c12" if v > mx * 0.6 else "#27ae60"
            is_last = " style='opacity:1'" if i == len(vals) - 1 else ""
            bars   += f'<div class="spark-bar" style="height:{h_pct}px;background:{clr}"{is_last}></div>'
        spark_html = f'<div class="sparkline">{bars}</div>'

    # En riskli 10 cihaz
    top10 = df.nlargest(10, "Final_Risk_Skoru")
    top10_html = ""
    for _, r in top10.iterrows():
        sev_clr = "#e74c3c" if r.get("Seviye") == "YÜKSEK" else "#f39c12" if r.get("Seviye") == "ORTA" else "#27ae60"
        lsw_url = str(r.get("Lansweeper", ""))
        isim    = str(r.get("AssetName", "?"))
        link    = f'<a href="{lsw_url}" style="color:#3498db;text-decoration:none">{isim}</a>' if lsw_url and lsw_url.startswith("http") else isim
        top10_html += f"""
        <tr>
          <td>{link}</td>
          <td>{r.get('Kullanıcı', '-')}</td>
          <td>{r.get('Cihaz_Tipi', '-')}</td>
          <td style="color:{sev_clr};font-weight:700">{int(r.get('Final_Risk_Skoru', 0))}</td>
          <td>{int(r.get('Yamasız Gün', 0))}g</td>
          <td style="color:{sev_clr};font-weight:700">{r.get('Seviye', '-')}</td>
        </tr>"""

    # Tehdit özeti
    ra = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)
    tehditler = {
        "Onaysız Yönetici": int(ra.str.contains("Onaysız Yönetici", na=False).sum()),
        "DLP Eksik":        int(ra.str.contains("DLP", na=False).sum()),
        "AV Eksik":         int(ra.str.contains("Antivirüs", na=False).sum()),
        "Patch Eksik":      pc,
        "EoL OS":           ec,
        "Şüpheli Yazılım":  shd,
        "Riskli Paylaşım":  int(ra.str.contains("Riskli Paylaşım", na=False).sum()),
    }
    tehdit_html = ""
    for t, c in sorted(tehditler.items(), key=lambda x: -x[1]):
        if c > 0:
            t_oran = round(c / max(n, 1) * 100, 1)
            t_bar  = min(100, t_oran)
            t_clr  = "#e74c3c" if t_oran > 30 else "#f39c12" if t_oran > 10 else "#f1c40f"
            tehdit_html += f"""
            <div class="threat-row">
              <div class="threat-label">{t}</div>
              <div class="threat-bar-wrap">
                <div class="threat-bar" style="width:{t_bar}%;background:{t_clr}"></div>
              </div>
              <div class="threat-count" style="color:{t_clr}">{c} &nbsp;<span style="color:#95a5a6;font-size:10px">%{t_oran}</span></div>
            </div>"""

    # Aksiyon maddeleri
    aksiyonlar = []
    if nh > 0:
        aksiyonlar.append(("🔴 ACİL", f"{nh} yüksek riskli cihazı incele ve patch operasyonu başlat", "#e74c3c"))
    if p180 > 0:
        aksiyonlar.append(("🔴 ACİL", f"{p180} cihaz 180+ gün yamasız — WSUS sağlığını kontrol et", "#e74c3c"))
    if adm > 0:
        aksiyonlar.append(("🟡 YÜKSEK", f"{adm} cihazdaki yetkisiz admin hesaplarını AD'den kaldır", "#f39c12"))
    if ec > 0:
        aksiyonlar.append(("🟡 YÜKSEK", f"{ec} EoL cihaz için upgrade takvimi hazırla", "#f39c12"))
    if disk > 0:
        aksiyonlar.append(("🟠 ORTA", f"{disk} cihazda disk kritik (%90+) — temizleme scripti çalıştır", "#e67e22"))
    if wu > 0:
        aksiyonlar.append(("🟠 ORTA", f"{wu} cihazda WU servisi kapalı — GPO ile zorla", "#e67e22"))
    if oc > 0:
        aksiyonlar.append(("🔵 BİLGİ", f"{oc} cihaz 60+ gün offline — envanter güncelle", "#3498db"))

    aksiyonlar_html = ""
    for seviye, metin, clr in aksiyonlar:
        aksiyonlar_html += f"""
        <div class="action-item" style="border-left:4px solid {clr}">
          <span class="action-sev" style="color:{clr}">{seviye}</span>
          <span class="action-text">{metin}</span>
        </div>"""

    # ── 3. HTML Şablonu ───────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IT Risk Raporu — {TARIH_TR}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Inter',sans-serif; background:#f0f2f5; color:#2c3e50; font-size:13px; }}

  .page {{ max-width:1100px; margin:0 auto; padding:20px; }}

  /* Başlık */
  .header {{ background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
             color:#fff; border-radius:12px; padding:28px 32px;
             display:flex; justify-content:space-between; align-items:center;
             margin-bottom:20px; }}
  .header h1 {{ font-size:22px; font-weight:800; margin-bottom:4px; }}
  .header .sub {{ color:rgba(255,255,255,0.55); font-size:11px; }}
  .posture-box {{ text-align:center; background:rgba(255,255,255,0.06);
                  border-radius:10px; padding:14px 22px; border:1px solid rgba(255,255,255,0.1); }}
  .posture-num {{ font-size:36px; font-weight:900; color:{posture_clr}; line-height:1; }}
  .posture-lbl {{ font-size:10px; color:rgba(255,255,255,0.5); text-transform:uppercase; margin-top:3px; }}
  .posture-sub {{ font-size:11px; color:{posture_clr}; font-weight:700; margin-top:2px; }}

  /* KPI'lar */
  .kpi-grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:10px; margin-bottom:20px; }}
  .kpi-card {{ background:#fff; border-radius:10px; padding:14px 12px; text-align:center;
               box-shadow:0 2px 8px rgba(0,0,0,0.06); border-top:3px solid #e0e0e0; }}
  .kpi-num {{ font-size:24px; font-weight:800; line-height:1; margin:4px 0 2px; }}
  .kpi-lbl {{ font-size:9px; color:#95a5a6; text-transform:uppercase; font-weight:600; }}
  .kpi-sub {{ font-size:10px; color:#bdc3c7; margin-top:1px; }}

  /* İki kolon layout */
  .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }}
  .grid-3 {{ display:grid; grid-template-columns:2fr 1fr; gap:16px; margin-bottom:20px; }}
  .card {{ background:#fff; border-radius:10px; padding:18px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }}
  .card h3 {{ font-size:12px; font-weight:700; color:#2c3e50; text-transform:uppercase;
              letter-spacing:.04em; margin-bottom:12px; padding-bottom:8px;
              border-bottom:2px solid #f0f2f5; }}

  /* Trend */
  .trend-box {{ background:#f8f9fa; border-radius:6px; padding:8px 12px; font-size:11px;
                color:#7f8c8d; margin-bottom:10px; }}
  .trend-arrow {{ font-size:15px; font-weight:700; }}
  .sparkline {{ display:flex; align-items:flex-end; gap:2px; height:44px;
                background:#f8f9fa; border-radius:6px; padding:4px 6px;
                margin-top:8px; }}
  .spark-bar {{ min-width:8px; border-radius:2px 2px 0 0; opacity:0.65;
                transition:opacity .2s; }}

  /* Tehdit barları */
  .threat-row {{ display:flex; align-items:center; gap:8px; padding:5px 0;
                 border-bottom:1px solid #f0f2f5; }}
  .threat-label {{ width:120px; font-size:11px; color:#34495e; flex-shrink:0; }}
  .threat-bar-wrap {{ flex:1; background:#f0f2f5; border-radius:4px; height:8px; overflow:hidden; }}
  .threat-bar {{ height:100%; border-radius:4px; min-width:4px; }}
  .threat-count {{ width:60px; text-align:right; font-size:11px; font-weight:700; }}

  /* Tablo */
  table {{ width:100%; border-collapse:collapse; }}
  th {{ background:#f8f9fa; font-size:10px; font-weight:700; color:#7f8c8d;
        text-transform:uppercase; padding:8px 10px; text-align:left;
        border-bottom:2px solid #ecf0f1; }}
  td {{ padding:7px 10px; font-size:11px; border-bottom:1px solid #f8f9fa; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#fafbfc; }}

  /* Aksiyonlar */
  .action-item {{ background:#fff; border-radius:6px; padding:10px 14px;
                  margin-bottom:8px; display:flex; gap:10px; align-items:flex-start;
                  box-shadow:0 1px 4px rgba(0,0,0,0.05); }}
  .action-sev {{ font-size:10px; font-weight:700; white-space:nowrap; min-width:70px; }}
  .action-text {{ font-size:12px; color:#34495e; }}

  /* Footer */
  .footer {{ text-align:center; color:#bdc3c7; font-size:10px; margin-top:24px; padding-top:16px;
             border-top:1px solid #ecf0f1; }}

  /* Baskı */
  @media print {{
    body {{ background:#fff; }}
    .page {{ padding:0; max-width:100%; }}
    .header {{ border-radius:0; }}
    .kpi-card, .card {{ box-shadow:none; border:1px solid #ecf0f1; }}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- BAŞLIK ────────────────────────────────────────────── -->
  <div class="header">
    <div>
      <div class="sub">🛡️ IT RISK INTELLIGENCE PLATFORM</div>
      <h1>Haftalık Risk Raporu</h1>
      <div class="sub" style="margin-top:4px">{TARIH_TR} &nbsp;|&nbsp; {HAFTA}</div>
      {f'<div style="margin-top:10px">{trend_html}</div>' if trend_html else ''}
    </div>
    <div style="display:flex;gap:16px;align-items:center">
      {spark_html}
      <div class="posture-box">
        <div class="posture-lbl">Güvenlik Postürü</div>
        <div class="posture-num">{posture}</div>
        <div style="background:{posture_clr};color:#fff;font-size:9px;
             padding:1px 8px;border-radius:10px;margin-top:4px;display:inline-block">{posture_lbl}</div>
      </div>
    </div>
  </div>

  <!-- KPI'LAR ───────────────────────────────────────────── -->
  <div class="kpi-grid">
    <div class="kpi-card" style="border-top-color:#3498db">
      <div class="kpi-lbl">🖥️ Toplam Cihaz</div>
      <div class="kpi-num" style="color:#3498db">{n:,}</div>
      <div class="kpi-sub">Ort. risk: {avg}</div>
    </div>
    <div class="kpi-card" style="border-top-color:#e74c3c">
      <div class="kpi-lbl">🔴 Yüksek Risk</div>
      <div class="kpi-num" style="color:#e74c3c">{nh:,}</div>
      <div class="kpi-sub">%{h_oran}</div>
    </div>
    <div class="kpi-card" style="border-top-color:#e67e22">
      <div class="kpi-lbl">🩹 Patch 60g+</div>
      <div class="kpi-num" style="color:#e67e22">{pc:,}</div>
      <div class="kpi-sub">%{p_oran}</div>
    </div>
    <div class="kpi-card" style="border-top-color:#9b59b6">
      <div class="kpi-lbl">👤 Yetk. Admin</div>
      <div class="kpi-num" style="color:#9b59b6">{adm:,}</div>
      <div class="kpi-sub">&nbsp;</div>
    </div>
    <div class="kpi-card" style="border-top-color:#e74c3c">
      <div class="kpi-lbl">💀 EoL OS</div>
      <div class="kpi-num" style="color:#e74c3c">{ec:,}</div>
      <div class="kpi-sub">&nbsp;</div>
    </div>
    <div class="kpi-card" style="border-top-color:#7f8c8d">
      <div class="kpi-lbl">📴 Offline 60g+</div>
      <div class="kpi-num" style="color:#7f8c8d">{oc:,}</div>
      <div class="kpi-sub">&nbsp;</div>
    </div>
  </div>

  <!-- ANA İÇERİK ────────────────────────────────────────── -->
  <div class="grid-3">
    <!-- Sol: En riskli cihazlar -->
    <div class="card">
      <h3>⚠️ En Riskli 10 Cihaz</h3>
      <table>
        <thead>
          <tr>
            <th>Cihaz</th><th>Kullanıcı</th><th>Tip</th>
            <th>Skor</th><th>Yamasız</th><th>Seviye</th>
          </tr>
        </thead>
        <tbody>{top10_html}</tbody>
      </table>
    </div>

    <!-- Sağ: Tehdit özeti + Aksiyonlar -->
    <div>
      <div class="card" style="margin-bottom:16px">
        <h3>🎯 Tehdit Dağılımı</h3>
        {tehdit_html if tehdit_html else '<p style="color:#95a5a6;font-size:11px">Aktif tehdit yok</p>'}
      </div>
    </div>
  </div>

  <!-- AKSİYONLAR ────────────────────────────────────────── -->
  <div class="card" style="margin-bottom:20px">
    <h3>⚡ Bu Hafta Yapılacaklar</h3>
    {aksiyonlar_html if aksiyonlar_html else '<p style="color:#27ae60;font-size:12px">✅ Bu hafta kritik aksiyon gerektiren durum tespit edilmedi.</p>'}
  </div>

  <!-- FOOTER ────────────────────────────────────────────── -->
  <div class="footer">
    IT Risk Intelligence Platform &nbsp;|&nbsp; Otomatik üretildi: {datetime.now().strftime("%d.%m.%Y %H:%M")}
    &nbsp;|&nbsp; <b>hsaldiran</b>
    &nbsp;|&nbsp; Bu rapor {n} cihaz üzerinde analiz yapılarak hazırlanmıştır.
  </div>

</div>
</body>
</html>
"""

    # ── 4. Kaydet ────────────────────────────────────────────────
    out_html = REPORTS_DIR / f"IT_RISK_HAFTALIK_{TARIH}.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"[RAPOR] HTML raporu kaydedildi → {out_html}")
    print(f"[RAPOR] Tarayıcıda aç veya Dosya→Yazdır ile PDF'e çevir")

    # "Latest" kopyası — her zaman aynı isimle bulunabilsin
    out_latest = REPORTS_DIR / "IT_RISK_SON_RAPOR.html"
    out_latest.write_text(html, encoding="utf-8")

    return str(out_html)


# ─── STANDALONE ÇALIŞMA ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Rapor üretiliyor...")
    sonuc = rapor_olustur()
    if sonuc:
        print(f"Tamamlandı: {sonuc}")
    else:
        print("HATA: Veri bulunamadı. Önce risk_engine_v62.py çalıştırın.")
