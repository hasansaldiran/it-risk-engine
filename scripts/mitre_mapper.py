# -*- coding: utf-8 -*-
"""
mitre_mapper.py — MITRE ATT&CK Eşleme Modülü
==============================================
Sistemizdeki tehditleri MITRE ATT&CK çerçevesine eşler.
Sıfır API çağrısı — tamamen yerel, veri dışarı çıkmaz.

MITRE ATT&CK nedir:
  MITRE Corporation tarafından geliştirilen, gerçek dünya saldırılarından
  derlenen bilgi tabanıdır. 14 Taktik, 190+ Teknik içerir.
  Dünyanın en yaygın kullanılan siber güvenlik referans çerçevesidir.
"""

from typing import Optional
import pandas as pd

# ─── 14 MITRE ATT&CK TAKTİĞİ ────────────────────────────────────────────────
TACTICS = {
    "TA0001": {"isim": "Initial Access",        "tr": "İlk Erişim",         "emoji": "🚪"},
    "TA0002": {"isim": "Execution",             "tr": "Çalıştırma",          "emoji": "▶️"},
    "TA0003": {"isim": "Persistence",           "tr": "Kalıcılık",           "emoji": "⚓"},
    "TA0004": {"isim": "Privilege Escalation",  "tr": "Yetki Yükseltme",     "emoji": "⬆️"},
    "TA0005": {"isim": "Defense Evasion",       "tr": "Savunma Atlatma",     "emoji": "🥷"},
    "TA0006": {"isim": "Credential Access",     "tr": "Kimlik Bilgisi Ele Geçirme", "emoji": "🔑"},
    "TA0007": {"isim": "Discovery",             "tr": "Keşif",               "emoji": "🔍"},
    "TA0008": {"isim": "Lateral Movement",      "tr": "Yanal Hareket",       "emoji": "↔️"},
    "TA0009": {"isim": "Collection",            "tr": "Veri Toplama",        "emoji": "📦"},
    "TA0010": {"isim": "Exfiltration",          "tr": "Veri Sızdırma",       "emoji": "📤"},
    "TA0011": {"isim": "Command and Control",   "tr": "Komuta & Kontrol",    "emoji": "📡"},
    "TA0040": {"isim": "Impact",                "tr": "Etki / Zarar",        "emoji": "💥"},
    "TA0042": {"isim": "Resource Development",  "tr": "Kaynak Geliştirme",   "emoji": "🏗️"},
    "TA0043": {"isim": "Reconnaissance",        "tr": "İstihbarat Toplama",  "emoji": "🕵️"},
}

# ─── KRİTİK TEKNİKLER — Sistemimizle İlgili Olanlar ────────────────────────
TECHNIQUES = {
    "T1078": {
        "isim":    "Valid Accounts",
        "tr":      "Geçerli Hesap Kötüye Kullanımı",
        "taktik":  ["TA0001","TA0003","TA0004","TA0005"],
        "risk":    "Kritik",
        "renk":    "#F85149",
        "aciklama": (
            "Saldırganlar mevcut kullanıcı hesaplarını ele geçirerek sisteme erişir. "
            "Yetkisiz admin hesapları bu tekniği özellikle kolaylaştırır. "
            "Normal güvenlik araçları meşru hesap aktivitesini genellikle algılayamaz."
        ),
        "oneri": "Tüm admin hesaplarını AD'de denetle, PasswordNeverExpires bayrağını kaldır, MFA zorla.",
        "bizim_tehdit": ["Onaysız Yönetici Yetkisi", "Sabit Şifreli Admin", "_RawAdminCount"],
        "url": "https://attack.mitre.org/techniques/T1078",
    },
    "T1098": {
        "isim":    "Account Manipulation",
        "tr":      "Hesap Manipülasyonu",
        "taktik":  ["TA0003","TA0004"],
        "risk":    "Kritik",
        "renk":    "#F85149",
        "aciklama": (
            "Saldırgan, kalıcı erişim sağlamak için mevcut hesaplara ekstra yetkiler ekler "
            "veya yeni admin hesabı oluşturur. Yetkisiz admin eklenmesi bu tekniğin göstergesidir."
        ),
        "oneri": "AD'de admin grubuna son 30 günde kim eklendi? Otomatik uyarı kur.",
        "bizim_tehdit": ["Onaysız Yönetici Yetkisi", "_RawAdminCount"],
        "url": "https://attack.mitre.org/techniques/T1098",
    },
    "T1110": {
        "isim":    "Brute Force",
        "tr":      "Kaba Kuvvet Saldırısı",
        "taktik":  ["TA0006"],
        "risk":    "Yüksek",
        "renk":    "#FF7B72",
        "aciklama": (
            "Sabit şifre veya şifresi hiç değişmeyen hesaplar kaba kuvvet saldırılarına açık. "
            "PasswordNeverExpires bayrağı bu riski doğrudan artırır."
        ),
        "oneri": "Fine-grained password policy uygula, hesap kilitleme politikasını etkinleştir.",
        "bizim_tehdit": ["Sabit Şifreli Admin"],
        "url": "https://attack.mitre.org/techniques/T1110",
    },
    "T1190": {
        "isim":    "Exploit Public-Facing Application",
        "tr":      "Açık Uygulama İstismarı",
        "taktik":  ["TA0001"],
        "risk":    "Kritik",
        "renk":    "#F85149",
        "aciklama": (
            "Yamasız sistemler üzerindeki bilinen güvenlik açıkları (CVE) saldırganlar "
            "tarafından aktif olarak istismar edilir. 60+ gün yamasız sistemler için risk üstel artar."
        ),
        "oneri": "WSUS/SCCM ile zorunlu patch politikası, CVSS≥7 yamalar 48 saatte uygulanmalı.",
        "bizim_tehdit": ["Güvenlik Yamaları Eksik", "Desteklenmeyen OS (EoL)", "CVE_Bonus"],
        "url": "https://attack.mitre.org/techniques/T1190",
    },
    "T1203": {
        "isim":    "Exploitation for Client Execution",
        "tr":      "İstemci Yürütme İstismarı",
        "taktik":  ["TA0002"],
        "risk":    "Yüksek",
        "renk":    "#FF7B72",
        "aciklama": (
            "Yamasız uygulamalar (Office, Chrome, Java vb.) açıkları üzerinden "
            "kötü amaçlı kod çalıştırılabilir. CVE içeren yazılımlar bu riskin kaynağıdır."
        ),
        "oneri": "CVE içeren yazılımları derhal güncelle veya kaldır.",
        "bizim_tehdit": ["Güvenlik Yamaları Eksik", "Tespit Edilen Şüpheli Yazılımlar"],
        "url": "https://attack.mitre.org/techniques/T1203",
    },
    "T1219": {
        "isim":    "Remote Access Software",
        "tr":      "Uzak Erişim Yazılımı",
        "taktik":  ["TA0011"],
        "risk":    "Yüksek",
        "renk":    "#D29922",
        "aciklama": (
            "AnyDesk, TeamViewer gibi araçlar meşru görünse de saldırganlar bunları "
            "C2 kanalı olarak kullanır. IT onaysız kurulumlar shadow IT riskini artırır."
        ),
        "oneri": "GPO ile onaysız uzak erişim yazılımlarını engelle, whitelist uygula.",
        "bizim_tehdit": ["Şüpheli Yazılım Tespit Edildi", "Tespit Edilen Şüpheli Yazılımlar"],
        "url": "https://attack.mitre.org/techniques/T1219",
    },
    "T1562": {
        "isim":    "Impair Defenses",
        "tr":      "Savunma Mekanizmalarını Devre Dışı Bırakma",
        "taktik":  ["TA0005"],
        "risk":    "Kritik",
        "renk":    "#F85149",
        "aciklama": (
            "AV kapalı, Windows Firewall kapalı, Update servisi durdurulmuş sistemler "
            "saldırganların en kolay hedefidir. Bu ayarlar ya kullanıcı hatası ya da "
            "saldırı sonrası kasıtlı devre dışı bırakmayı gösterir."
        ),
        "oneri": "GPO ile AV, Firewall ve WU politikalarını zorla. Devre dışı bırakmayı logla.",
        "bizim_tehdit": ["Antivirüs (SEP) Eksik", "Update Servisi Kapalı", "Firewall", "DLP Yüklü Değil"],
        "url": "https://attack.mitre.org/techniques/T1562",
    },
    "T1021": {
        "isim":    "Remote Services — SMB/Admin Shares",
        "tr":      "Uzak Servisler — SMB Paylaşımları",
        "taktik":  ["TA0008"],
        "risk":    "Kritik",
        "renk":    "#F85149",
        "aciklama": (
            "Herkese açık SMB paylaşımları ransomware lateral movement için en sık kullanılan vektördür. "
            "WannaCry, NotPetya bu vektörü kullanmıştır. Bir cihaz ele geçirilince "
            "tüm açık paylaşımlara erişim sağlanır."
        ),
        "oneri": "SMB paylaşımlarından Everyone/Domain Users yazma yetkisini kaldır, NTFS izinlerini uygula.",
        "bizim_tehdit": ["Riskli Paylaşım", "Riskli Paylaşılan Klasörler"],
        "url": "https://attack.mitre.org/techniques/T1021/002",
    },
    "T1048": {
        "isim":    "Exfiltration Over Alternative Protocol",
        "tr":      "Alternatif Protokolle Veri Sızdırma",
        "taktik":  ["TA0010"],
        "risk":    "Yüksek",
        "renk":    "#D29922",
        "aciklama": (
            "DLP (Data Loss Prevention) olmayan sistemlerde hassas veri USB, e-posta, "
            "bulut storage üzerinden kolayca dışarı çıkarılabilir. "
            "Tespit mekanizması olmadığı için ihlaller çoğunlukla geç fark edilir."
        ),
        "oneri": "Endpoint DLP çözümü deploy et, USB kısıtlamalarını GPO ile zorla.",
        "bizim_tehdit": ["DLP Yüklü Değil"],
        "url": "https://attack.mitre.org/techniques/T1048",
    },
    "T1486": {
        "isim":    "Data Encrypted for Impact",
        "tr":      "Fidye Yazılımı — Veri Şifreleme",
        "taktik":  ["TA0040"],
        "risk":    "Kritik",
        "renk":    "#8B1A1A",
        "aciklama": (
            "Ransomware saldırıları fidye ödenene kadar verileri şifreler. "
            "Yamasız sistemler, açık SMB paylaşımları ve AV eksikliği bu saldırıları "
            "doğrudan besleyen risk faktörleridir. Sistemin mevcut bulgularının büyük çoğunluğu "
            "ransomware saldırısının ön koşullarını oluşturmaktadır."
        ),
        "oneri": "Offline yedek al, SMB paylaşımlarını kapat, AV ve patch güncel tut.",
        "bizim_tehdit": ["Güvenlik Yamaları Eksik", "Riskli Paylaşım", "Antivirüs (SEP) Eksik"],
        "url": "https://attack.mitre.org/techniques/T1486",
    },
    "T1195": {
        "isim":    "Supply Chain Compromise",
        "tr":      "Tedarik Zinciri Saldırısı",
        "taktik":  ["TA0001"],
        "risk":    "Yüksek",
        "renk":    "#D29922",
        "aciklama": (
            "EoL (End-of-Life) işletim sistemleri artık güvenlik yaması almıyor. "
            "Tedarikçi artık destek vermediği için tedarik zinciri riski kategorisinde değerlendirilir."
        ),
        "oneri": "EoL sistemler için upgrade takvimi hazırla, geçici olarak VLAN izolasyonu uygula.",
        "bizim_tehdit": ["Desteklenmeyen OS (EoL)"],
        "url": "https://attack.mitre.org/techniques/T1195",
    },
    "T1070": {
        "isim":    "Indicator Removal",
        "tr":      "İz Silme",
        "taktik":  ["TA0005"],
        "risk":    "Orta",
        "renk":    "#FFA657",
        "aciklama": (
            "60+ gün offline olan cihazlar yetersiz log kaydı ve monitoring kapsamı dışında kalır. "
            "Bu durum saldırıların tespit edilmesini zorlaştırır."
        ),
        "oneri": "Offline cihazları envanterden çıkar veya düzenli check-in zorunluluğu getir.",
        "bizim_tehdit": ["Uzun Süredir Offline"],
        "url": "https://attack.mitre.org/techniques/T1070",
    },
}

# ─── TEHDİT → TEKNİK EŞLEMESİ ───────────────────────────────────────────────
THREAT_TO_TECHNIQUES = {
    "Onaysız Yönetici Yetkisi": ["T1078", "T1098"],
    "Sabit Şifreli Admin":       ["T1078", "T1110"],
    "DLP Yüklü Değil":           ["T1048", "T1562"],
    "Antivirüs (SEP) Eksik":     ["T1562", "T1486"],
    "Güvenlik Yamaları Eksik":   ["T1190", "T1203", "T1486"],
    "Şüpheli Yazılım":           ["T1219", "T1203"],
    "Desteklenmeyen OS (EoL)":   ["T1190", "T1195"],
    "Update Servisi Kapalı":     ["T1562"],
    "Riskli Paylaşım":           ["T1021", "T1486"],
    "Riskli Paylaşılan Klasörler":["T1021"],
    "Uzun Süredir Offline":      ["T1070"],
    "Firewall":                  ["T1562"],
}


def risk_analizi_to_techniques(risk_analizi_str: str) -> list[str]:
    """
    Bir cihazın Risk Analizi metnini alıp ilgili MITRE tekniklerini döndürür.
    """
    if not isinstance(risk_analizi_str, str):
        return []
    teknikler = set()
    for tehdit, techs in THREAT_TO_TECHNIQUES.items():
        if tehdit.lower() in risk_analizi_str.lower():
            teknikler.update(techs)
    return sorted(teknikler)


def df_to_technique_counts(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame'deki tüm cihazların Risk Analizi metinlerini tarayıp
    her teknik için etkilenen cihaz sayısını döndürür.

    Döndürür: DataFrame(technique_id, isim, tr, taktik, etkilenen, risk, renk, url, aciklama, oneri)
    """
    ra = df.get("Risk Analizi", pd.Series("", index=df.index)).astype(str)

    satirlar = []
    for tech_id, tech in TECHNIQUES.items():
        # Bu teknikle eşleşen tehditleri bul
        ilgili_tehditler = [t for t, techs in THREAT_TO_TECHNIQUES.items() if tech_id in techs]
        if not ilgili_tehditler:
            continue

        # Etkilenen cihaz sayısı
        mask = pd.Series(False, index=df.index)
        for tehdit in ilgili_tehditler:
            mask |= ra.str.contains(tehdit, na=False, regex=False)

        # _Raw sütunları da kontrol et
        if tech_id in ("T1078", "T1098"):
            if "_RawAdminCount" in df.columns:
                mask |= df["_RawAdminCount"].gt(0)
        if tech_id in ("T1562",):
            if "_RawUpdateStop" in df.columns:
                mask |= df["_RawUpdateStop"].gt(0)
        if tech_id == "T1190":
            if "CVE_Bonus" in df.columns:
                mask |= df["CVE_Bonus"].gt(0)
        if tech_id == "T1021":
            if "Riskli Paylaşılan Klasörler" in df.columns:
                mask |= df["Riskli Paylaşılan Klasörler"].ne("").fillna(False)

        etkilenen = int(mask.sum())
        satirlar.append({
            "ID":          tech_id,
            "Teknik":      tech["isim"],
            "Türkçe":      tech["tr"],
            "Taktikler":   ", ".join(TACTICS[t]["tr"] for t in tech["taktik"] if t in TACTICS),
            "Etkilenen":   etkilenen,
            "Risk":        tech["risk"],
            "Renk":        tech["renk"],
            "URL":         tech["url"],
            "Açıklama":    tech["aciklama"],
            "Öneri":       tech["oneri"],
        })

    return pd.DataFrame(satirlar).sort_values("Etkilenen" if "Etkilenen" in [c for c in pd.DataFrame(satirlar).columns] else "Etkilenen", ascending=False)


def taktik_bazli_ozet(df: pd.DataFrame) -> dict:
    """
    Her taktik için etkilenen cihaz sayısını döndürür.
    Döndürür: {taktik_id: {isim, tr, emoji, etkilenen}}
    """
    tech_df = df_to_technique_counts(df)
    ozet = {}
    for taktik_id, taktik in TACTICS.items():
        # Bu taktiğe ait teknikleri bul
        ilgili_techs = [t for t, td in TECHNIQUES.items() if taktik_id in td["taktik"]]
        if not ilgili_techs:
            continue
        etkilenen = int(tech_df[tech_df["ID"].isin(ilgili_techs)]["Etkilenen"].max()) if len(tech_df[tech_df["ID"].isin(ilgili_techs)]) > 0 else 0
        ozet[taktik_id] = {
            **taktik,
            "etkilenen": etkilenen,
        }
    return ozet
