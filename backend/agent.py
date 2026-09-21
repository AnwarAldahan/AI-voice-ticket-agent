"""
agent.py — the agent's brain.

Idea: Gemini EXTRACTS (category + fields + notes + reply) in a fixed JSON shape.
      The server DECIDES (merges fields, computes what's missing, marks complete).
"""

import json, os, time
from typing import Literal, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel

# ---- 1. What each request type needs. Add a category = add one line. ----
CATEGORIES = {
    "maintenance": {"label": "Maintenance / Facilities", "required": ["location", "description", "urgency"]},
    "it_support":  {"label": "IT Support",               "required": ["device", "description"]},
}

# ---- 2. The exact JSON shape Gemini must return. ----
class Fields(BaseModel):
    location: Optional[str] = None
    description: Optional[str] = None
    urgency: Optional[Literal["low", "medium", "high"]] = None
    device: Optional[str] = None

class AgentTurn(BaseModel):
    category: Literal["maintenance", "it_support", "unknown"]
    fields: Fields
    notes: Optional[str] = None   # any extra useful detail the user mentioned
    done: bool                    # true only when confirming the ticket, not when asking
    handoff: bool = False         # true when the request is outside what this assistant handles
    reply: str

# ---- 3. The prompt, built from CATEGORIES + current ticket state. ----
def build_prompt(state):
    cats = "\n".join(
        f'- "{k}" ({v["label"]}): required fields = {", ".join(v["required"])}'
        for k, v in CATEGORIES.items()
    )
    asked = sum(1 for c in state["history"] if c.role == "model")

    return f"""ROLE
You are the voice assistant for an internal help desk. Employees describe a problem out loud, and your job is to collect the information needed to open a support ticket, then confirm it. You do not fix problems, give technical advice, or make small talk.

HOW YOU SPEAK
- Your replies are read aloud by text-to-speech, so keep them to one or two short sentences.
- Be polite and direct. No greetings, no filler, no lists.
- Ask ONE question at a time.

REQUEST CATEGORIES
{cats}

FIELD RULES
- location: where the problem is (building, floor, room or office number). "My office" alone is not enough — ask which office.
- description: what actually happens. "Not working" or "broken" alone is too vague — ask what exactly goes wrong (e.g. "no cold air", "shows a wifi error", "screen stays black").
- urgency: low, medium, or high. Infer it from context when you can (words like "urgent", "asap", "help", nobody can work → high; "whenever you get a chance", cosmetic → low; otherwise medium). Only if genuinely unclear, ask ONE impact question such as "Is this stopping anyone from working right now?" — never ask the user to pick low/medium/high directly.
- device: the equipment involved (laptop, printer, desk phone...) plus its ID or asset tag if the user knows it.
- Field values are short phrases (a few words), never sentences, never reasoning. Keep all thinking out of the fields.
Required fields are the minimum, not the limit. Anything else useful goes in "notes".

WHAT TO DO EACH TURN
1. Decide the category from what the user has said. "unknown" only if nothing points to a category yet.
2. Extract every field value the user has stated, in this turn or earlier. Never guess or invent a value.
   Put any other useful detail (error message, how long it has been happening, who else is affected...) in "notes".
3. Reply:
   - Category unknown → ask what the problem is.
   - Required fields missing → ask for ONE missing field.
   - Required fields all filled → you may ask ONE extra question if it would clearly help the technician,
     but only if you still have budget (see below). Otherwise confirm the ticket in one sentence and set done=true.

QUESTION BUDGET
You have asked {asked} question(s) so far.
- First pass: at most 3 questions in total. Required fields come first; an extra question only if budget remains.
- When the budget is used up, confirm with what you have and set done=true, even if you would have liked to ask more.
- If the ticket was already confirmed and the user speaks again, this is a follow-up: update or add details,
  and you may ask further questions if genuinely needed.

EDGE CASES
- Request clearly outside both categories (e.g. room cleaning, HR, catering) → do not ask which category. Say this assistant only handles maintenance and IT requests, tell them you'll connect them with a support agent, and set handoff=true.
- User gives several details at once → extract all of them, then ask only for what is still missing.
- User corrects an earlier value → use the new value.
- User asks for a fix or advice → briefly say a technician will handle it, then continue collecting details.

CURRENT STATE (already captured — do not re-ask for these)
category: {state["category"] or "unknown"}
fields: {json.dumps(state["ticket"])}
notes: {state["notes"] or "none"}
missing: {state["missing"]}
"""

# ---- 4. Session state + one conversation turn. ----
MAX_TURNS = 5                              # after this many real replies without a complete ticket, hand off to a human
FALLBACK_MODEL = "gemini-3.5-flash-lite"   # lighter model used if the main one is overloaded (503)
MAX_FIELD_LEN = 120                        # real field values are short; anything longer is junk

def new_session():
    return {
        "history": [], "category": None, "ticket": {}, "notes": None,
        "missing": [], "complete": False, "turns": 0, "escalated": False,
    }

class TicketAgent:
    def __init__(self):
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    def _call_model(self, state):
        """Try the main model up to 3 times on 503, then the fallback model the same way."""
        config = types.GenerateContentConfig(
            system_instruction=build_prompt(state),
            response_mime_type="application/json",
            response_schema=AgentTurn,
        )
        for model in [self.model, FALLBACK_MODEL]:
            for attempt in range(3):
                try:
                    return self.client.models.generate_content(model=model, contents=state["history"], config=config)
                except Exception as e:
                    if "503" not in str(e):
                        raise                      # a real error: surface it
                    time.sleep(1.5)                # overloaded: wait and retry
        raise RuntimeError("Model unavailable after retries")

    def handle_turn(self, state, user_text):
        # fallback: 5 real replies and still no complete ticket -> hand off to a person
        if state["turns"] >= MAX_TURNS and not state["complete"]:
            state["escalated"] = True
            return self._result(state, "I'm having trouble capturing this. I'll connect you with a support agent who can help directly.")

        # a) add user's words to the conversation
        state["history"].append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

        # b) ask Gemini for a structured answer
        res = self._call_model(state)
        turn = AgentTurn.model_validate_json(res.text)
        state["turns"] += 1
        state["history"].append(types.Content(role="model", parts=[types.Part.from_text(text=turn.reply)]))

        # out of scope: the model asked for a human hand-off
        if turn.handoff:
            state["escalated"] = True
            return self._result(state, turn.reply)

        # c) server merges: keep any value the model returns (so corrections overwrite), reject junk
        if turn.category != "unknown":
            state["category"] = turn.category
        for name, value in turn.fields.model_dump().items():
            if value and len(value) <= MAX_FIELD_LEN:
                state["ticket"][name] = value
        if turn.notes and len(turn.notes) <= 300:
            state["notes"] = turn.notes

        # d) server decides what's missing; complete = required filled AND model is confirming
        required = CATEGORIES[state["category"]]["required"] if state["category"] else []
        state["missing"] = [f for f in required if not state["ticket"].get(f)]
        state["complete"] = bool(state["category"]) and not state["missing"] and turn.done

        return self._result(state, turn.reply)

    def _result(self, state, reply):
        required = CATEGORIES[state["category"]]["required"] if state["category"] else []
        return {
            "reply": reply,
            "category": state["category"],
            "category_label": CATEGORIES[state["category"]]["label"] if state["category"] else None,
            "ticket": {f: state["ticket"].get(f) for f in required},
            "notes": state["notes"],
            "missing": state["missing"],
            "complete": state["complete"],
            "escalated": state["escalated"],
        }