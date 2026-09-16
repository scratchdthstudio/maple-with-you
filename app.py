import os
import sqlite3
import re
import urllib.request
import hashlib
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI()

def init_db():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # To-Do 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )
    """)
    
    # 플레이리스트 그룹 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)
    
    # 플레이리스트 트랙 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            youtube_id TEXT NOT NULL,
            duration INTEGER DEFAULT 0,
            FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE
        )
    """)
    
    # 기본 플레이리스트 생성
    cursor.execute("INSERT OR IGNORE INTO playlists (id, name) VALUES (1, '기본 플레이리스트')")
    conn.commit()
    conn.close()

init_db()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def fetch_youtube_duration(youtube_id: str) -> int:
    try:
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        html = urllib.request.urlopen(req).read().decode('utf-8')
        match = re.search(r'"approxDurationMs"\s*:\s*"(\d+)"', html)
        if match:
            return int(match.group(1)) // 1000
    except Exception as e:
        print(f"시간 추출 실패: {e}")
    return 0

class CreatePlaylist(BaseModel):
    name: str

class PlaylistItem(BaseModel):
    playlist_id: int
    title: str
    youtube_id: str

class TodoItem(BaseModel):
    text: str
    done: bool = False

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

# ----------------- User Signup API -----------------
@app.post("/api/signup")
def signup(data: SignupRequest):
    username = data.username.strip()
    email = data.email.strip().lower()
    password = data.password.strip()

    if len(username) < 2:
        return {"success": False, "message": "아이디는 2자 이상이어야 합니다."}
    if "@" not in email or "." not in email:
        return {"success": False, "message": "올바른 이메일 형식을 입력해주세요."}
    if len(password) < 6:
        return {"success": False, "message": "비밀번호는 6자 이상이어야 합니다."}

    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        return {"success": False, "message": "이미 사용 중인 아이디 또는 이메일입니다."}

    cursor.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (username, email, hash_password(password))
    )
    conn.commit()
    conn.close()

    return {"success": True, "message": "회원가입이 완료되었습니다."}

# ----------------- Playlist Group API -----------------
@app.get("/api/playlists")
def get_playlists():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM playlists")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]

@app.post("/api/playlists")
def create_playlist(data: CreatePlaylist):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO playlists (name) VALUES (?)", (data.name,))
    conn.commit()
    pl_id = cursor.lastrowid
    conn.close()
    return {"id": pl_id, "name": data.name}

@app.delete("/api/playlists/{pl_id}")
def delete_playlist(pl_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playlists WHERE id = ?", (pl_id,))
    cursor.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (pl_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# ----------------- Playlist Items API -----------------
@app.get("/api/playlists/{pl_id}/items")
def get_playlist_items(pl_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, youtube_id, duration FROM playlist_items WHERE playlist_id = ?", (pl_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "youtube_id": r[2], "duration": r[3]} for r in rows]

@app.post("/api/playlist/items")
def add_playlist_item(item: PlaylistItem):
    duration = fetch_youtube_duration(item.youtube_id)
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO playlist_items (playlist_id, title, youtube_id, duration) VALUES (?, ?, ?, ?)", 
        (item.playlist_id, item.title, item.youtube_id, duration)
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return {"id": item_id, "playlist_id": item.playlist_id, "title": item.title, "youtube_id": item.youtube_id, "duration": duration}

@app.delete("/api/playlist/items/{item_id}")
def delete_playlist_item(item_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playlist_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

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
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
