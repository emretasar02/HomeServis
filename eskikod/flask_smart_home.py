# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, Response
import time
import sys

# ==========================================
# 1. GÜVENLİ MODÜL YÜKLEME
# ==========================================
MODULE_ERROR = None
try:
    from kamera import VideoCamera
    from arduino_yoneticisi import ArduinoManager
except ImportError as e:
    MODULE_ERROR = f"Modül Hatası: {e}. 'kamera.py' ve 'arduino_yoneticisi.py' dosyaları eksik."
    print(f"❌ {MODULE_ERROR}")
    
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

# ==========================================
# 3. DONANIMLARI BAŞLATMA
# ==========================================

try:
    print("📷 Kamera başlatılıyor...")
    global_camera = VideoCamera()
except Exception as e:
    print(f"⚠️ Kamera hatası: {e}")

try:
    print("🔌 Arduino yöneticisi hazırlanıyor...")
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
    print(f"⚠️ Arduino hatası: {e}")

# ==========================================
# 4. KAMERA AKIŞI
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
# 5. HTML ŞABLONLARI
# ==========================================

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giriş Yap</title>
    <style>
        body { background: #1a1a2e; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 40px; border-radius: 15px; text-align: center; width: 100%; max-width: 320px; }
        select, input, button { width: 100%; padding: 15px; margin: 10px 0; border-radius: 8px; border: none; font-size: 1rem; }
        select, input { background: #0f3460; color: white; }
        button { background: #e94560; color: white; cursor: pointer; font-weight: bold; }
        .error { color: #e74c3c; margin-top: 10px; }
        .sys-warning { background: #d35400; padding: 10px; border-radius: 5px; font-size: 0.8rem; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔒 Güvenlik Sistemi</h2>
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kontrol Paneli</title>
    <style>
        body { background: #0f3460; color: white; font-family: sans-serif; text-align: center; padding: 20px; }
        .header { display: flex; justify-content: space-between; border-bottom: 1px solid #e94560; padding-bottom: 20px; margin-bottom: 20px; }
        .btn-logout { color: white; text-decoration: none; border: 1px solid white; padding: 5px 15px; border-radius: 15px; }
        .card { background: #16213e; padding: 20px; border-radius: 15px; margin-bottom: 20px; }
        .switch-container { display: flex; gap: 10px; }
        .btn-toggle { flex: 1; padding: 25px; border-radius: 12px; border: none; font-weight: bold; cursor: pointer; font-size: 1rem; }
        .on { background: #2ecc71; color: black; }
        .off { background: #333; color: #888; }
        .camera-container { width: 100%; border: 3px solid #e94560; border-radius: 10px; overflow: hidden; background: #000; min-height: 200px; }
        .camera-img { width: 100%; display: block; }
        .alert-box { background-color: #e74c3c; color: white; padding: 15px; border-radius: 10px; font-weight: bold; display: none; animation: blink 1s infinite; margin-bottom: 20px; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        .status-badge { font-size: 0.8rem; padding: 5px 10px; border-radius: 12px; }
        .connected { background: #2ecc71; color: black; }
        .disconnected { background: #e74c3c; color: white; }
        
        /* Bildirim İzni Butonu (İsteğe Bağlı Görünürlük) */
        .notif-btn { background: #2980b9; color: white; padding: 5px 10px; border: none; border-radius: 5px; cursor: pointer; font-size: 0.8rem; margin-top: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            👤 {{ user|upper }} <span id="conn-status" class="status-badge disconnected">Bağlanıyor...</span><br>
            <button onclick="requestNotificationPermission()" class="notif-btn">🔔 Bildirimleri Aç</button>
        </div>
        <a href="/logout" class="btn-logout">Çıkış</a>
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
        <h3>🌡️ Sıcaklık: <span id="temp-display" style="color:#e94560">--°C</span></h3>
    </div>

    <script>
        // Bildirim durumunu takip etmek için değişken
        let lastNotificationMsg = "";

        // Sayfa yüklendiğinde bildirim izni iste
        function requestNotificationPermission() {
            if (!("Notification" in window)) {
                alert("Tarayıcınız bildirimleri desteklemiyor.");
            } else {
                Notification.requestPermission().then(permission => {
                    if (permission === "granted") {
                        new Notification("Bildirimler Aktif!", { body: "Artık hareket algılandığında size haber vereceğiz." });
                    }
                });
            }
        }

        // Web Bildirimi Gönderme Fonksiyonu
        function sendWebNotification(msg) {
            if (Notification.permission === "granted" && msg !== "") {
                // Eğer bu mesajı son 10 saniye içinde göndermediysek gönder (Spam önleme)
                if (msg !== lastNotificationMsg) {
                    const iconUrl = msg.includes("İNSAN") 
                        ? "https://cdn-icons-png.flaticon.com/512/564/564619.png" // Kırmızı uyarı
                        : "https://cdn-icons-png.flaticon.com/512/3602/3602145.png"; // Zil ikonu
                    
                    new Notification("GÜVENLİK UYARISI!", {
                        body: msg,
                        icon: iconUrl,
                        vibrate: [200, 100, 200]
                    });
                    
                    lastNotificationMsg = msg;
                    // 5 saniye sonra aynı mesajı tekrar gönderebilsin diye sıfırla
                    setTimeout(() => { lastNotificationMsg = ""; }, 5000);
                }
            }
        }

        setInterval(() => {
            // Durum Güncelleme
            fetch('/api/status').then(r=>r.json()).then(d => {
                document.getElementById('btn-l1').className = d.l1 ? 'btn-toggle on' : 'btn-toggle off';
                document.getElementById('btn-l2').className = d.l2 ? 'btn-toggle on' : 'btn-toggle off';
                document.getElementById('temp-display').innerText = d.temp + '°C';
                
                const st = document.getElementById('conn-status');
                st.className = d.arduino_connected ? 'status-badge connected' : 'status-badge disconnected';
                st.innerText = d.arduino_connected ? 'ARDUINO: AKTİF' : 'ARDUINO: PASİF';
            }).catch(e=>{});

            // Bildirim Güncelleme
            fetch('/api/alerts').then(r=>r.json()).then(d => {
                const box = document.getElementById('security-alert');
                if(d.alert) {
                    box.style.display = 'block';
                    box.innerText = d.alert;
                    box.style.backgroundColor = d.alert.includes("İNSAN") ? "#e74c3c" : "#f39c12";
                    
                    // Web Bildirimi Gönder (YENİ ÖZELLİK)
                    sendWebNotification(d.alert);
                } else {
                    box.style.display = 'none';
                }
            }).catch(e=>{});
        }, 1000);

        function toggle(l) { fetch('/api/toggle/'+l, {method:'POST'}); }
        
        // Otomatik izin iste (Sayfa açılınca)
        if ("Notification" in window && Notification.permission !== "granted" && Notification.permission !== "denied") {
            Notification.requestPermission();
        }
    </script>
</body>
</html>
"""

# ==========================================
# 6. ROTALAR
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
    return render_template_string(HTML_DASHBOARD, user=session['user'])

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
        print("🚀 Flask Sunucusu Başlatılıyor (Port 5000)...")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nKapatılıyor...")
        if arduino: arduino.running = False
