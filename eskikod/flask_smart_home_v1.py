# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, Response
import time
import threading

# ==========================================
# GÜVENLİ MODÜL YÜKLEME (HATA ÖNLEYİCİ)
# ==========================================
# Bu bölüm, yan dosyalar eksik olsa bile sunucunun çökmemesini sağlar.
MODULE_ERROR = None

try:
    from kamera import VideoCamera
    from arduino_yoneticisi import ArduinoManager
except ImportError as e:
    MODULE_ERROR = f"KRİTİK HATA: Yan dosyalar bulunamadı!\nDetay: {e}\nLütfen 'kamera.py' ve 'arduino_yoneticisi.py' dosyalarının bu dosya ile AYNI klasörde olduğundan emin olun."
    print(MODULE_ERROR)

    # Sunucunun çökmemesi için sahte (dummy) sınıflar oluşturuyoruz
    class VideoCamera:
        def get_frame(self): return None
        def get_alert(self): return "Sistem Hatası: Kamera Modülü Eksik"

    class ArduinoManager:
        def __init__(self, **kwargs): self.running = False
        def baslat(self): pass
        def gonder(self, cmd): return False

except Exception as e:
    MODULE_ERROR = f"Beklenmedik Hata: {e}"
    print(MODULE_ERROR)
    # Hata durumunda yine boş sınıflar tanımlayalım
    class VideoCamera:
        def get_frame(self): return None
        def get_alert(self): return f"Sistem Hatası: {str(e)}"
    class ArduinoManager:
        def __init__(self, **kwargs): self.running = False
        def baslat(self): pass
        def gonder(self, cmd): return False

# ==========================================
# AYARLAR VE GLOBAL DEĞİŞKENLER
# ==========================================

USERS = {
    "emre": "1234",
    "arif": "0000",
    "sedat": "1111"
}

# Sistemin anlık durumu
sys_state = {
    "l1": False,      # Salon Işığı
    "l2": False,      # Mutfak Işığı
    "temp": 22,       # Sıcaklık
    "brightness": 50, # Parlaklık
    "arduino_connected": False # Bağlantı durumu
}

app = Flask(__name__)
app.secret_key = 'super_gizli_anahtar_123'
app.config['JSON_AS_ASCII'] = False  # Türkçe karakter desteği

# Global kamera nesnesi
try:
    global_camera = VideoCamera()
except Exception as e:
    print(f"Kamera başlatılamadı: {e}")
    global_camera = None

# ==========================================
# ARDUINO BAŞLATMA
# ==========================================

def arduino_veri_isleyici(line):
    """Arduino'dan gelen veriyi işler."""
    try:
        if ":" in line:
            key, value = line.split(":")
            if key == "L1": sys_state["l1"] = (value == "1")
            elif key == "L2": sys_state["l2"] = (value == "1")
            elif key == "TEMP": sys_state["temp"] = int(value)
            elif key == "BRT": sys_state["brightness"] = int(value)
    except:
        pass

# Arduino Yöneticisini Başlat
try:
    arduino = ArduinoManager(baudrate=9600, data_handler=arduino_veri_isleyici, state_dict=sys_state)
    arduino.baslat()
except Exception as e:
    print(f"Arduino başlatma hatası: {e}")

# ==========================================
# KAMERA AKIŞ FONKSİYONU
# ==========================================
def gen_frames():
    """Kamera modülünden görüntüleri alır ve yayınlar."""
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
                time.sleep(1)
        except Exception as e:
            print(f"Kamera akış hatası: {e}")
            time.sleep(0.5)

# ==========================================
# HTML ARAYÜZLERİ
# ==========================================

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Giriş Yap</title>
    <style>
        body { background: #1a1a2e; color: white; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 40px; border-radius: 15px; text-align: center; box-shadow: 0 0 20px rgba(0,0,0,0.5); width: 100%; max-width: 320px; }
        h2 { color: #e94560; margin-bottom: 30px; }
        select, input { width: 100%; padding: 15px; margin: 10px 0; border: none; border-radius: 8px; box-sizing: border-box; background: #0f3460; color: white; font-size: 1rem; }
        button { width: 100%; padding: 15px; background: #e94560; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1.1rem; font-weight: bold; margin-top: 20px; }
        button:hover { background: #c72c41; }
        .error { color: #e74c3c; font-size: 0.9rem; margin-top: 10px; }
        .sys-error { background: #c0392b; color: white; padding: 10px; border-radius: 5px; margin-bottom: 15px; font-size: 0.8rem; text-align: left; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔒 Ev Güvenlik Sistemi</h2>
        
        {% if module_error %}
        <div class="sys-error">
            <strong>⚠️ SİSTEM HATASI:</strong><br>
            {{ module_error }}
        </div>
        {% endif %}

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
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
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
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e94560; padding-bottom: 20px; margin-bottom: 20px; }
        .welcome { font-size: 1.2rem; font-weight: bold; display: flex; align-items: center; gap: 10px; }
        .btn-logout { background: transparent; border: 1px solid white; color: white; padding: 5px 15px; border-radius: 20px; cursor: pointer; text-decoration: none; font-size: 0.9rem; }
        .card { background: #16213e; padding: 20px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        .switch-container { display: flex; gap: 10px; }
        .btn-toggle { flex: 1; padding: 25px; border: none; border-radius: 12px; font-weight: bold; cursor: pointer; font-size: 1rem; transition: 0.3s; }
        .on { background: #2ecc71; color: #000; box-shadow: 0 0 15px #2ecc71; }
        .off { background: #333; color: #888; }
        .temp-ctrl { display: flex; justify-content: center; align-items: center; gap: 20px; }
        .circle-btn { width: 50px; height: 50px; border-radius: 50%; border: none; background: #333; color: white; font-size: 1.5rem; cursor: pointer; }
        .temp-val { font-size: 2.5rem; color: #e94560; font-weight: bold; }
        input[type=range] { width: 100%; margin-top: 15px; }
        .sync-btn { background: #333; color: #aaa; border: 1px dashed #666; padding: 10px; width: 100%; margin-top: 20px; cursor: pointer; border-radius: 10px;}
        
        .camera-container { width: 100%; border: 3px solid #e94560; border-radius: 10px; overflow: hidden; background: #000; position: relative; min-height: 200px; }
        .camera-img { width: 100%; display: block; }
        .camera-error-msg { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #e74c3c; font-weight: bold; display: none; }

        .alert-box {
            background-color: #e74c3c;
            color: white;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 10px;
            font-weight: bold;
            font-size: 1.2rem;
            display: none;
            animation: blink 1s infinite;
        }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        
        .status-badge { font-size: 0.8rem; padding: 5px 10px; border-radius: 12px; font-weight: normal; }
        .status-connected { background-color: #2ecc71; color: black; border: 1px solid #27ae60; }
        .status-disconnected { background-color: #e74c3c; color: white; border: 1px solid #c0392b; animation: pulse 2s infinite; }
        
        /* Hata Kutusu */
        .module-warning { background: #d35400; color: white; padding: 10px; margin-bottom: 10px; border-radius: 5px; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="header">
        <div class="welcome">
            👤 {{ user|upper }}
            <span id="conn-status" class="status-badge status-disconnected">Bağlantı Aranıyor...</span>
        </div>
        <a href="/logout" class="btn-logout">Çıkış</a>
    </div>

    {% if module_error %}
    <div class="module-warning">⚠️ <strong>UYARI:</strong> {{ module_error }}</div>
    {% endif %}

    <!-- BİLDİRİM ALANI -->
    <div id="security-alert" class="alert-box">
        ⚠️ Hareket Algılandı!
    </div>

    <!-- KAMERA KARTI -->
    <div class="card">
        <h3>📷 Güvenlik Kamerası</h3>
        <div class="camera-container">
            <img id="cam-stream" src="/video_feed" class="camera-img" alt="Kamera Bağlanıyor..." onerror="retryCamera()">
            <div id="cam-error" class="camera-error-msg">Kamera Bağlantı Hatası<br>Tekrar deneniyor...</div>
        </div>
    </div>

    <div class="card">
        <h3>💡 Aydınlatma</h3>
        <div class="switch-container">
            <button id="btn-l1" class="btn-toggle" onclick="toggle('l1')">SALON</button>
            <button id="btn-l2" class="btn-toggle" onclick="toggle('l2')">MUTFAK</button>
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
    
    <button class="sync-btn" onclick="syncArduino()">🔄 Arduino'yu Eşitle</button>

    <script>
        setInterval(fetchStatus, 1000);   
        setInterval(checkAlerts, 1000);   
        
        window.onload = function() { fetchStatus(); };

        function retryCamera() {
            const img = document.getElementById('cam-stream');
            const err = document.getElementById('cam-error');
            img.style.display = 'none';
            err.style.display = 'block';
            setTimeout(() => {
                img.src = "/video_feed?" + new Date().getTime();
                img.style.display = 'block';
                err.style.display = 'none';
            }, 3000);
        }

        function checkAlerts() {
            fetch('/api/alerts')
            .then(r => r.json())
            .then(data => {
                const alertBox = document.getElementById('security-alert');
                if (data.alert) {
                    alertBox.style.display = 'block';
                    alertBox.innerText = data.alert;
                    if (data.alert.includes("İNSAN")) {
                        alertBox.style.backgroundColor = "#e74c3c";
                    } else {
                        alertBox.style.backgroundColor = "#f39c12";
                    }
                } else {
                    alertBox.style.display = 'none';
                }
            })
            .catch(e => console.log("Bildirim hatası:", e));
        }

        function fetchStatus() {
            fetch('/api/status').then(r => r.json()).then(data => {
                const b1 = document.getElementById('btn-l1');
                b1.className = data.l1 ? 'btn-toggle on' : 'btn-toggle off';
                b1.innerText = data.l1 ? 'SALON AÇIK' : 'SALON KAPALI';
                
                const b2 = document.getElementById('btn-l2');
                b2.className = data.l2 ? 'btn-toggle on' : 'btn-toggle off';
                b2.innerText = data.l2 ? 'MUTFAK AÇIK' : 'MUTFAK KAPALI';
                
                document.getElementById('temp-display').innerText = data.temp + '°C';
                
                const sl = document.getElementById('brt-slider');
                if(document.activeElement !== sl) sl.value = data.brightness;
                
                const statLabel = document.getElementById('conn-status');
                if (data.arduino_connected) {
                    statLabel.innerText = "ARDUINO: AKTİF";
                    statLabel.className = "status-badge status-connected";
                } else {
                    statLabel.innerText = "ARDUINO: PASİF";
                    statLabel.className = "status-badge status-disconnected";
                }
            })
            .catch(e => console.log("Status hatası:", e));
        }

        function toggle(l) { fetch('/api/toggle/'+l, {method:'POST'}).then(fetchStatus); }
        function temp(a) { fetch('/api/temp/'+a, {method:'POST'}).then(fetchStatus); }
        function setBrightness(v) { fetch('/api/brt/'+v, {method:'POST'}); }
        function syncArduino() { fetch('/api/sync', {method:'POST'}); }
    </script>
</body>
</html>
"""

# ==========================================
# FLASK ROTALARI
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
    if 'user' not in session: return "Yetkisiz Erişim", 401
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/alerts')
def get_alerts():
    if global_camera:
        msg = global_camera.get_alert()
    else:
        msg = ""
    return jsonify({"alert": msg})

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
