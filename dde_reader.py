try:
    import xlwings as xw
except ImportError:
    xw = None
import pandas as pd
import os

def read_live_prices_from_excel(file_path: str) -> dict[str, float]:
    """
    Açık olan Excel dosyasından (DDE canlı verileri içeren) güncel fiyatları okur.
    Dönen değer: {'THYAO': 324.50, 'EREGL': 48.20, ...}
    """
    if xw is None:
        return {}
        
    if not os.path.exists(file_path):
        return {}
        
    try:
        # Açık olan Excel uygulamasını bul
        # xlwings, Excel açıksa dosyayı kilitlemeden doğrudan COM üzerinden hücreleri okur.
        # Bu sayede Matriks hücrelere veri yazmaya kesintisiz devam edebilir.
        app = xw.apps.active
        if not app:
            # Excel uygulaması açık değilse veri okunamaz
            return {}
            
        file_name = os.path.basename(file_path)
        
        # Açık kitaplar arasında bu isimde bir dosya var mı kontrol et
        book = None
        for b in app.books:
            if b.name.lower() == file_name.lower():
                book = b
                break
                
        if not book:
            # Dosya açık değilse xlwings ile mevcut Excel uygulamasında aç
            book = app.books.open(file_path)
            
        sheet = book.sheets[0] # İlk sayfayı seç
        
        # A ve B kolonlarındaki verileri tek seferde oku (A: Hisse, B: Son Fiyat)
        # Performans açısından tek tek okumak yerine bloğu topluca almak çok daha hızlıdır
        data = sheet.range("A1:B100").value
        
        prices = {}
        for row in data:
            if not row or len(row) < 2:
                continue
            hisse = row[0]
            fiyat = row[1]
            
            if hisse and fiyat is not None:
                hisse_str = str(hisse).strip().upper()
                # Başlık kolonlarını ele
                if hisse_str in ["HISSE", "HİSSE", "SYMBOL", "KOD", "TICKER"]:
                    continue
                try:
                    prices[hisse_str] = float(fiyat)
                except (ValueError, TypeError):
                    pass
                    
        return prices
    except Exception:
        # Excel kilitlenmesi veya hücre güncellenirken oluşabilecek anlık okuma hatalarını yakala
        return {}
