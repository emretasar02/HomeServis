# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, Response
import time
import sys
import os
import threading
import socket

# ==========================================
# 1. GÜVENLİ MODÜL YÜKLEME
# ==========================================
MODULE_ERROR = None
try:
    from kamera import VideoCamera
    from arduino_yoneticisi import ArduinoManager
except ImportError as e:
    MODULE_ERROR = f"Modül Hatası: {e}. 'kamera.py' ve 'arduino_yoneticisi.py' dosyaları eksik."
    print(f"❌ {MODULE_ERROR}", flush=True)
    
    # Hata durumunda sunucunun çökmemesi için sahte sınıflar
    class VideoCamera:
        def get_frame(self): return None
        def get_alert(self): return "Sistem Hatası: Kamera Modülü Yok"
    class ArduinoManager:
        def __init__(self, **kwargs): self.running = False
        def baslat(self): pass
        def gonder(self, cmd): return False

# ==========================================
# 2. AYARLAR VE GLOBAL DEĞİŞKENLER
# ==========================================

USERS = {
    "emre": "1234",
    "arif": "0000",
    "sedat": "1111"
}

# Sistemin anlık durumu
sys_state = {
    "l1": False, "l2": False, "temp": 22, "brightness": 50, "arduino_connected": False
}

app = Flask(__name__)
app.secret_key = 'super_gizli_anahtar_123'
app.config['JSON_AS_ASCII'] = False

global_camera = None
arduino = None
IS_HTTPS = False  # Sunucunun hangi modda çalıştığını takip eder

# ==========================================
# 3. YARDIMCI FONKSİYONLAR (BİLGİLENDİRME)
# ==========================================
def get_ip_address():
    """Cihazın yerel ağ IP adresini bulur."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "192.168.X.X"

def sistem_bilgilendirme():
    """Sunucu açıldığında kullanıcıya giriş adreslerini gösterir."""
    time.sleep(3)  # Flask'ın başlatılmasını bekle
    ip = get_ip_address()
    protocol = "https" if IS_HTTPS else "http"
    
    print("\n" + "="*60, flush=True)
    print("✅  SİSTEM HAZIR! Web Arayüzüne Girmek İçin:", flush=True)
    print("="*60, flush=True)
    print(f"🌍 Yerel Ağdan (Telefon/PC):  {protocol}://{ip}:5000", flush=True)
    print(f"🏠 Bu Bilgisayardan:          {protocol}://127.0.0.1:5000", flush=True)
    print("-" * 60, flush=True)
    
    if IS_HTTPS:
        print("⚠️  UYARI: HTTPS Modu Açık!", flush=True)
        print("    1. Tarayıcı 'Güvenli Değil' diyebilir -> 'Gelişmiş' > 'Siteye İlerle' deyin.", flush=True)
        print("    2. Mobil tarayıcılarda da aynı şekilde izni vermeniz gerekir.", flush=True)
    else:
        print("ℹ️  Bilgi: HTTP (Güvensiz) Modu Açık.", flush=True)
        print("    Mobilde bildirimler HTTP modunda çalışmayabilir.", flush=True)
        
    print("="*60 + "\n", flush=True)

# ==========================================
# 4. DONANIMLARI BAŞLATMA
# ==========================================

# --- KAMERA BAŞLATMA ---
try:
    print("📷 Kamera başlatılıyor...", flush=True)
    global_camera = VideoCamera()
except Exception as e:
    print(f"⚠️ Kamera hatası: {e}", flush=True)

# --- ARDUINO BAŞLATMA ---
try:
    print("🔌 Arduino yöneticisi hazırlanıyor...", flush=True)
    def arduino_veri_isleyici(line):
        try:
            if ":" in line:
                key, value = line.split(":")
                if key == "L1": sys_state["l1"] = (value == "1")
                elif key == "L2": sys_state["l2"] = (value == "1")
                elif key == "TEMP": sys_state["temp"] = int(value)
                elif key == "BRT": sys_state["brightness"] = int(value)
        except:
            pass

    arduino = ArduinoManager(baudrate=9600, data_handler=arduino_veri_isleyici, state_dict=sys_state)
    arduino.baslat()
except Exception as e:
    print(f"⚠️ Arduino hatası: {e}", flush=True)

# ==========================================
# 5. KAMERA AKIŞI
# ==========================================
def gen_frames():
    while True:
        try:
            if global_camera:
                frame = global_camera.get_frame()
                if frame:
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
                else:
                    time.sleep(0.1)
            else:
                time.sleep(1)
        except:
            time.sleep(0.5)

# ==========================================
# 6. HTML ŞABLONLARI
# ==========================================

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <title>Giriş Yap</title>
    <style>
        body { background: #1a1a2e; color: white; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 30px; border-radius: 15px; text-align: center; width: 90%; max-width: 320px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        select, input, button { width: 100%; padding: 15px; margin: 10px 0; border-radius: 12px; border: none; font-size: 1rem; box-sizing: border-box; }
        select, input { background: #0f3460; color: white; -webkit-appearance: none; }
        button { background: #e94560; color: white; cursor: pointer; font-weight: bold; touch-action: manipulation; }
        .error { color: #e74c3c; margin-top: 10px; }
        .sys-warning { background: #d35400; padding: 10px; border-radius: 5px; font-size: 0.8rem; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔒 Ev Güvenlik</h2>
        {% if module_error %}<div class="sys-warning">⚠️ {{ module_error }}</div>{% endif %}
        <form method="POST">
            <select name="username" required>
                <option value="" disabled selected>Kullanıcı Seçin</option>
                <option value="emre">Emre</option>
                <option value="arif">Arif</option>
                <option value="sedat">Sedat</option>
            </select>
            <input type="password" name="password" placeholder="Şifre" required>
            <button type="submit">GİRİŞ YAP</button>
        </form>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </div>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <!-- PWA (Mobil Uygulama) Ayarları -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>Kontrol Paneli</title>
    <style>
        body { background: #0f3460; color: white; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 20px; margin: 0; padding-bottom: 50px; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e94560; padding-bottom: 15px; margin-bottom: 20px; }
        .btn-logout { color: white; text-decoration: none; border: 1px solid white; padding: 8px 15px; border-radius: 20px; font-size: 0.9rem; }
        .card { background: #16213e; padding: 20px; border-radius: 20px; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        .switch-container { display: flex; gap: 10px; }
        .btn-toggle { flex: 1; padding: 20px; border-radius: 15px; border: none; font-weight: bold; cursor: pointer; font-size: 1rem; touch-action: manipulation; transition: transform 0.1s; }
        .btn-toggle:active { transform: scale(0.95); }
        .on { background: #2ecc71; color: black; box-shadow: 0 0 10px rgba(46, 204, 113, 0.5); }
        .off { background: #333; color: #888; }
        .camera-container { width: 100%; border: 2px solid #e94560; border-radius: 15px; overflow: hidden; background: #000; min-height: 220px; position: relative; }
        .camera-img { width: 100%; display: block; }
        .alert-box { background-color: #e74c3c; color: white; padding: 15px; border-radius: 10px; font-weight: bold; display: none; animation: blink 1s infinite; margin-bottom: 20px; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        .status-badge { font-size: 0.75rem; padding: 4px 8px; border-radius: 10px; vertical-align: middle; }
        .connected { background: #2ecc71; color: black; }
        .disconnected { background: #e74c3c; color: white; }
        .notif-btn { background: #2980b9; color: white; padding: 8px 12px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.85rem; margin-top: 5px; width: 100%; }
        
        .temp-ctrl { display: flex; justify-content: center; align-items: center; gap: 20px; }
        .circle-btn { width: 55px; height: 55px; border-radius: 50%; border: none; background: #333; color: white; font-size: 1.8rem; cursor: pointer; touch-action: manipulation; }
        .circle-btn:active { background: #555; }
        .temp-val { font-size: 2.8rem; color: #e94560; font-weight: bold; }
        input[type=range] { width: 100%; margin-top: 20px; height: 30px; }
        
        /* iOS için özel uyarı */
        .ios-hint { font-size: 0.8rem; color: #aaa; margin-top: 5px; display: none; }
    </style>
</head>
<body>
    <div class="header">
        <div style="text-align:left;">
            <div style="font-size: 1.1rem; font-weight: bold;">👤 {{ user|upper }}</div>
            <span id="conn-status" class="status-badge disconnected">Bağlanıyor...</span>
        </div>
        <a href="/logout" class="btn-logout">Çıkış</a>
    </div>

    <!-- Bildirim İzni ve iOS Uyarısı -->
    <div style="margin-bottom: 15px;">
        <button onclick="requestNotificationPermission()" class="notif-btn" id="btn-notif">🔔 Bildirimleri Aç / Test Et</button>
        <div id="ios-msg" class="ios-hint">iPhone'da bildirimler için bu sayfayı <strong>"Ana Ekrana Ekle"</strong>melisiniz.</div>
    </div>

    <div id="security-alert" class="alert-box">⚠️ Hareket Algılandı!</div>

    <div class="card">
        <h3>📷 Güvenlik Kamerası</h3>
        <div class="camera-container">
            <img id="cam-stream" src="/video_feed" class="camera-img" onerror="this.style.display='none'; setTimeout(() => { this.src='/video_feed?'+new Date().getTime(); this.style.display='block'; }, 3000);">
        </div>
    </div>

    <div class="card">
        <h3>💡 Aydınlatma</h3>
        <div class="switch-container">
            <button id="btn-l1" class="btn-toggle off" onclick="toggle('l1')">SALON</button>
            <button id="btn-l2" class="btn-toggle off" onclick="toggle('l2')">MUTFAK</button>
        </div>
    </div>

    <div class="card">
        <h3>🌡️ Sıcaklık</h3>
        <div class="temp-ctrl">
            <button class="circle-btn" onclick="temp('down')">-</button>
            <div id="temp-display" class="temp-val">--°C</div>
            <button class="circle-btn" onclick="temp('up')">+</button>
        </div>
    </div>
    
    <div class="card">
        <h3>☀️ Parlaklık</h3>
        <input type="range" id="brt-slider" min="0" max="100" onchange="setBrightness(this.value)">
    </div>
    
    <button class="notif-btn" style="background:#333; margin-top:10px;" onclick="syncArduino()">🔄 Arduino'yu Eşitle</button>

    <script>
        let lastNotificationMsg = "";
        let lastNotificationTime = 0;

        // iOS Kontrolü
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        if (isIOS) {
            document.getElementById('ios-msg').style.display = 'block';
        }

        function requestNotificationPermission() {
            if (!("Notification" in window)) {
                alert("Tarayıcınız bildirimleri desteklemiyor.");
            } else {
                Notification.requestPermission().then(permission => {
                    if (permission === "granted") {
                        // Test bildirimi ve titreşim
                        sendWebNotification("Bildirimler Aktif!");
                        if (navigator.vibrate) navigator.vibrate([200]);
                    } else if (permission === "denied") {
                        alert("Bildirim izni reddedildi. Lütfen tarayıcı ayarlarından siteye izin verin.");
                    }
                });
            }
        }

        function sendWebNotification(msg) {
            if (Notification.permission === "granted" && msg !== "") {
                const now = Date.now();
                // 30 saniye spam kontrolü
                if (now - lastNotificationTime > 30000 || msg === "Bildirimler Aktif!") {
                    
                    const iconUrl = msg.includes("İNSAN") 
                        ? "https://cdn-icons-png.flaticon.com/512/564/564619.png" 
                        : "https://cdn-icons-png.flaticon.com/512/3602/3602145.png";

                    // Tarayıcı Bildirimi
                    new Notification("GÜVENLİK UYARISI!", { 
                        body: msg, 
                        icon: iconUrl,
                        vibrate: [200, 100, 200] 
                    });

                    // Telefon Titreşimi (Android)
                    if (navigator.vibrate) {
                        navigator.vibrate([500, 200, 500]); 
                    }
                    
                    if (msg !== "Bildirimler Aktif!") {
                        lastNotificationTime = now;
                    }
                }
            }
        }

        setInterval(() => {
            fetch('/api/status').then(r=>r.json()).then(d => {
                document.getElementById('btn-l1').className = d.l1 ? 'btn-toggle on' : 'btn-toggle off';
                document.getElementById('btn-l2').className = d.l2 ? 'btn-toggle on' : 'btn-toggle off';
                document.getElementById('temp-display').innerText = d.temp + '°C';
                const st = document.getElementById('conn-status');
                st.className = d.arduino_connected ? 'status-badge connected' : 'status-badge disconnected';
                st.innerText = d.arduino_connected ? 'ARDUINO: AKTİF' : 'ARDUINO: PASİF';
                
                const sl = document.getElementById('brt-slider');
                if(document.activeElement !== sl) sl.value = d.brightness;
            }).catch(e=>{});

            fetch('/api/alerts').then(r=>r.json()).then(d => {
                const box = document.getElementById('security-alert');
                if(d.alert) {
                    box.style.display = 'block';
                    box.innerText = d.alert;
                    box.style.backgroundColor = d.alert.includes("İNSAN") ? "#e74c3c" : "#f39c12";
                    sendWebNotification(d.alert);
                } else {
                    box.style.display = 'none';
                }
            }).catch(e=>{});
        }, 1000);

        function toggle(l) { fetch('/api/toggle/'+l, {method:'POST'}); }
        function temp(a) { fetch('/api/temp/'+a, {method:'POST'}); }
        function setBrightness(v) { fetch('/api/brt/'+v, {method:'POST'}); }
        function syncArduino() { fetch('/api/sync', {method:'POST'}); }
    </script>
</body>
</html>
"""

# ==========================================
# 7. ROTALAR
# ==========================================

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session: return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        if u in USERS and USERS[u] == p:
            session['user'] = u
            if arduino: arduino.gonder(f"LOGIN:{u}")
            return redirect(url_for('dashboard'))
        else:
            error = "Hatalı Şifre!"
    return render_template_string(HTML_LOGIN, error=error, module_error=MODULE_ERROR)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template_string(HTML_DASHBOARD, user=session['user'], module_error=MODULE_ERROR)

@app.route('/logout')
def logout():
    session.pop('user', None)
    if arduino: arduino.gonder("LOGOUT")
    return redirect(url_for('login'))

@app.route('/video_feed')
def video_feed():
    if 'user' not in session: return "Yetkisiz", 401
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/alerts')
def get_alerts():
    return jsonify({"alert": global_camera.get_alert() if global_camera else ""})

@app.route('/api/status')
def get_status(): return jsonify(sys_state)

@app.route('/api/sync', methods=['POST'])
def api_sync():
    if 'user' in session and arduino:
        arduino.gonder(f"LOGIN:{session['user']}")
        arduino.gonder(f"L1:{'1' if sys_state['l1'] else '0'}")
        arduino.gonder(f"L2:{'1' if sys_state['l2'] else '0'}")
    return jsonify({"success":True})

@app.route('/api/toggle/<light>', methods=['POST'])
def api_toggle(light):
    if 'user' in session and light in sys_state:
        sys_state[light] = not sys_state[light]
        if arduino: arduino.gonder(f"{light.upper()}:{'1' if sys_state[light] else '0'}")
        return jsonify({"success":True})
    return jsonify({"error":"Yetkisiz"}), 401

@app.route('/api/temp/<action>', methods=['POST'])
def api_temp(action):
    if 'user' in session:
        if action == 'up': sys_state["temp"] += 1
        elif action == 'down': sys_state["temp"] -= 1
        if arduino: arduino.gonder(f"TEMP:{sys_state['temp']}")
        return jsonify({"success":True})
    return jsonify({"error":"Yetkisiz"}), 401

@app.route('/api/brt/<int:val>', methods=['POST'])
def api_brt(val):
    if 'user' in session:
        sys_state["brightness"] = val
        if arduino: arduino.gonder(f"BRT:{val}")
        return jsonify({"success":True})
    return jsonify({"error":"Yetkisiz"}), 401

if __name__ == '__main__':
    try:
        # Bilgilendirme Thread'ini Başlat
        threading.Thread(target=sistem_bilgilendirme, daemon=True).start()

        print("🚀 Flask Sunucusu Başlatılıyor (Port 5000)...", flush=True)

        # 1. Öncelik: Dosya tabanlı sertifika (Manuel oluşturulmuş)
        if os.path.exists('cert.pem') and os.path.exists('key.pem'):
            print("🔐 Sertifikalar bulundu. HTTPS (Kalıcı) başlatılıyor...", flush=True)
            IS_HTTPS = True
            app.run(host='0.0.0.0', port=5000, debug=False, threaded=True, ssl_context=('cert.pem', 'key.pem'))
        
        else:
            # 2. Öncelik: Otomatik (Adhoc) Sertifika
            try:
                print("⚠️ Sertifika dosyası yok. Otomatik (Adhoc) sertifika deneniyor...", flush=True)
                IS_HTTPS = True
                app.run(host='0.0.0.0', port=5000, debug=False, threaded=True, ssl_context='adhoc')
            except Exception as e:
                # 3. Öncelik: Mecburen HTTP (Güvensiz)
                IS_HTTPS = False
                print(f"❌ HTTPS Başarısız: {e}", flush=True)
                print("🌍 HTTP (Güvensiz) modda başlatılıyor...", flush=True)
                app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
            
    except KeyboardInterrupt:
        print("\nKapatılıyor...", flush=True)
        if arduino: arduino.running = False
    except Exception as e:
        print(f"\n❌ KRİTİK HATA: {e}", flush=True)
