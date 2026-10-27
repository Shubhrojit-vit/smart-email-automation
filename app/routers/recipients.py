from fastapi import APIRouter, UploadFile, File, HTTPException
import pandas as pd
import re
import io
from datetime import datetime
from app.database import get_db

router = APIRouter(prefix="/api/recipients")

@router.get("/")
def get_recipients(search: str = None, page: int = 1, per_page: int = 100):
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
    
    # Retrieve upload metadata if present
    cursor.execute("SELECT filename, uploaded_at FROM upload_metadata WHERE id = 1")
    meta = cursor.fetchone()
    file_name = meta["filename"] if meta and meta["filename"] else ("recipients.xlsx" if total > 0 else None)
    
    db.close()
    
    recipients = [dict(row) for row in rows]
    return {
        "recipients": recipients,
        "total": total,
        "count": total,
        "page": page,
        "per_page": per_page,
        "fileName": file_name
    }

@router.post("/upload")
async def upload_recipients(file: UploadFile = File(...)):
    filename = file.filename or "recipients.xlsx"
    filename_lower = filename.lower()
    
    if not (filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls') or filename_lower.endswith('.csv')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Please upload an Excel (.xlsx, .xls) or CSV (.csv) file."
        )
        
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
            
        file_bytes = io.BytesIO(content)
        
        if filename_lower.endswith('.csv'):
            try:
                df = pd.read_csv(file_bytes)
            except UnicodeDecodeError:
                file_bytes.seek(0)
                df = pd.read_csv(file_bytes, encoding='latin1')
        else:
            df = pd.read_excel(file_bytes)
            
        if df.empty:
            raise HTTPException(status_code=400, detail="The uploaded spreadsheet contains no data rows.")
            
        # Strip whitespace from column headers
        df.columns = [str(c).strip() for c in df.columns]
        
        # Detect Name and Email columns flexibly
        name_col = None
        email_col = None
        
        # 1. Exact priority match
        for col in df.columns:
            cl = col.lower()
            if cl in ['email', 'email address', 'email_address', 'e-mail', 'mail']:
                email_col = col
                break
        
        for col in df.columns:
            cl = col.lower()
            if cl in ['name', 'full name', 'full_name', 'recipient', 'recipient name']:
                name_col = col
                break
                
        # 2. Fuzzy substring match if not found yet
        if not email_col:
            for col in df.columns:
                cl = col.lower()
                if 'email' in cl or 'mail' in cl:
                    email_col = col
                    break
                    
        if not name_col:
            for col in df.columns:
                cl = col.lower()
                if any(k in cl for k in ['name', 'recipient', 'contact', 'customer', 'person']):
                    name_col = col
                    break
                    
        # 3. Fallback: scan sample rows in any column for email pattern
        if not email_col:
            for col in df.columns:
                sample_vals = df[col].dropna().astype(str).head(5)
                if any(re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', str(v)) for v in sample_vals):
                    email_col = col
                    break
                    
        if not email_col:
            columns_detected = ", ".join([f"'{c}'" for c in df.columns])
            raise HTTPException(
                status_code=400,
                detail=f"Could not find an Email column. Found columns: [{columns_detected}]. Please include a column named 'Email'."
            )
            
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM recipients")
        
        count = 0
        seen_entries = set()
        
        for _, row in df.iterrows():
            raw_email = str(row[email_col]).strip() if pd.notna(row.get(email_col)) else ""
            match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', raw_email)
            if not match:
                continue
                
            email = match.group(0).lower()
            
            raw_name = str(row[name_col]).strip() if (name_col and pd.notna(row.get(name_col))) else ""
            if not raw_name or raw_name.lower() in ['nan', 'none', 'null']:
                # Derive friendly name from email username (e.g., rahul.kumar -> Rahul Kumar)
                name = email.split('@')[0].replace('.', ' ').replace('_', ' ').replace('-', ' ').title()
            else:
                name = raw_name
                
            entry_key = (name.strip().lower(), email)
            if entry_key in seen_entries:
                continue
            seen_entries.add(entry_key)
                
            cursor.execute(
                "INSERT INTO recipients (name, email, status) VALUES (?, ?, 'Valid')",
                (name, email)
            )
            count += 1
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT OR REPLACE INTO upload_metadata (id, filename, uploaded_at, total_recipients) VALUES (1, ?, ?, ?)",
            (filename, timestamp, count)
        )
        
        db.commit()
        db.close()
        
        if count == 0:
            raise HTTPException(
                status_code=400,
                detail="No valid email addresses found in the selected file."
            )
            
        return {
            "success": True,
            "message": f"Successfully loaded {count} recipients",
            "count": count,
            "fileName": filename
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )

@router.delete("/")
def clear_recipients():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM recipients")
    cursor.execute("DELETE FROM upload_metadata")
    db.commit()
    db.close()
    return {"message": "All recipients cleared", "count": 0}
