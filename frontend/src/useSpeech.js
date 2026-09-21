// useSpeech.js — wraps the browser's built-in speech APIs.
//
// STT: window.SpeechRecognition (Chrome/Edge). Streams interim results while you
//      talk (the live transcript). The full sentence is sent only when you click stop.
// TTS: window.speechSynthesis. Reads the agent's reply aloud.

import { useCallback, useEffect, useRef, useState } from "react";

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

export function useSpeech({ onFinal }) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const recRef = useRef(null);

  useEffect(() => {
    if (!Recognition) return;
    const rec = new Recognition();
    rec.lang = "en-US";
    rec.interimResults = true;   // show words as they are recognised
    rec.continuous = true;       // keep listening until stop is clicked

    let collected = "";          // everything said since start
    rec.onresult = (event) => {
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) collected += chunk + " ";
        else interimText = chunk;
      }
      setInterim((collected + interimText).trim());
    };
    rec.onend = () => {
      setListening(false);
      setInterim("");
      const text = collected.trim();
      collected = "";
      if (text) onFinal(text);   // one message per recording, not per pause
    };
    rec.onerror = () => setListening(false);

    recRef.current = rec;
    return () => rec.abort();
  }, [onFinal]);

  const start = useCallback(() => {
    if (!recRef.current || listening) return;
    window.speechSynthesis.cancel();   // don't transcribe the agent's own voice
    setInterim("");
    recRef.current.start();
    setListening(true);
  }, [listening]);

  const stop = useCallback(() => {
    recRef.current?.stop();
  }, []);

  const speak = useCallback((text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }, []);

  return { supported: Boolean(Recognition), listening, interim, start, stop, speak };
}