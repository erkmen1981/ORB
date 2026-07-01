import os
import sys
import time
from datetime import datetime
import json

# Gerekli paketleri kontrol et ve yükleme uyarısı ver
try:
    import requests
except ImportError:
    print("Hata: 'requests' paketi yüklü değil. Yüklemek için: pip install requests")
    sys.exit(1)

try:
    import xlwings as xw
except ImportError:
    print("Hata: 'xlwings' paketi yüklü değil. Yüklemek için: pip install xlwings")
    sys.exit(1)

# DDE Reader fonksiyonunu içe aktar
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from dde_reader import read_live_prices_from_excel
except ImportError:
    # Alternatif doğrudan tanımlama
    def read_live_prices_from_excel(file_path: str) -> dict[str, float]:
        if not os.path.exists(file_path):
            return {}
        try:
            app = xw.apps.active
            if not app:
                return {}
            file_name = os.path.basename(file_path)
            book = None
            for b in app.books:
                if b.name.lower() == file_name.lower():
                    book = b
                    break
            if not book:
                book = app.books.open(file_path)
            sheet = book.sheets[0]
            data = sheet.range("A1:B100").value
            prices = {}
            for row in data:
                if not row or len(row) < 2:
                    continue
                hisse = row[0]
                fiyat = row[1]
                if hisse and fiyat is not None:
                    hisse_str = str(hisse).strip().upper()
                    if hisse_str in ["HISSE", "HİSSE", "SYMBOL", "KOD", "TICKER"]:
                        continue
                    try:
                        prices[hisse_str] = float(fiyat)
                    except (ValueError, TypeError):
                        pass
            return prices
        except Exception:
            return {}

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def load_config():
    """Çevre değişkenlerinden veya yerel .env dosyasından ayarları yükler."""
    config = {
        "FIREBASE_URL": os.environ.get("FIREBASE_URL"),
        "EXCEL_PATH": os.environ.get("EXCEL_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "matriks_dde.xlsx")),
        "REFRESH_INTERVAL": os.environ.get("REFRESH_INTERVAL", "15")
    }
    
    # .env dosyasını oku
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip().strip('"').strip("'")
                    
    return config

def write_config(firebase_url, excel_path, refresh_interval):
    """Yerel bir .env dosyası oluşturur veya günceller."""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("# Firebase Realtime Database Ayarları\n")
        f.write(f"FIREBASE_URL={firebase_url}\n")
        f.write(f"EXCEL_PATH={excel_path}\n")
        f.write(f"REFRESH_INTERVAL={refresh_interval}\n")
    print(f"\n[Ayarlar] Ayarlar başarıyla kaydedildi: {ENV_FILE}")

def setup_wizard():
    """İlk kurulum için kullanıcıyı yönlendirir."""
    config = load_config()
    
    firebase_url = config.get("FIREBASE_URL")
    excel_path = config.get("EXCEL_PATH")
    refresh_interval = config.get("REFRESH_INTERVAL")
    
    print("=" * 60)
    print("🚀 BIST ORB Breakout - Firebase Canlı Veri Yayıncı Kurulumu")
    print("=" * 60)
    
    if not firebase_url:
        print("\nLütfen Firebase Realtime Database URL'nizi girin.")
        print("Örnek: https://proje-adi-default-rtdb.firebaseio.com/")
        firebase_url = input("Firebase URL: ").strip()
        while not firebase_url.startswith("http"):
            print("Hata: Geçersiz URL! Lütfen 'http' veya 'https' ile başlayan tam URL girin.")
            firebase_url = input("Firebase URL: ").strip()
            
    # Sonundaki eğik çizgiyi temizle ve standartlaştır
    if firebase_url.endswith("/"):
        firebase_url = firebase_url[:-1]
        
    print(f"\nDDE Excel dosya yolu [Varsayılan: {excel_path}]:")
    custom_excel = input("Excel Yolu (Boş geçmek için ENTER): ").strip()
    if custom_excel:
        excel_path = os.path.abspath(custom_excel)
        
    print(f"\nYayınlama aralığı (saniye) [Varsayılan: {refresh_interval}]:")
    custom_refresh = input("Saniye (Boş geçmek için ENTER): ").strip()
    if custom_refresh:
        refresh_interval = custom_refresh
        
    write_config(firebase_url, excel_path, refresh_interval)
    return firebase_url, excel_path, float(refresh_interval)

def main():
    config = load_config()
    firebase_url = config.get("FIREBASE_URL")
    excel_path = config.get("EXCEL_PATH")
    refresh_interval = float(config.get("REFRESH_INTERVAL", 3.0))
    
    if not firebase_url:
        firebase_url, excel_path, refresh_interval = setup_wizard()
        
    print("\n" + "=" * 60)
    print("📡 Firebase Canlı Veri Yayıncısı Başlatılıyor...")
    print(f"- Firebase URL: {firebase_url}")
    print(f"- DDE Excel Dosyası: {excel_path}")
    print(f"- Güncelleme Sıklığı: {refresh_interval} saniye")
    print("Durdurmak için Ctrl+C tuşlarına basın.")
    print("=" * 60 + "\n")
    
    # URL sonundaki slash'ları temizle ve standartlaştır
    firebase_url = firebase_url.strip()
    while firebase_url.endswith("/"):
        firebase_url = firebase_url[:-1]
    api_endpoint = f"{firebase_url}/prices.json"
    
    consecutive_errors = 0
    
    while True:
        loop_start = time.time()
        
        # Excel'den oku
        prices = read_live_prices_from_excel(excel_path)
        
        if prices:
            try:
                # Firebase'e yükle (HTTP PUT ile tüm fiyat ağacını yenileriz)
                # timeout vererek asılı kalmayı engelleriz
                res = requests.put(api_endpoint, json=prices, timeout=3.0)
                
                if res.status_code == 200:
                    current_time = datetime.now().strftime("%H:%M:%S")
                    print(f"[{current_time}] 🟢 {len(prices)} hisse fiyatı Firebase'e başarıyla gönderildi.")
                    consecutive_errors = 0
                else:
                    print(f"⚠️ Firebase Hatası (HTTP {res.status_code}): {res.text}")
                    consecutive_errors += 1
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Ağ / Bağlantı Hatası: {e}")
                consecutive_errors += 1
        else:
            print("⚠️ Excel'den veri okunamadı! Lütfen Matriks'in açık olduğundan ve Excel dosyasının çalıştığından emin olun.")
            consecutive_errors += 1
            
        if consecutive_errors >= 10:
            print("\n🚨 Çok sayıda ardışık hata alındı. Bağlantılar kontrol ediliyor...")
            time.sleep(5)
            consecutive_errors = 0
            
        # Kalan süreyi bekle
        elapsed = time.time() - loop_start
        sleep_time = max(0.1, refresh_interval - elapsed)
        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n👋 Yayıncı sonlandırıldı. İyi çalışmalar!")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Yayıncı sonlandırıldı. İyi çalışmalar!")
        sys.exit(0)
