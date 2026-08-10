from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.email_service import test_smtp_connection

router = APIRouter(prefix="/api/settings")

class SettingsUpdate(BaseModel):
    email: str
    app_password: Optional[str] = None
    server: Optional[str] = "smtp.gmail.com"
    port: Optional[int] = 465

@router.get("/")
def get_settings():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT email, app_password, smtp_server, smtp_port FROM settings WHERE id = 1")
    row = cursor.fetchone()
    db.close()
    
    if row:
        return {
            "email": row["email"] or "",
            "has_password": bool(row["app_password"]),
            "smtp_server": row["smtp_server"] or "smtp.gmail.com",
            "smtp_port": row["smtp_port"] or 465,
            "server": row["smtp_server"] or "smtp.gmail.com",
            "port": row["smtp_port"] or 465
        }
    return {"email": "", "has_password": False, "smtp_server": "smtp.gmail.com", "smtp_port": 465, "server": "smtp.gmail.com", "port": 465}

@router.post("/")
def save_settings(settings: SettingsUpdate):
    db = get_db()
    cursor = db.cursor()
    
    # If no new password provided, keep the existing one
    password_to_save = settings.app_password
    if not password_to_save:
        cursor.execute("SELECT app_password FROM settings WHERE id = 1")
        existing = cursor.fetchone()
        if existing:
            password_to_save = existing["app_password"]
    
    cursor.execute('''
        INSERT OR REPLACE INTO settings (id, email, app_password, smtp_server, smtp_port)
        VALUES (1, ?, ?, ?, ?)
    ''', (settings.email, password_to_save, settings.server or "smtp.gmail.com", settings.port or 465))
    db.commit()
    db.close()
    return {"message": "Settings saved successfully"}

@router.post("/test")
def test_connection():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT email, app_password, smtp_server, smtp_port FROM settings WHERE id = 1")
    row = cursor.fetchone()
    db.close()
    
    if not row or not row["email"] or not row["app_password"]:
        return {"success": False, "message": "Email and app password not configured."}
        
    success = test_smtp_connection(row["email"], row["app_password"], row["smtp_server"], row["smtp_port"])
    if success:
        return {"success": True, "message": "Connection successful"}
    else:
        return {"success": False, "message": "Failed to connect. Check credentials."}
