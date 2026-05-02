# -*- coding: utf-8 -*-
"""
device_history_engine.py — Cihaz Bazlı Risk Geçmişi, Şeffaflık & Tahmin
=========================================================================
3 bağımsız işlev bir arada:

1. gecmis_kaydet(df)
   Her risk_engine çalıştığında her cihazın günlük skorunu kaydeder.
   data/processed/device_history/<AssetName>.json

2. gecmis_oku(asset_name) → list[dict]
   Bir cihazın geçmiş kayıtlarını döndürür.

3. puan_dokumu(row) → list[dict]
   Bir cihazın risk skorunun madde madde dökümünü üretir.
   "Neden 65 puan?" sorusunu yanıtlar.

4. tahmin(gecmis) → dict
   Son N ölçümden lineer projeksiyon yaparak gelecek skoru tahmin eder.
   "Bu cihaz 2 haftaya YÜKSEK seviyeye ulaşacak" çıktısı verir.

Veri gizliliği: Hiçbir veri dışarı çıkmaz. Tamamen yerel dosya sistemi.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# ─── YOLLAR ─────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent
PROC_DIR        = BASE_DIR / "data" / "processed"
DEVICE_HIST_DIR = PROC_DIR / "device_history"

# ─── PUAN DÖKÜM KURALLARI ────────────────────────────────────────────────────
# Her kural: (sütun_adı, koşul, puan, etiket, açıklama)
# koşul: lambda row → bool
PUAN_KURALLARI = [
    # ── Kritik katman ──────────────────────────────────────────────────────
    (None,
     lambda r: r.get("AD_Enabled", 1) == 0 or
               (r.get("Offline Gün", 0) > 60 and r.get("AssetStateCode", 1) != 1),
     25, "AD Devre Dışı / Uzun Offline",
     "Cihaz AD'de devre dışı veya 60+ gün offline — aktif tehdit yüzeyi."),

    ("Risk Analizi",
     lambda r: "DLP Yüklü Değil" in str(r.get("Risk Analizi", "")),
     18, "DLP (EDPA) Eksik",
     "Endpoint DLP olmadan USB/e-posta ile veri sızdırılabilir."),

    ("Risk Analizi",
     lambda r: "Antivirüs (SEP) Eksik" in str(r.get("Risk Analizi", "")),
     18, "Antivirüs Eksik",
     "SEP olmayan cihaz ransomware için açık hedeftir."),

    ("Risk Analizi",
     lambda r: "Onaysız Yönetici" in str(r.get("Risk Analizi", "")),
     18, "Yetkisiz Admin",
     "Standart dışı admin üyeliği lateral movement riskidir."),

    # ── Yüksek katman ─────────────────────────────────────────────────────
    ("Risk Analizi",
     lambda r: "Riskli Paylaşım" in str(r.get("Risk Analizi", "")),
     13, "Riskli SMB Paylaşımı",
     "Herkese açık SMB paylaşımları ransomware yayılma vektörüdür."),

    ("Risk Analizi",
     lambda r: "Desteklenmeyen OS" in str(r.get("Risk Analizi", "")) or
               "EoL" in str(r.get("Risk Analizi", "")),
     13, "EoL İşletim Sistemi",
     "End-of-Life OS için güvenlik yaması artık çıkmıyor."),

    ("Risk Analizi",
     lambda r: "Şüpheli Yazılım" in str(r.get("Risk Analizi", "")),
     10, "Şüpheli/Yasaklı Yazılım",
     "Kontrolsüz yazılımlar C2 kanalı ve veri sızdırma riski taşır."),

    ("Risk Analizi",
     lambda r: "Antivirüs Güncel Değil" in str(r.get("Risk Analizi", "")),
     8, "AV Güncel Değil",
     "Kurulu ama güncellenmeyen AV yeni tehditlere karşı kör."),

    ("Yamasız Gün",
     lambda r: float(r.get("Yamasız Gün", 0)) > 60,
     8, "60+ Gün Yamasız",
     f"Son yamadan bu yana geçen süre kritik eşiği aştı."),

    # ── Orta katman ────────────────────────────────────────────────────────
    ("Risk Analizi",
     lambda r: "WSUS" in str(r.get("Risk Analizi", "")) or
               "Patch Bağlantısı" in str(r.get("Risk Analizi", "")),
     7, "WSUS Bağlantısı Kopuk",
     "Son 90 günde patch alınmamış — WSUS bağlantısı yok."),

    ("Risk Analizi",
     lambda r: "RDP Açık" in str(r.get("Risk Analizi", "")),
     6, "RDP Açık (Workstation)",
     "Workstation'da açık RDP lateral movement kapısıdır."),

    # ── Düşük katman ────────────────────────────────────────────────────────
    ("Risk Analizi",
     lambda r: "Update Servisi Kapalı" in str(r.get("Risk Analizi", "")),
     5, "WU Servisi Kapalı",
     "Windows Update servisi durdurulmuş."),

    ("Risk Analizi",
     lambda r: "Güvenlik Merkezi Kapalı" in str(r.get("Risk Analizi", "")),
     4, "Güvenlik Merkezi Kapalı",
     "wscsvc servisi kapalı — Windows Security Center devre dışı."),

    ("Risk Analizi",
     lambda r: "Sabit Şifreli Admin" in str(r.get("Risk Analizi", "")),
     4, "Sabit Şifreli Admin",
     "PasswordNeverExpires bayrağı aktif hesap var."),

    ("Risk Analizi",
     lambda r: "Uzun Süredir Giriş Yok" in str(r.get("Risk Analizi", "")),
     4, "Zombi Cihaz",
     "90+ gün kullanıcı girişi olmayan cihaz."),

    ("% Boş",
     lambda r: float(r.get("% Boş", 100)) < 10,
     4, "Disk Alanı Kritik",
     f"Disk doluluk %90+ — log kaybı ve servis çökmesi riski."),

    ("_RawDiskError",
     lambda r: float(r.get("_RawDiskError", 0)) > 0,
     3, "Disk I/O Hatası",
     "Donanım seviyesinde disk hatası tespit edildi."),

    ("Risk Analizi",
     lambda r: "Eski Tarayıcı" in str(r.get("Risk Analizi", "")),
     3, "Eski Tarayıcı Sürümü",
     "Chrome/Firefox eski sürüm — aktif CVE kampanya hedefi."),
]


# ─── 1. GEÇMİŞ KAYDET ───────────────────────────────────────────────────────

def gecmis_kaydet(df: pd.DataFrame) -> int:
    """
    Tüm cihazların günlük risk skorunu kaydeder.
    data/processed/device_history/<AssetName>.json

    Returns: kaydedilen cihaz sayısı
    """
    DEVICE_HIST_DIR.mkdir(parents=True, exist_ok=True)
    bugun    = datetime.now().strftime("%Y-%m-%d")
    kaydedilen = 0

    for _, row in df.iterrows():
        asset = str(row.get("AssetName", "")).strip()
        if not asset or asset in ("nan", "None", ""):
            continue

        # Dosya adında sorun çıkaracak karakterleri temizle
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in asset)
        hist_path = DEVICE_HIST_DIR / f"{safe_name}.json"

        # Mevcut geçmişi yükle
        try:
            mevcut = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
        except Exception:
            mevcut = []

        # Bugün zaten var mı?
        if mevcut and mevcut[-1].get("tarih") == bugun:
            # Güncelle — aynı gün tekrar çalışırsa üzerine yaz
            mevcut[-1] = _satir_olustur(row, bugun)
        else:
            mevcut.append(_satir_olustur(row, bugun))

        # En fazla 90 gün sakla
        mevcut = mevcut[-90:]

        try:
            hist_path.write_text(json.dumps(mevcut, ensure_ascii=False), encoding="utf-8")
            kaydedilen += 1
        except Exception:
            pass

    return kaydedilen


def _satir_olustur(row, tarih: str) -> dict:
    """Bir cihaz satırından geçmiş kaydı oluştur."""
    return {
        "tarih":       tarih,
        "skor":        int(row.get("Final_Risk_Skoru", 0)),
        "ham":         int(row.get("Risk Skoru", 0)),
        "seviye":      str(row.get("Seviye", "")),
        "yamasiz":     int(row.get("Yamasız Gün", 0)),
        "offline":     int(row.get("Offline Gün", 0)),
        "cve":         int(row.get("CVE_Bonus", 0)),
        "anomali":     int(row.get("Anomali_Skoru", 0)) if "Anomali_Skoru" in row.index else 0,
        "ra_hash":     hash(str(row.get("Risk Analizi", ""))) % 99999,  # içeriği saklamadan değişti mi?
    }


# ─── 2. GEÇMİŞ OKU ──────────────────────────────────────────────────────────

def gecmis_oku(asset_name: str) -> list[dict]:
    """
    Bir cihazın geçmiş kayıtlarını döndürür.
    Returns: [{tarih, skor, seviye, ...}, ...]  sıra: eskiden yeniye
    """
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in asset_name.strip())
    hist_path  = DEVICE_HIST_DIR / f"{safe_name}.json"
    if not hist_path.exists():
        return []
    try:
        return json.loads(hist_path.read_text(encoding="utf-8"))
    except Exception:
        return []


# ─── 3. PUAN DÖKÜM ──────────────────────────────────────────────────────────

def puan_dokumu(row) -> list[dict]:
    """
    Bir cihaz satırından madde madde puan dökümü üretir.

    Returns: [
        {etiket, puan, aciklama, aktif},
        ...
    ]
    aktif=True → bu cihazda bu madde geçerli, puan sayılıyor
    """
    sonuc = []
    for sütun, kosul, puan, etiket, aciklama in PUAN_KURALLARI:
        try:
            aktif = bool(kosul(row))
        except Exception:
            aktif = False
        sonuc.append({
            "etiket":    etiket,
            "puan":      puan,
            "aciklama":  aciklama,
            "aktif":     aktif,
        })

    # Sıralama: aktif olanlar önce, sonra puana göre
    sonuc.sort(key=lambda x: (-x["aktif"], -x["puan"]))
    return sonuc


def puan_ozeti(row) -> dict:
    """
    Puan dökümünü özetler: ham toplam, çarpan, final, madde listesi.
    """
    dokum    = puan_dokumu(row)
    aktifler = [d for d in dokum if d["aktif"]]
    ham_puan = sum(d["puan"] for d in aktifler)
    carpan   = float(row.get("Crit_Multiplier", 1.0))
    bonus    = int(row.get("Crit_Bonus", 0))
    cve_b    = int(row.get("CVE_Bonus", 0))
    ham_sql  = int(row.get("Risk Skoru", 0))
    final    = int(row.get("Final_Risk_Skoru", 0))

    return {
        "ham_sql":       ham_sql,     # SQL'den gelen orijinal ham skor
        "carpan":        carpan,
        "bonus":         bonus,
        "cve_bonus":     cve_b,
        "hesaplanan":    ham_puan,    # Python kurallarından hesaplanan
        "final":         final,
        "aktif_maddeler": aktifler,
        "pasif_maddeler": [d for d in dokum if not d["aktif"]],
    }


# ─── 4. TAHMİN MOTORU ────────────────────────────────────────────────────────

def tahmin(gecmis: list[dict], ileri_gun: int = 14) -> dict:
    """
    Geçmiş veriden lineer projeksiyon ile gelecek skoru tahmin eder.
    Minimum 3 ölçüm gerekir.

    Parameters
    ----------
    gecmis    : gecmis_oku() çıktısı
    ileri_gun : kaç gün ilerisi için tahmin yapılacak (varsayılan 14)

    Returns
    -------
    {
        "yeterli_veri": bool,
        "trend":        "yukseliyor" | "dusuyor" | "stabil",
        "trend_hiz":    float,       # günlük ortalama değişim
        "tahmin_skor":  int,         # ileri_gun sonraki tahmini skor
        "tahmin_seviye": str,
        "uyari":        str | None,  # uyarı mesajı
        "mesaj":        str,         # dashboard'da gösterilecek metin
        "guven":        str,         # "yüksek" | "orta" | "düşük"
        "veri_sayisi":  int,
    }
    """
    if len(gecmis) < 3:
        return {
            "yeterli_veri":  False,
            "trend":         "bilinmiyor",
            "trend_hiz":     0.0,
            "tahmin_skor":   0,
            "tahmin_seviye": "?",
            "uyari":         None,
            "mesaj":         f"Tahmin için en az 3 ölçüm gerekli. Şu an: {len(gecmis)}.",
            "guven":         "yok",
            "veri_sayisi":   len(gecmis),
        }

    # Son 21 günü al (daha eskisi gürültü yaratır)
    son = gecmis[-21:]
    skorlar = [g["skor"] for g in son]
    n       = len(skorlar)

    # Lineer regresyon (numpy ile, basit)
    x = np.arange(n, dtype=float)
    y = np.array(skorlar, dtype=float)
    A = np.vstack([x, np.ones(n)]).T
    try:
        egim, baslangic = np.linalg.lstsq(A, y, rcond=None)[0]
    except Exception:
        egim = 0.0

    # Trend hızı (günlük)
    hiz = round(float(egim), 2)

    # Tahmin: mevcut son skor + egim × ileri_gun
    mevcut     = skorlar[-1]
    tahmin_ham = mevcut + hiz * ileri_gun
    tahmin_skor = max(0, min(100, int(round(tahmin_ham))))

    # Trend etiketi
    if abs(hiz) < 0.2:
        trend = "stabil"
    elif hiz > 0:
        trend = "yukseliyor"
    else:
        trend = "dusuyor"

    # Tahmin seviye
    if tahmin_skor >= 50:
        tahmin_seviye = "YÜKSEK"
    elif tahmin_skor >= 25:
        tahmin_seviye = "ORTA"
    else:
        tahmin_seviye = "DÜŞÜK"

    # Güven skoru: veri sayısı ve lineerlik
    sapma = float(np.std(y - (egim * x + baslangic)))
    if n >= 10 and sapma < 5:
        guven = "yüksek"
    elif n >= 5:
        guven = "orta"
    else:
        guven = "düşük"

    # Uyarı oluştur
    uyari = None
    mevcut_seviye = "YÜKSEK" if mevcut >= 50 else "ORTA" if mevcut >= 25 else "DÜŞÜK"

    if trend == "yukseliyor" and tahmin_seviye == "YÜKSEK" and mevcut_seviye != "YÜKSEK":
        uyari = (f"⚠️ {ileri_gun} gün içinde YÜKSEK risk seviyesine ulaşabilir! "
                 f"Günlük artış hızı: +{hiz:.1f} puan/gün.")
    elif trend == "yukseliyor" and mevcut_seviye == "YÜKSEK":
        uyari = f"🔴 Risk zaten YÜKSEK ve artmaya devam ediyor. Günlük: +{hiz:.1f} puan."
    elif trend == "dusuyor" and mevcut_seviye == "YÜKSEK" and tahmin_seviye != "YÜKSEK":
        uyari = f"✅ İyileşiyor: {ileri_gun} gün sonra ORTA/DÜŞÜK seviyeye düşmesi bekleniyor."

    # Mesaj
    trend_tr = {"yukseliyor": "📈 Yükseliyor", "dusuyor": "📉 Düşüyor", "stabil": "⟳ Stabil"}[trend]
    mesaj = (
        f"{trend_tr} · Günlük {'+'if hiz>=0 else ''}{hiz:.1f} puan · "
        f"{ileri_gun}g sonraki tahmin: **{tahmin_skor}/100** ({tahmin_seviye}) · "
        f"Güven: {guven}"
    )

    return {
        "yeterli_veri":  True,
        "trend":         trend,
        "trend_hiz":     hiz,
        "tahmin_skor":   tahmin_skor,
        "tahmin_seviye": tahmin_seviye,
        "uyari":         uyari,
        "mesaj":         mesaj,
        "guven":         guven,
        "veri_sayisi":   n,
        "skorlar":       skorlar,  # grafik için
        "egim":          float(egim),
    }


# ─── STANDALONE TEST ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    clean = PROC_DIR / "risk_data_current.xlsx"
    if not clean.exists():
        print("HATA: risk_data_current.xlsx bulunamadı.")
        sys.exit(1)

    print("Veri yükleniyor...")
    df = pd.read_excel(clean)
    print(f"{len(df)} cihaz yüklendi.")

    print("\nGeçmiş kaydediliyor...")
    n = gecmis_kaydet(df)
    print(f"{n} cihaz geçmişe kaydedildi → {DEVICE_HIST_DIR}")

    # İlk cihazı test et
    if len(df) > 0:
        row = df.iloc[0]
        asset = row.get("AssetName", "?")
        print(f"\nTest cihazı: {asset}")

        ozet = puan_ozeti(row)
        print(f"\nPuan Dökümü:")
        print(f"  SQL Ham Skor : {ozet['ham_sql']}")
        print(f"  Çarpan       : {ozet['carpan']}")
        print(f"  CVE Bonus    : +{ozet['cve_bonus']}")
        print(f"  Final        : {ozet['final']}")
        print(f"\n  Aktif maddeler ({len(ozet['aktif_maddeler'])}):")
        for m in ozet["aktif_maddeler"]:
            print(f"    +{m['puan']:2d}  {m['etiket']}")

        gecmis = gecmis_oku(asset)
        if gecmis:
            t = tahmin(gecmis)
            print(f"\nTahmin: {t['mesaj']}")
            if t.get("uyari"):
                print(f"Uyarı : {t['uyari']}")
