import { useCallback, useRef, useState } from "react";
import { useSpeech } from "./useSpeech.js";

const FIELD_LABELS = {
  location: "Location",
  description: "Description",
  urgency: "Urgency",
  device: "Device / asset",
};

export default function App() {
  const sessionId = useRef(crypto.randomUUID());
  const [turns, setTurns] = useState([]);
  const [ticket, setTicket] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastText, setLastText] = useState("");
  const [voiceOn, setVoiceOn] = useState(true);

  const sendToAgent = useCallback(async (text, isRetry = false) => {
    if (!isRetry) setTurns((t) => [...t, { role: "user", text }]);
    setLastText(text);
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId.current, text }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const data = await res.json();
      setTicket(data);
      setTurns((t) => [...t, { role: "agent", text: data.reply }]);
      if (voiceOn) speech.speak(data.reply);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [voiceOn]); // eslint-disable-line react-hooks/exhaustive-deps

  const speech = useSpeech({ onFinal: sendToAgent });

  async function reset() {
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId.current }),
    });
    setTurns([]);
    setTicket(null);
    setError("");
    setLastText("");
  }

  if (!speech.supported) {
    return (
      <main className="app">
        <p className="error">
          Speech recognition isn't available in this browser. Open this page in Chrome or Edge.
        </p>
      </main>
    );
  }

  return (
    <main className="app">
      <header className="top">
        <h1>Voice ticket agent</h1>
        <div className="controls">
          <label className="toggle">
            <input type="checkbox" checked={voiceOn} onChange={(e) => setVoiceOn(e.target.checked)} />
            Read replies aloud
          </label>
          <button className="ghost" onClick={reset}>New ticket</button>
        </div>
      </header>

      <div className="panels">
        <section className="panel transcript">
          <h2>Conversation</h2>
          <div className="turns">
            {turns.length === 0 && !speech.interim && (
              <p className="hint">Click record and describe your problem</p>
            )}
            {turns.map((t, i) => (
              <p key={i} className={`turn ${t.role}`}>{t.text}</p>
            ))}
            {speech.interim && <p className="turn user interim">{speech.interim}</p>}
            {busy && <p className="turn agent thinking">…</p>}
          </div>
          {error && (
            <p className="error">
              {error}
              <button className="ghost" onClick={() => sendToAgent(lastText, true)}>Retry</button>
            </p>
          )}

          <button
            className={`talk ${speech.listening ? "on" : ""}`}
            disabled={busy || ticket?.escalated}
            onClick={speech.listening ? speech.stop : speech.start}
          >
            {speech.listening ? "Recording… click to send" : "Click to record"}
          </button>
        </section>

        <section className="panel ticket">
          <h2>Ticket</h2>
          {ticket?.escalated && (
            <p className="error">Handed off to a human agent. Partial details below.</p>
          )}
          {!ticket || !ticket.category ? (
            <p className="hint">The ticket appears here once the request type is clear.</p>
          ) : (
            <>
              <p className="category">{ticket.category_label}</p>
              <dl className="fields">
                {Object.entries(ticket.ticket).map(([key, value]) => (
                  <div key={key} className={value ? "filled" : "missing"}>
                    <dt>{FIELD_LABELS[key] || key}</dt>
                    <dd>{value || "not provided yet"}</dd>
                  </div>
                ))}
              </dl>
              <p className={`status ${ticket.complete ? "done" : ""}`}>
                {ticket.complete
                  ? "Ticket complete"
                  : `Still needed: ${ticket.missing.map((m) => FIELD_LABELS[m] || m).join(", ")}`}
              </p>
              {ticket.complete && (
                <pre className="json">
{JSON.stringify({ category: ticket.category, ...ticket.ticket, notes: ticket.notes }, null, 2)}
                </pre>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}