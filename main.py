import os
import glob
import sqlite3
import threading
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import webview

# ================= 1. FastAPI 백엔드 =================
app = FastAPI()

AUTO_SCAN_FOLDER = os.path.join(os.path.expanduser("~"), "Videos", "ChillSpace")

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT UNIQUE NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def scan_auto_folder():
    if not os.path.exists(AUTO_SCAN_FOLDER):
        os.makedirs(AUTO_SCAN_FOLDER, exist_ok=True)

    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    video_files = glob.glob(os.path.join(AUTO_SCAN_FOLDER, "*.mp4"))

    for file_path in video_files:
        title = os.path.splitext(os.path.basename(file_path))[0]
        cursor.execute("INSERT OR IGNORE INTO playlist (title, file_path) VALUES (?, ?)", (title, file_path))
    
    conn.commit()
    conn.close()

init_db()
scan_auto_folder()

class TodoItem(BaseModel):
    text: str
    done: bool = False

class PlaylistItem(BaseModel):
    title: str
    file_path: str

# API 엔드포인트
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

@app.get("/api/playlist")
def get_playlist():
    scan_auto_folder()
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, file_path FROM playlist")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "file_path": f"/api/stream?path={r[2]}"} for r in rows]

@app.post("/api/playlist")
def add_playlist_item(item: PlaylistItem):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO playlist (title, file_path) VALUES (?, ?)", (item.title, item.file_path))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return {"id": item_id, "title": item.title, "file_path": f"/api/stream?path={item.file_path}"}

@app.delete("/api/playlist/{item_id}")
def delete_playlist_item(item_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playlist WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

@app.get("/api/stream")
def stream_file(path: str):
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4")
    raise HTTPException(status_code=404, detail="File not found")

app.mount("/", StaticFiles(directory=".", html=True), name="static")

# ================= 2. 실행 구동부 =================
def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == "__main__":
    # 백그라운드 스레드로 파이썬 웹 서버 실행
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # pywebview 앱 창 띄우기 (Electron과 동일한 내장 브라우저 창 창출)
    webview.create_window('Chill Space', 'http://127.0.0.1:8000', width=1280, height=800)
    webview.start()