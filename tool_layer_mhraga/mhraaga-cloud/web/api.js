// Shared fetch helper for the studio pages. Redirects to sign-in when the session is missing or expired.
export const $ = (id) => document.getElementById(id);
let token = null; try { token = localStorage.getItem("mh_token"); } catch {}
export const signedIn = () => !!token;
export async function api(path, { method = "GET", body, auth = true } = {}) {
  if (auth && !token) { location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop() + location.hash); throw new Error("Sign in first."); }
  const r = await fetch("/api" + path, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401 && auth) { try { localStorage.removeItem("mh_token"); } catch {} location.href = "login.html"; throw new Error("Sign in again."); }
  if (!r.ok) throw new Error(d.error || "Error " + r.status);
  return d;
}
export function toast(m) { const t = $("toast"); if (!t) return; t.textContent = m; t.hidden = false; clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 4000); }
export const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
