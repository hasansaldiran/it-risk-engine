# -*- coding: utf-8 -*-
"""
anomaly_engine.py — Z-Score Tabanlı Anomali Tespiti
=====================================================
Her metrik için "bu cihaz filonun kaç standart sapma dışında?"
sorusunu yanıtlar. Kara kutu değil — her anomali yorumlanabilir.

ÇALIŞMA MANTIĞI:
  1. Seçilen metrikler için Z-Score hesaplanır
  2. |Z| > 2.5 olan metrikler "anomali" sayılır
  3. Birden fazla metrikte anomali olan cihazlar işaretlenir
  4. risk_data_current.xlsx'e Anomali_Skoru ve Anomali_Detay sütunları eklenir

ENTEGRASYON:
  risk_engine_v62.py'nin sonuna ekle:
    from anomaly_engine import anomali_hesapla
    df = anomali_hesapla(df)

  veya ayrı çalıştır:
    python scripts/anomaly_engine.py

ÇIKTI SÜTUNLARI:
  Anomali_Skoru  : 0-100 arası puan (yüksek = daha anormal)
  Anomali_Detay  : "Disk(Z=3.2), Yamasız(Z=2.8)" gibi insan okunur açıklama
  Anomali_Flag   : True/False — ana filtre
"""

import os, sys, json
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

# ─── KONFIGÜRASYON ──────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
PROC_DIR   = BASE_DIR / "data" / "processed"
CLEAN_DATA = PROC_DIR / "risk_data_current.xlsx"

ANOMALI_CFG = {
    # Hangi metrikler analiz edilsin?
    # (sütun_adı, yüksek_mi_kötü, insan_okunur_isim)
    "METRIKLER": [
        ("Final_Risk_Skoru",  True,  "Risk Skoru"),
        ("Yamasız Gün",       True,  "Yamasız Süre"),
        ("Offline Gün",       True,  "Offline Süre"),
        ("% Boş",             False, "Disk Doluluk"),   # düşük boş = kötü
        ("_RawAdminCount",    True,  "Admin Fazlalığı"),
        ("CVE_Bonus",         True,  "CVE Riski"),
    ],

    # Z-Score eşiği — bu değerin üstü anomali sayılır
    "Z_ESIK": 2.5,

    # Kaç metrikte anomali olursa cihaz flaglenir?
    "MIN_ANOMALI_METRIK": 2,

    # Maksimum Z-Score — normalizasyon için
    "MAX_Z_CAP": 6.0,
}

# ─── ANA FONKSİYON ──────────────────────────────────────────────────────────

def anomali_hesapla(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame'e Anomali_Skoru, Anomali_Detay ve Anomali_Flag sütunlarını ekler.

    Parametreler
    ────────────
    df : risk_data DataFrame (Final_Risk_Skoru vb. sütunlar içermeli)

    Döndürür
    ────────
    df : aynı DataFrame, 3 yeni sütunla
    """

    if len(df) < 10:
        print("[ANOMALİ] Yeterli veri yok (min 10 cihaz). Anomali tespiti atlandı.")
        df["Anomali_Skoru"] = 0
        df["Anomali_Detay"] = ""
        df["Anomali_Flag"]  = False
        return df

    metrikler      = ANOMALI_CFG["METRIKLER"]
    z_esik         = ANOMALI_CFG["Z_ESIK"]
    min_anomali    = ANOMALI_CFG["MIN_ANOMALI_METRIK"]
    max_z_cap      = ANOMALI_CFG["MAX_Z_CAP"]

    # Her metrik için Z-Score hesapla
    z_df = pd.DataFrame(index=df.index)

    for sutun, yuksek_kotu, isim in metrikler:
        if sutun not in df.columns:
            continue

        seri = pd.to_numeric(df[sutun], errors="coerce").fillna(0)

        # Disk için: düşük boş = yüksek risk → ters çevir
        if not yuksek_kotu:
            seri = 100 - seri

        ort = seri.mean()
        std = seri.std()

        if std < 0.001:
            # Tüm değerler aynı — anomali hesaplanamaz
            z_df[f"_z_{sutun}"] = 0.0
            continue

        z = (seri - ort) / std
        z_df[f"_z_{sutun}"] = z.clip(-max_z_cap, max_z_cap)

    if z_df.empty:
        df["Anomali_Skoru"] = 0
        df["Anomali_Detay"] = ""
        df["Anomali_Flag"]  = False
        return df

    # Her cihaz için anomali detayını hesapla
    anomali_skorlar = []
    anomali_detaylar = []
    anomali_flaglar  = []

    for idx in df.index:
        anomali_metrikler = []
        z_toplam          = 0.0

        for sutun, _, isim in metrikler:
            z_col = f"_z_{sutun}"
            if z_col not in z_df.columns:
                continue
            z_val = float(z_df.loc[idx, z_col])

            if z_val > z_esik:
                anomali_metrikler.append(f"{isim}(Z={z_val:.1f})")
                z_toplam += z_val

        # Anomali skoru: 0-100
        n_anomali = len(anomali_metrikler)
        if n_anomali == 0:
            skor = 0
        else:
            # n_anomali ve z ortalaması birleşik skor
            z_ort  = z_toplam / n_anomali
            skor   = min(100, int((n_anomali * 15) + (z_ort - z_esik) * 12))

        detay  = ", ".join(anomali_metrikler) if anomali_metrikler else ""
        flagli = n_anomali >= min_anomali

        anomali_skorlar.append(skor)
        anomali_detaylar.append(detay)
        anomali_flaglar.append(flagli)

    df = df.copy()
    df["Anomali_Skoru"] = anomali_skorlar
    df["Anomali_Detay"] = anomali_detaylar
    df["Anomali_Flag"]  = anomali_flaglar

    n_anomali = int(sum(anomali_flaglar))
    n_yuksek  = int((df["Anomali_Skoru"] > 40).sum())
    print(f"[ANOMALİ] {len(df)} cihazda Z-Score analizi tamamlandı.")
    print(f"[ANOMALİ] {n_anomali} anomali cihazı ({n_yuksek} yüksek skor)")

    return df


def anomali_ozet(df: pd.DataFrame) -> dict:
    """
    Anomali özetini döndürür (dashboard / mail için).

    Döndürür: dict(toplam, yuksek, top5=[...])
    """
    if "Anomali_Flag" not in df.columns:
        return {"toplam": 0, "yuksek": 0, "top5": []}

    anomaliler = df[df["Anomali_Flag"]].sort_values("Anomali_Skoru", ascending=False)
    return {
        "toplam": len(anomaliler),
        "yuksek": int((anomaliler["Anomali_Skoru"] > 40).sum()),
        "top5":   anomaliler.head(5)[
                      ["AssetName", "Anomali_Skoru", "Anomali_Detay",
                       "Final_Risk_Skoru", "Seviye"]
                  ].to_dict("records"),
    }


# ─── STANDALONE ─────────────────────────────────────────────────────────────

def _standalone():
    """risk_data_current.xlsx üzerinde doğrudan çalıştır ve kaydet."""
    if not CLEAN_DATA.exists():
        print(f"HATA: {CLEAN_DATA} bulunamadı. Önce risk_engine_v62.py çalıştırın.")
        sys.exit(1)

    print(f"[ANOMALİ] {CLEAN_DATA.name} okunuyor...")
    df = pd.read_excel(CLEAN_DATA)
    print(f"[ANOMALİ] {len(df)} cihaz yüklendi.")

    df = anomali_hesapla(df)

    # Sonuçları kaydet
    out = PROC_DIR / "anomali_sonuc.xlsx"
    df[["AssetName", "Final_Risk_Skoru", "Seviye",
        "Anomali_Skoru", "Anomali_Detay", "Anomali_Flag"]]\
      .sort_values("Anomali_Skoru", ascending=False)\
      .to_excel(out, index=False)
    print(f"[ANOMALİ] Sonuçlar → {out}")

    # risk_data_current'a da ekle
    # (risk_engine entegrasyonu olmadan ayrı çalıştırıldığında)
    df.to_excel(CLEAN_DATA, index=False)
    print(f"[ANOMALİ] risk_data_current.xlsx güncellendi.")

    ozet = anomali_ozet(df)
    print(f"\n{'='*45}")
    print(f"ANOMALİ ÖZETİ")
    print(f"{'='*45}")
    print(f"Toplam anomali cihazı : {ozet['toplam']}")
    print(f"Yüksek skor (>40)     : {ozet['yuksek']}")
    if ozet["top5"]:
        print(f"\nEn anomali 5 cihaz:")
        for r in ozet["top5"]:
            print(f"  {r['AssetName']:<25} Skor:{r['Anomali_Skoru']:3d}  {r['Anomali_Detay']}")
    print(f"{'='*45}")


if __name__ == "__main__":
    _standalone()
