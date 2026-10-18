import serial
import serial.tools.list_ports
import threading
import time
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for

# ==========================================
# 1. BÖLÜM: AYARLAR VE GLOBAL DEĞİŞKENLER
# ==========================================

# Web arayüzüne giriş yapabilecek kullanıcılar
USERS = {
    "emre": "1234",
    "arif": "0000",
    "sedat": "1111"
}

# Sistemin anlık durumu (Arduino ile senkronize çalışır)
sys_state = {
    "l1": False,      # Salon Işığı
    "l2": False,      # Mutfak Işığı
    "temp": 22,       # Sıcaklık
    "brightness": 50, # Parlaklık
    "arduino_connected": False # YENİ: Bağlantı durumu
}

app = Flask(__name__)
app.secret_key = 'super_gizli_anahtar_123'

# ==========================================
# 2. BÖLÜM: GELİŞMİŞ ARDUINO YÖNETİCİSİ
# ==========================================
class ArduinoManager:
    def __init__(self, baudrate=9600, data_handler=None):
        self.ser = None
        self.running = False
        self.baudrate = baudrate
        self.data_handler = data_handler # Veri gelince çalışacak fonksiyon
        self.thread = None
        self.lock = threading.Lock() # Thread çakışmalarını önlemek için

    def baslat(self):
        """Arka plan dinleme servisini başlatır."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._listen_loop)
            self.thread.daemon = True
            self.thread.start()
            print("Sistem: Arduino servisi başlatıldı.")

    def gonder(self, komut):
        """Arduino'ya veri gönderir. Örn: 'L1:1' """
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    full_cmd = f"{komut}\n".encode('utf-8')
                    self.ser.write(full_cmd)
                    return True
                except Exception as e:
                    print(f"Gönderme Hatası: {e}")
                    return False
        return False

    def _find_port(self):
        """Otomatik port bulma."""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            # Yaygın Arduino çip isimleri
            if any(x in port.description for x in ["Arduino", "USB", "ACM", "CH340", "FTDI", "CP210x"]):
                return port.device
        return None

    def _connect(self):
        """Bağlantı kurma."""
        port = self._find_port()
        if port:
            try:
                self.ser = serial.Serial(port, self.baudrate, timeout=1)
                time.sleep(2) # Arduino reset süresi
                print(f"✅ Bağlandı: {port}")
                sys_state['arduino_connected'] = True # YENİ: Durumu güncelle
                return True
            except:
                return False
        return False

    def _close(self):
        """Bağlantıyı güvenli kapatma."""
        with self.lock:
            sys_state['arduino_connected'] = False # YENİ: Durumu güncelle
            if self.ser:
                try:
                    self.ser.close()
                except: pass
                self.ser = None

    def _listen_loop(self):
        """Ana döngü: Bağlantıyı yönetir ve veri okur."""
        while self.running:
            if self.ser and self.ser.is_open:
                try:
                    # Veri var mı kontrol et
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if line and self.data_handler:
                            self.data_handler(line)
                            
                except (OSError, serial.SerialException):
                    print("⚠️ Bağlantı Koptu! Tekrar aranıyor...")
                    self._close()
                except Exception as e:
                    print(f"Hata: {e}")
            else:
                # Bağlantı yoksa bağlanmayı dene
                if self._connect():
                    # Bağlanınca son durumu Arduino'ya tekrar gönder (Senkronizasyon)
                    self._resync_state()
                else:
                    time.sleep(1)
            
            time.sleep(0.05) # CPU dostu bekleme

    def _resync_state(self):
        """Bağlantı tekrar gelince sistem durumunu Arduino'ya iletir."""
        time.sleep(2) # Arduino kendine gelsin
        print("🔄 Sistem senkronize ediliyor...")
        # Mevcut durumu geri yükle
        self.gonder(f"L1:{'1' if sys_state['l1'] else '0'}")
        self.gonder(f"L2:{'1' if sys_state['l2'] else '0'}")
        self.gonder(f"BRT:{sys_state['brightness']}")

# ==========================================
# 3. BÖLÜM: VERİ İŞLEME VE HTML
# ==========================================

def arduino_veri_isleyici(line):
    """Arduino'dan gelen veriyi işler ve sys_state'i günceller."""
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
arduino = ArduinoManager(baudrate=9600, data_handler=arduino_veri_isleyici)

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
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔒 Ev Güvenlik Sistemi</h2>
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
        
        /* YENİ: Durum Göstergesi Stili */
        .status-badge {
            font-size: 0.8rem;
            padding: 5px 10px;
            border-radius: 12px;
            font-weight: normal;
        }
        .status-connected {
            background-color: #2ecc71;
            color: black;
            border: 1px solid #27ae60;
        }
        .status-disconnected {
            background-color: #e74c3c;
            color: white;
            border: 1px solid #c0392b;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.6; }
            100% { opacity: 1; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="welcome">
            👤 {{ user|upper }}
            <!-- YENİ: Durum Göstergesi -->
            <span id="conn-status" class="status-badge status-disconnected">Bağlantı Aranıyor...</span>
        </div>
        <a href="/logout" class="btn-logout">Çıkış</a>
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
        window.onload = fetchStatus;

        function fetchStatus() {
            fetch('/api/status').then(r => r.json()).then(data => {
                // Aydınlatma Güncelle
                const b1 = document.getElementById('btn-l1');
                b1.className = data.l1 ? 'btn-toggle on' : 'btn-toggle off';
                b1.innerText = data.l1 ? 'SALON AÇIK' : 'SALON KAPALI';
                
                const b2 = document.getElementById('btn-l2');
                b2.className = data.l2 ? 'btn-toggle on' : 'btn-toggle off';
                b2.innerText = data.l2 ? 'MUTFAK AÇIK' : 'MUTFAK KAPALI';
                
                // Sıcaklık Güncelle
                document.getElementById('temp-display').innerText = data.temp + '°C';
                
                // Parlaklık Güncelle
                const sl = document.getElementById('brt-slider');
                if(document.activeElement !== sl) sl.value = data.brightness;
                
                // YENİ: Bağlantı Durumu Göstergesi Güncelle
                const statLabel = document.getElementById('conn-status');
                if (data.arduino_connected) {
                    statLabel.innerText = "ARDUINO: AKTİF";
                    statLabel.className = "status-badge status-connected";
                } else {
                    statLabel.innerText = "ARDUINO: PASİF";
                    statLabel.className = "status-badge status-disconnected";
                }
            });
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
# 4. BÖLÜM: FLASK ROTALARI
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
            arduino.gonder(f"LOGIN:{u}")
            return redirect(url_for('dashboard'))
        else:
            error = "Hatalı Şifre!"
    return render_template_string(HTML_LOGIN, error=error)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template_string(HTML_DASHBOARD, user=session['user'])

@app.route('/logout')
def logout():
    session.pop('user', None)
    arduino.gonder("LOGOUT")
    return redirect(url_for('login'))

@app.route('/api/status')
def get_status(): 
    return jsonify(sys_state)

@app.route('/api/sync', methods=['POST'])
def api_sync():
    if 'user' in session:
        arduino.gonder(f"LOGIN:{session['user']}")
        # Ayrıca mevcut durumları da tekrar gönderelim
        arduino.gonder(f"L1:{'1' if sys_state['l1'] else '0'}")
        arduino.gonder(f"L2:{'1' if sys_state['l2'] else '0'}")
    return jsonify({"success":True})

@app.route('/api/toggle/<light>', methods=['POST'])
def api_toggle(light):
    if 'user' in session and light in sys_state:
        sys_state[light] = not sys_state[light]
        arduino.gonder(f"{light.upper()}:{'1' if sys_state[light] else '0'}")
        return jsonify({"success":True})
    return jsonify({"error":"Yetkisiz"}), 401

@app.route('/api/temp/<action>', methods=['POST'])
def api_temp(action):
    if 'user' in session:
        if action == 'up': sys_state["temp"] += 1
        elif action == 'down': sys_state["temp"] -= 1
        arduino.gonder(f"TEMP:{sys_state['temp']}")
        return jsonify({"success":True})
    return jsonify({"error":"Yetkisiz"}), 401

@app.route('/api/brt/<int:val>', methods=['POST'])
def api_brt(val):
    if 'user' in session:
        sys_state["brightness"] = val
        arduino.gonder(f"BRT:{val}")
        return jsonify({"success":True})
    return jsonify({"error":"Yetkisiz"}), 401

if __name__ == '__main__':
    try:
        # Arduino dinleme servisini başlat
        arduino.baslat()
        print("🚀 Flask Sunucusu Başlatılıyor...")
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\nKapatılıyor...")
        arduino.running = False
