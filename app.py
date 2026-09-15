import os
import sqlite3
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI()

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
            youtube_id TEXT UNIQUE NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

class TodoItem(BaseModel):
    text: str
    done: bool = False

class PlaylistItem(BaseModel):
    title: str
    youtube_id: str

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

# ----------------- YouTube Playlist API -----------------
@app.get("/api/playlist")
def get_playlist():
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, youtube_id FROM playlist")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "youtube_id": r[2]} for r in rows]

@app.post("/api/playlist")
def add_playlist_item(item: PlaylistItem):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO playlist (title, youtube_id) VALUES (?, ?)", (item.title, item.youtube_id))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return {"id": item_id, "title": item.title, "youtube_id": item.youtube_id}

@app.delete("/api/playlist/{item_id}")
def delete_playlist_item(item_id: int):
    conn = sqlite3.connect("chill_space.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playlist WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
