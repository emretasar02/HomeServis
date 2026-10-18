# -*- coding: utf-8 -*-
"""
HomeServis - Flask Tabanlı Akıllı Ev ve Güvenlik Yönetim Sistemi
---------------------------------------------------------------
Bu sunucu;
1. Web kontrol arayüzünü (Dashboard) sunar,
2. Canlı kamera akışını (MJPEG) ve OpenCV hareket/insan tespiti sonuçlarını iletir,
3. Arduino ile seri port üzerinden haberleşerek ışıkları, sıcaklığı ve parlaklığı yönetir,
4. Kamera alarm durumlarını (Hareket / İnsan) Arduino LCD ekranına ve web tarayıcısına anlık bildirir.
"""

import os
import sys
import time
import socket
import atexit
import signal
import threading
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, Response

# ==========================================
# 1. MODÜLLERİ YÜKLEME & GÜVENLİK
# ==========================================
MODULE_ERROR = None
try:
    from kamera import VideoCamera
    from arduino_yoneticisi import ArduinoManager
except ImportError as e:
    MODULE_ERROR = f"Modül Hatası: {e}. 'kamera.py' ve 'arduino_yoneticisi.py' dosyaları eksik."
    print(f"❌ {MODULE_ERROR}", flush=True)

    class VideoCamera:
        def __init__(self, **kwargs): pass
        def get_frame(self): return None
        def get_alert(self): return "Kamera Modülü Yok"
        def stop(self): pass

    class ArduinoManager:
        def __init__(self, **kwargs): self.running = False
        def baslat(self): pass
        def durdur(self): pass
        def gonder(self, cmd): return False
        def alert_gonder(self, alert_tipi): return False

# ==========================================
# 2. AYARLAR VE YAPILANDIRMA (.env Destekli)
# ==========================================
# Güvenlik için kullanıcı bilgileri ortam değişkenlerinden alınabilir,
# ayarlanmamışsa varsayılan test kullanıcıları kullanılır.
DEFAULT_USERS = {
    "emre": "1234",
    "arif": "0000",
    "sedat": "1111"
}

# Ortam değişkeninden kullanıcıları yükle (isteğe bağlı JSON veya virgüllü)
USERS = DEFAULT_USERS

SECRET_KEY = os.getenv('SECRET_KEY', 'homeservis_default_secret_key_change_in_production')
SERVER_HOST = os.getenv('HOST', '0.0.0.0')
SERVER_PORT = int(os.getenv('PORT', 5000))

# Sistem Durumu (Thread-safe yönetim için)
sys_state = {
    "l1": False,
    "l2": False,
    "temp": 22,
    "brightness": 50,
    "arduino_connected": False
}
state_lock = threading.Lock()

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['JSON_AS_ASCII'] = False

global_camera = None
arduino = None
IS_HTTPS = False

# ==========================================
# 3. YARDIMCI FONKSİYONLAR
# ==========================================
def get_ip_address():
    """Cihazın yerel ağ IP adresini tespit eder."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def sistem_bilgilendirme():
    """Sunucu ayağa kalktıktan sonra erişim linklerini konsola basar."""
    time.sleep(2)
    ip = get_ip_address()
    protocol = "https" if IS_HTTPS else "http"

    print("\n" + "=" * 60, flush=True)
    print("✅  HOMESERVIS HAZIR! Web Arayüzüne Girmek İçin:", flush=True)
    print("=" * 60, flush=True)
    print(f"🌍 Yerel Ağdan (Telefon/PC):  {protocol}://{ip}:{SERVER_PORT}", flush=True)
    print(f"🏠 Bu Bilgisayardan:          {protocol}://127.0.0.1:{SERVER_PORT}", flush=True)
    print("-" * 60, flush=True)

    if IS_HTTPS:
        print("🔐  BİLGİ: HTTPS Modu Açık.", flush=True)
        print("    Self-signed sertifika kullanıldığı için tarayıcı uyarabilir;", flush=True)
        print("    'Gelişmiş' -> 'Siteye İlerle' seçeneğine tıklayabilirsiniz.", flush=True)
    else:
        print("ℹ️   BİLGİ: HTTP Modu Açık. (Mobil bildirimler için HTTPS önerilir)", flush=True)
    print("=" * 60 + "\n", flush=True)

# ==========================================
# 4. DONANIMLARI BAŞLATMA
# ==========================================
def on_kamera_alarm(alarm_tipi):
    """Kamera bir hareket veya insan tespit ettiğinde tetiklenir."""
    if arduino:
        arduino.alert_gonder(alarm_tipi)

try:
    print("🔌 Arduino yöneticisi hazırlanıyor...", flush=True)
    def arduino_veri_isleyici(line):
        """Arduino'dan gelen verileri ayrıştırıp sistem durumuna işler."""
        try:
            if ":" in line:
                key, value = line.split(":", 1)
                with state_lock:
                    if key == "L1":
                        sys_state["l1"] = (value.strip() == "1")
                    elif key == "L2":
                        sys_state["l2"] = (value.strip() == "1")
                    elif key == "TEMP":
                        sys_state["temp"] = int(value.strip())
                    elif key == "BRT":
                        sys_state["brightness"] = int(value.strip())
        except Exception as e:
            pass

    arduino = ArduinoManager(baudrate=9600, data_handler=arduino_veri_isleyici, state_dict=sys_state)
    arduino.baslat()
except Exception as e:
    print(f"⚠️ Arduino başlatma hatası: {e}", flush=True)

try:
    print("📷 Kamera başlatılıyor...", flush=True)
    global_camera = VideoCamera(alert_callback=on_kamera_alarm)
except Exception as e:
    print(f"⚠️ Kamera başlatma hatası: {e}", flush=True)

# ==========================================
# 5. GÖRÜNTÜ AKIŞI (STREAM GENERATOR)
# ==========================================
def gen_frames():
    """Kameradan gelen kareleri multipart MJPEG akışı olarak üretir."""
    while True:
        try:
            if global_camera:
                frame = global_camera.get_frame()
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
                else:
                    time.sleep(0.1)
            else:
                time.sleep(0.5)
        except Exception:
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
    <title>Giriş Yap - HomeServis</title>
    <style>
        body { background: #1a1a2e; color: white; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 30px; border-radius: 15px; text-align: center; width: 90%; max-width: 320px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        select, input, button { width: 100%; padding: 15px; margin: 10px 0; border-radius: 12px; border: none; font-size: 1rem; box-sizing: border-box; }
        select, input { background: #0f3460; color: white; -webkit-appearance: none; }
        button { background: #e94560; color: white; cursor: pointer; font-weight: bold; touch-action: manipulation; }
        button:hover { background: #ff5e78; }
        .error { color: #e74c3c; margin-top: 10px; }
        .sys-warning { background: #d35400; padding: 10px; border-radius: 5px; font-size: 0.8rem; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔒 HomeServis</h2>
        <p style="color:#aaa; font-size:0.85rem; margin-top:-5px;">Akıllı Ev & Güvenlik Paneli</p>
        {% if module_error %}<div class="sys-warning">⚠️ {{ module_error }}</div>{% endif %}
        <form method="POST">
            <select name="username" required>
                <option value="" disabled selected>Kullanıcı Seçin</option>
                {% for u in users %}
                <option value="{{ u }}">{{ u|capitalize }}</option>
                {% endfor %}
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
    <title>Kontrol Paneli - HomeServis</title>
    <style>
        body { background: #0f3460; color: white; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 15px; margin: 0; padding-bottom: 50px; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e94560; padding-bottom: 15px; margin-bottom: 20px; }
        .btn-logout { color: white; text-decoration: none; border: 1px solid white; padding: 8px 15px; border-radius: 20px; font-size: 0.9rem; }
        .btn-logout:hover { background: rgba(255,255,255,0.1); }
        .card { background: #16213e; padding: 15px; border-radius: 20px; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        .switch-container { display: flex; gap: 10px; }
        .btn-toggle { flex: 1; padding: 20px; border-radius: 15px; border: none; font-weight: bold; cursor: pointer; font-size: 1rem; touch-action: manipulation; transition: transform 0.1s, background-color 0.2s; }
        .btn-toggle:active { transform: scale(0.95); }
        .on { background: #2ecc71; color: black; box-shadow: 0 0 10px rgba(46, 204, 113, 0.5); }
        .off { background: #333; color: #888; }
        .camera-container { width: 100%; border: 2px solid #e94560; border-radius: 15px; overflow: hidden; background: #000; position: relative; padding-bottom: 75%; height: 0; }
        .camera-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; }
        .alert-box { background-color: #e74c3c; color: white; padding: 15px; border-radius: 10px; font-weight: bold; display: none; animation: blink 1s infinite; margin-bottom: 20px; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        .status-badge { font-size: 0.75rem; padding: 4px 8px; border-radius: 10px; vertical-align: middle; }
        .connected { background: #2ecc71; color: black; }
        .disconnected { background: #e74c3c; color: white; }
        .notif-btn { background: #2980b9; color: white; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9rem; margin-top: 5px; width: 100%; touch-action: manipulation; }
        .temp-ctrl { display: flex; justify-content: center; align-items: center; gap: 20px; }
        .circle-btn { width: 55px; height: 55px; border-radius: 50%; border: none; background: #333; color: white; font-size: 1.8rem; cursor: pointer; touch-action: manipulation; }
        .circle-btn:active { background: #555; }
        .temp-val { font-size: 2.8rem; color: #e94560; font-weight: bold; min-width: 120px; }
        input[type=range] { width: 100%; margin-top: 20px; height: 30px; }
    </style>
</head>
<body>
    <div class="header">
        <div style="text-align:left;">
            <div style="font-size: 1.1rem; font-weight: bold;">👤 {{ user|upper }}</div>
            <span id="conn-status" class="status-badge disconnected">ARDUINO: BAĞLANIYOR...</span>
        </div>
        <a href="/logout" class="btn-logout">Çıkış</a>
    </div>

    <div style="margin-bottom: 15px;">
        <button onclick="requestNotificationPermission()" class="notif-btn" id="btn-notif">🔔 Tarayıcı Bildirimlerini Aç</button>
    </div>

    <div id="security-alert" class="alert-box">⚠️ Hareket Algılandı!</div>

    <div class="card">
        <h3>📷 Güvenlik Kamerası (Canlı)</h3>
        <div class="camera-container">
            <img id="cam-stream" src="/video_feed" class="camera-img" onerror="handleCamError(this)">
        </div>
    </div>

    <div class="card">
        <h3>💡 Aydınlatma Kontrolü</h3>
        <div class="switch-container">
            <button id="btn-l1" class="btn-toggle off" onclick="toggle('l1')">SALON</button>
            <button id="btn-l2" class="btn-toggle off" onclick="toggle('l2')">MUTFAK</button>
        </div>
    </div>

    <div class="card">
        <h3>🌡️ Sıcaklık Ayarı</h3>
        <div class="temp-ctrl">
            <button class="circle-btn" onclick="temp('down')">-</button>
            <div id="temp-display" class="temp-val">--°C</div>
            <button class="circle-btn" onclick="temp('up')">+</button>
        </div>
    </div>

    <div class="card">
        <h3>☀️ Ortam Parlaklığı</h3>
        <input type="range" id="brt-slider" min="0" max="100" onchange="setBrightness(this.value)">
    </div>

    <button class="notif-btn" style="background:#333; margin-top:10px;" onclick="syncArduino()">🔄 Arduino'yu Yeniden Eşitle</button>

    <script>
        let lastNotificationTime = 0;

        function handleCamError(img) {
            img.style.display = 'none';
            setTimeout(() => {
                img.src = '/video_feed?' + new Date().getTime();
                img.style.display = 'block';
            }, 3000);
        }

        function requestNotificationPermission() {
            if (!("Notification" in window)) {
                alert("Tarayıcınız bildirimleri desteklemiyor.");
            } else {
                Notification.requestPermission().then(permission => {
                    if (permission === "granted") {
                        sendWebNotification("Bildirimler Aktif!");
                        if (navigator.vibrate) navigator.vibrate([200]);
                    } else {
                        alert("İzin verilmedi. HTTPS bağlantısı ve tarayıcı ayarlarını kontrol edin.");
                    }
                });
            }
        }

        function sendWebNotification(msg) {
            if (Notification.permission === "granted" && msg !== "") {
                const now = Date.now();
                if (now - lastNotificationTime > 30000 || msg === "Bildirimler Aktif!") {
                    try {
                        new Notification("HomeServis Uyarısı", {
                            body: msg,
                            vibrate: [200, 100, 200]
                        });
                        if (navigator.vibrate) navigator.vibrate([500, 200, 500]);
                    } catch(e) {}
                    if (msg !== "Bildirimler Aktif!") lastNotificationTime = now;
                }
            }
        }

        setInterval(() => {
            fetch('/api/status').then(r => r.json()).then(d => {
                document.getElementById('btn-l1').className = d.l1 ? 'btn-toggle on' : 'btn-toggle off';
                document.getElementById('btn-l2').className = d.l2 ? 'btn-toggle on' : 'btn-toggle off';
                document.getElementById('temp-display').innerText = d.temp + '°C';
                const st = document.getElementById('conn-status');
                st.className = d.arduino_connected ? 'status-badge connected' : 'status-badge disconnected';
                st.innerText = d.arduino_connected ? 'ARDUINO: AKTİF' : 'ARDUINO: PASİF';

                const sl = document.getElementById('brt-slider');
                if (document.activeElement !== sl) sl.value = d.brightness;
            }).catch(() => {});

            fetch('/api/alerts').then(r => r.json()).then(d => {
                const box = document.getElementById('security-alert');
                if (d.alert) {
                    box.style.display = 'block';
                    box.innerText = d.alert;
                    box.style.backgroundColor = d.alert.includes("İNSAN") ? "#e74c3c" : "#f39c12";
                    sendWebNotification(d.alert);
                } else {
                    box.style.display = 'none';
                }
            }).catch(() => {});
        }, 1000);

        function toggle(l) { fetch('/api/toggle/' + l, {method:'POST'}).catch(() => {}); }
        function temp(a) { fetch('/api/temp/' + a, {method:'POST'}).catch(() => {}); }
        function setBrightness(v) { fetch('/api/brt/' + v, {method:'POST'}).catch(() => {}); }
        function syncArduino() { fetch('/api/sync', {method:'POST'}).catch(() => {}); }
    </script>
</body>
</html>
"""

# ==========================================
# 7. ROTALAR (HTTP API & VIEWS)
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        if u in USERS and USERS[u] == p:
            session['user'] = u
            if arduino:
                arduino.gonder(f"LOGIN:{u}")
            return redirect(url_for('dashboard'))
        else:
            error = "Hatalı Şifre!"
    return render_template_string(HTML_LOGIN, error=error, module_error=MODULE_ERROR, users=list(USERS.keys()))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template_string(HTML_DASHBOARD, user=session['user'], module_error=MODULE_ERROR)

@app.route('/logout')
def logout():
    session.pop('user', None)
    if arduino:
        arduino.gonder("LOGOUT")
    return redirect(url_for('login'))

@app.route('/video_feed')
def video_feed():
    if 'user' not in session:
        return "Yetkisiz Erişim", 401
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/alerts')
def get_alerts():
    alert_txt = global_camera.get_alert() if global_camera else ""
    return jsonify({"alert": alert_txt})

@app.route('/api/status')
def get_status():
    with state_lock:
        return jsonify(sys_state)

@app.route('/api/sync', methods=['POST'])
def api_sync():
    if 'user' in session and arduino:
        with state_lock:
            l1_val = '1' if sys_state['l1'] else '0'
            l2_val = '1' if sys_state['l2'] else '0'
            brt_val = sys_state['brightness']
            temp_val = sys_state['temp']

        arduino.gonder(f"LOGIN:{session['user']}")
        arduino.gonder(f"L1:{l1_val}")
        arduino.gonder(f"L2:{l2_val}")
        arduino.gonder(f"BRT:{brt_val}")
        arduino.gonder(f"TEMP:{temp_val}")
        return jsonify({"success": True})
    return jsonify({"error": "Yetkisiz veya Arduino yok"}), 401

@app.route('/api/toggle/<light>', methods=['POST'])
def api_toggle(light):
    if 'user' in session and light in sys_state:
        with state_lock:
            sys_state[light] = not sys_state[light]
            new_val = sys_state[light]

        if arduino:
            arduino.gonder(f"{light.upper()}:{'1' if new_val else '0'}")
        return jsonify({"success": True, "state": new_val})
    return jsonify({"error": "Yetkisiz"}), 401

@app.route('/api/temp/<action>', methods=['POST'])
def api_temp(action):
    if 'user' in session:
        with state_lock:
            if action == 'up':
                sys_state["temp"] += 1
            elif action == 'down':
                sys_state["temp"] -= 1
            curr_temp = sys_state["temp"]

        if arduino:
            arduino.gonder(f"TEMP:{curr_temp}")
        return jsonify({"success": True, "temp": curr_temp})
    return jsonify({"error": "Yetkisiz"}), 401

@app.route('/api/brt/<int:val>', methods=['POST'])
def api_brt(val):
    if 'user' in session:
        val = max(0, min(100, val))
        with state_lock:
            sys_state["brightness"] = val

        if arduino:
            arduino.gonder(f"BRT:{val}")
        return jsonify({"success": True, "brightness": val})
    return jsonify({"error": "Yetkisiz"}), 401

# ==========================================
# 8. ÇIKIŞ & TEMİZLİK PROTOKOLÜ
# ==========================================
def cleanup():
    """Program sonlandığında donanımları güvenle serbest bırakır."""
    print("\n🛑 [Sistem] Donanımlar kapatılıyor...", flush=True)
    if global_camera:
        global_camera.stop()
    if arduino:
        arduino.durdur()

atexit.register(cleanup)

def sig_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)

# ==========================================
# 9. SUNUCU BAŞLATICI
# ==========================================
if __name__ == '__main__':
    # Bilgilendirme konsol çıktısı thread'i
    threading.Thread(target=sistem_bilgilendirme, daemon=True).start()

    print(f"🚀 Flask Sunucusu Başlatılıyor (Port: {SERVER_PORT})...", flush=True)

    # SSL Kontrolü
    if os.path.exists('cert.pem') and os.path.exists('key.pem'):
        print("🔐 Sertifikalar bulundu. HTTPS (Kalıcı) başlatılıyor...", flush=True)
        IS_HTTPS = True
        app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True, ssl_context=('cert.pem', 'key.pem'))
    else:
        try:
            print("⚠️ Özel sertifika bulunamadı. Adhoc HTTPS deneniyor...", flush=True)
            IS_HTTPS = True
            app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True, ssl_context='adhoc')
        except Exception as e:
            IS_HTTPS = False
            print(f"⚠️ HTTPS başlatılamadı ({e}). HTTP moduna geçiliyor...", flush=True)
            app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)
