# -*- coding: utf-8 -*-
"""
launcher.py — IT Risk Engine Kontrol Merkezi v7.0
Calistir.bat bu dosyayi cagiriyor.

Gunluk is akisi:
  [1] Veri Cek: Risk         → lansweeper_risk.xlsx
  [2] Veri Cek: Yazilim      → lansweeper_software.xlsx
  [3] CVE Tarama             → haftalik / gerektiginde
  ────────────────────────────────
  [4] Tam Analiz             → risk + anomali + gecmis + rapor
  [5] Anomali Guncelle       → sadece anomali
  [6] Sadece HTML Rapor      → son veriden rapor
  ────────────────────────────────
  [7] MITRE Haritasi
  [8] CIS Uyum Raporu
  ────────────────────────────────
  [9]  Dashboard Ac
  [10] Dashboard Kapat
  ────────────────────────────────
  [L]  Log Dosyasini Ac
  [0]  Cikis
"""

import os, sys, shutil, subprocess, json
from pathlib import Path
from datetime import datetime
import time

# ── ANSI renk kodlari ─────────────────────────────────────────
RST  = "\033[0m"
BLD  = "\033[1m"
DIM  = "\033[2m"
RED  = "\033[91m"
GRN  = "\033[92m"
YLW  = "\033[93m"
BLU  = "\033[94m"
MAG  = "\033[95m"
CYN  = "\033[96m"
WHT  = "\033[97m"
ORN  = "\033[38;5;208m"   # turuncu

# Windows'ta ANSI'yi aktif et
if sys.platform == "win32":
    os.system("color 0")
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)

# ── YOLLAR ────────────────────────────────────────────────────
BASE    = Path(__file__).parent.parent
SCRIPTS = BASE / "scripts"
RAW     = BASE / "data" / "raw"
PROC    = BASE / "data" / "processed"

# Lansweeper export URL'leri
LSW_RISK_URL = (
    "http://LANSWEEPER_HOST:81/export.aspx"
    "?export=xls&det=web50repa708189d18f54a03b1bf873a2155f749"
)
LSW_SW_URL = (
    "http://LANSWEEPER_HOST:81/export.aspx"
    "?export=xls&det=web50rep58b7bbecdee24c18922700c4900e6302"
)

# Dosya hedefleri
RISK_HEDEF = RAW / "lansweeper_risk.xlsx"
SW_HEDEF   = RAW / "lansweeper_software.xlsx"
LOG_FILE   = BASE / "logs" / "engine.log"
RAPOR      = BASE / "output" / "reports" / "IT_RISK_SON_RAPOR.html"
SW_CHANGES = PROC / "software_changes.json"


# ── YARDIMCILAR ───────────────────────────────────────────────

def cls():
    os.system("cls" if sys.platform == "win32" else "clear")


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def pause(msg="  Devam etmek icin ENTER'a basin..."):
    ask(f"\n{DIM}{msg}{RST}")


def run(script_name, extra_args=None):
    """Bir Python scriptini calistir, ciktisini canli goster."""
    p = SCRIPTS / script_name
    if not p.exists():
        print(f"\n{RED}  HATA: {p} bulunamadi!{RST}")
        return False
    cmd = [sys.executable, str(p)] + (extra_args or [])
    result = subprocess.run(cmd, cwd=str(BASE))
    return result.returncode == 0


def _dosya_yasi(path: Path) -> str:
    """Dosyanın son değiştirilme zamanını kısa string olarak döndür."""
    if not path.exists():
        return f"{RED}YOK{RST}"
    delta = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    zaman = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m %H:%M")
    if h < 2:
        return f"{GRN}{zaman} ({h}s {m}dk önce){RST}"
    elif h < 12:
        return f"{YLW}{zaman} ({h} saat önce){RST}"
    else:
        return f"{ORN}{zaman} ({h} saat önce — güncellemeli){RST}"


def banner():
    print(f"""
{BLU}{BLD}  +=============================================================+
  ||   IT Risk Engine   Intelligence Platform  v7.0          ||
  ||                       by  h s a l d i r a n             ||
  +=============================================================+{RST}""")


def status_bar():
    """Mevcut veri durumunu göster."""
    print(f"\n  {DIM}┌─ Veri Durumu {'─'*42}┐{RST}")
    print(f"  {DIM}│{RST}  Risk verisi    : {_dosya_yasi(RISK_HEDEF)}")
    print(f"  {DIM}│{RST}  Yazilim env.   : {_dosya_yasi(SW_HEDEF)}")

    # Yazılım değişim özeti
    if SW_CHANGES.exists():
        try:
            c = json.loads(SW_CHANGES.read_text(encoding="utf-8"))
            n_y = len(c.get("yeni_yazilim", []))
            n_s = len(c.get("suphe_yeni", []))
            tarih = c.get("tarih", "?")
            suphe_str = f"  {RED}{BLD}⚠ {n_s} suphe yeni!{RST}" if n_s > 0 else ""
            print(f"  {DIM}│{RST}  SW degisimler  : {DIM}{tarih}{RST} → "
                  f"{GRN}+{n_y} yeni{RST}{suphe_str}")
        except Exception:
            pass

    rapor_str = f"{GRN}var{RST}" if RAPOR.exists() else f"{DIM}yok{RST}"
    print(f"  {DIM}│{RST}  Son rapor      : {rapor_str}")
    print(f"  {DIM}└{'─'*54}┘{RST}\n")


# ── MENÜ ──────────────────────────────────────────────────────

def menu():
    while True:
        cls()
        banner()
        status_bar()
        print(f"""\
  {DIM}── VERİ TOPLAMA {'─'*38}{RST}
    {CYN}[1]{RST}  {WHT}Risk Verisi Cek       {DIM}Lansweeper'dan risk xlsx indir{RST}
    {CYN}[2]{RST}  {WHT}Yazilim Envanteri Cek {DIM}Lansweeper'dan software xlsx indir{RST}
    {MAG}[3]{RST}  {WHT}CVE Tarama            {DIM}NIST NVD — haftalik / gerektiginde{RST}

  {DIM}── ANALİZ {'─'*44}{RST}
    {YLW}[4]{RST}  {BLD}{WHT}Tam Analiz            {RST}{DIM}risk + anomali + gecmis + rapor{RST}
    {YLW}[5]{RST}  {WHT}Anomali Guncelle      {DIM}son veriden anomali hesapla{RST}
    {YLW}[6]{RST}  {WHT}Sadece HTML Rapor     {DIM}son veriden rapor olustur{RST}

  {DIM}── İSTİHBARAT {'─'*40}{RST}
    {BLU}[7]{RST}  {WHT}MITRE ATT&CK Haritasi {DIM}tehdit-teknik analizi{RST}
    {BLU}[8]{RST}  {WHT}CIS Uyum Raporu       {DIM}compliance skoru hesapla{RST}

  {DIM}── DASHBOARD {'─'*41}{RST}
    {GRN}[9]{RST}  {WHT}Dashboard Ac          {DIM}http://localhost:8501{RST}
    {RED}[10]{RST} {WHT}Dashboard Kapat{RST}

  {DIM}── DİĞER {'─'*45}{RST}
    {DIM}[L]  Log Dosyasini Ac{RST}
    {DIM}[0]  Cikis{RST}
  {DIM}{'─'*54}{RST}
""")
        secim = ask(f"  {BLD}{WHT}Seciminiz: {RST}").upper()

        if   secim == "1":  risk_veri_cek()
        elif secim == "2":  yazilim_veri_cek()
        elif secim == "3":  cve_tara()
        elif secim == "4":  tam_analiz()
        elif secim == "5":  anomali()
        elif secim == "6":  rapor()
        elif secim == "7":  mitre_rapor()
        elif secim == "8":  cis_rapor()
        elif secim == "9":  dashboard_ac()
        elif secim == "10": dashboard_kapat()
        elif secim == "L":  log_ac()
        elif secim == "0":  cikis()
        else:
            print(f"\n  {RED}Gecersiz secim.{RST}")
            time.sleep(1)


# ── [1] RİSK VERİSİ ÇEK ──────────────────────────────────────

def risk_veri_cek():
    cls()
    print(f"\n{CYN}{BLD}  +---------------------------------------------+")
    print(f"  |  [1] LANSWEEPER RİSK VERİSİ ÇEKİLİYOR...   |")
    print(f"  +---------------------------------------------+{RST}")
    _lansweeper_indir(
        url=LSW_RISK_URL,
        hedef=RISK_HEDEF,
        aciklama="Risk Raporu (lansweeper_risk.xlsx)",
        sonraki_soru="Analizi hemen calistirmak ister misiniz? (E/H)",
        sonraki_fn=tam_analiz,
    )


# ── [2] YAZILIM ENVANTERİ ÇEK ────────────────────────────────

def yazilim_veri_cek():
    cls()
    print(f"\n{CYN}{BLD}  +---------------------------------------------+")
    print(f"  |  [2] YAZILIM ENVANTERİ ÇEKİLİYOR...        |")
    print(f"  +---------------------------------------------+{RST}")
    print(f"  {DIM}Kaynak: Software Inventory raporu{RST}")
    print(f"  {DIM}Hedef : {SW_HEDEF}{RST}\n")

    ok = _lansweeper_indir(
        url=LSW_SW_URL,
        hedef=SW_HEDEF,
        aciklama="Yazilim Envanteri (lansweeper_software.xlsx)",
        sonraki_soru=None,
        sonraki_fn=None,
    )

    if ok:
        print(f"\n  {YLW}Yazilim degisim analizi yapiliyor...{RST}")
        ok2 = run("software_tracker.py")
        if ok2:
            # Değişim özetini göster
            if SW_CHANGES.exists():
                try:
                    c = json.loads(SW_CHANGES.read_text(encoding="utf-8"))
                    n_y = len(c.get("yeni_yazilim", []))
                    n_k = len(c.get("kaldirilan", []))
                    n_g = len(c.get("guncellenen", []))
                    n_s = len(c.get("suphe_yeni", []))
                    print(f"\n  {GRN}Degisim Ozeti:{RST}")
                    print(f"  {GRN}+{n_y}{RST} yeni yazilim  "
                          f"{RED}-{n_k}{RST} kaldirilmis  "
                          f"{BLU}↑{n_g}{RST} guncellenmis")
                    if n_s > 0:
                        print(f"\n  {RED}{BLD}  ⚠  {n_s} SUPHE YAZILIM YENİ KURULMUŞ!{RST}")
                        for s in c["suphe_yeni"][:5]:
                            print(f"  {RED}     {s['cihaz']:<25} {s['yazilim']}{RST}")
                        if n_s > 5:
                            print(f"  {RED}     ... ve {n_s-5} tane daha{RST}")
                except Exception:
                    pass
        cevap = ask(f"\n  {BLD}{WHT}Analizi simdi calistirmak ister misiniz? (E/H): {RST}")
        if cevap.upper() == "E":
            tam_analiz()
            return
    pause()


# ── [3] CVE TARAMA ───────────────────────────────────────────

def cve_tara():
    cls()
    print(f"\n{MAG}{BLD}  +---------------------------------------------+")
    print(f"  |  [3] CVE TARAMA BASLATILIYOR...             |")
    print(f"  +---------------------------------------------+{RST}")
    print(f"  {DIM}NIST NVD'den guncel CVE bilgileri cekilecek.{RST}")
    print(f"  {DIM}Internet hizina gore 5-30 dakika surebilir.{RST}")
    print(f"  {DIM}Tarama bitince Tam Analiz (4) calistirin.{RST}\n")
    ok = run("cve_scanner_last.py")
    if ok:
        print(f"\n  {GRN}OK CVE tarama tamamlandi!{RST}")
        print(f"  {DIM}Sonuclar: data/processed/cve_results_*.xlsx{RST}\n")
        cevap = ask(f"  {BLD}{WHT}Analizi simdi calistirmak ister misiniz? (E/H): {RST}")
        if cevap.upper() == "E":
            tam_analiz()
            return
    else:
        print(f"\n  {RED}CVE tarama basarisiz.{RST}")
        print(f"  {DIM}Kontrol: internet baglantisi var mi?{RST}")
    pause()


# ── [4] TAM ANALİZ ───────────────────────────────────────────

def tam_analiz():
    cls()
    print(f"\n{YLW}{BLD}  +---------------------------------------------+")
    print(f"  |  [4] TAM ANALİZ BASLIYOR...                 |")
    print(f"  +---------------------------------------------+{RST}")
    print(f"  {DIM}Adimlar: Risk Engine → Anomali → Gecmis → Rapor{RST}")

    # Risk verisini kontrol et
    if not RISK_HEDEF.exists():
        print(f"\n  {RED}HATA: Risk verisi bulunamadi!{RST}")
        print(f"  {YLW}Once [1] Risk Verisi Cek'i calistirin.{RST}")
        pause()
        return

    # Yazılım envanteri uyarısı
    if not SW_HEDEF.exists():
        print(f"  {YLW}UYARI: Yazilim envanteri yok — [2] ile cekilmedi.{RST}")
        print(f"  {DIM}Analiz devam ediyor ama yazilim degisim takibi calismayacak.{RST}\n")

    ok = run("risk_engine_v62.py")
    if ok:
        print(f"\n  {GRN}OK Analiz tamamlandi!{RST}")
        print(f"  {DIM}Excel/PPTX  →  output/reports/  ve  output/alerts/{RST}")
        print(f"  {DIM}HTML Rapor  →  output/reports/IT_RISK_SON_RAPOR.html{RST}")
        print(f"  {DIM}Dashboard   →  data/processed/risk_data_current.xlsx{RST}")
        print(f"  {DIM}Gecmis      →  data/processed/device_history/{RST}")
    else:
        print(f"\n  {RED}HATA olustu. Log dosyasini kontrol edin ([L]).{RST}")
    pause()


# ── [5] ANOMALİ GÜNCELLE ─────────────────────────────────────

def anomali():
    cls()
    print(f"\n{YLW}{BLD}  +---------------------------------------------+")
    print(f"  |  [5] ANOMALİ TESPİTİ CALISTIRILIYOR...     |")
    print(f"  +---------------------------------------------+{RST}\n")
    ok = run("anomaly_engine.py")
    if ok:
        print(f"\n  {GRN}OK Tamamlandi!{RST}")
        print(f"  {DIM}Dashboard 'Anomali Tespiti' sayfasini yenileyin.{RST}")
    pause()


# ── [6] SADECE RAPOR ─────────────────────────────────────────

def rapor():
    cls()
    print(f"\n{YLW}{BLD}  +---------------------------------------------+")
    print(f"  |  [6] HTML RAPORU OLUSTURULUYOR...           |")
    print(f"  +---------------------------------------------+{RST}\n")
    ok = run("report_generator.py")
    if ok:
        print(f"\n  {GRN}OK Rapor olusturuldu!{RST}")
        print(f"  {DIM}Konum: output/reports/IT_RISK_SON_RAPOR.html{RST}")
    pause()


# ── [7] MITRE ATT&CK ─────────────────────────────────────────

def mitre_rapor():
    cls()
    print(f"\n{BLU}{BLD}  +---------------------------------------------+")
    print(f"  |  [7] MITRE ATT&CK TEHDIT HARITASI           |")
    print(f"  +---------------------------------------------+{RST}")
    print(f"\n  {DIM}Mevcut risk verisi MITRE tekniklerine eslestirilecek.{RST}")
    print(f"  {DIM}Veri disari cikmaz — tamamen yerel islem.{RST}\n")
    try:
        sys.path.insert(0, str(SCRIPTS))
        import pandas as pd
        from mitre_mapper import df_to_technique_counts
        clean = PROC / "risk_data_current.xlsx"
        if not clean.exists():
            print(f"  {RED}Veri bulunamadi. Once [4] Tam Analiz calistirin.{RST}")
            pause(); return
        df = pd.read_excel(clean)
        tech_df = df_to_technique_counts(df)
        aktif   = tech_df[tech_df["Etkilenen"] > 0]
        kritik  = aktif[aktif["Risk"] == "Kritik"]
        print(f"  {GRN}OK Analiz tamamlandi!{RST}")
        print(f"  {WHT}Aktif teknik : {GRN}{len(aktif)}{RST}   "
              f"Kritik : {RED}{len(kritik)}{RST}")
        if len(aktif) > 0:
            print(f"\n  {DIM}En cok etkilenen teknikler:{RST}")
            for _, r in aktif.head(6).iterrows():
                clr = RED if r["Risk"] == "Kritik" else YLW
                print(f"  {clr}  [{r['ID']}]{RST}  {r['Türkçe']:<35} "
                      f"{WHT}{r['Etkilenen']} cihaz{RST}")
        print(f"\n  {DIM}Detay icin Dashboard → MITRE ATT&CK sayfasini acin.{RST}")
    except ImportError:
        print(f"  {YLW}mitre_mapper.py scripts/ klasorunde bulunamadi.{RST}")
    except Exception as e:
        print(f"  {RED}HATA: {e}{RST}")
    pause()


# ── [8] CIS UYUM RAPORU ──────────────────────────────────────

def cis_rapor():
    cls()
    print(f"\n{BLU}{BLD}  +---------------------------------------------+")
    print(f"  |  [8] CIS CONTROLS v8 UYUM SKORU            |")
    print(f"  +---------------------------------------------+{RST}\n")
    try:
        sys.path.insert(0, str(SCRIPTS))
        import pandas as pd
        from compliance_engine import cis_hesapla, genel_uyum_skoru
        clean = PROC / "risk_data_current.xlsx"
        if not clean.exists():
            print(f"  {RED}Veri bulunamadi. Once [4] Tam Analiz calistirin.{RST}")
            pause(); return
        df    = pd.read_excel(clean)
        sonuc = cis_hesapla(df)
        ozet  = genel_uyum_skoru(sonuc)
        g_clr = GRN if ozet["genel_skor"] >= 75 else YLW if ozet["genel_skor"] >= 50 else RED
        print(f"  {WHT}Genel CIS Uyum Skoru : {g_clr}{BLD}{ozet['genel_skor']}/100  "
              f"[{ozet['lbl']}]{RST}")
        print(f"  {WHT}IG1 Temel Skor       : {ozet['ig1_skor']}/100{RST}")
        print(f"  {GRN}Uyumlu               : {ozet['uyumlu']}/{ozet['toplam']}{RST}")
        print(f"  {YLW}Kismen Uyumlu        : {ozet['kismen']}/{ozet['toplam']}{RST}")
        print(f"  {RED}Uyumsuz              : {ozet['uyumsuz']}/{ozet['toplam']}{RST}")
        uyumsuzlar = [(n,v) for n,v in sonuc.items() if v["durum"] == "UYUMSUZ"]
        if uyumsuzlar:
            print(f"\n  {RED}Uyumsuz Kontroller:{RST}")
            for n, v in uyumsuzlar:
                print(f"  {RED}  CIS {n:2d}{RST}: {v['baslik'][:50]}")
        print(f"\n  {DIM}Detay icin Dashboard → CIS Uyum Skoru sayfasini acin.{RST}")
    except ImportError:
        print(f"  {YLW}compliance_engine.py scripts/ klasorunde bulunamadi.{RST}")
    except Exception as e:
        print(f"  {RED}HATA: {e}{RST}")
    pause()


# ── [9] DASHBOARD AÇ ─────────────────────────────────────────

def _port_acik_mi(port=8501) -> bool:
    """Port kullanımda mı kontrol et."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) == 0


def dashboard_ac():
    cls()
    print(f"\n{GRN}{BLD}  +---------------------------------------------+")
    print(f"  |  [9] DASHBOARD BASLATILIYOR...              |")
    print(f"  +---------------------------------------------+{RST}")

    if _port_acik_mi(8501):
        print(f"\n  {YLW}Dashboard zaten çalışıyor!{RST}")
        print(f"  {GRN}Adres: http://localhost:8501{RST}")
        # Yerel IP'yi göster
        import socket as _sock
        try:
            _ip = _sock.gethostbyname(_sock.gethostname())
            print(f"  {GRN}Ağdan:  http://{_ip}:8501{RST}")
        except Exception:
            pass
        print(f"\n  {DIM}Yeni sekme açmak için tarayıcıda bu adresi ziyaret edin.{RST}")
        pause()
        return

    print(f"\n  {WHT}Adres: {GRN}http://localhost:8501{RST}")
    print(f"  {DIM}Durdurmak icin Ctrl+C veya [10] kullanin.{RST}\n")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(SCRIPTS / "dashboard.py"),
        "--server.address", "0.0.0.0",
        "--server.port", "8501",
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false",
    ], cwd=str(BASE))
    pause()


# ── [10] DASHBOARD KAPAT ─────────────────────────────────────

def dashboard_kapat():
    cls()
    print(f"\n  {YLW}Dashboard prosesi durduruluyor...{RST}")
    if sys.platform == "win32":
        os.system("taskkill /f /im streamlit.exe >nul 2>&1")
        os.system("taskkill /f /im python.exe /fi \"WINDOWTITLE eq streamlit\" >nul 2>&1")
    print(f"  {GRN}OK Durduruldu.{RST}")
    time.sleep(1)


# ── [L] LOG ──────────────────────────────────────────────────

def log_ac():
    cls()
    if LOG_FILE.exists():
        if sys.platform == "win32":
            os.startfile(str(LOG_FILE))
            print(f"  {GRN}Log dosyasi acildi: {LOG_FILE.name}{RST}")
        else:
            subprocess.run(["tail", "-50", str(LOG_FILE)])
    else:
        print(f"\n  {YLW}Log dosyasi henuz olusturulmamis.{RST}")
        print(f"  {DIM}Once [4] Tam Analiz calistirin.{RST}")
    pause()


# ── [0] ÇIKIŞ ────────────────────────────────────────────────

def cikis():
    cls()
    print(f"\n  {DIM}IT Risk Engine kapatiliyor... Gorusuruz!{RST}\n")
    time.sleep(1)
    sys.exit(0)


# ── ORTAK: LANSWEEPER İNDİR ──────────────────────────────────

def _lansweeper_indir(url: str, hedef: Path, aciklama: str,
                      sonraki_soru, sonraki_fn) -> bool:
    """
    PowerShell ile Lansweeper'dan dosya indir.
    Windows kimlik bilgileriyle (integrated auth) çalışır.
    Returns True if downloaded successfully.
    """
    RAW.mkdir(parents=True, exist_ok=True)

    # Mevcut dosyayı yedekle
    if hedef.exists():
        yedek = hedef.with_suffix(".xlsx.yedek")
        shutil.copy2(hedef, yedek)
        print(f"  {DIM}Eski dosya yedeklendi → {yedek.name}{RST}")

    print(f"  {YLW}İndiriliyor: {aciklama}...{RST}\n")

    ps_cmd = (
        f"try {{"
        f"  [System.Net.ServicePointManager]::SecurityProtocol = 'Tls12,Tls11,Tls';"
        f"  $wc = New-Object System.Net.WebClient;"
        f"  $wc.UseDefaultCredentials = $true;"
        f"  $wc.DownloadFile('{url}', '{hedef}');"
        f"  Write-Host 'INDIRILDI';"
        f"}} catch {{"
        f"  Write-Host ('HATA:' + $_.Exception.Message);"
        f"  exit 1;"
        f"}}"
    )

    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=120
    )
    output = (result.stdout + result.stderr).strip()

    if result.returncode != 0 or "HATA:" in output:
        hata_msg = output.replace("HATA:", "").strip()
        print(f"  {RED}İndirme basarisiz!{RST}")
        print(f"  {DIM}Hata: {hata_msg[:120]}{RST}\n")
        print(f"  {YLW}Olasi nedenler:{RST}")
        print(f"  {DIM}  1. Lansweeper sunucusuna erisim yok{RST}")
        print(f"  {DIM}  2. Windows kimlik dogrulamasi calismiyor{RST}")
        print(f"  {DIM}  3. Rapor URL'si degismis{RST}")
        print(f"\n  {WHT}Manuel alternatif:{RST}")
        print(f"  {DIM}  Tarayicidan indir: {url[:65]}...{RST}")
        print(f"  {DIM}  Hedef konum: {hedef}{RST}\n")
        yol = ask(f"  {WHT}Dosya yolunu yapistirin (bos=iptal): {RST}")
        if yol:
            yol = Path(yol.strip('"').strip("'"))
            if yol.exists():
                shutil.copy2(yol, hedef)
                print(f"\n  {GRN}OK Dosya kopyalandi.{RST}")
                return True
            else:
                print(f"\n  {RED}Dosya bulunamadi: {yol}{RST}")
        return False

    if hedef.exists() and hedef.stat().st_size > 5000:
        boyut_kb = hedef.stat().st_size // 1024
        print(f"  {GRN}OK Indirildi! ({boyut_kb} KB) → {hedef.name}{RST}")
        if sonraki_soru and sonraki_fn:
            cevap = ask(f"\n  {BLD}{WHT}{sonraki_soru}: {RST}")
            if cevap.upper() == "E":
                sonraki_fn()
                return True
        return True
    else:
        print(f"  {RED}Dosya cok kucuk/bos — export hatali olabilir!{RST}")
        return False


# ── ENTRY ─────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print(f"\n\n  {DIM}Kapatildi.{RST}\n")
        sys.exit(0)
