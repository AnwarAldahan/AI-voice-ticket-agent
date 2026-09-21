"""
main.py — FastAPI wrapper around the agent.

Two endpoints:
  POST /api/chat   {session_id, text}  -> agent reply + current ticket state
  POST /api/reset  {session_id}        -> start a fresh ticket

Sessions live in memory (a dict). Fine for a demo; a real system would use Redis/DB.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()  # reads backend/.env

from agent import TicketAgent, new_session  # noqa: E402  (needs env loaded first)

app = FastAPI(title="Voice Ticket Agent")

# The Vite dev server runs on a different port, so allow it to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = TicketAgent()
sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    session_id: str
    text: str


class ResetRequest(BaseModel):
    session_id: str


@app.get("/api/health")
def health():
    return {"ok": True, "model": agent.model}


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty transcript")
    state = sessions.setdefault(req.session_id, new_session())
    try:
        return agent.handle_turn(state, req.text)
    except Exception as e:  # surface model/API errors to the UI instead of a bare 500
        raise HTTPException(status_code=502, detail=f"Model call failed: {e}")


@app.post("/api/reset")
def reset(req: ResetRequest):
    sessions[req.session_id] = new_session()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
