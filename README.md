# Voice Ticket Agent

A voice agent that listens to a spoken service request, works out which kind of request it is, asks only for the details that category still needs, and produces a structured ticket. A React frontend shows the live transcript and the ticket as it fills in.

## How to run

Requirements: Python 3.10+, Node 18+, and a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

**1. Backend** — from the project root:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

Create the environment file by copying the example and adding your key:

```bash
copy backend\.env.example backend\.env     # Windows   (macOS/Linux: cp backend/.env.example backend/.env)
```

Then open `backend/.env` and set:
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash # optional, this is the default


Start the server:

```bash
cd backend
python main.py                    
```

**2. Frontend** — in a second terminal:

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Open http://localhost:5173, click **Click to record**, describe a problem, then click again to send.

## Models and APIs used

Cascade, not Gemini Live:

- **Speech-to-text:** browser Web Speech API
- **LLM:** `gemini-3.6-flash` via the `google-genai` SDK, with a JSON response schema. Falls back to `gemini-3.8-flash` if overloaded or rate-limited.
- **Text-to-speech:** browser `speechSynthesis`

I chose the cascade because each stage is simple and replaceable, and it fit the time budget. Gemini Live (`gemini-3.8-live`) would be the next step.

## How it handles more than one type of request

- **One config.** `CATEGORIES` in `agent.py` lists each request type and its required fields. The prompt and the missing-field check are both built from it. A new type is one line.
- **Model extracts, server decides.** Gemini returns `{category, fields, notes, done, handoff, reply}` as JSON. The server saves the fields, works out what's missing, and marks the ticket complete. The model gets the current ticket state every turn, so it never re-asks.
- **Nothing is asked that can be inferred.** Category comes from what the user said. Urgency is inferred from context — asking for low/medium/high just gets "high".
- **Guardrails.** Max three questions per ticket. Hand-off to a human when the request is out of scope or after five turns with no ticket. Retry and a fallback model on 503/429, plus a Retry button. Field values over 120 characters are dropped as junk.

## What I'd improve with more time

- Gemini Live for real-time voice
- Let the user edit the transcript before sending
- Store tickets in a database
- Unit tests for the merge/missing logic

## Blockers

- **Rate limits.** Free tier returned 503s at times. Fixed with retry, a fallback model, and a Retry button.
- **Split sentences.** The browser finalised text at every pause. Fixed by collecting everything and sending once on stop.
