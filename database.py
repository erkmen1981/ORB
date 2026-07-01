import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

def init_db():
    """Veritabanını ve varsayılan tabloları başlatır."""
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
    # 1. erkmen
    cursor.execute("SELECT * FROM users WHERE username = 'erkmen'")
    if not cursor.fetchone():
        admin_pass = "462081he"
        hash_val = hashlib.sha256(admin_pass.encode('utf-8')).hexdigest()
        cursor.execute(
            "INSERT INTO users (username, password_hash, status, role) VALUES (?, ?, ?, ?)",
            ('erkmen', hash_val, 'APPROVED', 'ADMIN')
        )
        
    # 2. admin
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    row = cursor.fetchone()
    if not row:
        admin_pass = "462081he"
        hash_val = hashlib.sha256(admin_pass.encode('utf-8')).hexdigest()
        cursor.execute(
            "INSERT INTO users (username, password_hash, status, role) VALUES (?, ?, ?, ?)",
            ('admin', hash_val, 'APPROVED', 'ADMIN')
        )
    else:
        # Eğer zaten varsa, rolünün ADMIN ve durumunun APPROVED olmasını garanti et
        cursor.execute(
            "UPDATE users SET role = 'ADMIN', status = 'APPROVED' WHERE username = 'admin'"
        )
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Verilen şifreyi SHA-256 ile hashler."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def authenticate_user(username: str, password: str):
    """Kullanıcı adı ve şifreyi doğrular. Eşleşirse kullanıcı bilgilerini döner."""
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, status, role, created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"username": r[0], "status": r[1], "role": r[2], "created_at": r[3]} for r in rows]

def update_user_status(username: str, status: str):
    """Kullanıcının durumunu (APPROVED, REJECTED vb.) günceller."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE username = ?", (status, username))
    conn.commit()
    conn.close()

def delete_user(username: str) -> tuple[bool, str]:
    """Kullanıcıyı sistemden tamamen siler."""
    if username == "erkmen":
        return False, "Ana yönetici hesabı silinemez."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True, f"'{username}' kullanıcısı başarıyla silindi."

def update_user_role(username: str, role: str):
    """Kullanıcının yetki rolünü (ADMIN, USER vb.) günceller."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
    conn.commit()
    conn.close()
