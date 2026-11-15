// Admin-only cost view: per user, per song, per day, and OpenRouter credits used by this app.
import { useEffect, useState } from 'react';
import { fetchCosts, type Costs as C } from './api';

const usd = (n: number) => `$${n < 0.01 ? n.toFixed(5) : n.toFixed(3)}`;

export function Costs() {
  const [d, setD] = useState<C | null>(null);
  const [err, setErr] = useState('');
  useEffect(() => { fetchCosts().then(setD).catch((e) => setErr(e instanceof Error ? e.message : 'Could not load costs')); }, []);
  if (err) return <div className="empty"><b>Costs unavailable</b>{err}</div>;
  if (!d) return <div className="empty"><b>Loading costs…</b></div>;
  const o = d.openrouter;
  const users = Object.entries(d.by_creator).sort((a, b) => b[1].create_usd - a[1].create_usd);
  const days = Object.entries(d.by_day).sort((a, b) => b[0].localeCompare(a[0]));
  return (
    <div className="costs">
      <div className="pagehead"><h1>Costs</h1><p>Estimates in USD, visible to admins and senior managers only.</p></div>
      <div className="cost-cards">
        <div><span>Songs made</span><b>{d.totals.songs}</b></div>
        <div><span>Total create cost</span><b>{usd(d.totals.create_usd)}</b></div>
        <div><span>Average per song</span><b>{usd(d.totals.avg_create_usd)}</b></div>
        <div><span>Voice characters</span><b>{d.totals.polly_chars.toLocaleString()}</b></div>
        <div><span>LLM tokens (this app)</span><b>{d.totals.llm_tokens.toLocaleString()}</b></div>
        <div><span>Storage / month</span><b>{usd(d.totals.storage_usd_month)}</b></div>
      </div>
      <h2>OpenRouter credits (shared with Kalkee)</h2>
      <div className="cost-cards">
        <div><span>Used by aRaaga</span><b>{usd(o.raaga_usd)}</b></div>
        <div><span>Tokens by aRaaga</span><b>{o.raaga_tokens.toLocaleString()}</b></div>
        <div><span>Account used (all apps)</span><b>{o.account?.total_usage != null ? usd(o.account.total_usage) : '—'}</b></div>
        <div><span>Credits remaining</span><b>{o.account?.remaining != null ? usd(o.account.remaining) : '—'}</b></div>
        <div><span>Raaga share of use</span><b>{o.raaga_share_of_usage != null ? `${(o.raaga_share_of_usage * 100).toFixed(1)}%` : '—'}</b></div>
      </div>
      {!o.akanade_connected && <p className="cost-note">No OpenRouter model calls recorded yet for this app. Songs use the signed-in person&apos;s own Kalkee login; AKANADE_TOKEN on the server is the fallback.</p>}
      {!o.account && <p className="cost-note">Account-wide credits need an OpenRouter management key (OPENROUTER_MANAGEMENT_KEY) on the server.</p>}
      <h2>Per user</h2>
      <table><thead><tr><th>User</th><th>Songs</th><th>Create cost</th><th>Voice chars</th><th>LLM tokens</th><th>Plays</th></tr></thead>
        <tbody>{users.map(([u, a]) => <tr key={u}><td>{u}</td><td>{a.songs}</td><td>{usd(a.create_usd)}</td><td>{a.polly_chars.toLocaleString()}</td><td>{a.llm_tokens.toLocaleString()}</td><td>{a.plays}</td></tr>)}</tbody></table>
      <h2>Per song</h2>
      <table><thead><tr><th>Song</th><th>User</th><th>Voice</th><th>LLM</th><th>Compute</th><th>Create total</th><th>Storage/mo</th><th>Delivery so far</th></tr></thead>
        <tbody>{d.songs.map((s) => <tr key={s.id}><td>{s.title}<small> · {s.language} · {s.duration_seconds}s</small></td><td>{s.creator}</td><td>{usd(s.polly_usd)}</td><td>{usd(s.llm_usd)}</td><td>{usd(s.compute_usd)}</td><td><b>{usd(s.create_usd)}</b></td><td>{usd(s.storage_usd_month)}</td><td>{usd(s.delivery_usd_to_date)}</td></tr>)}</tbody></table>
      <h2>Per day</h2>
      <table><thead><tr><th>Day</th><th>Songs</th><th>Create cost</th><th>LLM tokens</th></tr></thead>
        <tbody>{days.map(([k, a]) => <tr key={k}><td>{k}</td><td>{a.songs}</td><td>{usd(a.create_usd)}</td><td>{a.llm_tokens.toLocaleString()}</td></tr>)}</tbody></table>
    </div>
  );
}
