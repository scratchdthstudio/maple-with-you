import os
import json
import sqlite3
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = FastAPI()

# ----------------- Google OAuth 및 Drive 설정 -----------------
# ⚠️ 실제 발급받은 Google OAuth Client ID 및 Secret으로 교체하세요.
CLIENT_CONFIG = {
    "web": {
        "client_id": "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
        "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8000/auth/callback"]
    }
}

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email"
]

# 메모리 기반 토큰 세션 (실서비스 시 세션 DB 저장 추천)
user_tokens = {}

# ----------------- DB 초기화 -----------------
def init_db():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

class TodoItem(BaseModel):
    text: str
    done: bool = False

# ----------------- Google OAuth API -----------------
@app.get("/auth/login")
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = "http://localhost:8000/auth/callback"
    authorization_url, state = flow.authorization_url(prompt='consent')
    return RedirectResponse(authorization_url)

@app.get("/auth/callback")
def auth_callback(code: str):
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = "http://localhost:8000/auth/callback"
    flow.fetch_token(code=code)
    
    credentials = flow.credentials
    user_tokens["default"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    }
    return RedirectResponse(url="/")

@app.get("/api/user")
def get_user_info():
    if "default" not in user_tokens:
        return {"logged_in": False}
    return {"logged_in": True}

# ----------------- Google Drive Playlist API -----------------
@app.get("/api/drive/playlist")
def get_drive_playlist():
    if "default" not in user_tokens:
        raise HTTPException(status_code=401, detail="Google Log-in required")
    
    creds = Credentials(**user_tokens["default"])
    service = build('drive', 'v3', credentials=creds)

    # 구글 드라이브 내 MP4 파일 검색
    query = "mimeType='video/mp4' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    items = results.get('files', [])

    playlist = []
    for item in items:
        playlist.append({
            "id": item['id'],
            "title": item['name'],
            "file_path": f"/api/drive/stream/{item['id']}"
        })
    return playlist

@app.get("/api/drive/stream/{file_id}")
def stream_drive_file(file_id: str):
    if "default" not in user_tokens:
        raise HTTPException(status_code=401, detail="Google Log-in required")

    access_token = user_tokens["default"]["token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    drive_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    req = requests.get(drive_url, headers=headers, stream=True)
    return StreamingResponse(req.iter_content(chunk_size=1024 * 1024), media_type="video/mp4")

# ----------------- To-Do API -----------------
@app.get("/api/todos")
def get_todos():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, done FROM todos")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "text": r[1], "done": bool(r[2])} for r in rows]

@app.post("/api/todos")
def add_todo(todo: TodoItem):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO todos (text, done) VALUES (?, ?)", (todo.text, int(todo.done)))
    conn.commit()
    todo_id = cursor.lastrowid
    conn.close()
    return {"id": todo_id, "text": todo.text, "done": todo.done}

@app.put("/api/todos/{todo_id}")
def toggle_todo(todo_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE todos SET done = NOT done WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/todos/{todo_id}")
def delete_todo(todo_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)