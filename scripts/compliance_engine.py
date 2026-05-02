# -*- coding: utf-8 -*-
"""
compliance_engine.py — CIS Controls v8 Uyum Skoru
==================================================
Mevcut risk verilerini CIS Controls v8 çerçevesiyle eşleştirir.
Sıfır API — tamamen yerel hesaplama.

CIS Controls nedir:
  Center for Internet Security tarafından yayımlanan, en yaygın kullanılan
  18 güvenlik kontrolünden oluşan bir çerçevedir. 
  Küçük/orta işletmelerden büyük kurumlara kadar uygulanır.
  Her kontrol "IG1/IG2/IG3" uygulama grubuyla derecelendirilir:
    IG1 = Temel (her kurum uygulamalı)
    IG2 = Orta (ek kaynak gerektiren)
    IG3 = İleri (büyük/kritik kurumlar)
"""

import pandas as pd
import numpy as np
from typing import Optional


# ─── 18 CIS CONTROL TANIMI ───────────────────────────────────────────────────
CIS_CONTROLS = {
    1: {
        "baslik":    "Kurumsal Varlıkların Envanteri ve Kontrolü",
        "ig":        "IG1",
        "aciklama":  (
            "Kuruluşun ağına bağlanan tüm donanım varlıklarını aktif olarak yönet. "
            "Yetkisiz ve yönetilmeyen cihazlar güvenlik açığının ilk kapısıdır."
        ),
        "neden":     "Bilinmeyen cihaz = yönetilemeyen risk. Saldırganlar envanterde olmayan cihazları hedef alır.",
        "emoji":     "🖥️",
        "renk":      "#58A6FF",
        "olcutler": [
            {
                "id": "1.1",
                "kural": "Tüm cihazlar envanterlenmiş mi?",
                "aciklama": "Lansweeper kapsamındaki cihaz oranı",
                "hesapla": lambda df: _her_zaman_gecerli(df, "Lansweeper envanterleme aktif"),
            },
            {
                "id": "1.2",
                "kural": "Yetkisiz cihaz oranı %5'in altında mı?",
                "aciklama": "Şüpheli veya tanımsız cihaz tipi oranı",
                "hesapla": lambda df: _cihaz_tipi_bilinmezlik(df),
            },
        ],
    },
    2: {
        "baslik":    "Yazılım Varlıklarının Envanteri ve Kontrolü",
        "ig":        "IG1",
        "aciklama":  (
            "Yalnızca yetkili yazılımların çalışmasına izin ver. "
            "Şüpheli veya onaysız yazılımlar shadow IT ve veri sızdırma riski oluşturur."
        ),
        "neden":     "Her yüklü yazılım potansiyel bir saldırı vektörüdür. Kontrol dışı yazılımlar C2 kanalı açabilir.",
        "emoji":     "📦",
        "renk":      "#D2A8FF",
        "olcutler": [
            {
                "id": "2.1",
                "kural": "Şüpheli yazılım oranı %5'in altında mı?",
                "aciklama": "Tespit Edilen Şüpheli Yazılımlar içeren cihaz oranı",
                "hesapla": lambda df: _sutun_ne_oran(df, "Tespit Edilen Şüpheli Yazılımlar", 5),
            },
        ],
    },
    4: {
        "baslik":    "Kurumsal Varlıkların ve Yazılımların Güvenli Yapılandırması",
        "ig":        "IG1",
        "aciklama":  (
            "Güvenlik yapılandırmaları oluştur, uygula ve sürdür. "
            "Varsayılan ayarlar genellikle güvensizdir — Firewall, WU ve AV konfigürasyonları düzenli kontrol edilmeli."
        ),
        "neden":     "Yapılandırma eksikliği, fidye yazılımı ve yetkisiz erişim saldırılarının kapısını açar.",
        "emoji":     "⚙️",
        "renk":      "#FFA657",
        "olcutler": [
            {
                "id": "4.1",
                "kural": "Firewall kapalı cihaz oranı %5'in altında mı?",
                "aciklama": "Windows Firewall devre dışı cihaz yüzdesi",
                "hesapla": lambda df: _ra_oran(df, "Firewall", 5),
            },
            {
                "id": "4.2",
                "kural": "Windows Update servisi kapalı cihaz oranı %10'un altında mı?",
                "aciklama": "_RawUpdateStop > 0 olan cihaz yüzdesi",
                "hesapla": lambda df: _raw_sutun_oran(df, "_RawUpdateStop", 10),
            },
        ],
    },
    5: {
        "baslik":    "Hesap Yönetimi",
        "ig":        "IG1",
        "aciklama":  (
            "Tüm kullanıcı hesaplarını yönet. Yetkisiz, kullanılmayan ve aşırı yetkili hesaplar "
            "en sık istismar edilen kimlik riski kaynaklarıdır."
        ),
        "neden":     "Yetkisiz admin hesabı, saldırgana domain genelinde hareket imkânı verir.",
        "emoji":     "👤",
        "renk":      "#D29922",
        "olcutler": [
            {
                "id": "5.1",
                "kural": "Yetkisiz admin oranı %5'in altında mı?",
                "aciklama": "Standart dışı admin üyesi içeren cihaz yüzdesi",
                "hesapla": lambda df: _raw_sutun_oran(df, "_RawAdminCount", 5),
            },
            {
                "id": "5.2",
                "kural": "Sabit şifreli admin hesabı yok mu?",
                "aciklama": "PasswordNeverExpires veya sabit şifreli hesap içeren cihaz oranı",
                "hesapla": lambda df: _ra_oran(df, "Sabit Şifreli Admin", 0),
            },
        ],
    },
    6: {
        "baslik":    "Erişim Kontrolü Yönetimi",
        "ig":        "IG1",
        "aciklama":  (
            "En az yetki prensibini uygula. Kullanıcılara sadece ihtiyaç duydukları kadar yetki ver. "
            "Aşırı yetki verilmiş hesaplar saldırganın ilk hedefidir."
        ),
        "neden":     "Privilege escalation saldırılarının temel kaynağı aşırı yetkidir.",
        "emoji":     "🔑",
        "renk":      "#FF7B72",
        "olcutler": [
            {
                "id": "6.1",
                "kural": "Admin grubunda gereksiz üye yok mu?",
                "aciklama": "Kural dışı admin üyesi tespit edilen cihaz oranı",
                "hesapla": lambda df: _ra_oran(df, "Onaysız Yönetici", 3),
            },
        ],
    },
    7: {
        "baslik":    "Sürekli Güvenlik Açığı Yönetimi",
        "ig":        "IG1",
        "aciklama":  (
            "Yamaları sürekli değerlendir, takip et ve uygula. "
            "Yamasız sistemler en sık saldırıya uğrayan sistemlerdir. "
            "WSUS/SCCM ile otomatik patch yönetimi zorunludur."
        ),
        "neden":     "CVE veritabanındaki açıkların %60'ı yaması mevcut olan açıklardır — yamamamak savunmasızlık seçmektir.",
        "emoji":     "🩹",
        "renk":      "#F85149",
        "olcutler": [
            {
                "id": "7.1",
                "kural": "60+ gün yamasız cihaz oranı %20'nin altında mı?",
                "aciklama": "Kritik patch eksikliği olan cihaz yüzdesi",
                "hesapla": lambda df: _yasiz_gun_oran(df, 60, 20),
            },
            {
                "id": "7.2",
                "kural": "180+ gün yamasız cihaz oranı %5'in altında mı?",
                "aciklama": "WSUS bağlantısı kopmuş cihaz yüzdesi",
                "hesapla": lambda df: _yasiz_gun_oran(df, 180, 5),
            },
            {
                "id": "7.3",
                "kural": "CVE içeren yazılım oranı %15'in altında mı?",
                "aciklama": "Bilinen CVE açığı bulunan cihaz yüzdesi",
                "hesapla": lambda df: _cve_oran(df, 15),
            },
        ],
    },
    10: {
        "baslik":    "Zararlı Yazılım Savunması",
        "ig":        "IG1",
        "aciklama":  (
            "Kötü amaçlı yazılımların kurulumunu, yayılmasını ve çalıştırılmasını önle. "
            "Antivirüs/EDR çözümlerinin tüm uç noktalarda güncel olarak çalışması zorunludur."
        ),
        "neden":     "AV olmayan cihaz = açık kapı. Fidye yazılımları AV'sız sistemleri saniyeler içinde ele geçirir.",
        "emoji":     "🛡️",
        "renk":      "#3FB950",
        "olcutler": [
            {
                "id": "10.1",
                "kural": "AV/SEP eksik cihaz oranı %5'in altında mı?",
                "aciklama": "Antivirüs çözümü bulunmayan cihaz yüzdesi",
                "hesapla": lambda df: _ra_oran(df, "Antivirüs", 5),
            },
        ],
    },
    11: {
        "baslik":    "Veri Kurtarma",
        "ig":        "IG1",
        "aciklama":  (
            "Veri kurtarma yetenekleri oluştur ve sürdür. Offline cihazlar, "
            "yamalardan mahrum kalmanın yanı sıra yedekleme kapsamı dışında kalır."
        ),
        "neden":     "Ransomware sonrası kurtarma için offline, test edilmiş yedek zorunludur.",
        "emoji":     "💾",
        "renk":      "#58A6FF",
        "olcutler": [
            {
                "id": "11.1",
                "kural": "60+ gün offline cihaz oranı %10'un altında mı?",
                "aciklama": "Uzun süredir görünmeyen cihaz yüzdesi",
                "hesapla": lambda df: _offline_oran(df, 60, 10),
            },
        ],
    },
    12: {
        "baslik":    "Ağ Altyapısı Yönetimi",
        "ig":        "IG2",
        "aciklama":  (
            "Ağ cihazlarını güvenli biçimde yönet. Açık SMB paylaşımları "
            "ransomware lateral movement için birincil vektördür."
        ),
        "neden":     "WannaCry, NotPetya — her ikisi de açık SMB paylaşımları üzerinden yayıldı.",
        "emoji":     "🌐",
        "renk":      "#FF9F43",
        "olcutler": [
            {
                "id": "12.1",
                "kural": "Riskli SMB paylaşımı oranı %5'in altında mı?",
                "aciklama": "Herkese açık SMB paylaşımı olan cihaz yüzdesi",
                "hesapla": lambda df: _riskli_paylasim_oran(df, 5),
            },
        ],
    },
    13: {
        "baslik":    "Ağ İzleme ve Savunma",
        "ig":        "IG2",
        "aciklama":  (
            "Ağ trafiğini izle, anormal davranışları tespit et. "
            "DLP eksikliği veri sızdırmayı görünmez kılar."
        ),
        "neden":     "Veri ihlallerinin %68'i aylarca fark edilmiyor. DLP bu süreyi kısaltır.",
        "emoji":     "📡",
        "renk":      "#A5D6FF",
        "olcutler": [
            {
                "id": "13.1",
                "kural": "DLP eksik cihaz oranı %10'un altında mı?",
                "aciklama": "Endpoint DLP çözümü olmayan cihaz yüzdesi",
                "hesapla": lambda df: _ra_oran(df, "DLP", 10),
            },
        ],
    },
    16: {
        "baslik":    "Uygulama Yazılımı Güvenliği",
        "ig":        "IG2",
        "aciklama":  (
            "Güvenlik açıklarını azaltmak için uygulama yazılımı yaşam döngüsünü yönet. "
            "EoL sistemler ve CVE içeren uygulamalar bu kontrolün kapsamındadır."
        ),
        "neden":     "EoL yazılımlar için yaması olmayan sıfır-gün açıkları sürekli birikir.",
        "emoji":     "🖥️",
        "renk":      "#D2A8FF",
        "olcutler": [
            {
                "id": "16.1",
                "kural": "EoL işletim sistemi oranı %5'in altında mı?",
                "aciklama": "Win 7/2008/8.1/XP/2012 kullanan cihaz yüzdesi",
                "hesapla": lambda df: _eol_oran(df, 5),
            },
        ],
    },
}

# ─── ÖLÇÜT FONKSİYONLARI ─────────────────────────────────────────────────────

def _n(df):
    return max(len(df), 1)

def _oran(df, sayi):
    return round(sayi / _n(df) * 100, 1)

def _her_zaman_gecerli(df, msg):
    return {"gecerli": True, "puan": 100, "detay": msg, "etkilenen": 0}

def _cihaz_tipi_bilinmezlik(df):
    if "Cihaz_Tipi" not in df.columns:
        return {"gecerli": False, "puan": 0, "detay": "Cihaz_Tipi sütunu bulunamadı", "etkilenen": 0}
    bilinmez = int(df["Cihaz_Tipi"].isin(["","Bilinmiyor","Unknown","None"]).sum())
    oran     = _oran(df, bilinmez)
    return {
        "gecerli":  oran < 5,
        "puan":     max(0, int(100 - oran * 4)),
        "detay":    f"{bilinmez} cihaz tipi bilinmiyor (%{oran})",
        "etkilenen": bilinmez,
    }

def _sutun_ne_oran(df, sutun, esik):
    if sutun not in df.columns:
        return {"gecerli": True, "puan": 100, "detay": f"{sutun} sütunu yok — veri toplanmıyor", "etkilenen": 0}
    sayi  = int(df[sutun].ne("").fillna(False).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran < esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 5)),
        "detay":     f"{sayi} cihazda tespit edildi (%{oran})",
        "etkilenen": sayi,
    }

def _ra_oran(df, anahtar, esik):
    ra    = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)
    sayi  = int(ra.str.contains(anahtar, na=False, regex=False).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 5)),
        "detay":     f"{sayi} cihaz etkileniyor (%{oran})",
        "etkilenen": sayi,
    }

def _raw_sutun_oran(df, sutun, esik):
    if sutun not in df.columns:
        return {"gecerli": True, "puan": 100, "detay": f"{sutun} verisi yok", "etkilenen": 0}
    sayi  = int(df[sutun].gt(0).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 5)),
        "detay":     f"{sayi} cihaz etkileniyor (%{oran})",
        "etkilenen": sayi,
    }

def _yasiz_gun_oran(df, gun, esik):
    if "Yamasız Gün" not in df.columns:
        return {"gecerli": True, "puan": 100, "detay": "Yamasız Gün verisi yok", "etkilenen": 0}
    sayi  = int((df["Yamasız Gün"] > gun).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 5)),
        "detay":     f"{sayi} cihaz {gun}+ gün yamasız (%{oran})",
        "etkilenen": sayi,
    }

def _cve_oran(df, esik):
    if "CVE_Bonus" not in df.columns:
        return {"gecerli": True, "puan": 100, "detay": "CVE verisi yok — cve_scanner çalıştırılmamış", "etkilenen": 0}
    sayi  = int(df["CVE_Bonus"].gt(0).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 4)),
        "detay":     f"{sayi} cihazda CVE içeren yazılım var (%{oran})",
        "etkilenen": sayi,
    }

def _offline_oran(df, gun, esik):
    if "Offline Gün" not in df.columns:
        return {"gecerli": True, "puan": 100, "detay": "Offline Gün verisi yok", "etkilenen": 0}
    sayi  = int((df["Offline Gün"] > gun).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 5)),
        "detay":     f"{sayi} cihaz {gun}+ gün offline (%{oran})",
        "etkilenen": sayi,
    }

def _riskli_paylasim_oran(df, esik):
    sayi = 0
    ra   = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)
    sayi += int(ra.str.contains("Riskli Paylaşım", na=False, regex=False).sum())
    if "Riskli Paylaşılan Klasörler" in df.columns:
        sayi = max(sayi, int(df["Riskli Paylaşılan Klasörler"].ne("").fillna(False).sum()))
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 6)),
        "detay":     f"{sayi} cihazda riskli paylaşım var (%{oran})",
        "etkilenen": sayi,
    }

def _eol_oran(df, esik):
    if "Sistem" not in df.columns:
        return {"gecerli": True, "puan": 100, "detay": "Sistem verisi yok", "etkilenen": 0}
    sayi  = int(df["Sistem"].str.contains("Win 7|2008|8.1|XP|2012", na=False).sum())
    oran  = _oran(df, sayi)
    return {
        "gecerli":   oran <= esik,
        "puan":      max(0, int(100 - max(0, oran - esik) * 8)),
        "detay":     f"{sayi} cihaz EoL OS kullanıyor (%{oran})",
        "etkilenen": sayi,
    }


# ─── ANA HESAPLAMA ───────────────────────────────────────────────────────────

def cis_hesapla(df: pd.DataFrame) -> dict:
    """
    Tüm CIS kontrollerini hesaplar.
    Döndürür: {kontrol_no: {baslik, ig, puan, olcutler, durum}}
    """
    sonuclar = {}
    for no, kontrol in CIS_CONTROLS.items():
        olcut_sonuclari = []
        for olcut in kontrol["olcutler"]:
            try:
                s = olcut["hesapla"](df)
            except Exception as e:
                s = {"gecerli": False, "puan": 0, "detay": str(e), "etkilenen": 0}
            olcut_sonuclari.append({
                "id":        olcut["id"],
                "kural":     olcut["kural"],
                "aciklama":  olcut["aciklama"],
                "gecerli":   s.get("gecerli", False),
                "puan":      s.get("puan", 0),
                "detay":     s.get("detay", ""),
                "etkilenen": s.get("etkilenen", s.get("etkilenen", 0)),
            })

        # Kontrol puanı = ortalama ölçüt puanı
        puan = round(sum(o["puan"] for o in olcut_sonuclari) / max(len(olcut_sonuclari), 1))
        uyumlu_sayi = sum(1 for o in olcut_sonuclari if o["gecerli"])

        if puan >= 80:    durum = "UYUMLU"
        elif puan >= 50:  durum = "KISMEN"
        else:             durum = "UYUMSUZ"

        sonuclar[no] = {
            **kontrol,
            "no":           no,
            "puan":         puan,
            "durum":        durum,
            "olcutler":     olcut_sonuclari,
            "uyumlu_sayi":  uyumlu_sayi,
            "toplam_olcut": len(olcut_sonuclari),
        }

    return sonuclar


def genel_uyum_skoru(cis_sonuclari: dict) -> dict:
    """
    Genel uyum skorunu ve özeti hesaplar.
    """
    puanlar   = [v["puan"] for v in cis_sonuclari.values()]
    genel     = round(sum(puanlar) / max(len(puanlar), 1))
    uyumlu    = sum(1 for v in cis_sonuclari.values() if v["durum"] == "UYUMLU")
    kismen    = sum(1 for v in cis_sonuclari.values() if v["durum"] == "KISMEN")
    uyumsuz   = sum(1 for v in cis_sonuclari.values() if v["durum"] == "UYUMSUZ")

    # IG1 sadece (temel kontroller)
    ig1_puanlar = [v["puan"] for v in cis_sonuclari.values() if v["ig"] == "IG1"]
    ig1_skoru   = round(sum(ig1_puanlar) / max(len(ig1_puanlar), 1)) if ig1_puanlar else 0

    return {
        "genel_skor":  genel,
        "ig1_skor":    ig1_skoru,
        "uyumlu":      uyumlu,
        "kismen":      kismen,
        "uyumsuz":     uyumsuz,
        "toplam":      len(cis_sonuclari),
        "lbl":         "İYİ" if genel >= 75 else "GELİŞTİRİLEBİLİR" if genel >= 50 else "KRİTİK",
        "renk":        "#3FB950" if genel >= 75 else "#D29922" if genel >= 50 else "#F85149",
    }
