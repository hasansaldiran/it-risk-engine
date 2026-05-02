# -*- coding: utf-8 -*-
"""
lansweeper_sync.py — Otomatik Lansweeper Veri Senkronizasyonu
=============================================================
Bu script Lansweeper'ın export ettiği dosyayı otomatik olarak
doğru konuma kopyalar ve risk_engine'i tetikler.

KURULUM:
  1. Bu scripti scripts/ klasörüne koy
  2. CONFIG bölümünü düzenle (kaynak yol, hedef, saat)
  3. Windows Task Scheduler'a ekle:
     Tetikleyici: Her gün saat CONFIG["CALISMA_SAATI"]
     Eylem: python C:\\Users\\hsaldiran\\IT_Risk_Engine\\scripts\\lansweeper_sync.py

LANSWEEPER SCHEDULED REPORT KURULUMU:
  1. Lansweeper → Configuration → Scheduled Reports
  2. Yeni rapor oluştur: "IT Risk Export"
  3. Report Type: Asset List (tüm sütunlar seçili)
  4. Schedule: Her gün saat CONFIG["LANSWEEPER_EXPORT_SAATI"] (sync'ten 30dk önce)
  5. Output Format: Excel (.xlsx)
  6. Output Location: CONFIG["LANSWEEPER_EXPORT_DIR"] (ağ paylaşımı veya yerel klasör)
  7. Dosya adı: lansweeper_risk.xlsx (sabit isim)

PIP:
  pip install pandas openpyxl schedule
"""

import os, sys, shutil, json, logging, time, subprocess
from pathlib import Path
from datetime import datetime, timedelta

# ─── KONFIGÜRASYON ─────────────────────────────────────────────────────────
CONFIG = {
    # Lansweeper'ın Scheduled Report ile export ettiği dosyanın yolu
    # Ağ paylaşımı örneği: r"\\LANSWEEPER-SRV\Reports\lansweeper_risk.xlsx"
    # Yerel klasör örneği: r"C:\LansExports\lansweeper_risk.xlsx"
    "LANSWEEPER_EXPORT_PATH": r"\\LANSWEEPER-SRV\Reports\lansweeper_risk.xlsx",

    # Hedef: risk_engine'in okuduğu yer
    "HEDEF_DIR":  Path(__file__).parent.parent / "data" / "raw",

    # risk_engine çalıştırılsın mı? (True = tam pipeline)
    "ENGINE_OTOMATIK_CALISTIR": True,

    # Çalışma saati — Task Scheduler bu saatte tetikler
    "CALISMA_SAATI": "07:30",

    # Lansweeper export saati (bu saatten önce bu script çalışmamalı)
    "LANSWEEPER_EXPORT_SAATI": "07:00",

    # Dosya güncelleme kontrolü: en az X dakika önce güncellenmiş olmalı
    "MIN_DOSYA_YASI_DAKIKA": 5,

    # Dosya en fazla X saat önce oluşturulmuş olmalı (eski dosyayı işleme)
    "MAX_DOSYA_YASI_SAAT": 6,

    # Yedek klasör (eski dosyaları sakla)
    "YEDEK_AKTIF": True,
    "YEDEK_SAKLA_GUN": 30,
}

# ─── LOG KURULUMU ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "sync.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("sync")

# ─── YARDIMCI FONKSİYONLAR ─────────────────────────────────────────────────

def _dosya_yasi_kontrol(dosya_yolu: Path) -> tuple[bool, str]:
    """Dosyanın yaşını kontrol et — çok eski veya çok yeni dosyaları reddet."""
    if not dosya_yolu.exists():
        return False, f"Dosya bulunamadı: {dosya_yolu}"

    mod_time   = datetime.fromtimestamp(dosya_yolu.stat().st_mtime)
    simdi      = datetime.now()
    yas_dakika = (simdi - mod_time).total_seconds() / 60
    yas_saat   = yas_dakika / 60

    if yas_dakika < CONFIG["MIN_DOSYA_YASI_DAKIKA"]:
        return False, (f"Dosya çok yeni ({yas_dakika:.1f} dk önce değişti). "
                       f"Lansweeper hâlâ yazmıyor olabilir. {CONFIG['MIN_DOSYA_YASI_DAKIKA']} dakika bekle.")

    if yas_saat > CONFIG["MAX_DOSYA_YASI_SAAT"]:
        return False, (f"Dosya çok eski ({yas_saat:.1f} saat). "
                       f"Lansweeper Scheduled Report çalışmamış olabilir. "
                       f"Maksimum beklenen yaş: {CONFIG['MAX_DOSYA_YASI_SAAT']} saat.")

    return True, f"Dosya yaşı OK: {yas_dakika:.0f} dakika önce güncellendi"


def _yedekle(hedef_dosya: Path):
    """Mevcut dosyayı yedekle."""
    if not CONFIG["YEDEK_AKTIF"] or not hedef_dosya.exists():
        return

    yedek_dir = hedef_dosya.parent / "backup"
    yedek_dir.mkdir(parents=True, exist_ok=True)

    # Tarihe göre yedek adı
    tarih = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek_dosya = yedek_dir / f"lansweeper_risk_{tarih}.xlsx"
    shutil.copy2(hedef_dosya, yedek_dosya)
    log.info(f"  Yedeklendi → {yedek_dosya.name}")

    # Eski yedekleri temizle
    _eski_yedekleri_temizle(yedek_dir)


def _eski_yedekleri_temizle(yedek_dir: Path):
    """X günden eski yedekleri sil."""
    sinir = datetime.now() - timedelta(days=CONFIG["YEDEK_SAKLA_GUN"])
    silinen = 0
    for f in yedek_dir.glob("lansweeper_risk_*.xlsx"):
        try:
            mod = datetime.fromtimestamp(f.stat().st_mtime)
            if mod < sinir:
                f.unlink()
                silinen += 1
        except Exception:
            pass
    if silinen:
        log.info(f"  {silinen} eski yedek silindi ({CONFIG['YEDEK_SAKLA_GUN']}+ gün)")


def _boyut_kontrol(kaynak: Path, hedef: Path) -> tuple[bool, str]:
    """Yeni dosyanın makul boyutta olduğunu kontrol et."""
    yeni_boyut = kaynak.stat().st_size
    if hedef.exists():
        eski_boyut = hedef.stat().st_size
        fark_pct   = abs(yeni_boyut - eski_boyut) / max(eski_boyut, 1) * 100
        if fark_pct > 80:
            return False, (f"Dosya boyutu çok farklı! Eski: {eski_boyut/1024:.0f} KB, "
                           f"Yeni: {yeni_boyut/1024:.0f} KB ({fark_pct:.0f}% fark). "
                           "Lansweeper export hatalı olabilir.")
    if yeni_boyut < 10_000:  # 10 KB altı şüpheli
        return False, f"Dosya çok küçük ({yeni_boyut/1024:.1f} KB). Export eksik olabilir."
    return True, f"Boyut OK: {yeni_boyut/1024:.0f} KB"


def _satir_kontrol(kaynak: Path) -> tuple[bool, str, int]:
    """Excel'i okuyup satır sayısını kontrol et."""
    try:
        import pandas as pd
        df = pd.read_excel(kaynak, nrows=5)  # sadece başlık + 5 satır
        if len(df.columns) < 5:
            return False, f"Çok az sütun ({len(df.columns)}). Export yapısı değişmiş olabilir.", 0

        # Tam satır sayısı için tekrar oku (sadece index)
        df_full = pd.read_excel(kaynak, usecols=[0])
        satir   = len(df_full)

        if satir < 10:
            return False, f"Çok az cihaz ({satir}). Export hatalı olabilir.", satir

        return True, f"Satır sayısı OK: {satir} cihaz, {len(df.columns)} sütun", satir
    except Exception as e:
        return False, f"Excel okuma hatası: {e}", 0


def _durum_kaydet(durum: dict):
    """Son sync durumunu JSON'a kaydet (dashboard okuyabilsin)."""
    try:
        durum_dosya = BASE_DIR / "data" / "processed" / "sync_status.json"
        with open(durum_dosya, "w", encoding="utf-8") as f:
            json.dump(durum, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _engine_calistir():
    """risk_engine_v62.py'yi tetikle."""
    engine_path = Path(__file__).parent / "risk_engine_v62.py"
    if not engine_path.exists():
        log.error(f"risk_engine bulunamadı: {engine_path}")
        return False
    try:
        log.info("risk_engine_v62.py başlatılıyor...")
        result = subprocess.run(
            [sys.executable, str(engine_path)],
            capture_output=True, text=True, timeout=300,
            encoding="utf-8"
        )
        if result.returncode == 0:
            log.info("risk_engine tamamlandı ✅")
            return True
        else:
            log.error(f"risk_engine hata (returncode={result.returncode}):\n{result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        log.error("risk_engine zaman aşımı (300 saniye)")
        return False
    except Exception as e:
        log.error(f"risk_engine başlatılamadı: {e}")
        return False


# ─── ANA FONKSİYON ──────────────────────────────────────────────────────────

def sync():
    """Ana senkronizasyon fonksiyonu."""
    log.info("=" * 55)
    log.info(f"Lansweeper Sync başlıyor... {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    log.info("=" * 55)

    kaynak = Path(CONFIG["LANSWEEPER_EXPORT_PATH"])
    hedef  = Path(CONFIG["HEDEF_DIR"]) / "lansweeper_risk.xlsx"
    Path(CONFIG["HEDEF_DIR"]).mkdir(parents=True, exist_ok=True)

    sonuc = {
        "tarih":       datetime.now().isoformat(),
        "basarili":    False,
        "mesaj":       "",
        "cihaz_sayisi": 0,
        "kaynak":      str(kaynak),
        "hedef":       str(hedef),
    }

    # ── 1. Kaynak dosya var mı? ─────────────────────────────────
    if not kaynak.exists():
        mesaj = (f"HATA: Kaynak dosya bulunamadı: {kaynak}\n"
                 "Kontrol: Lansweeper Scheduled Report çalıştı mı? Ağ paylaşımı erişilebilir mi?")
        log.error(mesaj)
        sonuc["mesaj"] = mesaj
        _durum_kaydet(sonuc)
        return False

    # ── 2. Dosya yaşı kontrolü ───────────────────────────────────
    gecerli, msg = _dosya_yasi_kontrol(kaynak)
    log.info(f"  Yaş kontrolü: {msg}")
    if not gecerli:
        log.warning(f"UYARI: {msg}")
        sonuc["mesaj"] = msg
        _durum_kaydet(sonuc)
        return False

    # ── 3. Boyut kontrolü ────────────────────────────────────────
    gecerli, msg = _boyut_kontrol(kaynak, hedef)
    log.info(f"  Boyut kontrolü: {msg}")
    if not gecerli:
        log.error(f"HATA: {msg}")
        sonuc["mesaj"] = msg
        _durum_kaydet(sonuc)
        return False

    # ── 4. İçerik kontrolü ───────────────────────────────────────
    gecerli, msg, satir = _satir_kontrol(kaynak)
    log.info(f"  İçerik kontrolü: {msg}")
    if not gecerli:
        log.error(f"HATA: {msg}")
        sonuc["mesaj"] = msg
        _durum_kaydet(sonuc)
        return False

    # ── 5. Yedekle ───────────────────────────────────────────────
    _yedekle(hedef)

    # ── 6. Kopyala ───────────────────────────────────────────────
    try:
        shutil.copy2(kaynak, hedef)
        log.info(f"  ✅ Kopyalandı: {hedef.name} ({satir} cihaz)")
    except Exception as e:
        mesaj = f"Kopyalama hatası: {e}"
        log.error(mesaj)
        sonuc["mesaj"] = mesaj
        _durum_kaydet(sonuc)
        return False

    sonuc.update({"basarili": True, "mesaj": f"{satir} cihaz başarıyla aktarıldı.",
                  "cihaz_sayisi": satir})
    _durum_kaydet(sonuc)
    log.info(f"  Sync durumu kaydedildi → sync_status.json")

    # ── 7. risk_engine tetikle ───────────────────────────────────
    if CONFIG["ENGINE_OTOMATIK_CALISTIR"]:
        _engine_calistir()

    log.info("=" * 55)
    log.info(f"Sync tamamlandı ✅  {datetime.now().strftime('%H:%M:%S')}")
    log.info("=" * 55)
    return True


# ─── TASK SCHEDULER .BAT ÜRETİCİ ────────────────────────────────────────────

def bat_olustur():
    """
    Windows Task Scheduler için .bat dosyası oluşturur.
    CMD'de: python lansweeper_sync.py --bat
    """
    bat_icerik = f"""@echo off
REM IT Risk Engine — Lansweeper Otomatik Sync
REM Task Scheduler bu dosyayı her gün {CONFIG["CALISMA_SAATI"]}'de çalıştırır
cd /d %~dp0
python lansweeper_sync.py >> "..\logs\sync_bat.log" 2>&1
echo [%date% %time%] Sync tamamlandı >> "..\logs\sync_bat.log"
"""
    bat_path = Path(__file__).parent / "run_sync.bat"
    bat_path.write_text(bat_icerik, encoding="utf-8")
    print(f"\n✅ run_sync.bat oluşturuldu: {bat_path}")
    print("\nTask Scheduler Kurulumu:")
    print("  1. 'Görev Zamanlayıcı' aç (Task Scheduler)")
    print("  2. Eylem → Temel Görev Oluştur")
    print(f"  3. Tetikleyici: Her gün, saat {CONFIG['CALISMA_SAATI']}")
    print(f"  4. Eylem: run_sync.bat dosyasını çalıştır")
    print(f"  5. Başlangıç klasörü: {Path(__file__).parent}")
    print("\nPowerShell ile otomatik kayıt (Yönetici olarak çalıştır):")
    script_path = str(bat_path).replace("\\", "\\\\")
    print(f"""
$action  = New-ScheduledTaskAction -Execute "{bat_path}"
$trigger = New-ScheduledTaskTrigger -Daily -At "{CONFIG['CALISMA_SAATI']}"
$settings= New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "ITRiskEngineSync" \\
    -Action $action -Trigger $trigger -Settings $settings \\
    -Description "IT Risk Engine - Lansweeper Otomatik Veri Sync" \\
    -RunLevel Highest
""")


# ─── ENTRY POINT ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--bat" in sys.argv:
        bat_olustur()
    elif "--test" in sys.argv:
        # Test modu: engine çalıştırmadan sadece dosya kontrolü yap
        CONFIG["ENGINE_OTOMATIK_CALISTIR"] = False
        sync()
    else:
        sync()
