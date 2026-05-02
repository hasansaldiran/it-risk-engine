# -*- coding: utf-8 -*-
"""
software_tracker.py — Yazılım Envanteri Takip ve Değişim Tespiti
=================================================================
Lansweeper'dan çekilen yazılım envanterini (lansweeper_software.xlsx)
okur, önceki snapshotla karşılaştırır ve değişiklikleri raporlar.

Tespit edilenler:
  + Yeni kurulan yazılım (dün yoktu, bugün var)
  - Kaldırılan yazılım  (dün vardı, bugün yok)
  ↑ Versiyon güncellemesi
  ⚠ Şüpheli yazılım yeni kurulmuşsa acil uyarı

Veri gizliliği: Tamamen yerel. Hiçbir veri dışarı çıkmaz.

Çalıştırmak için:
    python scripts/software_tracker.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ─── YOLLAR ─────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
RAW_DIR     = BASE_DIR / "data" / "raw"
PROC_DIR    = BASE_DIR / "data" / "processed"
SW_RAW      = RAW_DIR  / "lansweeper_software.xlsx"
SW_SNAP_DIR = PROC_DIR / "software_snapshots"
SW_CHANGES  = PROC_DIR / "software_changes.json"   # dashboard okur
SW_CURRENT  = PROC_DIR / "software_current.xlsx"   # temiz kopya

# ─── ŞÜPHELİ YAZILIM LİSTESİ (shadow IT) ────────────────────────────────────
# risk_engine'deki SQL listesiyle birebir aynı tutuluyor
SUPHELILER = [
    "Torrent","VPN","Psiphon","Betternet","ZenMate","Hotspot Shield",
    "Steam","Epic Games","Ubisoft","Origin","Gaijin","Roblox","Minecraft",
    "BlueStacks","Angry IP","Nmap","Wireshark","Cheat Engine","Keygen",
    "AnyDesk","TeamViewer","Ammyy","WhatsApp","Telegram","Piriform",
]


def _suphelimi(sw_name: str) -> bool:
    nm = str(sw_name).lower()
    return any(s.lower() in nm for s in SUPHELILER)


# ─── ANA FONKSİYON ──────────────────────────────────────────────────────────

def yazilim_guncelle() -> dict:
    """
    Yazılım envanterini okur, önceki snapshotla karşılaştırır.

    Returns: {
        tarih, yeni_yazilim, kaldirilan, guncellenen, suphe_yeni,
        toplam_kayit, toplam_cihaz, ozet_str
    }
    """
    if not SW_RAW.exists():
        return {"hata": f"Yazılım envanteri bulunamadı: {SW_RAW}",
                "tarih": datetime.now().isoformat()}

    print(f"[SW] {SW_RAW.name} okunuyor...")
    try:
        df = pd.read_excel(SW_RAW)
    except Exception as e:
        return {"hata": str(e), "tarih": datetime.now().isoformat()}

    # Sütun adlarını normalize et
    df.columns = df.columns.str.strip()
    kolon_map = {
        "AssetName":    "AssetName",
        "Assetname":    "AssetName",
        "assetname":    "AssetName",
        "SoftwareName": "SoftwareName",
        "softwareName": "SoftwareName",
        "Publisher":    "Publisher",
        "Version":      "Version",
        "softwareVersion": "Version",
        "AssetStatus":  "AssetStatus",
        "IPAddress":    "IPAddress",
        "OS":           "OS",
        "DaysOffline":  "DaysOffline",
    }
    df.rename(columns={k: v for k, v in kolon_map.items() if k in df.columns}, inplace=True)

    # Zorunlu sütunlar
    for col in ["AssetName", "SoftwareName"]:
        if col not in df.columns:
            return {"hata": f"'{col}' sütunu eksik. SQL raporunu kontrol et.",
                    "tarih": datetime.now().isoformat()}

    df["Version"]   = df.get("Version",   pd.Series("", index=df.index)).fillna("").astype(str)
    df["Publisher"] = df.get("Publisher", pd.Series("", index=df.index)).fillna("").astype(str)
    df["Suphe"]     = df["SoftwareName"].apply(_suphelimi)

    n_kayit  = len(df)
    n_cihaz  = df["AssetName"].nunique()
    n_suphe  = int(df["Suphe"].sum())
    tarih    = datetime.now().strftime("%Y-%m-%d")

    print(f"[SW] {n_kayit} yazılım kaydı, {n_cihaz} cihaz, {n_suphe} şüpheli")

    # Temiz kopyayı kaydet (dashboard ve CVE scanner için)
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    df.to_excel(SW_CURRENT, index=False)
    print(f"[SW] Temiz kopya: {SW_CURRENT.name}")

    # Snapshot klasörü
    SW_SNAP_DIR.mkdir(parents=True, exist_ok=True)

    # Bugünkü snapshot: {asset}|{sw}|{version} setleri
    bugun_set: dict[str, str] = {}  # "asset|sw" → version
    for _, row in df.iterrows():
        key = f"{row['AssetName']}|{row['SoftwareName']}"
        bugun_set[key] = str(row.get("Version", ""))

    # Dünkü snapshot
    snap_path = SW_SNAP_DIR / f"snapshot_{tarih}.json"
    # Önceki snapshot: bugünden farklı tarihli son dosya
    snaplar = sorted(SW_SNAP_DIR.glob("snapshot_*.json"), reverse=True)
    onceki_snap_path = None
    for s in snaplar:
        if s.name != snap_path.name:
            onceki_snap_path = s
            break

    degisimler = {
        "tarih":        tarih,
        "toplam_kayit": n_kayit,
        "toplam_cihaz": n_cihaz,
        "yeni_yazilim": [],
        "kaldirilan":   [],
        "guncellenen":  [],
        "suphe_yeni":   [],
    }

    if onceki_snap_path:
        try:
            onceki_set: dict[str, str] = json.loads(
                onceki_snap_path.read_text(encoding="utf-8")
            )
            onceki_tarih = onceki_snap_path.stem.replace("snapshot_", "")
            print(f"[SW] Önceki snapshot: {onceki_tarih}")

            # Yeni kurulanlar
            for key, ver in bugun_set.items():
                if key not in onceki_set:
                    asset, sw = key.split("|", 1)
                    kayit = {"cihaz": asset, "yazilim": sw, "versiyon": ver}
                    degisimler["yeni_yazilim"].append(kayit)
                    if _suphelimi(sw):
                        degisimler["suphe_yeni"].append(kayit)

            # Kaldırılanlar
            for key, ver in onceki_set.items():
                if key not in bugun_set:
                    asset, sw = key.split("|", 1)
                    degisimler["kaldirilan"].append(
                        {"cihaz": asset, "yazilim": sw, "versiyon_eski": ver}
                    )

            # Güncellenenler (versiyon değişti)
            for key in bugun_set:
                if key in onceki_set and bugun_set[key] != onceki_set[key]:
                    asset, sw = key.split("|", 1)
                    degisimler["guncellenen"].append({
                        "cihaz":         asset,
                        "yazilim":       sw,
                        "versiyon_eski": onceki_set[key],
                        "versiyon_yeni": bugun_set[key],
                    })

            n_y = len(degisimler["yeni_yazilim"])
            n_k = len(degisimler["kaldirilan"])
            n_g = len(degisimler["guncellenen"])
            n_s = len(degisimler["suphe_yeni"])
            print(f"[SW] Değişimler: +{n_y} yeni, -{n_k} kaldırılan, "
                  f"↑{n_g} güncellenen, ⚠{n_s} şüpheli yeni")
        except Exception as e:
            print(f"[SW] Önceki snapshot okunamadı: {e}")
    else:
        print("[SW] İlk çalıştırma — karşılaştırma yapılamadı, snapshot oluşturuluyor.")

    # Bugünkü snapshotı kaydet
    snap_path.write_text(
        json.dumps(bugun_set, ensure_ascii=False), encoding="utf-8"
    )

    # En fazla 30 snapshot sakla
    tum_snaplar = sorted(SW_SNAP_DIR.glob("snapshot_*.json"))
    for eski in tum_snaplar[:-30]:
        try: eski.unlink()
        except: pass

    # Özet string (launcher'da gösterilir)
    degisimler["ozet_str"] = (
        f"{n_kayit} kayıt · {n_cihaz} cihaz · "
        f"+{len(degisimler['yeni_yazilim'])} yeni · "
        f"-{len(degisimler['kaldirilan'])} kaldırılan · "
        f"⚠{len(degisimler['suphe_yeni'])} şüpheli yeni"
    )

    # Değişim raporunu kaydet (dashboard okur)
    SW_CHANGES.write_text(
        json.dumps(degisimler, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[SW] Değişim raporu: {SW_CHANGES.name}")
    print(f"[SW] Özet: {degisimler['ozet_str']}")
    return degisimler


# ─── STANDALONE ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sonuc = yazilim_guncelle()
    if "hata" in sonuc:
        print(f"\nHATA: {sonuc['hata']}")
        sys.exit(1)

    print(f"\n{'='*50}")
    print("YAZILIM ENVANTERİ ÖZETİ")
    print(f"{'='*50}")
    print(f"Toplam kayıt  : {sonuc['toplam_kayit']}")
    print(f"Toplam cihaz  : {sonuc['toplam_cihaz']}")
    print(f"Yeni yazılım  : {len(sonuc['yeni_yazilim'])}")
    print(f"Kaldırılan    : {len(sonuc['kaldirilan'])}")
    print(f"Güncellenen   : {len(sonuc['guncellenen'])}")

    if sonuc["suphe_yeni"]:
        print(f"\n{'!'*50}")
        print(f"⚠  {len(sonuc['suphe_yeni'])} ŞÜPHELİ YAZILIM YENİ KURULDU!")
        for s in sonuc["suphe_yeni"][:10]:
            print(f"   {s['cihaz']:<25} {s['yazilim']}")
        print(f"{'!'*50}")
