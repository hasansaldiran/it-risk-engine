# IT Risk Engine — BT Risk Yönetim Platformu

Kurum BT envanterinden MITRE ATT&CK ve CIS Controls v8 tabanlı risk
puanlaması, CVE eşlemesi, anomali tespiti ve yönetici raporları üreten bir
Python platform. Özgeçmişimde yer alan **"BT Risk Yönetim Platformu"**
projesinin motor katmanıdır (Dünyagöz Hastaneler Grubu bünyesinde
geliştirdim).

## Bileşenler

| Modül | Görevi |
|---|---|
| `risk_engine_v62.py` | Ana risk puanlama motoru. Lansweeper envanterini alır, varlık başına risk skoru üretir, e-posta raporu gönderir. |
| `lansweeper_sync.py` | Lansweeper API ile envanter senkronizasyonu. |
| `cve_scanner_last.py` | Varlıklardaki yazılım sürümlerini NIST NVD CVE'leriyle eşler. |
| `mitre_mapper.py` | Tespit edilen riskleri MITRE ATT&CK teknikleri ile ilişkilendirir. |
| `compliance_engine.py` | CIS Controls v8 uyum skorunu hesaplar. |
| `anomaly_engine.py` | Zaman serisi tabanlı sapma tespiti (yeni yazılım, yeni kullanıcı vs.). |
| `device_history_engine.py` | Cihaz yaşam döngüsü ve geçmiş hareket kaydı. |
| `software_tracker.py` | Envanterde yeni/kaldırılan yazılım değişikliklerini izler. |
| `report_generator.py` | Excel + PDF yönetici raporlarını üretir. |
| `dashboard.py` + `dashboard_streamlit.cmd` | Streamlit tabanlı canlı dashboard. |
| `launcher.py` | Tüm pipeline'ı sırayla tetikleyen giriş noktası. |

## Klasör yapısı

```
it-risk-engine/
├── scripts/              # Tüm motor modülleri
│   └── _archive/         # Eski sürümler (referans amaçlı)
├── config/               # .env.example, ayar dosyaları
├── data/                 # Lansweeper exportları (git'e girmez)
├── output/               # Üretilen Excel + PDF raporlar
├── logs/                 # Çalışma günlükleri
├── requirements.txt
└── RiskEngine.bat        # Windows için tek tık başlatıcı
```

## Kurulum

```bash
pip install -r requirements.txt
# pandas, xlsxwriter, openpyxl, requests, streamlit, reportlab, ...
```

## Ortam değişkenleri

`risk_engine_v62.py` e-posta alıcılarını ortam değişkeninden okur:

```bash
export RISK_MAIL_TO="alici1@sirket.com,alici2@sirket.com"
export RISK_MAIL_CC="yonetim@sirket.com"
export SMTP_HOST=smtp.office365.com
export SMTP_PORT=587
export SMTP_USER=bot@sirket.com
export SMTP_PASSWORD=xxx
```

## Çalıştırma

```bash
# Tüm pipeline:
python scripts/launcher.py

# Sadece dashboard:
streamlit run scripts/dashboard.py

# Windows tek tık:
RiskEngine.bat
```

## Teknoloji yığını

Python · pandas · Streamlit · ReportLab · xlsxwriter · Lansweeper API ·
MITRE ATT&CK · CIS Controls v8 · NIST NVD

## Lisans

MIT — bkz. [LICENSE](LICENSE).
