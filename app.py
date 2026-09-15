from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3

app = FastAPI()

# DB 초기화 및 테이블 생성
def init_db():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    # 투두 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )
    """)
    # 플레이리스트 메타데이터 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# 데이터 데이터 구조 정의
class TodoItem(BaseModel):
    text: str
    done: bool = False

class PlaylistItem(BaseModel):
    title: str
    file_path: str

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

# ----------------- Playlist API -----------------
@app.get("/api/playlist")
def get_playlist():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, file_path FROM playlist")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "file_path": r[2]} for r in rows]

@app.post("/api/playlist")
def add_playlist_item(item: PlaylistItem):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO playlist (title, file_path) VALUES (?, ?)", (item.title, item.file_path))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return {"id": item_id, "title": item.title, "file_path": item.file_path}

# 정적 파일(index.html 및 media 파일) 서빙
app.mount("/", StaticFiles(directory=".", html=True), name="static")