/*
  ===================================================================
  HomeServis - Arduino Akıllı Ev ve Güvenlik Ekranı Aygıt Yazılımı
  ===================================================================
  Açıklama:
    Bu yazılım, HomeServis Python/Flask sunucusundan Seri Port (USB)
    üzerinden gelen komutları dinler, 16x2 LCD ekranda sistem durumunu,
    giriş yapan kullanıcıyı, oda sıcaklığını ve kameradan gelen güvenlik
    uyarılarını (Hareket / İnsan Tespiti) gösterir.

  Protokol (Gelen Komutlar - Python -> Arduino):
    - LOGIN:<kullanici_adi>  -> Giriş yapan kullanıcıyı ekranda gösterir.
    - LOGOUT                 -> Ekranı kilitli/bekleme moduna alır.
    - L1:1 / L1:0           -> Salon ışığını açar/kapatır (Pin 8).
    - L2:1 / L2:0           -> Mutfak ışığını açar/kapatır (Pin 9).
    - BRT:<0-100>           -> Ortam/LED parlaklığını PWM ile ayarlar (Pin 6).
    - TEMP:<deger>          -> Sunucudan gelen hedef sıcaklığı ayarlar.
    - ALERT:HUMAN           -> Kamera insan tespit ettiğinde buzzer çalar, ekranda uyarı çıkar!
    - ALERT:MOTION          -> Kamera hareket algıladığında uyarı verir.
    - ALERT:CLEAR           -> Uyarı durumunu temizler.

  Protokol (Giden Veriler - Arduino -> Python):
    - TEMP:<olculen_deger>  -> LM35/DHT sensöründen okunan sıcaklık (her 5 sn).
    - L1:1 / L1:0           -> Donanımsal buton basıldığında durum değişimi.
    - L2:1 / L2:0           -> Donanımsal buton basıldığında durum değişimi.

  Kütüphaneler:
    - LiquidCrystal_I2C (Arduino Kütüphane Yöneticisi'nden yüklenebilir)
    - Wire.h (Standart I2C)
  ===================================================================
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// --- PIN TANIMLAMALARI ---
const int PIN_L1 = 8;        // Salon Işığı (LED / Röle)
const int PIN_L2 = 9;        // Mutfak Işığı (LED / Röle)
const int PIN_PWM = 6;       // PWM Parlaklık Çıkışı (Dimmer LED)
const int PIN_BUZZER = 7;    // Güvenlik alarm buzzer'ı
const int PIN_TEMP = A0;     // LM35 Analog Sıcaklık Sensörü (Opsiyonel)

// --- LCD AYARLARI ---
// Genellikle I2C adresi 0x27 veya 0x3F olur.
LiquidCrystal_I2C lcd(0x27, 16, 2);

// --- SİSTEM DEĞİŞKENLERİ ---
bool l1_state = false;
bool l2_state = false;
int brightness_val = 50;     // 0 - 100 arası
int current_temp = 22;       // Sıcaklık
String current_user = "YOK"; // Giriş yapan kullanıcı
String alert_msg = "";       // Anlık güvenlik uyarısı
unsigned long alert_start_time = 0;
unsigned long last_temp_send = 0;
String serial_buffer = "";

void setup() {
  Serial.begin(9600);
  
  // Pin modları
  pinMode(PIN_L1, OUTPUT);
  pinMode(PIN_L2, OUTPUT);
  pinMode(PIN_PWM, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  
  digitalWrite(PIN_L1, LOW);
  digitalWrite(PIN_L2, LOW);
  digitalWrite(PIN_BUZZER, LOW);
  analogWrite(PIN_PWM, map(brightness_val, 0, 100, 0, 255));

  // LCD Başlatma
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(" HomeServis v2.0 ");
  lcd.setCursor(0, 1);
  lcd.print("Baglanti Bekliyor");
  
  delay(1500);
  updateDisplay();
}

void loop() {
  // 1. Seri Porttan Veri Oku
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    if (inChar == '\n' || inChar == '\r') {
      if (serial_buffer.length() > 0) {
        processCommand(serial_buffer);
        serial_buffer = "";
      }
    } else {
      serial_buffer += inChar;
    }
  }

  // 2. Alarm Süresi Kontrolü (3 saniye sonra alarm yazısını temizle)
  if (alert_msg.length() > 0 && millis() - alert_start_time > 3500) {
    alert_msg = "";
    digitalWrite(PIN_BUZZER, LOW);
    updateDisplay();
  }

  // 3. Periyodik Sensör Okuma ve Gönderme (5 saniyede bir)
  if (millis() - last_temp_send > 5000) {
    last_temp_send = millis();
    readAndSendTemperature();
  }
}

// Gelen komutları ayrıştırma fonksiyonu
void processCommand(String cmd) {
  cmd.trim();
  
  // GİRİŞ / ÇIKIŞ KOMUTLARI
  if (cmd.startsWith("LOGIN:")) {
    current_user = cmd.substring(6);
    current_user.toUpperCase();
    toneAlert(1000, 150); // Hoş geldin bipi
    updateDisplay();
  }
  else if (cmd == "LOGOUT") {
    current_user = "YOK";
    toneAlert(600, 150);
    updateDisplay();
  }
  // AYDINLATMA KOMUTLARI
  else if (cmd.startsWith("L1:")) {
    l1_state = (cmd.substring(3) == "1");
    digitalWrite(PIN_L1, l1_state ? HIGH : LOW);
    updateDisplay();
  }
  else if (cmd.startsWith("L2:")) {
    l2_state = (cmd.substring(3) == "1");
    digitalWrite(PIN_L2, l2_state ? HIGH : LOW);
    updateDisplay();
  }
  // PARLAKLIK AYARI (PWM)
  else if (cmd.startsWith("BRT:")) {
    brightness_val = cmd.substring(4).toInt();
    brightness_val = constrain(brightness_val, 0, 100);
    int pwm = map(brightness_val, 0, 100, 0, 255);
    analogWrite(PIN_PWM, pwm);
    updateDisplay();
  }
  // HEDEF SICAKLIK BİLGİSİ
  else if (cmd.startsWith("TEMP:")) {
    current_temp = cmd.substring(5).toInt();
    updateDisplay();
  }
  // GÜVENLİK / KAMERA ALARMLARI
  else if (cmd.startsWith("ALERT:")) {
    String type = cmd.substring(6);
    alert_start_time = millis();
    
    if (type == "HUMAN") {
      alert_msg = "!INSAN ALGILANDI!";
      toneAlert(1800, 400); // Tiz uyarı sesi
    } else if (type == "MOTION") {
      alert_msg = "!HAREKET VAR!";
      toneAlert(1200, 200);
    } else if (type == "CLEAR") {
      alert_msg = "";
      digitalWrite(PIN_BUZZER, LOW);
    }
    updateDisplay();
  }
}

// 16x2 LCD Ekranı Güncelleme
void updateDisplay() {
  lcd.clear();
  
  // Eğer aktif bir güvenlik uyarısı varsa ekrana onu bas
  if (alert_msg.length() > 0) {
    lcd.setCursor(0, 0);
    lcd.print(">>> GUVENLIK <<<");
    lcd.setCursor(0, 1);
    lcd.print(alert_msg);
    return;
  }

  // Satır 1: Kullanıcı ve Sıcaklık (Örn: "U:EMRE   24C")
  lcd.setCursor(0, 0);
  if (current_user == "YOK") {
    lcd.print("KILITLI ");
  } else {
    lcd.print("U:" + current_user.substring(0, 6) + " ");
  }
  
  lcd.setCursor(10, 0);
  lcd.print("T:" + String(current_temp) + (char)223 + "C");

  // Satır 2: Işıklar ve Parlaklık (Örn: "L1:1 L2:0 B:%50")
  lcd.setCursor(0, 1);
  lcd.print("L1:");
  lcd.print(l1_state ? "A" : "K");
  lcd.print(" L2:");
  lcd.print(l2_state ? "A" : "K");
  
  lcd.setCursor(10, 1);
  lcd.print("B:%" + String(brightness_val));
}

// Buzzer sesi üretici
void toneAlert(int freq, int duration_ms) {
  tone(PIN_BUZZER, freq, duration_ms);
}

// Analog Sıcaklık Okuma (LM35 bağlıysa okur, yoksa mevcut değeri yollar)
void readAndSendTemperature() {
  int sensorValue = analogRead(PIN_TEMP);
  // LM35 formülü: (Vout in mV) / 10 = Sıcaklık (°C)
  // 5V Arduino için: (sensorValue * 5.0 * 100.0) / 1024.0
  float voltage = (sensorValue * 5.0) / 1024.0;
  float tempC = voltage * 100.0;
  
  // Eğer sensör bağlıysa (mantıklı bir aralıktaysa) gönder
  if (tempC > 5.0 && tempC < 60.0) {
    current_temp = (int)tempC;
    Serial.print("TEMP:");
    Serial.println(current_temp);
  }
}
