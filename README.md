# 🏠 HomeServis - Akıllı Ev ve Güvenlik Yönetim Sistemi

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)](https://opencv.org/)
[![Arduino](https://img.shields.io/badge/Arduino-Uno%20%7C%20Nano-teal.svg)](https://www.arduino.cc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**HomeServis**, Raspberry Pi veya herhangi bir Linux/Windows/macOS bilgisayar üzerinde çalışan, **bilgisayarla görme (OpenCV)** ve **mikrodenetleyici donanımını (Arduino)** birleştiren açık kaynaklı, hafif bir akıllı ev ve güvenlik hub'ıdır.

Proje, USB kameradan alınan görüntüyü işleyerek hareket ve insan/yüz tespiti yapar; tespit edilen alarmları anlık olarak hem mobil uyumlu web arayüzüne (Web Bildirimi & Titreşim) hem de **Arduino 16x2 LCD ekranına ve buzzer'a** iletir. Aynı web arayüzünden ışıklar, ortam parlaklığı ve sıcaklık kontrol edilebilir.

---

## 📸 Ekran Görüntüsü & Sistem Mimarisi

```
                 +-----------------------------------------------+
                 |              İSTEMCİ / TARAYICI               |
                 |     (Mobil Web Dashboard, Bildirim & Titreşim)|
                 +-----------------------+-----------------------+
                                         |
                                         | HTTPS / REST / MJPEG Stream
                                         v
                 +-----------------------------------------------+
                 |             FLASK SUNUCUSU (Python)           |
                 |  - Kullanıcı Giriş / Oturum Yönetimi         |
                 |  - MJPEG Canlı Video Akışı                    |
                 |  - REST API & Durum Senkronizasyonu          |
                 +---------------+---------------+---------------+
                                 |               |
               Frame İletimi &   |               | Seri Haberleşme
               Alarm Callback    |               | (USB / 9600 Baud)
                                 v               v
    +--------------------------------+       +--------------------------------+
    |         KAMERA MODÜLÜ          |       |        ARDUINO YÖNETİCİSİ      |
    |  - USB Kamera (V4L2)           |       |  - Otomatik Port Tarama        |
    |  - Arka Plan Farkı ile Hareket |       |  - Durum Senkronizasyonu       |
    |  - Haar Cascade ile İnsan/Yüz  |       |  - Yeniden Bağlanma (Reconnect)|
    +--------------------------------+       +---------------+----------------+
                                                             |
                                                             v
                                             +--------------------------------+
                                             |     ARDUINO DONANIM DEVRESİ    |
                                             |  - 16x2 I2C LCD Ekran          |
                                             |  - Salon & Mutfak Işıkları     |
                                             |  - PWM Dimmer Parlaklık        |
                                             |  - Güvenlik Buzzer Alarmı      |
                                             |  - Sıcaklık Sensörü (LM35/DHT) |
                                             +--------------------------------+
```

---

## ✨ Temel Özellikler

- **📹 Canlı Güvenlik Akışı (MJPEG):** Tarayıcıda eklentiye ihtiyaç duymadan düşük gecikmeli kamera izleme.
- **👁️ Bilgisayarlı Görme & Güvenlik:**
  - **Hareket Algılama:** *Background Subtraction* ve kontur alanı filtreleme ile sahte alarmları engelleyen hareket tespiti.
  - **İnsan/Yüz Tespiti:** OpenCV *Haar Cascade* modeli ile görüntüdeki insanları algılama ve çerçeveleme.
- **🖥️ Kamera & Arduino Doğrudan Köprüsü:**
  - Kamerada bir insan veya hareket görüldüğünde, sistem anında Arduino'ya `ALERT:HUMAN` veya `ALERT:MOTION` komutu gönderir.
  - Arduino 16x2 ekranında `>>> GUVENLIK <<< !INSAN ALGILANDI!` uyarısı çıkar ve buzzer öter.
- **💡 Donanım Kontrolü:**
  - Salon ve mutfak ışıklarını röle veya LED üzerinden bağımsız anahtarlama.
  - PWM çıkışı ile ayarlanabilir ortam parlaklığı (Dimmer).
  - İki yönlü sıcaklık senkronizasyonu (Sensörden sunucuya, sunucudan ekrana).
- **📱 Mobil Uyumlu Arayüz:** Modern, karanlık temalı (Dark Mode), akıllı telefonlara tam oturan dokunmatik kontrol paneli.
- **🔔 Web Push Bildirimleri & Titreşim:** Alarm durumlarında Web Notification API ve titreşim desteği.
- **🔄 Akıllı Yeniden Bağlanma (Auto-Reconnect):** USB kablosu çıkarılıp takılsa bile sunucuyu yeniden başlatmaya gerek kalmadan Arduino'yu otomatik bulur ve son ışık/sıcaklık durumunu hafızadan geri yükler.
- **🔐 HTTPS & SSL Desteği:** Güvenli oturumlar ve tarayıcı bildirim izinleri için dahili self-signed SSL desteği.

---

## 🔌 Donanım Bileşenleri & Bağlantı Şeması

### Gerekli Malzemeler
1. **Ana Bilgisayar:** Raspberry Pi (3/4/5), Turp, Mini PC veya herhangi bir Linux/Windows bilgisayar.
2. **Kamera:** Standart USB Web Kamerası veya Raspberry Pi Kamera Modülü.
3. **Mikrodenetleyici:** Arduino Uno, Nano, Mega veya CH340 uyumlu klonlar.
4. **Ekran:** 16x2 Karakter LCD + I2C Modülü (PCFC8574).
5. **Aydınlatma & Alarm:**
   - 2x LED veya 2'li Röle Kartı (Salon ve Mutfak için).
   - 1x PWM Kontrollü LED (Ortam parlaklığı için).
   - 1x Aktif/Pasif Buzzer.
   - 1x Sıcaklık Sensörü (LM35 veya DHT11).

### Arduino Pin Bağlantı Tablosu

| Arduino Pini | Bağlanan Bileşen | Açıklama |
| :--- | :--- | :--- |
| **Pin 8** | Salon Işığı (LED / Röle) | `L1` komutuyla kontrol edilir (Açık/Kapalı) |
| **Pin 9** | Mutfak Işığı (LED / Röle) | `L2` komutuyla kontrol edilir (Açık/Kapalı) |
| **Pin 6** | PWM Dimmer LED | `BRT` komutuyla analog voltaj (0-255 PWM) |
| **Pin 7** | Alarm Buzzer | Güvenlik uyarısında sesli ikaz |
| **A0** | Sıcaklık Sensörü (LM35) | Ortam sıcaklığını okuyup sunucuya yollar |
| **A4 (SDA)** | LCD I2C SDA | 16x2 LCD Ekran Veri Hattı |
| **A5 (SCL)** | LCD I2C SCL | 16x2 LCD Ekran Saat Hattı |
| **5V / GND** | Besleme Hatları | Sensör ve ekran güç bağlantıları |

---

## 📡 Seri Haberleşme Protokolü

Sunucu (Python) ile Arduino arasındaki haberleşme **9600 baud rate** hızında, basit ASCII satır tabanlı metin protokolüyle çalışır:

### Python ➔ Arduino Komutları
| Komut | Anlamı | Örnek |
| :--- | :--- | :--- |
| `LOGIN:<isim>` | Kullanıcı sisteme girdiğinde ekranda göster | `LOGIN:EMRE` |
| `LOGOUT` | Oturum kapandı, ekranı bekleme moduna al | `LOGOUT` |
| `L1:<0\|1>` | Salon ışığını kapat / aç | `L1:1` |
| `L2:<0\|1>` | Mutfak ışığını kapat / aç | `L2:0` |
| `BRT:<0-100>` | PWM parlaklık değerini ayarla | `BRT:75` |
| `TEMP:<derece>` | Sunucudan hedef sıcaklık değeri | `TEMP:24` |
| `ALERT:<tip>` | Kamera alarmı (`HUMAN`, `MOTION`, `CLEAR`) | `ALERT:HUMAN` |

### Arduino ➔ Python Telemetrisi
| Komut | Anlamı |
| :--- | :--- |
| `TEMP:<derece>` | Sensörden periyodik okunan anlık sıcaklık değeri |
| `L1:<0\|1>` | Arduino üzerindeki fiziksel butona basıldığında durum bildirimi |
| `L2:<0\|1>` | Arduino üzerindeki fiziksel butona basıldığında durum bildirimi |

---

## 🚀 Kurulum ve Çalıştırma

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/emretasar02/HomeServis.git
cd HomeServis
```

### 2. Python Sanal Ortamını Hazırlayın
```bash
python3 -m venv venv
source venv/bin/activate  # Windows için: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Linux Cihaz İzinlerini Ayarlayın (Raspberry Pi / Linux)
Kullanıcınızın USB kameraya ve seri porta `sudo` olmadan erişebilmesi için gerekli gruplara ekleyin:
```bash
sudo usermod -aG video,dialout $USER
```
*(Bu işlemden sonra oturumu kapatıp açmanız gerekir.)*

### 4. SSL Sertifikası Üretin (İsteğe Bağlı ama Önerilir)
Tarayıcıların bildirim göndermesine ve mobil cihazlardan güvenli erişime izin vermesi için yerel HTTPS sertifikası oluşturabilirsiniz:
```bash
chmod +x scripts/generate_ssl.sh
./scripts/generate_ssl.sh
```
> **Not:** Sertifika oluşturmazsanız sunucu otomatik olarak HTTP modunda veya geçici adhoc SSL ile başlar.

### 5. Yapılandırma (.env)
Örnek yapılandırma dosyasını kopyalayın:
```bash
cp .env.example .env
```
Gerekiyorsa `.env` dosyası içindeki port veya gizli anahtar ayarlarını düzenleyin.

### 6. Arduino Yazılımını Yükleyin
1. Arduino IDE'yi açın.
2. `arduino/homeservis/homeservis.ino` dosyasını açın.
3. Kütüphane Yöneticisi'nden (Ctrl+Shift+I) **LiquidCrystal_I2C** kütüphanesini yükleyin.
4. Kart ve Port seçimini yapıp yükleyin (Upload).

### 7. Sunucuyu Başlatın
```bash
python flask_smart_home.py
```
Konsolda yerel ağ IP adresiniz basılacaktır:
```text
============================================================
✅  HOMESERVIS HAZIR! Web Arayüzüne Girmek İçin:
============================================================
🌍 Yerel Ağdan (Telefon/PC):  https://192.168.1.35:5000
🏠 Bu Bilgisayardan:          https://127.0.0.1:5000
------------------------------------------------------------
```

---

## 🔑 Varsayılan Kullanıcı Girişleri

Giriş ekranında test amacıyla aşağıdaki kullanıcılar tanımlıdır (bunları `flask_smart_home.py` içerisinden değiştirebilirsiniz):

| Kullanıcı Adı | Şifre |
| :--- | :--- |
| `emre` | `1234` |
| `arif` | `0000` |
| `sedat` | `1111` |

---

## 🛠️ Gelecek Geliştirme Önerileri (Roadmap)

Projenizi daha da ileri taşımak ve topluluk katkılarına açmak için planlanan geliştirmeler:

- [ ] **WebSocket Entegrasyonu:** Polling (saniyede 1 istek) yerine `Flask-SocketIO` kullanarak çift yönlü anlık veri akışı sağlamak.
- [ ] **YOLOv8 Nano Entegrasyonu:** Haar Cascade yerine hafif bir YOLOv8 Nano modeli ile kedi, köpek, araç ve insan ayrımı yapabilmek.
- [ ] **Telegram / Discord Bot Bildirimi:** Hareket algılandığında anlık ekran görüntüsünü Telegram botu üzerinden cep telefonuna göndermek.
- [ ] **Veritabanı ve Olay Günlüğü (Event Logging):** SQLite tabanlı bir loglama ile son 24 saatteki hareket saatlerini ve sıcaklık grafiklerini kaydetmek.
- [ ] **Docker Desteği:** `Dockerfile` ve `docker-compose.yml` ile tek komutla her platformda izole çalışabilirlik.

---

## 🤝 Katkıda Bulunma (Contributing)

Her türlü katkıya açığız!
1. Bu depoyu Fork'layın (`Fork`).
2. Yeni bir özellik dalı oluşturun (`git checkout -b feature/YeniOzellik`).
3. Değişikliklerinizi commit edin (`git commit -m 'feat: Yeni özellik eklendi'`).
4. Dalınızı push edin (`git push origin feature/YeniOzellik`).
5. Bir **Pull Request** açın.

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) kapsamında açık kaynak olarak paylaşılmıştır. Dilediğiniz gibi kullanabilir, değiştirebilir ve geliştirebilirsiniz.
