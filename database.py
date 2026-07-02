import sqlite3
import hashlib
import os
import requests
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
IST_TZ = ZoneInfo("Europe/Istanbul")

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

def get_firebase_url():
    url = os.environ.get("FIREBASE_URL")
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get("FIREBASE_URL")
        except Exception:
            pass
    if not url:
        env_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            if key.strip() == "FIREBASE_URL":
                                url = val.strip().strip('"').strip("'")
                                break
            except Exception:
                pass
    if url:
        url = url.strip()
        while url.endswith("/"):
            url = url[:-1]
    return url

def hash_password(password: str) -> str:
    """Verilen şifreyi SHA-256 ile hashler."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    """Veritabanını ve varsayılan tabloları başlatır (Firebase veya SQLite)."""
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            # Check/Create default admins in Firebase
            for username in ['erkmen', 'admin']:
                res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
                user_exists = False
                if res.status_code == 200:
                    val = res.json()
                    if val is not None:
                        user_exists = True
                        # If admin already exists, guarantee role is ADMIN and status is APPROVED
                        if username == 'admin' and (val.get("role") != "ADMIN" or val.get("status") != "APPROVED"):
                            val["role"] = "ADMIN"
                            val["status"] = "APPROVED"
                            requests.put(f"{firebase_url}/users/{username}.json", json=val, timeout=3.0)
                
                if not user_exists:
                    admin_pass = "462081he"
                    hash_val = hash_password(admin_pass)
                    user_data = {
                        "username": username,
                        "password_hash": hash_val,
                        "status": "APPROVED",
                        "role": "ADMIN",
                        "created_at": datetime.now(IST_TZ).strftime("%Y-%m-%d %H:%M:%S")
                    }
                    requests.put(f"{firebase_url}/users/{username}.json", json=user_data, timeout=3.0)
            return
        except Exception:
            pass # Fallback to SQLite if Firebase connection fails during init
            
    # SQLite Fallback
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED
            role TEXT NOT NULL,    -- ADMIN, USER
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    # Varsayılan admin kullanıcılarını ekle (şifre: 462081he)
    for username in ['erkmen', 'admin']:
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            admin_pass = "462081he"
            hash_val = hash_password(admin_pass)
            cursor.execute(
                "INSERT INTO users (username, password_hash, status, role) VALUES (?, ?, ?, ?)",
                (username, hash_val, 'APPROVED', 'ADMIN')
            )
        elif username == 'admin':
            cursor.execute(
                "UPDATE users SET role = 'ADMIN', status = 'APPROVED' WHERE username = 'admin'"
            )
    conn.commit()
    conn.close()

def authenticate_user(username: str, password: str):
    """Kullanıcı adı ve şifreyi doğrular. Eşleşirse kullanıcı bilgilerini döner."""
    username = username.strip()
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
            if res.status_code == 200:
                user = res.json()
                if user:
                    stored_hash = user.get("password_hash")
                    input_hash = hash_password(password)
                    if stored_hash == input_hash:
                        return {
                            "username": user.get("username"),
                            "status": user.get("status"),
                            "role": user.get("role")
                        }
            return None
        except Exception:
            pass
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, password_hash, status, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        stored_hash = row[1]
        input_hash = hash_password(password)
        if stored_hash == input_hash:
            return {
                "username": row[0],
                "status": row[2],
                "role": row[3]
            }
    return None

def register_user(username: str, password: str) -> tuple[bool, str]:
    """Kullanıcının kendi kendine kayıt talebi oluşturmasını sağlar."""
    username = username.strip()
    if not username:
        return False, "Kullanıcı adı boş olamaz."
    if len(password) < 4:
        return False, "Şifre en az 4 karakter olmalıdır."
        
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
            if res.status_code == 200 and res.json() is not None:
                return False, "Bu kullanıcı adı zaten alınmış."
                
            pass_hash = hash_password(password)
            user_data = {
                "username": username,
                "password_hash": pass_hash,
                "status": "PENDING",
                "role": "USER",
                "created_at": datetime.now(IST_TZ).strftime("%Y-%m-%d %H:%M:%S")
            }
            requests.put(f"{firebase_url}/users/{username}.json", json=user_data, timeout=3.0)
            return True, "Kayıt talebiniz alındı! Yöneticinin onaylaması bekleniyor."
        except Exception as e:
            return False, f"Bulut veritabanı hatası: {str(e)}"
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return False, "Bu kullanıcı adı zaten alınmış."
        
        pass_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, status, role) VALUES (?, ?, ?, ?)",
            (username, pass_hash, 'PENDING', 'USER')
        )
        conn.commit()
        return True, "Kayıt talebiniz alındı! Yöneticinin onaylaması bekleniyor."
    except Exception as e:
        return False, f"Veritabanı hatası: {str(e)}"
    finally:
        conn.close()

def add_user_by_admin(username: str, password: str, role: str = "USER", status: str = "APPROVED") -> tuple[bool, str]:
    """Yöneticinin doğrudan kullanıcı eklemesini sağlar."""
    username = username.strip()
    if not username:
        return False, "Kullanıcı adı boş olamaz."
    if not password:
        return False, "Şifre boş olamaz."
        
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
            if res.status_code == 200 and res.json() is not None:
                return False, "Bu kullanıcı zaten mevcut."
                
            pass_hash = hash_password(password)
            user_data = {
                "username": username,
                "password_hash": pass_hash,
                "status": status,
                "role": role,
                "created_at": datetime.now(IST_TZ).strftime("%Y-%m-%d %H:%M:%S")
            }
            requests.put(f"{firebase_url}/users/{username}.json", json=user_data, timeout=3.0)
            return True, f"'{username}' kullanıcısı başarıyla oluşturuldu."
        except Exception as e:
            return False, f"Bulut veritabanı hatası: {str(e)}"
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return False, "Bu kullanıcı zaten mevcut."
        
        pass_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, status, role) VALUES (?, ?, ?, ?)",
            (username, pass_hash, status, role)
        )
        conn.commit()
        return True, f"'{username}' kullanıcısı başarıyla oluşturuldu."
    except Exception as e:
        return False, f"Veritabanı hatası: {str(e)}"
    finally:
        conn.close()

def get_all_users() -> list[dict]:
    """Tüm kullanıcı listesini çeker."""
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/users.json", timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                if data:
                    users = []
                    for username, u in data.items():
                        if u:
                            users.append({
                                "username": u.get("username"),
                                "status": u.get("status"),
                                "role": u.get("role"),
                                "created_at": u.get("created_at")
                            })
                    # Sort by created_at descending
                    users.sort(key=lambda x: x.get("created_at", "") or "", reverse=True)
                    return users
                return []
        except Exception:
            pass
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, status, role, created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"username": r[0], "status": r[1], "role": r[2], "created_at": r[3]} for r in rows]

def update_user_status(username: str, status: str):
    """Kullanıcının durumunu (APPROVED, REJECTED vb.) günceller."""
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
            if res.status_code == 200:
                user = res.json()
                if user:
                    user["status"] = status
                    requests.put(f"{firebase_url}/users/{username}.json", json=user, timeout=3.0)
            return
        except Exception:
            pass
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE username = ?", (status, username))
    conn.commit()
    conn.close()

def delete_user(username: str) -> tuple[bool, str]:
    """Kullanıcıyı sistemden tamamen siler."""
    if username == "erkmen":
        return False, "Ana yönetici hesabı silinemez."
        
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            requests.delete(f"{firebase_url}/users/{username}.json", timeout=3.0)
            return True, f"'{username}' kullanıcısı başarıyla silindi."
        except Exception as e:
            return False, f"Bulut veritabanı hatası: {str(e)}"
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True, f"'{username}' kullanıcısı başarıyla silindi."

def update_user_role(username: str, role: str):
    """Kullanıcının yetki rolünü (ADMIN, USER vb.) günceller."""
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
            if res.status_code == 200:
                user = res.json()
                if user:
                    user["role"] = role
                    requests.put(f"{firebase_url}/users/{username}.json", json=user, timeout=3.0)
            return
        except Exception:
            pass
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
    conn.commit()
    conn.close()

def create_user_session(username: str, role: str) -> str:
    """Yeni bir oturum tokenı oluşturup kaydeder."""
    token = uuid.uuid4().hex
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            session_data = {
                "username": username,
                "role": role,
                "created_at": datetime.now(IST_TZ).strftime("%Y-%m-%d %H:%M:%S")
            }
            requests.put(f"{firebase_url}/sessions/{token}.json", json=session_data, timeout=3.0)
            return token
        except Exception:
            pass
            
    # SQLite fallback
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "INSERT INTO sessions (token, username, role) VALUES (?, ?, ?)",
        (token, username, role)
    )
    conn.commit()
    conn.close()
    return token

def get_user_by_session(token: str) -> dict:
    """Verilen tokena sahip aktif oturum kullanıcısını getirir."""
    if not token:
        return None
        
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            res = requests.get(f"{firebase_url}/sessions/{token}.json", timeout=3.0)
            if res.status_code == 200:
                sess = res.json()
                if sess:
                    username = sess.get("username")
                    user_res = requests.get(f"{firebase_url}/users/{username}.json", timeout=3.0)
                    if user_res.status_code == 200:
                        user = user_res.json()
                        if user and user.get("status") == "APPROVED":
                            return {
                                "username": username,
                                "role": user.get("role")
                            }
            return None
        except Exception:
            pass
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username, role FROM sessions WHERE token = ?", (token,))
        row = cursor.fetchone()
        if row:
            username = row[0]
            # Kullanıcı durumunu kontrol et
            cursor.execute("SELECT status, role FROM users WHERE username = ?", (username,))
            user_row = cursor.fetchone()
            if user_row and user_row[0] == 'APPROVED':
                return {
                    "username": username,
                    "role": user_row[1]
                }
    except Exception:
        pass
    finally:
        conn.close()
    return None

def delete_user_session(token: str):
    """Oturumu sonlandırır."""
    if not token:
        return
    firebase_url = get_firebase_url()
    if firebase_url:
        try:
            requests.delete(f"{firebase_url}/sessions/{token}.json", timeout=3.0)
            return
        except Exception:
            pass
            
    # SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
