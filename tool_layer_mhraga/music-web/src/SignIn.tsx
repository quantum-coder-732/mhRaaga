// Sign in / create account, laid out like Akanade's sign-in (brand panel left, form right) in aRaaga's own colors.
import { useState, type FormEvent } from 'react';
import { signIn, signUp, setToken, type Me } from './api';
import { BRAND } from './brand';

export function SignIn({ onDone }: { onDone: (me: Me) => void }) {
  const [mode, setMode] = useState<'in' | 'up'>('in');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const up = mode === 'up';

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      const r = up ? await signUp(name.trim(), email.trim(), password) : await signIn(email.trim(), password);
      setToken(r.token);
      onDone(r.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally { setBusy(false); }
  }

  return (
    <div className="si">
      <aside className="si-brand">
        <div className="si-logo"><img src="/raaga-logo.svg" alt="" /><span>{BRAND.name}</span></div>
        <div className="si-body">
          <img className="si-mandala" src="/raaga-logo.svg" alt="" />
          <h1>Say it.<br /><span>Hear it as a raga.</span></h1>
          <p>Describe a mood, a deity or a time of day. {BRAND.name} composes a song or raga for you, planned by Algo&apos;s Pecova music agent.</p>
          <div className="si-tags"><span>Ragas &amp; taals</span><span>AI music</span></div>
        </div>
        <span className="si-fine">© 2026 AlgoAnalytics</span>
      </aside>
      <main className="si-main">
        <form className="si-form" onSubmit={(e) => void submit(e)}>
          <div className="si-head">
            <h2>{up ? `Create your ${BRAND.short} account` : `Sign in to ${BRAND.name}`}</h2>
            <p>{up ? 'It takes a few seconds.' : 'Welcome back. Your songs are waiting.'}</p>
          </div>
          {up && (
            <label className="si-field">Name
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" maxLength={60} required />
            </label>
          )}
          <label className="si-field">Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" required />
          </label>
          <label className="si-field">Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={up ? 'At least 8 characters' : 'Enter your password'}
              autoComplete={up ? 'new-password' : 'current-password'} minLength={up ? 8 : undefined} required />
          </label>
          {error && <p className="si-error" role="alert">{error}</p>}
          <button type="submit" className="go si-submit" disabled={busy || !email || !password || (up && !name.trim())}>
            {busy ? 'Please wait…' : up ? 'Create account' : 'Sign in'}
          </button>
          <p className="si-switch">
            {up ? 'Already have an account?' : 'New to ' + BRAND.short + '?'}{' '}
            <button type="button" onClick={() => { setMode(up ? 'in' : 'up'); setError(''); }}>{up ? 'Sign in' : 'Create an account'}</button>
          </p>
        </form>
        <div className="si-product">
          <img src="/algoanalytics-logo.png" alt="AlgoAnalytics" />
          <span>A Product of AlgoAnalytics PVT LTD</span>
        </div>
      </main>
    </div>
  );
}
