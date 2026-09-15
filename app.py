import os
import sqlite3
import re
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
import uvicorn

# 비밀번호 암호화 및 JWT 설정
SECRET_KEY = "chill_space_secret_key_change_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7일 유지

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

app = FastAPI()

def get_db():
    conn = sqlite3.connect("chill_space.db")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 사용자 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)
    
    # 플레이리스트 테이블 (user_id 추가)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    
    # 플레이리스트 아이템 테이블
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

    # Todo 테이블 (user_id 추가)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

init_db()

# --- Auth Helpers ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 자격 증명이 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise credentials_exception
    return {"id": user[0], "username": user[1]}

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

# --- Models ---
class UserAuth(BaseModel):
    username: str
    password: str

class CreatePlaylist(BaseModel):
    name: str

class PlaylistItem(BaseModel):
    playlist_id: int
    title: str
    youtube_id: str

class TodoItem(BaseModel):
    text: str
    done: bool = False

# ----------------- Auth API -----------------
@app.post("/api/signup")
def signup(user_data: UserAuth):
    conn = get_db()
    cursor = conn.cursor()
    try:
        hashed_pwd = get_password_hash(user_data.password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user_data.username, hashed_pwd))
        user_id = cursor.lastrowid
        # 새 사용자를 위한 기본 플레이리스트 생성
        cursor.execute("INSERT INTO playlists (user_id, name) VALUES (?, ?)", (user_id, "기본 플레이리스트"))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")
    conn.close()
    return {"message": "회원가입이 완료되었습니다."}

@app.post("/api/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (form_data.username,))
    row = cursor.fetchone()
    conn.close()

    if not row or not verify_password(form_data.password, row[1]):
        raise HTTPException(status_code=400, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user

# ----------------- Playlist Group API -----------------
@app.get("/api/playlists")
def get_playlists(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM playlists WHERE user_id = ?", (current_user["id"],))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]

@app.post("/api/playlists")
def create_playlist(data: CreatePlaylist, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO playlists (user_id, name) VALUES (?, ?)", (current_user["id"], data.name))
    conn.commit()
    pl_id = cursor.lastrowid
    conn.close()
    return {"id": pl_id, "name": data.name}

@app.delete("/api/playlists/{pl_id}")
def delete_playlist(pl_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playlists WHERE id = ? AND user_id = ?", (pl_id, current_user["id"]))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# ----------------- Playlist Items API -----------------
@app.get("/api/playlists/{pl_id}/items")
def get_playlist_items(pl_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    # 유저 권한 검증
    cursor.execute("SELECT id FROM playlists WHERE id = ? AND user_id = ?", (pl_id, current_user["id"]))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    cursor.execute("SELECT id, title, youtube_id, duration FROM playlist_items WHERE playlist_id = ?", (pl_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "youtube_id": r[2], "duration": r[3]} for r in rows]

@app.post("/api/playlist/items")
def add_playlist_item(item: PlaylistItem, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM playlists WHERE id = ? AND user_id = ?", (item.playlist_id, current_user["id"]))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    duration = fetch_youtube_duration(item.youtube_id)
    cursor.execute(
        "INSERT INTO playlist_items (playlist_id, title, youtube_id, duration) VALUES (?, ?, ?, ?)", 
        (item.playlist_id, item.title, item.youtube_id, duration)
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return {"id": item_id, "playlist_id": item.playlist_id, "title": item.title, "youtube_id": item.youtube_id, "duration": duration}

@app.delete("/api/playlist/items/{item_id}")
def delete_playlist_item(item_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM playlist_items 
        WHERE id = ? AND playlist_id IN (SELECT id FROM playlists WHERE user_id = ?)
    """, (item_id, current_user["id"]))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# ----------------- To-Do API -----------------
@app.get("/api/todos")
def get_todos(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, done FROM todos WHERE user_id = ?", (current_user["id"],))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "text": r[1], "done": bool(r[2])} for r in rows]

@app.post("/api/todos")
def add_todo(todo: TodoItem, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO todos (user_id, text, done) VALUES (?, ?, ?)", (current_user["id"], todo.text, int(todo.done)))
    conn.commit()
    todo_id = cursor.lastrowid
    conn.close()
    return {"id": todo_id, "text": todo.text, "done": todo.done}

@app.put("/api/todos/{todo_id}")
def toggle_todo(todo_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE todos SET done = NOT done WHERE id = ? AND user_id = ?", (todo_id, current_user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/todos/{todo_id}")
def delete_todo(todo_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, current_user["id"]))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
