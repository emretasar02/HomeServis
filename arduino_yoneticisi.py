# -*- coding: utf-8 -*-
"""
HomeServis - Arduino Haberleşme Yöneticisi
------------------------------------------
Bu modül, USB Seri Port üzerinden Arduino ile çift yönlü haberleşmeyi sağlar.
Otomatik port bulma, arka plan dinleme thread'i, kopan bağlantıyı otomatik
yeniden kurma ve durum senkronizasyonu özelliklerine sahiptir.
"""

import time
import threading
import serial
import serial.tools.list_ports


class ArduinoManager:
    def __init__(self, port=None, baudrate=9600, data_handler=None, state_dict=None):
        """
        Arduino bağlantısını yöneten sınıf.
        :param port: Belirli bir port (None verilirse otomatik taranır)
        :param baudrate: Seri haberleşme hızı (Varsayılan: 9600)
        :param data_handler: Veri geldiğinde çağrılacak geri çağırma (callback) fonksiyonu
        :param state_dict: Ana sistem durumunu (sys_state) güncellemek için referans
        """
        self.manual_port = port
        self.baudrate = baudrate
        self.data_handler = data_handler
        self.state_dict = state_dict if state_dict is not None else {}

        self.ser = None
        self.running = False
        self.connected = False
        self.thread = None
        self.lock = threading.Lock()

    def baslat(self):
        """Arka plan dinleme servisini başlatır."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._listen_loop, daemon=True, name="ArduinoListenerThread")
            self.thread.start()
            print("🔌 [Sistem] Arduino dinleme servisi başlatıldı.")

    def durdur(self):
        """Servisi ve seri portu güvenle durdurur."""
        self.running = False
        self._close()
        print("🔌 [Sistem] Arduino dinleme servisi durduruldu.")

    def gonder(self, komut):
        """
        Arduino'ya satır sonu ekleyerek komut gönderir (Thread-safe).
        :param komut: Gönderilecek string (örn: 'L1:1', 'BRT:80')
        :return: Başarılıysa True, aksi halde False
        """
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    full_cmd = f"{komut.strip()}\n".encode('utf-8')
                    self.ser.write(full_cmd)
                    self.ser.flush()
                    return True
                except Exception as e:
                    print(f"⚠️ [Arduino] Komut gönderme hatası ({komut}): {e}")
                    return False
        return False

    def alert_gonder(self, alert_tipi):
        """
        Kamera güvenlik uyarılarını Arduino'ya iletir (Ekran & Buzzer).
        :param alert_tipi: 'HUMAN', 'MOTION', 'CLEAR'
        """
        return self.gonder(f"ALERT:{alert_tipi}")

    def _find_port(self):
        """Bilgisayardaki Arduino/Seri portunu otomatik bulur."""
        if self.manual_port:
            return self.manual_port

        ports = serial.tools.list_ports.comports()
        for port in ports:
            tanim = f"{port.description} {port.hwid}".upper()
            # Yaygın Arduino ve USB-Serial çip tanımları
            if any(x in tanim for x in ["ARDUINO", "USB SERIAL", "ACM", "CH340", "FTDI", "CP210", "USB-SERIAL"]):
                return port.device

        # Linux'ta standart ttyACM0 veya ttyUSB0 varsa ilkini dene
        for dev in ["/dev/ttyACM0", "/dev/ttyUSB0", "/dev/ttyACM1", "/dev/ttyUSB1"]:
            import os
            if os.path.exists(dev):
                return dev

        return None

    def _connect(self):
        """Bağlantı kurmayı dener."""
        port = self._find_port()
        if not port:
            return False

        try:
            self.ser = serial.Serial(port, self.baudrate, timeout=1)
            # Arduino resetlenme süresini bekle (DTR reset)
            time.sleep(2)
            self.connected = True
            with self.lock:
                if self.state_dict is not None:
                    self.state_dict['arduino_connected'] = True
            print(f"✅ [Arduino] Başarıyla bağlandı: {port} ({self.baudrate} baud)")
            return True
        except serial.SerialException as se:
            # İzin hatası (PermissionError / dialout) uyarısı
            if "Permission denied" in str(se):
                print(f"❌ [Arduino İzin Hatası] {port} portuna erişilemiyor!")
                print("   👉 Çözüm: Terminalde şu komutu çalıştırıp oturumu yeniden başlatın:")
                print("   sudo usermod -aG dialout $USER")
            return False
        except Exception as e:
            return False

    def _close(self):
        """Bağlantıyı güvenli bir şekilde kapatır."""
        with self.lock:
            self.connected = False
            if self.state_dict is not None:
                self.state_dict['arduino_connected'] = False

            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None

    def _listen_loop(self):
        """Sürekli çalışan arka plan döngüsü."""
        while self.running:
            # 1. DURUM: Bağlantı varsa oku
            if self.ser and self.ser.is_open:
                try:
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            if self.data_handler:
                                try:
                                    self.data_handler(line)
                                except Exception as handler_err:
                                    print(f"⚠️ [Arduino] Data handler hatası: {handler_err}")
                except (OSError, serial.SerialException):
                    print("⚠️ [Arduino] Bağlantı koptu! Yeniden aranıyor...")
                    self._close()
                except Exception as e:
                    print(f"⚠️ [Arduino] Dinleme hatası: {e}")

            # 2. DURUM: Bağlantı yoksa bağlanmayı dene
            else:
                if self._connect():
                    self._resync_state()
                else:
                    time.sleep(2)  # CPU'yu yormamak için bekle

            time.sleep(0.05)

    def _resync_state(self):
        """Bağlantı kurulduğunda sunucudaki son durumu Arduino'ya senkronize eder."""
        time.sleep(1)
        print("🔄 [Arduino] Sistem durumu donanıma senkronize ediliyor...")
        if self.state_dict:
            try:
                l1_val = '1' if self.state_dict.get('l1') else '0'
                l2_val = '1' if self.state_dict.get('l2') else '0'
                brt_val = self.state_dict.get('brightness', 50)
                temp_val = self.state_dict.get('temp', 22)

                self.gonder(f"L1:{l1_val}")
                self.gonder(f"L2:{l2_val}")
                self.gonder(f"BRT:{brt_val}")
                self.gonder(f"TEMP:{temp_val}")
            except Exception as e:
                print(f"⚠️ [Arduino] Senkronizasyon hatası: {e}")
