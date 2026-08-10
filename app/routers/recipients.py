from fastapi import APIRouter, UploadFile, File, Query
import pandas as pd
import re
import os
import tempfile
from app.database import get_db

router = APIRouter(prefix="/api/recipients")

@router.get("/")
def get_recipients(search: str = None, page: int = 1, per_page: int = 50):
    db = get_db()
    cursor = db.cursor()
    
    query = "SELECT * FROM recipients"
    params = []
    
    if search:
        query += " WHERE name LIKE ? OR email LIKE ?"
        params.extend([f"%{search}%", f"%{search}%"])
        
    cursor.execute(f"SELECT COUNT(*) as count FROM ({query})", params)
    total = cursor.fetchone()["count"]
    
    query += " LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    db.close()
    
    recipients = [dict(row) for row in rows]
    return {"recipients": recipients, "total": total, "page": page, "per_page": per_page}

@router.post("/upload")
async def upload_recipients(file: UploadFile = File(...)):
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        return {"message": "Invalid file format", "count": 0}
        
    # Save temp file
    fd, temp_path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, 'wb') as f:
            content = await file.read()
            f.write(content)
            
        if file.filename.endswith('.csv'):
            df = pd.read_csv(temp_path)
        else:
            df = pd.read_excel(temp_path)
            
        if 'Name' not in df.columns or 'Email' not in df.columns:
            return {"message": "Missing 'Name' or 'Email' columns", "count": 0}
            
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM recipients")
        
        count = 0
        for _, row in df.iterrows():
            email = str(row['Email']).strip()
            name = str(row['Name']).strip()
            
            if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email):
                cursor.execute("INSERT INTO recipients (name, email) VALUES (?, ?)", (name, email))
                count += 1
                
        db.commit()
        db.close()
        
        return {"message": "Recipients uploaded successfully", "count": count}
    except Exception as e:
        return {"message": f"Error processing file: {str(e)}", "count": 0}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@router.delete("/")
def clear_recipients():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM recipients")
    db.commit()
    db.close()
    return {"message": "All recipients cleared"}
