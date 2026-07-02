import streamlit as st
import pandas as pd
import os
from datetime import datetime
from zoneinfo import ZoneInfo
IST_TZ = ZoneInfo("Europe/Istanbul")
from concurrent.futures import ThreadPoolExecutor, as_completed
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from range import (
    run_backtest,
    backtest_summary,
    generate_trade_log,
    trade_statistics,
    performance_breakdown,
    simulate_viop_portfolio,
)
from database import (
    init_db,
    authenticate_user,
    register_user,
    get_all_users,
    update_user_status,
    delete_user,
    add_user_by_admin,
    update_user_role,
    create_user_session,
    get_user_by_session,
    delete_user_session
)
from dde_reader import read_live_prices_from_excel

# Streamlit-autorefresh importu (Otomatik eksik paket yükleme mekanizmalı)
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    import subprocess
    import sys
    try:
        # Sunucunun çalıştığı aktif Python/Sanal Ortam (venv) içine paketi kurar
        subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit-autorefresh"])
        from streamlit_autorefresh import st_autorefresh
    except Exception:
        st_autorefresh = None

# Veritabanını başlat
init_db()

# Sayfa Genişlik ve Tema Ayarları
st.set_page_config(
    page_title="BIST ORB Breakout Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# YETKİLİ GİRİŞ KONTROLÜ
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.role = None
        
    # Tarayıcı yenilendiğinde (F5) veya yeni sekmede oturumu otomatik kurtar
    if not st.session_state.authenticated and "session_token" in st.query_params:
        user = get_user_by_session(st.query_params["session_token"])
        if user:
            st.session_state.authenticated = True
            st.session_state.username = user["username"]
            st.session_state.role = user["role"]
            st.rerun()
        
    # Eski/bozuk oturum durumlarında rol veya kullanıcı adı eksikse oturumu temizle
    if st.session_state.authenticated:
        if "username" not in st.session_state or st.session_state.username is None or \
           "role" not in st.session_state or st.session_state.role is None:
            st.session_state.authenticated = False
            st.session_state.username = None
            st.session_state.role = None
            st.rerun()

    if "username" not in st.session_state:
        st.session_state.username = None
    if "role" not in st.session_state:
        st.session_state.role = None

    if not st.session_state.authenticated:
        # Sayfa stilini yükle
        st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');
            html, body, [class*="css"] {
                font-family: 'Outfit', sans-serif;
            }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1.8, 1])
        with col2:
            st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
            st.markdown("""
            <div style="padding: 30px 24px 20px 24px; border-radius: 16px 16px 0 0; background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(9, 13, 22, 0.99) 100%); border: 1px solid rgba(255,255,255,0.08); border-bottom: none; text-align: center; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);">
                <h2 style="background: linear-gradient(90deg, #c084fc 0%, #6366f1 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 2.1rem; margin:0;">🔐 Yetkili Girişi</h2>
                <p style="color: #64748b; font-size: 0.9rem; margin-top:8px; margin-bottom:0;">ORB Breakout Takip Paneline erişmek için giriş yapın veya kayıt olun.</p>
            </div>
            """, unsafe_allow_html=True)
            
            tab_login, tab_register = st.tabs(["Giriş Yap", "Kayıt Ol"])
            
            with tab_login:
                with st.form("login_form"):
                    username = st.text_input("Kullanıcı Adı", placeholder="Kullanıcı adınızı girin", key="login_username")
                    password = st.text_input("Şifre", type="password", placeholder="••••••••", key="login_password")
                    submit = st.form_submit_button("Giriş Yap", use_container_width=True)
                    
                    if submit:
                        user = authenticate_user(username, password)
                        if user:
                            status = user["status"]
                            if status == "APPROVED":
                                # Oturum tokenı oluştur ve query param olarak kaydet
                                token = create_user_session(user["username"], user["role"])
                                st.query_params["session_token"] = token
                                
                                st.session_state.authenticated = True
                                st.session_state.username = user["username"]
                                st.session_state.role = user["role"]
                                st.success("Giriş başarılı! Yönlendiriliyorsunuz...")
                                st.rerun()
                            elif status == "PENDING":
                                st.warning("Üyeliğiniz henüz onaylanmamış. Lütfen yöneticinizin onaylamasını bekleyin.")
                            elif status == "REJECTED":
                                st.error("Üyelik talebiniz reddedilmiştir.")
                        else:
                            st.error("Hatalı kullanıcı adı veya şifre!")
                            
            with tab_register:
                with st.form("register_form"):
                    reg_username = st.text_input("Kullanıcı Adı", placeholder="Yeni kullanıcı adı", key="reg_username")
                    reg_password = st.text_input("Şifre", type="password", placeholder="Şifreniz", key="reg_password")
                    reg_confirm = st.text_input("Şifre Tekrar", type="password", placeholder="Şifrenizi doğrulayın", key="reg_confirm")
                    reg_submit = st.form_submit_button("Kayıt Ol", use_container_width=True)
                    
                    if reg_submit:
                        if not reg_username or not reg_password:
                            st.error("Lütfen tüm alanları doldurun.")
                        elif reg_password != reg_confirm:
                            st.error("Şifreler uyuşmuyor.")
                        else:
                            success, message = register_user(reg_username, reg_password)
                            if success:
                                st.success(message)
                            else:
                                st.error(message)
            
            st.markdown("""
            <div style="text-align: center; margin-top: 15px; color: #475569; font-size: 0.8rem;">
                Protected by Streamlit Session Auth System.
            </div>
            """, unsafe_allow_html=True)
            st.stop()

check_login()

# Giriş yapan kullanıcının yönetici olup olmadığını belirle
is_admin = st.session_state.get("role") == "ADMIN"

# Premium Arayüz İçin CSS Enjeksiyonu
st.markdown("""
<style>
    /* Premium Font ve Arka Plan İyileştirmeleri */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Neon Glow Gradient Title */
    .dashboard-title {
        background: linear-gradient(90deg, #c084fc 0%, #6366f1 50%, #38bdf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.75rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 2px;
        text-shadow: 0 0 40px rgba(168, 85, 247, 0.15);
    }
    
    /* Alt Başlık */
    .custom-subtitle {
        color: #94a3b8;
        font-size: 1.15rem;
        font-weight: 400;
        margin-top: -5px;
        margin-bottom: 30px;
    }
    
    /* Özel Kartlar (KPI Cards) */
    .kpi-container {
        display: flex;
        gap: 16px;
        margin-bottom: 30px;
        flex-wrap: wrap;
    }
    
    .kpi-card {
        flex: 1;
        min-width: 220px;
        padding: 24px;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(9, 13, 22, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.05);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .kpi-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 4px;
    }
    
    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 15px 45px -10px rgba(168, 85, 247, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    
    .kpi-title {
        font-size: 0.75rem;
        color: #64748b;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 10px;
    }
    
    .kpi-value {
        font-size: 2rem;
        font-weight: 800;
        color: #f8fafc;
        margin: 0;
        letter-spacing: -0.02em;
        text-shadow: 0 0 24px rgba(255, 255, 255, 0.1);
    }
    
    /* Sol Sınır Glow Efektleri */
    .border-blue::before { background: linear-gradient(90deg, #38bdf8, #6366f1); }
    .border-green::before { background: linear-gradient(90deg, #34d399, #059669); }
    .border-red::before { background: linear-gradient(90deg, #f87171, #dc2626); }
    .border-amber::before { background: linear-gradient(90deg, #fbbf24, #d97706); }
    .border-purple::before { background: linear-gradient(90deg, #c084fc, #818cf8); }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="dashboard-title">⚡ BIST - ORB Breakout Dashboard</h1>', unsafe_allow_html=True)
st.markdown("<p class='custom-subtitle'>Kaldıraçlı VIOP ve Hisse İlk 15 Dk. Kanal Kırılım Stratejisi & Gelişmiş Portföy Analitiği</p>", unsafe_allow_html=True)

# Örnek BIST Tickers Listesi
BIST_TICKERS = [
    "THYAO.IS", "EREGL.IS", "ASELS.IS", "AKBNK.IS", "GARAN.IS", 
    "TUPRS.IS", "SAHOL.IS", "KCHOL.IS", "SISE.IS", "BIMAS.IS", "ULKER.IS", "BRSAN.IS", "TKFEN.IS", "HALKB.IS", "YKBNK.IS",
    "ISCTR.IS", "ASTOR.IS", "AEFES.IS", "SASA.IS", "HEKTS.IS", "KRDMD.IS", "TOASO.IS", "PETKM.IS", "ENJSA.IS", "EKGYO.IS",
    "FROTO.IS", "TAVHL.IS", "ARCLK.IS", "MGROS.IS", "ODAS.IS", "VESTL.IS", "ALARK.IS", "CIMSA.IS", "OYAKC.IS", 
    "DOAS.IS", "ENKAI.IS", "GUBRF.IS", "PGSUS.IS", "AKSEN.IS", "SOKM.IS", "TRALT.IS", "TRMET.IS", "TSKB.IS", "VAKBN.IS",
    "HEKTS.IS",
    
]

# SİDEBAR - AYARLAR
st.sidebar.markdown(f"<div style='text-align: center; color: #94a3b8; font-size: 0.95rem; margin-bottom: 10px;'>👤 Giriş Yapan: <b>{st.session_state.username}</b> ({st.session_state.role})</div>", unsafe_allow_html=True)

# Sayfa Navigasyonu (Sadece Adminler Görebilir)
selected_page = "📈 ORB Dashboard"
if is_admin:
    st.sidebar.markdown("---")
    selected_page = st.sidebar.radio(
        "📂 Sayfa Navigasyonu",
        ["📈 ORB Dashboard", "👥 Kullanıcı Yönetimi"],
        index=0
    )
    st.sidebar.markdown("---")

if st.sidebar.button("🔒 Oturumu Kapat", use_container_width=True):
    # Oturumu veritabanından sil ve URL parametresini temizle
    if "session_token" in st.query_params:
        delete_user_session(st.query_params["session_token"])
        del st.query_params["session_token"]
        
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.rerun()

# BİLDİRİM GEÇMİŞİ PANELİ (Sidebar'da gösterim)
if "signal_history" in st.session_state and st.session_state.signal_history:
    st.sidebar.markdown("---")
    with st.sidebar.expander(f"🔔 Son Bildirimler ({len(st.session_state.signal_history)})", expanded=True):
        # Ters kronolojik sırada göster (en yeni en üstte)
        for alert in reversed(st.session_state.signal_history):
            st.markdown(f"<div style='font-size:0.8rem; border-bottom:1px solid rgba(255,255,255,0.06); padding:5px 0; line-height:1.25; color:#e2e8f0;'>{alert}</div>", unsafe_allow_html=True)
        if st.sidebar.button("Geçmişi Temizle", key="clear_alerts_btn", use_container_width=True):
            st.session_state.signal_history = []
            st.rerun()

# VERİ BAĞLANTI AYARLARI
st.sidebar.header("📡 Veri Bağlantı Ayarları")

data_source_options = ["Yahoo Finance (15 dk Gecikmeli)", "Matriks Bulut (Canlı - Firebase)"]
if is_admin:
    data_source_options.append("Matriks DDE (Anlık Canlı Excel)")

data_source = st.sidebar.selectbox(
    "Veri Kaynağı",
    data_source_options,
    index=0
)

live_prices = {}
refresh_sec = 5

if data_source in ["Matriks DDE (Anlık Canlı Excel)", "Matriks Bulut (Canlı - Firebase)"]:
    refresh_sec = st.sidebar.slider("Yenileme Sıklığı (Saniye)", 2, 60, 5, key="live_refresh_slider")
    
    # Otomatik yenilemeyi başlat
    # Alternatif 1: st_autorefresh yüklü ise kullan (En kararlı yöntem)
    if st_autorefresh is not None:
        st_autorefresh(interval=refresh_sec * 1000, key=f"live_refresh_{refresh_sec}")
        
    # Alternatif 2: Gizli buton ve HTML/JS tıklama mekanizması (Sözde-görünmez img tagı, iframe/sandboxing engellerini aşar)
    else:
        # Ekran dışında (off-screen) buton stili enjekte et
        st.markdown(
            """
            <style>
            div.fn-refresh-btn {
                position: fixed !important;
                top: -100px !important;
                left: -100px !important;
                width: 1px !important;
                height: 1px !important;
                opacity: 0 !important;
                pointer-events: none !important;
                z-index: -9999 !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        st.markdown('<div class="fn-refresh-btn">', unsafe_allow_html=True)
        if st.button("RerunState", key="hidden_refresh_btn"):
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Streamlit HTML bileşeni ile JavaScript'i sansüre uğramadan güvenli bir şekilde enjekte ederiz
        import streamlit.components.v1 as components
        components.html(
            f"""
            <script>
            if (window.parent) {{
                if (window.parent.myAutorefreshInterval) {{
                    clearInterval(window.parent.myAutorefreshInterval);
                }}
                window.parent.myAutorefreshInterval = setInterval(function() {{
                    var btn = window.parent.document.querySelector('div.fn-refresh-btn button');
                    if (btn) {{
                        btn.click();
                    }}
                }}, {refresh_sec * 1000});
            }}
            </script>
            """,
            height=0,
            width=0
        )

# Firebase veya Excel Verisini Yükle
if data_source == "Matriks DDE (Anlık Canlı Excel)" and is_admin:
    dde_file_path = st.sidebar.text_input(
        "DDE Excel Dosya Yolu",
        value=os.path.join(os.path.dirname(os.path.abspath(__file__)), "matriks_dde.xlsx"),
        help="Açık olan Matriks DDE Excel dosyasının tam yolunu girin."
    )
    # Excel'den canlı fiyatları oku
    live_prices = read_live_prices_from_excel(dde_file_path)
    if not live_prices:
        st.sidebar.warning("⚠️ Excel dosyasından veri okunamadı! Lütfen Excel dosyasının açık olduğundan emin olun.")
    else:
        st.sidebar.success(f"🟢 {len(live_prices)} hissenin canlı verisi Excel'den okunuyor.")

elif data_source == "Matriks Bulut (Canlı - Firebase)":
    # Firebase URL'sini çevre değişkenlerinden veya secrets'tan al
    firebase_url = os.environ.get("FIREBASE_URL")
    if not firebase_url:
        try:
            firebase_url = st.secrets.get("FIREBASE_URL")
        except Exception:
            pass
            
    # Eğer bulamadıysak yerel .env dosyasından oku (lokal çalıştırma kolaylığı)
    if not firebase_url:
        env_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            if key.strip() == "FIREBASE_URL":
                                firebase_url = val.strip().strip('"').strip("'")
                                break
            except Exception:
                pass
            
    # Yönetici ise arayüzden URL'yi görebilsin/düzenleyebilsin
    if is_admin:
        firebase_url = st.sidebar.text_input(
            "Firebase DB URL",
            value=firebase_url or "",
            type="password",
            help="Firebase Realtime Database URL'niz (örn: https://proje.firebaseio.com/)"
        )
        
    if not firebase_url:
        if is_admin:
            st.sidebar.warning("⚠️ Lütfen Firebase DB URL alanını doldurun.")
        else:
            st.sidebar.warning("⚠️ Canlı veri kaynağı yapılandırılmamış (Firebase URL eksik).")
    else:
        # Firebase'den fiyatları çek
        try:
            import requests
            clean_url = firebase_url.strip()
            while clean_url.endswith("/"):
                clean_url = clean_url[:-1]
            res = requests.get(f"{clean_url}/prices.json", timeout=3.0)
            if res.status_code == 200:
                live_prices = res.json() or {}
                if live_prices:
                    st.sidebar.success(f"🟢 {len(live_prices)} hissenin canlı verisi buluttan çekildi.")
                else:
                    st.sidebar.info("ℹ️ Bulutta henüz veri yok. publisher.py'yi çalıştırın.")
            else:
                st.sidebar.error(f"🔴 Bulut Hatası: HTTP {res.status_code}")
        except Exception as e:
            st.sidebar.error(f"🔴 Bulut Bağlantı Hatası: {e}")

# Yasal Uyarı
if data_source in ["Matriks DDE (Anlık Canlı Excel)", "Matriks Bulut (Canlı - Firebase)"]:
    st.sidebar.markdown(
        """
        <div style="font-size: 0.8rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px; margin-top: 12px;">
            ⚠️ <b>BIST Canlı Veri Uyarısı:</b> Borsa İstanbul canlı verilerinin dağıtımı lisansa tabidir. Bu ekrandaki verilerin üçüncü şahıslara izinsiz aktarılması yasal sorumluluk doğurabilir.
        </div>
        """,
        unsafe_allow_html=True
    )

# Hata ayıklama ve teşhis paneli
with st.sidebar.expander("🛠️ Veritabanı Teşhis Paneli (Hata Ayıklama)"):
    st.write("Oturum Bilgileri:")
    st.write(f"- **Kullanıcı**: `{st.session_state.username}`")
    st.write(f"- **Rol**: `{st.session_state.role}`")
    st.write(f"- **Yönetici mi?**: `{is_admin}`")
    st.write(f"- **Veri Kaynağı**: `{data_source}`")
    if "firebase_url" in locals() and firebase_url:
        masked = firebase_url[:20] + "..." if len(firebase_url) > 20 else firebase_url
        st.write(f"- **Firebase URL**: `{masked}`")
    st.write(f"- **Bulunan Canlı Fiyat Sayısı**: `{len(live_prices)}`")
    if live_prices:
        sample_keys = list(live_prices.keys())[:3]
        sample_data = {k: live_prices[k] for k in sample_keys}
        st.write(f"- **Örnek Veri**: `{sample_data}`")

# KULLANICI YÖNETİMİ SAYFASI (Eğer admin seçtiyse ve navigasyon tıklandıysa)
if is_admin and selected_page == "👥 Kullanıcı Yönetimi":
    st.markdown('<h1 class="dashboard-title">👥 Kullanıcı Yönetim Paneli</h1>', unsafe_allow_html=True)
    st.markdown("<p class='custom-subtitle'>Sistem Kayıtları, Onaylama ve Yetkilendirme Kontrolleri</p>", unsafe_allow_html=True)
    
    # Kullanıcı Listesi
    users_list = get_all_users()
    if users_list:
        users_df = pd.DataFrame(users_list)
        users_df_display = users_df.copy()
        users_df_display.columns = ["Kullanıcı Adı", "Onay Durumu", "Rol/Yetki", "Kayıt Tarihi"]
        
        st.write("### 📋 Sistemdeki Tüm Kullanıcılar")
        st.dataframe(users_df_display, use_container_width=True)
        
        st.markdown("### ⚙️ Kullanıcı İşlemleri")
        
        # Kendisi hariç işlem yapılacak kullanıcılar
        other_usernames = [u["username"] for u in users_list if u["username"] != st.session_state.username]
        
        if other_usernames:
            selected_user_to_manage = st.selectbox("İşlem yapmak istediğiniz kullanıcıyı seçin:", other_usernames)
            
            # Seçilen kullanıcının bilgileri
            target_user = next(u for u in users_list if u["username"] == selected_user_to_manage)
            
            st.markdown(f"""
            <div style="padding: 16px; border-radius: 12px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 20px;">
                <b>Kullanıcı Adı:</b> {target_user['username']} &nbsp;&nbsp;|&nbsp;&nbsp; 
                <b>Mevcut Rol:</b> <code>{target_user['role']}</code> &nbsp;&nbsp;|&nbsp;&nbsp; 
                <b>Mevcut Durum:</b> <code>{target_user['status']}</code> &nbsp;&nbsp;|&nbsp;&nbsp; 
                <b>Kayıt Tarihi:</b> {target_user['created_at']}
            </div>
            """, unsafe_allow_html=True)
            
            col_act1, col_act2, col_act3, col_act4 = st.columns(4)
            
            # 1. Onayla
            if target_user["status"] in ["PENDING", "REJECTED"]:
                if col_act1.button("🟢 Üyeliği Onayla", use_container_width=True):
                    update_user_status(target_user["username"], "APPROVED")
                    st.success(f"'{target_user['username']}' kullanıcısı onaylandı!")
                    st.rerun()
            else:
                col_act1.write("*(Kullanıcı zaten onaylı)*")
                
            # 2. Reddet
            if target_user["status"] in ["PENDING", "APPROVED"]:
                if col_act2.button("🔴 Üyeliği Reddet", use_container_width=True):
                    update_user_status(target_user["username"], "REJECTED")
                    st.warning(f"'{target_user['username']}' kullanıcısının üyeliği reddedildi!")
                    st.rerun()
            else:
                col_act2.write("*(Kullanıcı zaten reddedilmiş)*")
            
            # 3. Rol Değiştir (ADMIN <-> USER)
            new_role_val = "ADMIN" if target_user["role"] == "USER" else "USER"
            role_btn_label = "🔑 Yönetici Yap (Admin)" if target_user["role"] == "USER" else "👤 Standart Üye Yap"
            if col_act3.button(role_btn_label, use_container_width=True):
                update_user_role(target_user["username"], new_role_val)
                st.success(f"'{target_user['username']}' rolü {new_role_val} olarak güncellendi!")
                st.rerun()
                
            # 4. Kullanıcıyı Sil
            if col_act4.button("🗑️ Kullanıcıyı Sil", use_container_width=True):
                success, msg = delete_user(target_user["username"])
                if success:
                    st.error(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("Kendi hesabınız dışında işlem yapabileceğiniz başka bir kayıtlı kullanıcı bulunmuyor.")
    else:
        st.info("Sistemde kayıtlı kullanıcı bulunamadı.")
        
    st.markdown("---")
    st.subheader("➕ Yeni Kullanıcı Ekle (Manuel)")
    
    with st.form("admin_add_user_form_page"):
        new_user = st.text_input("Kullanıcı Adı", placeholder="Örn: ahmet")
        new_pass = st.text_input("Şifre", type="password", placeholder="Örn: 123456")
        new_role = st.selectbox("Yetki Rolü", ["USER", "ADMIN"])
        new_status = st.selectbox("Giriş İzni", ["APPROVED", "PENDING"])
        
        add_btn = st.form_submit_button("Kullanıcıyı Sisteme Ekle", use_container_width=True)
        if add_btn:
            if not new_user or not new_pass:
                st.error("Kullanıcı adı ve şifre boş olamaz.")
            else:
                success, msg = add_user_by_admin(new_user, new_pass, new_role, new_status)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
                    
    st.stop()

st.sidebar.header("⚙️ Genel Ayarlar")
custom_list = st.sidebar.text_area(
    "İzleme Listesi (.IS uzantılı, virgülle ayrılmış)",
    value=", ".join(BIST_TICKERS),
    help="Örnek: THYAO.IS, GARAN.IS, TUPRS.IS",
    height=120
)

range_start = st.sidebar.time_input("ORB Başlangıç Saati", value=datetime.strptime("10:00", "%H:%M").time())
range_end = st.sidebar.time_input("ORB Bitiş Saati", value=datetime.strptime("10:15", "%H:%M").time())
interval_label = st.sidebar.selectbox("Veri Aralığı (Bar)", ["1 dk", "5 dk", "60 dk"], index=0)
show_only_signals = st.sidebar.checkbox("Sadece AL/SAT Sinyali Verenleri Göster", value=False)
allow_short = st.sidebar.checkbox("Açığa Satış Aktif (VIOP/Short)", value=True)
strict_end_bar = st.sidebar.checkbox("10:15 Barı Zorunlu (Matriks Uyumlu)", value=True)
execution_mode = st.sidebar.selectbox(
    "Sinyal Uygulama Modu",
    ["Aynı bar (Anlık Sinyal Eşleşmesi)", "Sonraki bar (Backtest Gerçekçi)"],
    index=1,
)

st.sidebar.markdown("---")
st.sidebar.header("💰 Risk & Komisyon Ayarları")
quantity = st.sidebar.number_input("Pozisyon Büyüklüğü (Lot/Adet)", min_value=1.0, value=100.0, step=1.0)
commission_bps = st.sidebar.number_input("Komisyon Oranı (bps - Onbinde)", min_value=0.0, value=5.0, step=0.5, help="Örn: Onbinde 5 komisyon = 5 bps")
slippage_bps = st.sidebar.number_input("Fiyat Kayması (bps - Onbinde)", min_value=0.0, value=2.0, step=0.5, help="Örn: Onbinde 2 kayma = 2 bps")

st.sidebar.markdown("---")
st.sidebar.header("📈 VIOP Portföy Ayarları")
viop_starting_balance = st.sidebar.number_input("VIOP Başlangıç Bakiyesi (TL)", min_value=1000.0, value=100000.0, step=5000.0)
viop_margin_pct = st.sidebar.slider("VIOP Teminat Oranı (%)", min_value=5, max_value=100, value=20, step=5, help="Örn: Hisse pozisyon değerinin %20'si kadar teminat bağlanır (5x kaldıraç).")
viop_commission_bps = st.sidebar.number_input("VIOP Komisyon Oranı (bps - Onbinde)", min_value=0.0, value=1.0, step=0.1, help="Örn: Onbinde 1 = 1.0 bps")
viop_slippage_bps = st.sidebar.number_input("VIOP Fiyat Kayması (bps - Onbinde)", min_value=0.0, value=5.0, step=0.5, help="Örn: Onbinde 5 = 5.0 bps")

if st.sidebar.button("🗑️ Önbelleği Temizle"):
    st.cache_data.clear()
    st.rerun()

# YARDIMCI FONKSİYONLAR
def parse_tickers(raw_value: str) -> list[str]:
    symbols = [s.strip().upper() for s in raw_value.split(",") if s.strip()]
    normalized = []
    for s in symbols:
        normalized.append(s if s.endswith(".IS") else f"{s}.IS")
    return list(dict.fromkeys(normalized))

def get_interval_and_period(label: str) -> tuple[str, str]:
    mapping = {
        "1 dk": ("1m", "7d"),
        "5 dk": ("5m", "60d"),
        "60 dk": ("60m", "730d"),
    }
    return mapping.get(label, ("1m", "7d"))

def get_orb_lookback(start_time: str, end_time: str, interval: str) -> int:
    start_dt = datetime.strptime(start_time, "%H:%M")
    end_dt = datetime.strptime(end_time, "%H:%M")
    total_minutes = max(int((end_dt - start_dt).total_seconds() // 60), 1)

    step_map = {"1m": 1, "5m": 5, "60m": 60}
    step = step_map.get(interval, 1)
    return max((total_minutes + step - 1) // step, 1)

# Paralel Veri Çekme ve Hesaplama Fonksiyonu
def extract_ticker_data(bulk_df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if bulk_df.empty:
        return pd.DataFrame()
    try:
        if isinstance(bulk_df.columns, pd.MultiIndex):
            if ticker in bulk_df.columns.levels[0]:
                df = bulk_df[ticker].copy()
            elif ticker in bulk_df.columns.levels[1]:
                df = bulk_df.xs(ticker, axis=1, level=1).copy()
            else:
                return pd.DataFrame()
        else:
            df = bulk_df.copy()
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        df = df.dropna(subset=["Close"]).copy()
        return df
    except Exception:
        return pd.DataFrame()


def safe_applymap(styler, func, subset=None):
    if hasattr(styler, "map"):
        return styler.map(func, subset=subset)
    else:
        return styler.applymap(func, subset=subset)

def strip_timezone_from_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df_copy = df.copy()
    if getattr(df_copy.index, "tz", None) is not None:
        df_copy.index = df_copy.index.tz_localize(None)
    for col in df_copy.columns:
        if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
            try:
                df_copy[col] = pd.to_datetime(df_copy[col]).dt.tz_localize(None)
            except Exception:
                pass
        elif df_copy[col].dtype == object:
            try:
                converted = pd.to_datetime(df_copy[col], errors='ignore')
                if pd.api.types.is_datetime64_any_dtype(converted):
                    df_copy[col] = converted.dt.tz_localize(None)
            except Exception:
                pass
    return df_copy

def update_df_with_live_prices(df: pd.DataFrame, live_prices: dict[str, float], allow_short_enabled: bool, end_time: str) -> pd.DataFrame:
    """Yfinance geçmiş verisine Matriks DDE canlı fiyatlarını giydirir ve sinyalleri anlık günceller."""
    if df.empty or not live_prices:
        return df
        
    updated_df = df.copy()
    for idx, row in updated_df.iterrows():
        ticker = row["Hisse"] # örn: "THYAO" veya "THYAO.IS"
        ticker_clean = ticker.replace(".IS", "")
        
        live_price = None
        if ticker in live_prices:
            live_price = live_prices[ticker]
        elif ticker_clean in live_prices:
            live_price = live_prices[ticker_clean]
            
        if live_price is not None:
            range_high = row[f"Range High ({end_time})"]
            range_low = row[f"Range Low ({end_time})"]
            last_signal = int(row.get("Son Sinyal", 0))
            
            # Fiyatı güncelle
            updated_df.at[idx, "Son Fiyat"] = live_price
            
            # Uzaklıkları güncelle
            updated_df.at[idx, "Kanal Üstüne Uzaklık (%)"] = round(((live_price - range_high) / range_high) * 100, 2)
            updated_df.at[idx, "Kanal Altına Uzaklık (%)"] = round(((live_price - range_low) / range_low) * 100, 2)
            
            # Sinyal Durumunu Devlet/Durum Mantığıyla (Stateful) Güncelle
            status = "⏳ Kanal İçi / Beklemede"
            if live_price > range_high:
                status = "🚀 AL (Kırılım Gerçekleşti - Pozisyonda)"
            elif live_price < range_low:
                if allow_short_enabled:
                    status = "📉 AÇIĞA SAT (Kırılım Gerçekleşti - Pozisyonda)"
                else:
                    status = "📤 POZ KAPAT / SAT"
            else:
                # Fiyat kanalın içindeyse, pozisyon durumunu koru
                if last_signal == 1:
                    status = "🚀 AL (Kanal İçi - Pozisyonda)"
                elif last_signal == -1:
                    status = "📉 AÇIĞA SAT (Kanalı İçi - Pozisyonda)"
                else:
                    # Günlük sinyal geçmişinde işlem var mı kontrol et
                    if last_signal == 0 and "Durum" in row and "POZ KAPAT" in str(row["Durum"]):
                        status = "📤 POZ KAPAT / NAKİT"
                    else:
                        status = "⏳ Kanal İçi / Beklemede"
                        
            updated_df.at[idx, "Durum"] = status
            
            # Güncelleme saatini saniyeli yazalım
            updated_df.at[idx, "Son Güncelleme"] = datetime.now(IST_TZ).strftime("%H:%M:%S")
            
    return updated_df

def update_open_trades_with_live_prices(trades_df: pd.DataFrame, live_prices: dict[str, float], qty: float, commission_bps: float, slippage_bps: float) -> pd.DataFrame:
    if trades_df.empty or not live_prices:
        return trades_df
        
    updated = trades_df.copy()
    commission_rate = commission_bps / 10000.0
    slippage_rate = slippage_bps / 10000.0
    cost_rate_side = commission_rate + slippage_rate
    
    for idx, row in updated.iterrows():
        if row["Durum"] == "ACIK":
            ticker = row["Hisse"]
            live_price = None
            if ticker in live_prices:
                live_price = live_prices[ticker]
            elif f"{ticker}.IS" in live_prices:
                live_price = live_prices[f"{ticker}.IS"]
                
            if live_price is not None:
                entry_price = float(row["Giris Fiyat"])
                # PnL hesaplama
                if row["Yon"] == "LONG":
                    gross_pct = ((live_price - entry_price) / entry_price) * 100
                    gross_tl = (live_price - entry_price) * qty
                else:
                    gross_pct = ((entry_price - live_price) / entry_price) * 100
                    gross_tl = (entry_price - live_price) * qty
                    
                cost_tl = (entry_price + live_price) * qty * cost_rate_side
                cost_pct = ((cost_tl / (entry_price * qty)) * 100) if entry_price > 0 and qty > 0 else 0.0
                net_pct = gross_pct - cost_pct
                net_tl = gross_tl - cost_tl
                
                updated.at[idx, "Cikis Fiyat"] = round(live_price, 4)
                updated.at[idx, "Brut PnL (%)"] = round(gross_pct, 2)
                updated.at[idx, "Maliyet (%)"] = round(cost_pct, 2)
                updated.at[idx, "Net PnL (%)"] = round(net_pct, 2)
                updated.at[idx, "Brut PnL (TL)"] = round(gross_tl, 2)
                updated.at[idx, "Maliyet (TL)"] = round(cost_tl, 2)
                updated.at[idx, "Net PnL (TL)"] = round(net_tl, 2)
                
    return updated

def recalculate_trades_to_viop(trades_df: pd.DataFrame, balance: float = 100000.0, margin_pct: float = 0.20, commission_bps: float = 1.0, slippage_bps: float = 5.0) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df
        
    recalculated = trades_df.copy()
    cost_rate = (commission_bps + slippage_bps) / 10000.0
    
    for idx, row in recalculated.iterrows():
        entry_price = float(row["Giris Fiyat"])
        exit_price = row["Cikis Fiyat"]
        if pd.isna(exit_price) or exit_price is None:
            exit_price = entry_price
        else:
            exit_price = float(exit_price)
            
        # 1 kontrat teminatı = Giriş Fiyatı * 100 * margin_pct
        margin_per_contract = entry_price * 100.0 * margin_pct
        if margin_per_contract > 0:
            contracts = int(balance // margin_per_contract)
        else:
            contracts = 0
            
        if contracts < 1:
            contracts = 1
            
        yon = row["Yon"]
        if yon == "LONG":
            gross_tl = (exit_price - entry_price) * 100.0 * contracts
            gross_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
        else: # SHORT
            gross_tl = (entry_price - exit_price) * 100.0 * contracts
            gross_pct = ((entry_price - exit_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
            
        cost_tl = (entry_price + exit_price) * 100.0 * contracts * cost_rate
        cost_pct = ((cost_tl / (entry_price * contracts * 100.0)) * 100.0) if entry_price > 0 and contracts > 0 else 0.0
        net_tl = gross_tl - cost_tl
        net_pct = gross_pct - cost_pct
        
        recalculated.at[idx, "Adet/Lot"] = contracts
        recalculated.at[idx, "Brut PnL (%)"] = round(gross_pct, 2)
        recalculated.at[idx, "Maliyet (%)"] = round(cost_pct, 2)
        recalculated.at[idx, "Net PnL (%)"] = round(net_pct, 2)
        recalculated.at[idx, "Brut PnL (TL)"] = round(gross_tl, 2)
        recalculated.at[idx, "Maliyet (TL)"] = round(cost_tl, 2)
        recalculated.at[idx, "Net PnL (TL)"] = round(net_tl, 2)
        
    return recalculated

@st.cache_data(ttl=60)
def fetch_and_analyze_parallel(
    tickers: list[str],
    start_time: str,
    end_time: str,
    interval: str,
    period: str,
    allow_short_enabled: bool,
    qty: float,
    commission: float,
    slippage: float,
    strict_end: bool,
    exec_delay: int,
):
    results = []
    all_trades_list = []
    orb_lookback = get_orb_lookback(start_time, end_time, interval)
    
    from range import normalize_period_for_interval
    safe_period = normalize_period_for_interval(interval, period)
    
    import yfinance as yf
    try:
        bulk_raw = yf.download(
            tickers=tickers,
            period=safe_period,
            interval=interval,
            group_by='ticker',
            progress=False
        )
    except Exception as e:
        st.error(f"Veri indirme hatası: {e}")
        bulk_raw = pd.DataFrame()

    if bulk_raw.empty:
        return pd.DataFrame(), pd.DataFrame()
        
    for ticker in tickers:
        try:
            raw_df = extract_ticker_data(bulk_raw, ticker)
            if raw_df.empty:
                continue
                
            bt = run_backtest(
                ticker=ticker,
                interval=interval,
                period=period,
                range_lookback=orb_lookback,
                allow_short=allow_short_enabled,
                strategy_mode="matriks",
                orb_start=start_time,
                orb_end=end_time,
                strict_end_bar=strict_end,
                execution_delay_bars=exec_delay,
                raw_df=raw_df,
            )
            if bt.empty:
                continue

            last_day = bt.index.max().date()
            df_today = bt[bt.index.date == last_day]
            if df_today.empty:
                continue

            kesin_high = float(df_today["Range_High"].iloc[-1])
            kesin_low = float(df_today["Range_Low"].iloc[-1])
            current_close = float(df_today["Close"].iloc[-1])
            current_time = df_today.index[-1].strftime('%H:%M')
            islem_saati = df_today.index[-1].time() >= datetime.strptime(end_time, "%H:%M").time()
            
            # Son satırdaki sinyal durumunu kontrol et
            last_signal = 0
            if "Signal" in df_today.columns and not df_today.empty:
                last_signal = int(df_today["Signal"].iloc[-1])
            
            status = "⏳ Kanal İçi / Beklemede"
            
            if islem_saati:
                if last_signal == 1:
                    status = "🚀 AL (Kırılım Gerçekleşti - Pozisyonda)"
                elif last_signal == -1:
                    status = "📉 AÇIĞA SAT (Kırılım Gerçekleşti - Pozisyonda)"
                elif last_signal == 0:
                    if (df_today["Signal"] != 0).any():
                        status = "📤 POZ KAPAT / NAKİT"
                    else:
                        status = "⏳ Kanal İçi / Beklemede"
            else:
                status = f"⏱️ {end_time} Öncesi - Kanal Oluşuyor"
                
            dist_to_high = ((current_close - kesin_high) / kesin_high) * 100
            dist_to_low = ((current_close - kesin_low) / kesin_low) * 100
            bt_info = backtest_summary(bt)
            trades = generate_trade_log(
                bt,
                quantity=qty,
                commission_bps=commission,
                slippage_bps=slippage,
            )
            t_stats = trade_statistics(trades)
            
            if not trades.empty:
                trades_copy = trades.copy()
                trades_copy["Hisse"] = ticker.replace(".IS", "")
                all_trades_list.append(trades_copy)
            
            results.append({
                "Hisse": ticker.replace(".IS", ""),
                "Son Fiyat": round(current_close, 2),
                f"Range High ({end_time})": round(kesin_high, 2),
                f"Range Low ({end_time})": round(kesin_low, 2),
                "Kanal Üstüne Uzaklık (%)": round(dist_to_high, 2),
                "Kanal Altına Uzaklık (%)": round(dist_to_low, 2),
                "Durum": status,
                "Son Güncelleme": current_time,
                "Son Sinyal": last_signal,
                "5G ORB Getiri (%)": round(bt_info["strategy_pct"], 2),
                "5G Al-Tut (%)": round(bt_info["market_pct"], 2),
                "İşlem Sayısı": int(bt_info["total_trades"]),
                "Kazanma Oranı (%)": round(bt_info["win_rate_pct"], 2),
                "Net PnL (TL)": round(t_stats["net_realized_pnl_tl"], 2),
                "Max DD (%)": round(bt_info["max_drawdown_pct"], 2),
                "Veri Gunu": str(last_day),
                "Son Güncelleme": current_time,
                
            })
        except Exception:
            continue
            
    if all_trades_list:
        all_trades_df = pd.concat(all_trades_list, ignore_index=True)
    else:
        all_trades_df = pd.DataFrame()
        
    return pd.DataFrame(results), all_trades_df


@st.cache_data(ttl=60)
def generate_viop_scanner_data(
    tickers: list[str],
    start_time: str,
    end_time: str,
    interval: str,
    period: str,
    allow_short_enabled: bool,
    starting_balance: float,
    margin_pct: float,
    commission_bps: float,
    slippage_bps: float,
    strict_end: bool,
    exec_delay: int,
):
    results = []
    orb_lookback = get_orb_lookback(start_time, end_time, interval)
    
    from range import normalize_period_for_interval
    safe_period = normalize_period_for_interval(interval, period)
    
    import yfinance as yf
    try:
        bulk_raw = yf.download(
            tickers=tickers,
            period=safe_period,
            interval=interval,
            group_by='ticker',
            progress=False
        )
    except Exception:
        bulk_raw = pd.DataFrame()

    if bulk_raw.empty:
        return pd.DataFrame()
        
    for ticker in tickers:
        try:
            raw_df = extract_ticker_data(bulk_raw, ticker)
            if raw_df.empty:
                continue
                
            bt = run_backtest(
                ticker=ticker,
                interval=interval,
                period=period,
                range_lookback=orb_lookback,
                allow_short=allow_short_enabled,
                strategy_mode="matriks",
                orb_start=start_time,
                orb_end=end_time,
                strict_end_bar=strict_end,
                execution_delay_bars=exec_delay,
                raw_df=raw_df,
            )
            if bt.empty:
                continue
                
            _, _, viop_summary = simulate_viop_portfolio(
                df=bt,
                starting_balance=starting_balance,
                margin_pct=margin_pct,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps
            )
            
            if not viop_summary:
                continue
                
            results.append({
                "Hisse": ticker.replace(".IS", ""),
                "Başlangıç Bakiyesi": round(viop_summary["starting_balance"], 2),
                "Son Bakiye": round(viop_summary["final_balance"], 2),
                "Net P&L (TL)": round(viop_summary["total_pnl_tl"], 2),
                "Net P&L (%)": round(viop_summary["total_pnl_pct"], 2),
                "İşlem Sayısı": int(viop_summary["total_trades"]),
                "Kazanma Oranı (%)": round(viop_summary["win_rate_pct"], 2),
                "Sharpe Oranı": round(viop_summary["sharpe_ratio"], 2),
                "Toplam Maliyet (TL)": round(viop_summary["total_costs_tl"], 2),
                "Max Drawdown (%)": round(viop_summary.get("max_drawdown_pct", 0.0), 2)
            })
        except Exception:
            continue
            
    return pd.DataFrame(results)

# İnteraktif Plotly Çizim Fonksiyonu
def create_interactive_plot(df: pd.DataFrame, ticker: str, start_time: str, end_time: str, trades: pd.DataFrame = None):
    # Plotly JSON serialization hatasını önlemek için zaman dilimi (timezone) bilgisini kaldır
    df_plot = df.copy()
    if df_plot.index.tz is not None:
        df_plot.index = df_plot.index.tz_localize(None)

    trades_plot = None
    if trades is not None and not trades.empty:
        trades_plot = trades.copy()
        for col in ["Giris Zamani", "Cikis Zamani"]:
            if col in trades_plot.columns:
                try:
                    trades_plot[col] = pd.to_datetime(trades_plot[col]).dt.tz_localize(None)
                except Exception:
                    pass

    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.1,
        subplot_titles=(f"📈 {ticker} Fiyat & ORB Kanal Seviyeleri", "📊 Kümülatif Getiri Karşılaştırması (%)"),
        row_heights=[0.6, 0.4]
    )

    # 1. Kapanış Fiyatı Çizgisi
    fig.add_trace(
        go.Scatter(
            x=df_plot.index, 
            y=df_plot["Close"], 
            name="Kapanış Fiyatı",
            line=dict(color="#3b82f6", width=2),
            hovertemplate="Tarih: %{x}<br>Fiyat: %{y:.2f} TL<extra></extra>"
        ),
        row=1, col=1
    )

    # 2. Kanal Üst Sınırı (Range High)
    fig.add_trace(
        go.Scatter(
            x=df_plot.index, 
            y=df_plot["Range_High"], 
            name="Kanal Üst Sınırı (High)",
            line=dict(color="#10b981", width=1.5, dash="dash"),
            hovertemplate="Kanal Üstü: %{y:.2f} TL<extra></extra>"
        ),
        row=1, col=1
    )
    
    # 3. Kanal Alt Sınırı (Range Low)
    fig.add_trace(
        go.Scatter(
            x=df_plot.index, 
            y=df_plot["Range_Low"], 
            name="Kanal Alt Sınırı (Low)",
            line=dict(color="#ef4444", width=1.5, dash="dash"),
            hovertemplate="Kanal Altı: %{y:.2f} TL<extra></extra>"
        ),
        row=1, col=1
    )

    # Sinyal Noktaları (Markers)
    if trades_plot is not None and not trades_plot.empty:
        # Long Girişler
        longs = trades_plot[trades_plot["Yon"] == "LONG"]
        if not longs.empty:
            fig.add_trace(
                go.Scatter(
                    x=longs["Giris Zamani"],
                    y=longs["Giris Fiyat"],
                    mode="markers",
                    marker=dict(symbol="triangle-up", size=14, color="#10b981", line=dict(color="#064e3b", width=1.5)),
                    name="AL Giriş",
                    hovertemplate="AL Giriş: %{y:.2f} TL<br>Zaman: %{x}<extra></extra>"
                ),
                row=1, col=1
            )
            
            # Long Çıkışlar (Kapanan Pozlar)
            long_exits = longs.dropna(subset=["Cikis Zamani"])
            if not long_exits.empty:
                fig.add_trace(
                    go.Scatter(
                        x=long_exits["Cikis Zamani"],
                        y=long_exits["Cikis Fiyat"],
                        mode="markers",
                        marker=dict(symbol="x", size=11, color="#10b981", line=dict(color="#064e3b", width=1.5)),
                        name="AL Pozisyon Kapat",
                        hovertemplate="AL Çıkış: %{y:.2f} TL<br>Zaman: %{x}<br>Net PnL: %{text}%<extra></extra>",
                        text=long_exits["Net PnL (%)"]
                    ),
                    row=1, col=1
                )
                
        # Short Girişler (Açığa Satış)
        shorts = trades_plot[trades_plot["Yon"] == "SHORT"]
        if not shorts.empty:
            fig.add_trace(
                go.Scatter(
                    x=shorts["Giris Zamani"],
                    y=shorts["Giris Fiyat"],
                    mode="markers",
                    marker=dict(symbol="triangle-down", size=14, color="#ef4444", line=dict(color="#7f1d1d", width=1.5)),
                    name="AÇIĞA SAT Giriş",
                    hovertemplate="Açığa Satış: %{y:.2f} TL<br>Zaman: %{x}<extra></extra>"
                ),
                row=1, col=1
            )
            
            short_exits = shorts.dropna(subset=["Cikis Zamani"])
            if not short_exits.empty:
                fig.add_trace(
                    go.Scatter(
                        x=short_exits["Cikis Zamani"],
                        y=short_exits["Cikis Fiyat"],
                        mode="markers",
                        marker=dict(symbol="x", size=11, color="#ef4444", line=dict(color="#7f1d1d", width=1.5)),
                        name="AÇIĞA SAT Kapat",
                        hovertemplate="Açığa Kapat: %{y:.2f} TL<br>Zaman: %{x}<br>Net PnL: %{text}%<extra></extra>",
                        text=short_exits["Net PnL (%)"]
                    ),
                    row=1, col=1
                )

    # 2. Grafik: Kümülatif Getiri
    fig.add_trace(
        go.Scatter(
            x=df_plot.index,
            y=df_plot["Cum_Market_Return"] * 100,
            name="Al-Tut (Market)",
            line=dict(color="#64748b", width=1.5),
            hovertemplate="Market Getirisi: %{y:.2f}%<extra></extra>"
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df_plot.index,
            y=df_plot["Cum_Strategy_Return"] * 100,
            name="ORB Stratejisi",
            line=dict(color="#8b5cf6", width=2.5),
            hovertemplate="ORB Strateji Getirisi: %{y:.2f}%<extra></extra>"
        ),
        row=2, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=680,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=10, r=10, t=60, b=10)
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=1, col=1)
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=1, col=1)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=2, col=1)
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#334155", row=2, col=1)
    
    fig.update_yaxes(title_text="Fiyat (TL)", row=1, col=1)
    fig.update_yaxes(title_text="Kümülatif Getiri (%)", row=2, col=1)
    
    return fig

# ANA AKIŞ BAŞLANGICI
tickers = parse_tickers(custom_list)
if not tickers:
    st.error("Lütfen en az bir geçerli hisse kodu giriniz.")
    st.stop()

selected_interval, selected_period = get_interval_and_period(interval_label)

# Veriyi arka planda paralel çek ve analiz et
data_df, all_trades_df = fetch_and_analyze_parallel(
    tickers=tickers,
    start_time=range_start.strftime("%H:%M"),
    end_time=range_end.strftime("%H:%M"),
    interval=selected_interval,
    period=selected_period,
    allow_short_enabled=allow_short,
    qty=quantity,
    commission=commission_bps,
    slippage=slippage_bps,
    strict_end=strict_end_bar,
    exec_delay=0 if execution_mode.startswith("Aynı") else 1,
)

# Matriks canlı fiyatlarını giydir (Excel DDE veya Firebase Bulut)
if data_source in ["Matriks DDE (Anlık Canlı Excel)", "Matriks Bulut (Canlı - Firebase)"] and live_prices:
    data_df = update_df_with_live_prices(
        data_df,
        live_prices,
        allow_short_enabled=allow_short,
        end_time=range_end.strftime("%H:%M")
    )
    if not all_trades_df.empty:
        all_trades_df = update_open_trades_with_live_prices(
            all_trades_df,
            live_prices,
            qty=quantity,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps
        )

# Yeni Sinyal Tetiklenme Algılama ve Bildirim Sistemi (st.toast)
if "prev_signal_states" not in st.session_state:
    st.session_state.prev_signal_states = {}

if "signal_history" not in st.session_state:
    st.session_state.signal_history = []

if not data_df.empty:
    for idx, row in data_df.iterrows():
        ticker = row["Hisse"]
        current_status = row["Durum"]
        
        # Sinyal tipini belirle (AL, SAT, BEKLE)
        short_state = "BEKLE"
        if "AL" in current_status:
            short_state = "AL"
        elif "SAT" in current_status or "AÇIĞA" in current_status:
            short_state = "SAT"
            
        # Önceki durumu al
        prev_state = st.session_state.prev_signal_states.get(ticker)
        
        # İlk yükleme değilse ve durum değiştiyse bildirim gönder
        if prev_state is not None and prev_state != short_state:
            time_str = datetime.now(IST_TZ).strftime("%H:%M:%S")
            if short_state == "AL":
                msg = f"🚀 **{ticker}** için YENİ **AL** Sinyali Tetiklendi! (Fiyat: {row['Son Fiyat']} TL)"
                st.toast(msg, icon="🔔")
                st.session_state.signal_history.append(f"⏰ {time_str} - 🚀 **{ticker}**: Yeni **AL** Sinyali ({row['Son Fiyat']} TL)")
            elif short_state == "SAT":
                msg = f"📉 **{ticker}** için YENİ **SAT / AÇIĞA SAT** Sinyali Tetiklendi! (Fiyat: {row['Son Fiyat']} TL)"
                st.toast(msg, icon="🔔")
                st.session_state.signal_history.append(f"⏰ {time_str} - 📉 **{ticker}**: Yeni **SAT/SHORT** Sinyali ({row['Son Fiyat']} TL)")
            elif short_state == "BEKLE" and prev_state in ["AL", "SAT"]:
                msg = f"📤 **{ticker}**: Pozisyon kapandı, kanal içine geri dönüldü veya nakite geçildi. (Fiyat: {row['Son Fiyat']} TL)"
                st.toast(msg, icon="ℹ️")
                st.session_state.signal_history.append(f"⏰ {time_str} - 📤 **{ticker}**: Pozisyon Kapatıldı ({row['Son Fiyat']} TL)")
                
        # Durumu güncelle
        st.session_state.prev_signal_states[ticker] = short_state

    # Tarihçeyi son 30 bildirim ile sınırla
    st.session_state.signal_history = st.session_state.signal_history[-30:]

# SEKMELERİ TANIMLA
tab_scanner, tab_analysis, tab_viop, tab_daily_trades, tab_guide = st.tabs([
    "📋 Sinyal Tarayıcı (Scanner)", 
    "📈 Tek Hisse Analiz & Grafik", 
    "📈 VIOP Portföy Backtest",
    "📊 Günlük İşlemler",
    "📖 Strateji Açıklaması & Rehber"
])

# TAB 1: SİNYAL TARAYICI
with tab_scanner:
    if not data_df.empty:
        # Filtreleme
        if show_only_signals:
            data_df = data_df[data_df["Durum"].str.contains("AL|SAT|AÇIĞA", regex=True)]
            
        if data_df.empty:
            st.info("Filtreleme kriterlerine uyan aktif bir sinyal bulunmamaktadır.")
        else:
            # Sinyal Sayaçları
            al_sayisi = len(data_df[data_df['Durum'].str.contains("AL")])
            sat_sayisi = len(data_df[data_df['Durum'].str.contains("SAT|AÇIĞA", regex=True)])
            bekle_sayisi = len(data_df[data_df['Durum'].str.contains("Beklemede|Öncesi", regex=True)])
            
            # Premium Metrik Kartları
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-card border-blue">
                    <div class="kpi-title">Taranan Hisse Sayısı</div>
                    <div class="kpi-value">{len(data_df)}</div>
                </div>
                <div class="kpi-card border-green">
                    <div class="kpi-title">🟢 Aktif AL Sinyali</div>
                    <div class="kpi-value">{al_sayisi}</div>
                </div>
                <div class="kpi-card border-red">
                    <div class="kpi-title">🔴 Aktif SAT/AÇIĞA SAT</div>
                    <div class="kpi-value">{sat_sayisi}</div>
                </div>
                <div class="kpi-card border-amber">
                    <div class="kpi-title">⏳ Bekleme / Oluşumda</div>
                    <div class="kpi-value">{bekle_sayisi}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Tablo Filtreleme Seçici (KPI kartlarının altında şık bir düğme grubu)
            filter_choice = st.radio(
                "📂 Hisse Filtresi:",
                [
                    f"Tümü ({len(data_df)})",
                    f"🟢 Aktif AL Sinyalleri ({al_sayisi})",
                    f"🔴 Aktif SAT / AÇIĞA SAT ({sat_sayisi})",
                    f"⏳ Bekleme / Oluşumda ({bekle_sayisi})"
                ],
                horizontal=True,
                index=0
            )

            st.subheader("Hisse Sinyal Matrisi")
            
            # DataFrame Görsel İyileştirmesi ve Pandas Styling
            display_df = data_df.sort_values(
                by=["Durum", "Kanal Üstüne Uzaklık (%)"], 
                ascending=[True, False]
            )
            # Son Sinyal kolonunu kullanıcıdan gizle
            display_df = display_df.drop(columns=["Son Sinyal"], errors="ignore")
            
            # Seçilen filtreyi dataframe'e uygula
            if "Aktif AL Sinyalleri" in filter_choice:
                display_df = display_df[display_df["Durum"].str.contains("AL")]
            elif "Aktif SAT / AÇIĞA SAT" in filter_choice:
                display_df = display_df[display_df["Durum"].str.contains("SAT|AÇIĞA", regex=True)]
            elif "Bekleme / Oluşumda" in filter_choice:
                display_df = display_df[display_df["Durum"].str.contains("Beklemede|Öncesi", regex=True)]
            
            def style_status_column(val):
                if "AL" in str(val):
                    return 'background-color: rgba(16, 185, 129, 0.18); color: #00ffb7; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(0,255,183,0.35);'
                elif "SAT" in str(val) or "AÇIĞA" in str(val):
                    return 'background-color: rgba(239, 68, 68, 0.18); color: #ff5252; font-weight: bold; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(255,82,82,0.35);'
                elif "Beklemede" in str(val):
                    return 'background-color: rgba(245, 158, 11, 0.12); color: #ffd166; font-weight: 500; border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 6px;'
                return 'color: #94a3b8;'

            styled_table = safe_applymap(display_df.style, style_status_column, subset=["Durum"])
            st.dataframe(styled_table, use_container_width=True, height=480)
            
            # Yenileme butonu
            col_ref_1, col_ref_2 = st.columns([10, 2])
            with col_ref_2:
                if st.button("🔄 Paneli Yenile", use_container_width=True):
                    st.rerun()
    else:
        st.warning("Henüz taranan verilere erişilemiyor. Lütfen piyasanın açık olduğundan veya Yahoo Finance'in veri döndürdüğünden emin olun.")

# TAB 2: DETAYLI HİSSE ANALİZİ
with tab_analysis:
    if not data_df.empty:
        st.subheader("Tek Hisse Derinlemesine Backtest & Detayları")
        
        selected_symbol = st.selectbox("Analiz edilecek hisseyi seçin", data_df["Hisse"].tolist())
        selected_ticker = f"{selected_symbol.split(' ')[0]}.IS"
        
        # Seçili hissenin backtestini tekrar hızlıca al
        selected_bt = run_backtest(
            ticker=selected_ticker,
            interval=selected_interval,
            period=selected_period,
            range_lookback=get_orb_lookback(range_start.strftime("%H:%M"), range_end.strftime("%H:%M"), selected_interval),
            allow_short=allow_short,
            strategy_mode="matriks",
            orb_start=range_start.strftime("%H:%M"),
            orb_end=range_end.strftime("%H:%M"),
            strict_end_bar=strict_end_bar,
            execution_delay_bars=0 if execution_mode.startswith("Aynı") else 1,
        )
        
        if not selected_bt.empty:
            # Matriks canlı fiyatını son satıra giydir (Excel DDE veya Firebase Bulut)
            ticker_short = selected_symbol
            if data_source in ["Matriks DDE (Anlık Canlı Excel)", "Matriks Bulut (Canlı - Firebase)"] and live_prices:
                live_price = None
                if ticker_short in live_prices:
                    live_price = live_prices[ticker_short]
                elif f"{ticker_short}.IS" in live_prices:
                    live_price = live_prices[f"{ticker_short}.IS"]
                
                if live_price is not None:
                    selected_bt.loc[selected_bt.index[-1], "Close"] = live_price
        
        if not selected_bt.empty:
            # Gerekli günlük ve istatistikleri çek
            trade_df = generate_trade_log(
                selected_bt,
                quantity=quantity,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
            )
            stats = trade_statistics(trade_df)
            daily_df, weekly_df, max_dd = performance_breakdown(selected_bt)
            
            # Zaman diliminden kaynaklı PyArrow serileştirme hatalarını önlemek için kopyaları naive yap
            trade_df_display = strip_timezone_from_df(trade_df)
            daily_df_display = strip_timezone_from_df(daily_df)
            weekly_df_display = strip_timezone_from_df(weekly_df)
            
            # Gelişmiş Risk Metriklerini Kartlarla Yazdır
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-card border-blue">
                    <div class="kpi-title">Toplam İşlem sayısı</div>
                    <div class="kpi-value">{int(stats["total_trades"])} <span style="font-size: 0.85rem; color:#94a3b8;">({int(stats["closed_trades"])} Kapanan)</span></div>
                </div>
                <div class="kpi-card border-green">
                    <div class="kpi-title">🏆 Kazanma Oranı</div>
                    <div class="kpi-value">%{stats["win_rate_pct"]:.2f}</div>
                </div>
                <div class="kpi-card border-purple">
                    <div class="kpi-title">📈 Toplam Net Kar (TL)</div>
                    <div class="kpi-value">{stats["net_realized_pnl_tl"]:,.2f} TL <span style="font-size: 0.85rem; color:#94a3b8;">(%{stats["net_realized_pnl_pct"]:.2f})</span></div>
                </div>
                <div class="kpi-card border-amber">
                    <div class="kpi-title">📊 Profit Factor</div>
                    <div class="kpi-value">{stats.get("profit_factor", 0.0)}</div>
                </div>
                <div class="kpi-card border-red">
                    <div class="kpi-title">📉 Max Drawdown</div>
                    <div class="kpi-value">%{max_dd:.2f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # İnteraktif Plotly Grafiği Ekle
            plotly_fig = create_interactive_plot(
                selected_bt, 
                selected_symbol, 
                range_start.strftime("%H:%M"), 
                range_end.strftime("%H:%M"), 
                trade_df
            )
            st.plotly_chart(plotly_fig, use_container_width=True)
            
            # İşlem Listesi ve İstatistik Detay Tabloları
            col_l, col_r = st.columns([7, 3])
            
            with col_l:
                st.subheader("📋 İşlem Günlüğü (Trade Log)")
                if not trade_df.empty:
                    # İşlem bazında PnL renklendirmesi
                    def style_pnl_rows(val):
                        try:
                            val_float = float(val)
                            if val_float > 0:
                                return 'color: #10b981; font-weight: 500;'
                            elif val_float < 0:
                                return 'color: #ef4444; font-weight: 500;'
                        except ValueError:
                            pass
                        return ''

                    styled_trades = safe_applymap(trade_df_display.style, style_pnl_rows, subset=["Brut PnL (%)", "Net PnL (%)", "Brut PnL (TL)", "Net PnL (TL)"])
                    st.dataframe(styled_trades, use_container_width=True, height=350)
                    
                    # CSV İndirme Butonu
                    csv_data = trade_df_display.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 İşlem Günlüğünü Excel/CSV Olarak İndir",
                        data=csv_data,
                        file_name=f"{selected_symbol}_orb_islemleri.csv",
                        mime="text/csv",
                        use_container_width=False
                    )
                else:
                    st.info("Bu tarih aralığında henüz oluşmuş işlem bulunmamaktadır.")
            
            with col_r:
                st.subheader("⚡ Detaylı İstatistikler")
                stat_data = {
                    "Risk Metrikleri": [
                        "Ort. Net İşlem Getirisi (%)",
                        "En İyi İşlem Getirisi (%)",
                        "En Kötü İşlem Getirisi (%)",
                        "Toplam Katlanılan Maliyet (TL)",
                        "Aktif Açık Pozisyonlar"
                    ],
                    "Değer": [
                        f"%{stats['avg_net_pnl_pct']:.2f}",
                        f"%{stats.get('max_win_pct', 0.0):.2f}",
                        f"%{stats.get('max_loss_pct', 0.0):.2f}",
                        f"{stats.get('total_costs_tl', 0.0):,.2f} TL",
                        str(stats["open_positions"])
                    ]
                }
                st.table(pd.DataFrame(stat_data))
                
            # Performans Periyodik Kırılımları
            st.markdown("---")
            col_day, col_week = st.columns(2)
            with col_day:
                st.subheader("📅 Günlük Performans Özeti (Son 15 Gün)")
                st.dataframe(daily_df_display.tail(15).rename(columns={"Gunluk Getiri (%)": "Günlük Getiri (%)"}), use_container_width=True, height=250)
            with col_week:
                st.subheader("📆 Haftalık Performans Özeti (Son 10 Hafta)")
                st.dataframe(weekly_df_display.tail(10).rename(columns={"Haftalik Getiri (%)": "Haftalık Getiri (%)"}), use_container_width=True, height=250)
        else:
            st.warning("Seçilen hisse için backtest verisi çekilemedi.")
    else:
        st.warning("Hisse verileri yüklenemedi.")
def create_viop_balance_plot(portfolio_df: pd.DataFrame, ticker: str, start_balance: float):
    # Plotly JSON serialization hatasını önlemek için zaman dilimi (timezone) bilgisini kaldır
    df_plot = portfolio_df.copy()
    if df_plot.index.tz is not None:
        df_plot.index = df_plot.index.tz_localize(None)

    fig = go.Figure()
    
    # Portföy Bakiye Eğrisi
    fig.add_trace(
        go.Scatter(
            x=df_plot.index,
            y=df_plot["Bakiye"],
            name="Portföy Bakiyesi",
            line=dict(color="#10b981", width=2.5),
            fill='tozeroy',
            fillcolor='rgba(16, 185, 129, 0.05)',
            hovertemplate="Tarih: %{x}<br>Bakiye: %{y:,.2f} TL<extra></extra>"
        )
    )
    
    # Başlangıç bakiyesi referans çizgisi
    fig.add_shape(
        type="line",
        x0=df_plot.index[0],
        y0=start_balance,
        x1=df_plot.index[-1],
        y1=start_balance,
        line=dict(color="#64748b", width=1.5, dash="dash"),
    )
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=450,
        title=dict(text=f"📈 {ticker} Kaldıraçlı VIOP Portföy Bakiye Eğrisi", font=dict(size=16)),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=50, b=10)
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#334155")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#334155")
    fig.update_yaxes(title_text="Bakiye (TL)")
    
    return fig

# TAB 3: VIOP PORTFÖY BACKTEST
with tab_viop:
    if not data_df.empty:
        st.subheader("📊 Tüm Hisselerin VIOP Performans Matrisi")
        
        # Tüm hisselerin kaldıraçlı portföy özetlerini hesapla
        viop_scanner_df = generate_viop_scanner_data(
            tickers=tickers,
            start_time=range_start.strftime("%H:%M"),
            end_time=range_end.strftime("%H:%M"),
            interval=selected_interval,
            period=selected_period,
            allow_short_enabled=allow_short,
            starting_balance=viop_starting_balance,
            margin_pct=viop_margin_pct / 100.0,
            commission_bps=viop_commission_bps,
            slippage_bps=viop_slippage_bps,
            strict_end=strict_end_bar,
            exec_delay=0 if execution_mode.startswith("Aynı") else 1,
        )
        
        if not viop_scanner_df.empty:
            # PnL kolonlarını renklendir
            def style_viop_scanner_pnl(val):
                try:
                    val_float = float(val)
                    if val_float > 0:
                        return 'background-color: rgba(16, 185, 129, 0.18); color: #00ffb7; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(0,255,183,0.35);'
                    elif val_float < 0:
                        return 'background-color: rgba(239, 68, 68, 0.18); color: #ff5252; font-weight: bold; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; text-shadow: 0 0 10px rgba(255,82,82,0.35);'
                except ValueError:
                    pass
                return ''
                
            styled_viop_scanner = safe_applymap(
                viop_scanner_df.style, 
                style_viop_scanner_pnl, 
                subset=["Net P&L (TL)", "Net P&L (%)"]
            )
            st.dataframe(styled_viop_scanner, use_container_width=True, height=320)
        else:
            st.info("VIOP tarayıcı verileri yüklenemedi.")
            
        st.markdown("---")
        st.subheader("🔍 Tek Hisse VIOP Detay Analizi")
        selected_viop_symbol = st.selectbox("VIOP Analizi için Hisse Seçin", data_df["Hisse"].tolist(), key="viop_symbol_select")
        selected_viop_ticker = f"{selected_viop_symbol.split(' ')[0]}.IS"
        
        # Seçili hissenin backtest verilerini çek
        viop_bt = run_backtest(
            ticker=selected_viop_ticker,
            interval=selected_interval,
            period=selected_period,
            range_lookback=get_orb_lookback(range_start.strftime("%H:%M"), range_end.strftime("%H:%M"), selected_interval),
            allow_short=allow_short,
            strategy_mode="matriks",
            orb_start=range_start.strftime("%H:%M"),
            orb_end=range_end.strftime("%H:%M"),
            strict_end_bar=strict_end_bar,
            execution_delay_bars=0 if execution_mode.startswith("Aynı") else 1,
        )
        
        if not viop_bt.empty:
            # Matriks canlı fiyatını son satıra giydir (Excel DDE veya Firebase Bulut)
            ticker_short = selected_viop_symbol.split(' ')[0]
            if data_source in ["Matriks DDE (Anlık Canlı Excel)", "Matriks Bulut (Canlı - Firebase)"] and live_prices:
                live_price = None
                if ticker_short in live_prices:
                    live_price = live_prices[ticker_short]
                elif f"{ticker_short}.IS" in live_prices:
                    live_price = live_prices[f"{ticker_short}.IS"]
                
                if live_price is not None:
                    viop_bt.loc[viop_bt.index[-1], "Close"] = live_price
        
        if not viop_bt.empty:
            # VIOP Portföy simülasyonunu çalıştır
            viop_portfolio, viop_trades, viop_summary = simulate_viop_portfolio(
                df=viop_bt,
                starting_balance=viop_starting_balance,
                margin_pct=viop_margin_pct / 100.0,
                commission_bps=viop_commission_bps,
                slippage_bps=viop_slippage_bps
            )
            
            # Zaman diliminden kaynaklı PyArrow serileştirme hatalarını önlemek için kopyaları naive yap
            viop_trades_display = strip_timezone_from_df(viop_trades)
            
            if not viop_portfolio.empty:
                # Portföy Özet Metrikleri
                pnl_color = "#10b981" if viop_summary["total_pnl_tl"] >= 0 else "#ef4444"
                
                st.markdown(f"""
                <div class="kpi-container">
                    <div class="kpi-card border-blue">
                        <div class="kpi-title">Başlangıç Bakiyesi</div>
                        <div class="kpi-value">{viop_summary["starting_balance"]:,.2f} TL</div>
                    </div>
                    <div class="kpi-card border-purple">
                        <div class="kpi-title">Son Bakiye</div>
                        <div class="kpi-value">{viop_summary["final_balance"]:,.2f} TL</div>
                    </div>
                    <div class="kpi-card" style="border-left: 5px solid {pnl_color};">
                        <div class="kpi-title">Toplam Net P&L</div>
                        <div class="kpi-value" style="color: {pnl_color};">{viop_summary["total_pnl_tl"]:,.2f} TL <span style="font-size: 0.85rem; color:#94a3b8;">(%{viop_summary["total_pnl_pct"]:.2f})</span></div>
                    </div>
                    <div class="kpi-card border-green">
                        <div class="kpi-title">🏆 Kazanma Oranı</div>
                        <div class="kpi-value">%{viop_summary["win_rate_pct"]:.2f}</div>
                    </div>
                    <div class="kpi-card border-amber">
                        <div class="kpi-title">📊 Sharpe Oranı</div>
                        <div class="kpi-value">{viop_summary["sharpe_ratio"]:.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Bakiye Eğrisi Grafiği
                balance_fig = create_viop_balance_plot(viop_portfolio, selected_viop_symbol, viop_starting_balance)
                st.plotly_chart(balance_fig, use_container_width=True)
                
                # Detaylı Tablolar
                col_viop_l, col_viop_r = st.columns([7, 3])
                
                with col_viop_l:
                    st.subheader("📋 VIOP İşlem Günlüğü")
                    if not viop_trades.empty:
                        def style_viop_pnl(val):
                            try:
                                val_float = float(val)
                                if val_float > 0:
                                    return 'color: #10b981; font-weight: 500;'
                                elif val_float < 0:
                                    return 'color: #ef4444; font-weight: 500;'
                            except ValueError:
                                pass
                            return ''
                            
                        styled_viop_trades = safe_applymap(viop_trades_display.style, style_viop_pnl, subset=["Brut PnL (TL)", "Net PnL (TL)", "Net PnL (%)"])
                        st.dataframe(styled_viop_trades, use_container_width=True, height=350)
                        
                        # CSV İndirme Butonu
                        viop_csv = viop_trades_display.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 VIOP İşlemlerini Excel/CSV Olarak İndir",
                            data=viop_csv,
                            file_name=f"{selected_viop_symbol}_viop_islemleri.csv",
                            mime="text/csv",
                            key="download_viop_csv"
                        )
                    else:
                        st.info("Bu hisse için oluşmuş VIOP işlemi bulunmamaktadır.")
                        
                with col_viop_r:
                    st.subheader("⚡ Portföy Risk Analizi")
                    viop_stats = {
                        "VIOP Metriği": [
                            "Toplam İşlem Sayısı",
                            "Toplam Ödenen Komisyon + Kayma (TL)",
                            "Aktif Açık Pozisyonlar",
                            "Kontrat Başı Lot Sayısı",
                            "Simüle Edilen Kaldıraç Oranı"
                        ],
                        "Değer": [
                            str(viop_summary["total_trades"]),
                            f"{viop_summary['total_costs_tl']:,.2f} TL",
                            "Evet (1)" if viop_summary["open_positions"] > 0 else "Hayır (0)",
                            "100 Lot",
                            f"{round(100.0 / viop_margin_pct, 1)}x Kaldıraç"
                        ]
                    }
                    st.table(pd.DataFrame(viop_stats))
            else:
                st.warning("Portföy simülasyonu çalıştırılamadı.")
        else:
            st.warning("Seçilen hissenin fiyat verileri çekilemedi.")
    else:
        st.warning("Hisse verileri yüklenemedi.")

# TAB 4: GÜNLÜK İŞLEMLER
with tab_daily_trades:
    st.subheader("📆 Günlük İşlem Takip Listesi")
    st.markdown("Bugün açılan veya kapatılan tüm işlemler, güncel kar/zarar durumlarıyla birlikte burada listelenir.")
    
    trades_today = pd.DataFrame()
    if not all_trades_df.empty:
        # Zaman kolonlarını güvenli bir şekilde datetime formatına çevir
        giris_dt = pd.to_datetime(all_trades_df["Giris Zamani"], errors="coerce")
        cikis_dt = pd.to_datetime(all_trades_df["Cikis Zamani"], errors="coerce")
        
        # yfinance verilerindeki en son tarihi bul
        latest_datetime = giris_dt.max()
        latest_date = latest_datetime.date() if pd.notna(latest_datetime) else datetime.now().date()
        
        trades_today = all_trades_df[
            (giris_dt.dt.date == latest_date) | 
            (cikis_dt.dt.date == latest_date)
        ].copy()
        
        # Günlük işlemleri VIOP kaldıraç ve teminat koşullarına göre yeniden hesapla
        trades_today = recalculate_trades_to_viop(
            trades_today,
            balance=viop_starting_balance,
            margin_pct=viop_margin_pct / 100.0,
            commission_bps=viop_commission_bps,
            slippage_bps=viop_slippage_bps
        )
        
    if not trades_today.empty:
        # Metrikleri hesapla
        toplam_islem = len(trades_today)
        karda_olanlar = trades_today[trades_today["Net PnL (TL)"] > 0]
        zararda_olanlar = trades_today[trades_today["Net PnL (TL)"] < 0]
        
        karda_sayisi = len(karda_olanlar)
        zararda_sayisi = len(zararda_olanlar)
        toplam_pnl_tl = trades_today["Net PnL (TL)"].sum()
        
        success_rate = (karda_sayisi / toplam_islem * 100) if toplam_islem > 0 else 0.0
        pnl_color = "#10b981" if toplam_pnl_tl >= 0 else "#ef4444"
        
        # Premium Metrik Kartları
        st.markdown(f"""
        <div class="kpi-container">
            <div class="kpi-card border-blue">
                <div class="kpi-title">Bugünkü Toplam İşlem</div>
                <div class="kpi-value">{toplam_islem}</div>
            </div>
            <div class="kpi-card border-green">
                <div class="kpi-title">🟢 Karda Olan İşlemler</div>
                <div class="kpi-value">{karda_sayisi}</div>
            </div>
            <div class="kpi-card border-red">
                <div class="kpi-title">🔴 Zararda Olan İşlemler</div>
                <div class="kpi-value">{zararda_sayisi}</div>
            </div>
            <div class="kpi-card border-purple">
                <div class="kpi-title">🏆 Başarı Oranı</div>
                <div class="kpi-value">%{success_rate:.2f}</div>
            </div>
            <div class="kpi-card" style="border-left: 5px solid {pnl_color}; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.45);">
                <div class="kpi-title" style="color: {pnl_color}; font-weight: bold;">💰 Toplam Net Kar/Zarar</div>
                <div class="kpi-value" style="color: {pnl_color};">{toplam_pnl_tl:,.2f} TL</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        
        # Tabloyu düzenle ve formatla
        display_trades = trades_today.copy()
        display_trades = strip_timezone_from_df(display_trades)
        
        cols_to_show = ["Hisse", "Yon", "Giris Zamani", "Cikis Zamani", "Giris Fiyat", "Cikis Fiyat", "Adet/Lot", "Net PnL (%)", "Net PnL (TL)", "Durum", "Kapanis Nedeni"]
        cols_to_show = [c for c in cols_to_show if c in display_trades.columns]
        display_trades = display_trades[cols_to_show]
        
        rename_cols = {
            "Hisse": "Hisse Kodu",
            "Yon": "İşlem Yönü",
            "Giris Zamani": "Giriş Zamanı",
            "Cikis Zamani": "Çıkış Zamanı",
            "Giris Fiyat": "Giriş Fiyatı",
            "Cikis Fiyat": "Son / Çıkış Fiyatı",
            "Adet/Lot": "Kontrat Sayısı",
            "Net PnL (%)": "Net P&L (%)",
            "Net PnL (TL)": "Net P&L (TL)",
            "Durum": "İşlem Durumu",
            "Kapanis Nedeni": "Kapanış Nedeni"
        }
        display_trades = display_trades.rename(columns=rename_cols)
        
        # Stilleri uygula
        def style_daily_pnl(val):
            try:
                val_float = float(val)
                if val_float > 0:
                    return 'color: #00ffb7; font-weight: bold; background-color: rgba(16, 185, 129, 0.1);'
                elif val_float < 0:
                    return 'color: #ff5252; font-weight: bold; background-color: rgba(239, 68, 68, 0.1);'
            except ValueError:
                pass
            return ''
            
        def style_direction(val):
            if str(val) == "LONG":
                return 'color: #00ffb7; font-weight: bold;'
            elif str(val) == "SHORT":
                return 'color: #ff5252; font-weight: bold;'
            return ''
            
        styled_daily_trades = safe_applymap(display_trades.style, style_daily_pnl, subset=["Net P&L (%)", "Net P&L (TL)"])
        styled_daily_trades = safe_applymap(styled_daily_trades, style_direction, subset=["İşlem Yönü"])
        
        st.dataframe(styled_daily_trades, use_container_width=True, height=400)
        
        # CSV İndirme Butonu
        csv_data = display_trades.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Günlük İşlemleri CSV Olarak İndir",
            data=csv_data,
            file_name=f"gunluk_islemler_{latest_date}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("Bugün açılan veya kapatılan herhangi bir aktif ORB işlemi bulunmamaktadır.")

# TAB 5: STRATEJİ REHBERİ
with tab_guide:
    st.subheader("📖 Opening Range Breakout (ORB) Nedir ve Nasıl Çalışır?")
    st.markdown("""
    ORB stratejisi, piyasa açılışından sonra belirli bir süre boyunca (genellikle ilk 15 veya 30 dakika) oluşan en yüksek ve en düşük fiyat seviyelerinin (kanal sınırları) kırılmasına dayanan klasik bir trend takip stratejisidir.
    
    ### Strateji İşleyiş Kuralları:
    1. **Kanalın Belirlenmesi**: Pazar açılış saatinden (örneğin 10:00) kanal bitiş saatine (örneğin 10:15) kadar hisse senedinin ulaştığı **en yüksek fiyat (Range High)** ve **en düşük fiyat (Range Low)** kaydedilir.
    2. **Breakout (Kırılım) İzleme**: Kanal belirlendikten sonra fiyat kanalın dışına çıkarsa işlem tetiklenir.
       * **Kapanış > Range High**: **AL** sinyali tetiklenir (Trend yukarı yönlü).
       * **Kapanış < Range Low**: 
         * Eğer **Açığa Satış (Short)** aktifse: **AÇIĞA SAT** sinyali tetiklenir.
         * Eğer short aktif değilse: Mevcut AL pozisyonu kapatılarak **NAKİT** durumuna geçilir.
    
    ### Parametrelerin Anlamı:
    * **10:15 Barı Zorunlu (Matriks Birebir)**: Eğer bu seçenek aktifse, Matriks formulasyonuyla uyumlu çalışarak tam kanal bitiş saatindeki (10:15) barın oluşması beklenir. Bar oluşmadan kanal hesaplanmaz.
    * **Sinyal Uygulama Modu**:
      * *Aynı Bar*: Sinyalin oluştuğu barın kapanışında hemen işlem gerçekleştirilir.
      * *Sonraki Bar*: Sinyal oluştuktan sonraki ilk barın açılışında işlem gerçekleştirilir. Backtestlerin daha gerçekçi olması için genelde 1 bar gecikme (Sonraki Bar) tercih edilir.
      
    ### Risk Yönetimi İpuçları:
    * **Bps (Basis Points - Onbinde Bir)**: Komisyon ve Slippage ayarları için kullanılır. Örneğin, aracı kurum komisyonunuz onbinde 2 ise bunu 2.0 bps olarak girmeniz gerekir. 
    * Fiyat Kayması (**Slippage**), yüksek volatilitede emrinizin istediğiniz fiyattan eşleşmeme payını temsil eder. Backtestlerinizi daha gerçekçi kılmak için mutlaka onbinde 1 veya 2 (1-2 bps) kayma payı eklemeniz tavsiye edilir.
    """)
