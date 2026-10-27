from fastapi import APIRouter, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.email_service import send_email
import os
import shutil
import io
import csv
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api")

@router.post("/send")
async def send_emails_route(
    subject: str = Form(...),
    body: str = Form(...),
    attachment: Optional[UploadFile] = File(None)
):
    db = get_db()
    cursor = db.cursor()
    
    # Get settings
    cursor.execute("SELECT email, app_password FROM settings WHERE id = 1")
    settings = cursor.fetchone()
    
    if not settings or not settings["email"] or not settings["app_password"]:
        db.close()
        return {"total": 0, "sent": 0, "failed": 0, "results": [], "error": "SMTP credentials not configured."}
        
    sender_email = settings["email"]
    app_password = settings["app_password"]
    
    # Get recipients
    cursor.execute("SELECT name, email FROM recipients")
    recipients = cursor.fetchall()
    
    if not recipients:
        db.close()
        return {"total": 0, "sent": 0, "failed": 0, "results": [], "error": "No recipients found."}

    # Handle attachment
    attachment_path = None
    if attachment and attachment.filename:
        os.makedirs("attachments", exist_ok=True)
        attachment_path = os.path.join("attachments", attachment.filename)
        with open(attachment_path, "wb") as buffer:
            shutil.copyfileobj(attachment.file, buffer)

    sent = 0
    failed = 0
    results = []

    for rec in recipients:
        name = rec["name"]
        rec_email = rec["email"]
        personalized_body = body.replace("{name}", name)
        
        status = "Failed"
        try:
            success = send_email(sender_email, app_password, rec_email, subject, personalized_body, attachment_path)
            if success:
                status = "Sent"
                sent += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"Failed to send to {rec_email}: {e}")
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO logs (timestamp, name, email, status, subject) VALUES (?, ?, ?, ?, ?)",
            (timestamp, name, rec_email, status, subject)
        )
        results.append({"name": name, "email": rec_email, "status": status})
        
    db.commit()
    db.close()
    
    return {"total": len(recipients), "sent": sent, "failed": failed, "results": results}

@router.get("/logs")
def get_logs(search: str = None, page: int = 1, per_page: int = 50):
    db = get_db()
    cursor = db.cursor()
    
    query = "SELECT * FROM logs"
    params = []
    
    if search:
        query += " WHERE name LIKE ? OR email LIKE ? OR subject LIKE ?"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        
    cursor.execute(f"SELECT COUNT(*) as count FROM ({query})", params)
    total = cursor.fetchone()["count"]
    
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    db.close()
    
    logs = [dict(row) for row in rows]
    return {"logs": logs, "total": total, "page": page, "per_page": per_page}

@router.get("/logs/export")
def export_logs():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT timestamp, name, email, status, subject FROM logs ORDER BY id DESC")
    rows = cursor.fetchall()
    db.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Name", "Email", "Status", "Subject"])
    for row in rows:
        writer.writerow([row["timestamp"], row["name"], row["email"], row["status"], row["subject"]])
        
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=email_logs.csv"}
    )

@router.get("/dashboard/stats")
def get_stats():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM logs")
    total_emails = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as sent FROM logs WHERE status = 'Sent'")
    sent = cursor.fetchone()["sent"]
    
    cursor.execute("SELECT COUNT(*) as failed FROM logs WHERE status = 'Failed'")
    failed = cursor.fetchone()["failed"]
    
    cursor.execute("SELECT COUNT(*) as total FROM recipients")
    pending = cursor.fetchone()["total"]
    
    db.close()
    
    return {
        "total": total_emails,
        "total_emails": total_emails,
        "sent": sent,
        "failed": failed,
        "pending": pending
    }
