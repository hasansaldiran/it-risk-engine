# 🛡️ IT Risk Engine — Enterprise Security Monitoring Platform

> Python/Streamlit tabanlı, kurumsal sağlık sektörü için sıfırdan inşa edilmiş IT risk yönetim platformu.
> Lansweeper · NIST NVD CVE · MITRE ATT&CK Framework · CIS Controls v8 · Z-Score Anomali Tespiti

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io)
[![MITRE ATT&CK](https://img.shields.io/badge/MITRE-ATT%26CK-E22C2C?style=flat)](https://attack.mitre.org)
[![CIS Controls](https://img.shields.io/badge/CIS-Controls%20v8-1565C0?style=flat)](https://www.cisecurity.org)

---

## 📌 Genel Bakış

IT Risk Engine, **Dünyagöz Hastaneler Grubu** bünyesinde geliştirilen kurumsal güvenlik izleme platformudur.

Platform, Türkiye ve Azerbaycan'da **25+ lokasyona** yayılmış **2.250+ BT varlığını** gerçek zamanlı olarak izler; merkezi güvenlik görünürlüğü olmayan heterojen bir altyapıyı kapsayan bu boşluğu kapatmak amacıyla sıfırdan tasarlanmıştır.

---

## ✨ Temel Özellikler

### 🔍 Varlık Risk Skorlama
- Lansweeper envanter verisi üzerinden otomatik risk puanlama
- İşletim sistemi, yama durumu ve yazılım envanterine göre ağırlıklı skor
- **Z-Score anomali tespiti** — ani risk artışlarını otomatik flagler

### 🔗 NIST NVD CVE Entegrasyonu
- Yüklü yazılım sürümlerine karşı otomatik CVE sorgusu
- CVSS önem derecesi eşleme (Kritik / Yüksek / Orta / Düşük)
- Cihaz başına CVE geçmiş takibi

### ⚔️ MITRE ATT&CK Eşleme
- Tespit edilen açıklıkları ATT&CK tekniklerine otomatik eşler
- Sağlık sektörü tehdit ortamına göre uyarlanmış taktik önceliği
- Tüm varlık filosunda teknik frekans ısı haritası

### 📋 CIS Controls v8 Uyumluluk
- IG1/IG2/IG3 grupları genelinde uyumluluk skoru
- Boşluk analizi ve düzeltme öncelik kuyruğu

### 📊 Streamlit Dashboard
- Renk kodlu önem seviyesiyle gerçek zamanlı risk özeti
- 25+ lokasyon bazlı risk dağılımı
- Cihaz detay drilldown: tam risk profili

### 📄 Otomatik HTML Raporlar
- Tek tıkla yönetim raporu — sıfır manuel formatlama
- Trafik ışığı renk sistemi (Kırmızı / Sarı / Yeşil)
- Zamanlayıcı ile otomatik rapor üretimi

---

## 📈 Etki

| Metrik | Değer |
|--------|-------|
| İzlenen varlık | 2.250+ |
| Kapsanan lokasyon | 25+ (Türkiye & Azerbaycan) |
| CVE veritabanı | NIST NVD (100.000+ kayıt) |
| ATT&CK tekniği | Enterprise Matrix |
| CIS Kontrol değerlendirmesi | v8 IG1/IG2/IG3 |
| Rapor üretim süresi | < 30 saniye |

---

## 🏗️ Mimari

```
it-risk-engine/
├── app.py                      # Streamlit giriş noktası
├── config/settings.py          # Eşikler, API uç noktaları
├── core/
│   ├── lansweeper.py           # Lansweeper veri alımı & normalizasyon
│   ├── nvd_fetcher.py          # NIST NVD CVE API v2 entegrasyonu
│   ├── mitre_mapper.py         # MITRE ATT&CK teknik eşleme
│   ├── cis_scorer.py           # CIS Controls v8 uyumluluk skorlama
│   ├── risk_engine.py          # Risk skoru hesaplama + Z-Score
│   └── report_generator.py     # Otomatik HTML rapor üretici
├── pages/
│   ├── 01_overview.py          # Yönetici dashboard
│   ├── 02_assets.py            # Varlık envanteri + risk skorları
│   ├── 03_cve.py               # CVE analizi
│   ├── 04_mitre.py             # ATT&CK eşleme görünümü
│   ├── 05_cis.py               # CIS Controls uyumluluğu
│   ├── 06_locations.py         # Lokasyon bazlı dağılım
│   └── 07_reports.py           # Rapor üretim modülü
└── utils/
    ├── subnet_map.py           # Subnet → lokasyon eşleme
    └── ui_helpers.py           # Paylaşılan Plotly bileşenleri
```

---

## 🔧 Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| Frontend | Streamlit, Plotly |
| Backend | Python 3.10+, SQLAlchemy |
| Veritabanı | SQLite |
| Varlık Verisi | Lansweeper REST API |
| Zafiyet Verisi | NIST NVD CVE API v2 |
| Tehdit İstihbaratı | MITRE ATT&CK (enterprise-attack.json) |
| Güvenlik Çerçevesi | CIS Controls v8 |
| Anomali Tespiti | Z-Score (özel implementasyon) |
| Raporlama | Jinja2 HTML şablonları |

---

## ⚠️ Veri Gizliliği Notu

Bu repo gerçek hasta, personel veya altyapı verisi içermez. Tüm ekran görüntüleri ve raporlar yayınlanmadan önce anonimleştirilmiştir. Platform üretim ortamında aktif olarak kullanılmaktadır.

---

## 👤 Geliştirici

**Hasan Saldıran** — IT Sistemleri & Güvenlik Uzmanı @ Dünyagöz Hastaneler Grubu

[![LinkedIn](https://img.shields.io/badge/LinkedIn-hasansaldiran-0A66C2?style=flat&logo=linkedin)](https://linkedin.com/in/hasansaldiran)
[![Portfolio](https://img.shields.io/badge/Portfolio-hasansaldiran.github.io-222?style=flat&logo=github)](https://hasansaldiran.github.io)
