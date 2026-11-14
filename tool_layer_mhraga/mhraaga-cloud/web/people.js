// People: profiles with consent, voice samples (record or upload), pasted transcripts that teach the writer a speaker's manner.
import { $, api, toast, el } from "./api.js";

const PROMPTS = ["Good morning, this is my voice for the studio.", "The river carries the moon without effort.", "I will speak slowly, and let each word land.", "Patience is a kind of love that does not hurry.",
  "Today I am learning to listen before I answer.", "A small lamp is enough to cross the dark.", "Let the flute begin, and let the heart follow.", "Every ending is a quiet beginning.",
  "The morning sun touches the temple wall.", "Say what is true, and say it kindly.", "Numbers: one, two, three, four, five, six, seven.", "Where there is love, there is always room.",
  "Rain on the roof keeps a gentle rhythm.", "I carry a song that no one has heard yet.", "Hold each other's hands, hold tight and true.", "The silence between two notes is also music.",
  "Tell the story again, but softer this time.", "Wait for the answer; it will come in its own time.", "Gratitude is the shortest prayer.", "And now, we begin."];
const say = (m) => ($("p-status").textContent = m);

async function load() {
  const { people } = await api("/people"), box = $("plist"); box.replaceChildren();
  if (!people.length) box.append(el("p", { className: "muted" }, "No one yet. Add yourself first."));
  for (const p of people) box.append(card(p));
}
$("p-add").onclick = async () => {
  try { await api("/people", { method: "POST", body: { name: $("p-name").value, role: $("p-role").value, consent: $("p-consent").checked } }); $("p-name").value = ""; $("p-role").value = ""; say(""); await load(); }
  catch (e) { say(e.message); }
};
function card(p) {
  const c = el("section", { className: "card person" }), st = el("span", { className: "muted" });
  const note = el("textarea", { rows: 4, maxLength: 1500, placeholder: "Speaking style notes (the learner fills these in; edit freely)" }); note.value = p.style_notes || "";
  const tr = el("textarea", { rows: 5, maxLength: 12000, placeholder: "Paste a transcript of this person speaking (for YouTube: open the video, ⋯ → Show transcript, copy). At least a few paragraphs." });
  const links = el("textarea", { rows: 2, placeholder: "Reference links (video or playlist URLs), kept as notes only. They are not downloaded." }); links.value = (p.sources || []).join("\n");
  const run = async (fn, ok) => { try { await fn(); st.textContent = ok; await load(); } catch (e) { st.textContent = e.message; } };
  const prompt = el("div", { className: "sprompt" }, "Read aloud: " + PROMPTS[p.samples % PROMPTS.length]);
  const rec = el("button", { type: "button", className: "ghost" }, "🎙 Record a sample"), file = el("input", { type: "file", accept: "audio/*" });
  const sendBlob = async (blob, mime) => { const b64 = await new Promise((r) => { const f = new FileReader(); f.onload = () => r(f.result.split(",")[1]); f.readAsDataURL(blob); });
    await api(`/people/${p.id}/samples`, { method: "POST", body: { audio_b64: b64, mime } }); };
  rec.onclick = async () => {
    if (rec.dataset.on) { rec.mr.stop(); return; }
    try { const s = await navigator.mediaDevices.getUserMedia({ audio: true }), mr = new MediaRecorder(s), parts = []; rec.mr = mr; rec.dataset.on = 1; rec.textContent = "■ Stop (max 25 s)";
      mr.ondataavailable = (e) => parts.push(e.data); const t = setTimeout(() => mr.state === "recording" && mr.stop(), 25000);
      mr.onstop = async () => { clearTimeout(t); s.getTracks().forEach((x) => x.stop()); delete rec.dataset.on; rec.textContent = "🎙 Record a sample"; run(() => sendBlob(new Blob(parts, { type: mr.mimeType }), mr.mimeType || "audio/webm"), "Sample saved."); };
      mr.start(); } catch { st.textContent = "Microphone not available."; }
  };
  file.onchange = () => file.files[0] && run(() => sendBlob(file.files[0], file.files[0].type || "audio/mpeg"), "Sample saved.");
  const play = el("button", { type: "button", className: "ghost" }, "▶ Play samples");
  play.onclick = async () => { for (let i = 0; i < p.samples; i++) { const d = await api(`/people/${p.id}/samples/${i}`), a = new Audio(`data:${d.mime};base64,${d.audio_b64}`); await a.play().catch(() => {}); await new Promise((r) => (a.onended = a.onerror = r)); } };
  c.append(el("h2", {}, `${p.name} `, el("small", {}, p.role || "")),
    el("p", { className: "muted" }, `${p.consent ? "✔ consent given" : "✖ no consent yet (samples are blocked)"} · ${p.samples}/20 voice samples · ${p.excerpts} transcripts learned`),
    el("div", { className: "bar" }, el("i", { style: `width:${Math.min(100, (p.samples / 10) * 100)}%` })), el("small", { className: "muted" }, "10 samples is a good minimum"),
    prompt, el("div", { className: "actions" }, rec, file, play), el("h3", {}, "Speaking style"), note, el("div", { className: "actions" },
      el("button", { type: "button", className: "ghost", onclick: () => run(() => api(`/people/${p.id}`, { method: "PUT", body: { style_notes: note.value, sources: links.value.split("\n").filter(Boolean), consent: p.consent } }), "Saved.") }, "Save notes and links")),
    links, el("h3", {}, "Learn from a transcript"), tr, el("div", { className: "actions" },
      el("button", { type: "button", className: "primary", onclick: () => { st.textContent = "Learning…"; run(() => api(`/people/${p.id}/learn`, { method: "POST", body: { text: tr.value } }), "Learned. The notes above are updated."); } }, "Learn style"),
      el("button", { type: "button", className: "ghost", onclick: () => p.consent || run(() => api(`/people/${p.id}`, { method: "PUT", body: { consent: true } }), "Consent recorded.") }, p.consent ? "Consent recorded" : "I confirm consent"),
      el("button", { type: "button", className: "ghost danger", onclick: () => confirm(`Delete ${p.name} and all samples?`) && run(() => api(`/people/${p.id}`, { method: "DELETE" }), "Deleted.") }, "Delete"), st));
  return c;
}
load().catch((e) => say(e.message));
