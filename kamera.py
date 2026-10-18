# -*- coding: utf-8 -*-
"""
HomeServis - Akıllı Kamera Modülü (OpenCV)
------------------------------------------
Bu modül, web kamerasından görüntü alarak:
- Canlı MJPEG video akışı üretir,
- Kare farkı yöntemiyle (Background Subtraction) hareket algılar,
- Haar Cascade sınıflandırıcısı ile insan/yüz tespiti yapar,
- Tespit anında geri çağırma (callback) ile Arduino veya Web arayüzüne alarm iletir.
"""

import time
import os
import threading
import cv2
import numpy as np


class VideoCamera:
    def __init__(self, camera_index=None, alert_callback=None):
        """
        :param camera_index: Belirli bir kamera indexi (None ise 0, 1, 2 otomatik taranır)
        :param alert_callback: Alarm tetiklendiğinde çağrılacak fonksiyon: callback(alert_type)
        """
        self.alert_callback = alert_callback
        self.video = None
        self.running = True
        self.lock = threading.Lock()
        self.son_jpeg = None
        self.son_bildirim = ""
        self.bildirim_zamani = 0
        self.onceki_kare = None

        # Yüz tanıma modeli (OpenCV dahili Haar Cascade)
        self.face_cascade = None
        if hasattr(cv2, 'CascadeClassifier') and hasattr(cv2, 'data') and hasattr(cv2.data, 'haarcascades'):
            try:
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
            except Exception as e:
                print(f"⚠️ [Kamera] Haar Cascade yüklenemedi: {e}")
        else:
            print("ℹ️ [Kamera] CascadeClassifier bu OpenCV derlemesinde bulunamadı. Sadece hareket algılama aktif.")

        # Kamera cihazını bul ve başlat
        self._init_camera(camera_index)

        # Arka plan işleme thread'ini başlat
        self.thread = threading.Thread(target=self._update_loop, daemon=True, name="CameraProcessingThread")
        self.thread.start()
        print("🎥 [Kamera] Arka plan görüntü işleme thread'i başlatıldı.")

    def _init_camera(self, camera_index):
        """Uygun kamera portunu bulur ve açar."""
        if camera_index is not None:
            indexes = [camera_index]
        else:
            indexes = [0, 1, 2, -1]

        print("📷 [Kamera] Kamera aranıyor...")
        for idx in indexes:
            try:
                # Linux ortamlarında V4L2 backend tercih edilir
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2 if hasattr(cv2, 'CAP_V4L2') else cv2.CAP_ANY)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        print(f"✅ [Kamera] Kamera bulundu ve açıldı! (Index: {idx})")
                        self.video = cap
                        return
                    cap.release()
            except Exception as e:
                print(f"⚠️ [Kamera] Index {idx} denenirken hata: {e}")

        print("⚠️ [Kamera] Aktif bir kamera bulunamadı! Simülasyon/bekleme moduna geçiliyor.")
        # Eğer kamera bulunamazsa kullanıcıya boş ekran yerine bilgi görseli üreteceğiz

    def _generate_placeholder_frame(self, text="KAMERA BULUNAMADI"):
        """Kamera bağlı olmadığında veya görüntü alınamadığında gösterilecek yer tutucu kare."""
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        # Koyu lacivert arka plan
        img[:] = (30, 20, 20)
        cv2.putText(img, "HomeServis Guvenlik", (140, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (233, 69, 96), 2)
        cv2.putText(img, f"[ {text} ]", (120, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(img, "USB Baglantisini veya Izinleri Kontrol Edin", (90, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)

        ret, jpeg = cv2.imencode('.jpg', img)
        return jpeg.tobytes() if ret else None

    def _update_loop(self):
        """Kameradan sürekli görüntü okuyup analiz eden arka plan döngüsü."""
        son_alarm_durumu = ""

        while self.running:
            # Kamera açılmamışsa yer tutucu görsel üretip bekle
            if not self.video or not self.video.isOpened():
                placeholder = self._generate_placeholder_frame("KAMERA BAGLANTISI YOK")
                with self.lock:
                    self.son_jpeg = placeholder
                time.sleep(1.0)
                continue

            success, image = self.video.read()
            if not success:
                time.sleep(0.1)
                continue

            try:
                # 1. Çözünürlüğü optimize et (İşlemci yükünü azaltmak için 640x480)
                image = cv2.resize(image, (640, 480))

                # 2. Gri tonlama ve bulanıklaştırma (Gürültüyü engellemek için)
                gri_kare = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                gri_kare = cv2.GaussianBlur(gri_kare, (21, 21), 0)

                # --- HAREKET ALGILAMA ---
                hareket_var = False
                if self.onceki_kare is None:
                    self.onceki_kare = gri_kare
                else:
                    kare_farki = cv2.absdiff(self.onceki_kare, gri_kare)
                    _, esik = cv2.threshold(kare_farki, 25, 255, cv2.THRESH_BINARY)
                    esik = cv2.dilate(esik, None, iterations=2)
                    konturlar, _ = cv2.findContours(esik.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                    for kontur in konturlar:
                        if cv2.contourArea(kontur) < 800:
                            continue
                        hareket_var = True
                        (x, y, w, h) = cv2.boundingRect(kontur)
                        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    self.onceki_kare = gri_kare

                # --- YÜZ / İNSAN TESPİTİ ---
                faces = []
                if self.face_cascade is not None:
                    try:
                        faces = self.face_cascade.detectMultiScale(
                            gri_kare,
                            scaleFactor=1.3,
                            minNeighbors=5,
                            minSize=(30, 30)
                        )
                    except Exception:
                        faces = []
                insan_var = len(faces) > 0

                for (x, y, w, h) in faces:
                    cv2.rectangle(image, (x, y), (x + w, y + h), (255, 0, 0), 2)
                    cv2.putText(image, "INSAN", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

                # --- BİLDİRİM VE TETİKLEME YÖNETİMİ ---
                yeni_alarm = ""
                if insan_var:
                    yeni_alarm = "HUMAN"
                    self.son_bildirim = "⚠️ İNSAN TESPİT EDİLDİ!"
                    self.bildirim_zamani = time.time()
                elif hareket_var and self.son_bildirim != "⚠️ İNSAN TESPİT EDİLDİ!":
                    yeni_alarm = "MOTION"
                    self.son_bildirim = "🔔 HAREKET ALGILANDI"
                    self.bildirim_zamani = time.time()

                # Alarm durumu değiştiyse callback üzerinden Arduino veya sunucuya bildir
                if yeni_alarm and yeni_alarm != son_alarm_durumu:
                    son_alarm_durumu = yeni_alarm
                    if self.alert_callback:
                        try:
                            self.alert_callback(yeni_alarm)
                        except Exception as cb_err:
                            print(f"⚠️ [Kamera] Callback hatası: {cb_err}")
                elif not yeni_alarm and son_alarm_durumu != "":
                    # Alarm sona erdi
                    if time.time() - self.bildirim_zamani > 3.0:
                        son_alarm_durumu = ""

                # Görüntüyü JPEG formatına sıkıştırıp thread-safe şekilde kaydet
                ret, jpeg = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ret:
                    with self.lock:
                        self.son_jpeg = jpeg.tobytes()

            except Exception as e:
                print(f"⚠️ [Kamera] Frame işleme hatası: {e}")

            time.sleep(0.02)  # ~30 FPS sınırı

    def get_frame(self):
        """Web istemcisine sunulmak üzere bellekteki son hazır kareyi döndürür."""
        with self.lock:
            if self.son_jpeg:
                return self.son_jpeg
        return self._generate_placeholder_frame("GORUNTU ALINAMIYOR")

    def get_alert(self):
        """Son bildirim metnini döndürür (3 saniye sonra otomatik temizlenir)."""
        if time.time() - self.bildirim_zamani > 3.0:
            self.son_bildirim = ""
        return self.son_bildirim

    def stop(self):
        """Kamera ve okuma thread'ini güvenle durdurur."""
        self.running = False
        if self.video and self.video.isOpened():
            self.video.release()
        print("📷 [Kamera] Kamera servisi durduruldu.")

    def __del__(self):
        self.stop()
