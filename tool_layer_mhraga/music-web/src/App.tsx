// aRaaga: discover / create / library with a persistent player. A standalone app: it only talks to the Raaga service,
// which asks Algo's Pecova music agent (on the Akanade AI platform) to plan each song and then renders it.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Costs as CostsPage } from './Costs';
import { SIGNED_OUT, audioSrc, countPlay, fetchMe, generate, getJob, getToken, deleteTrack, listTracks, setToken, toggleLike, type Me, type Track } from './api';
import { SignIn } from './SignIn';
import { BRAND } from './brand';

type View = 'discover' | 'create' | 'mine' | 'liked' | 'costs';
const GENRES = ['raga', 'devotional', 'ghazal', 'classical', 'folk', 'lofi', 'pop', 'ambient', 'cinematic'];
const EXAMPLES = [
  'A calm Yaman raga with flute and tabla',
  'Dawn Bhairav raga, meditative, sitar and tanpura',
  'Joyful Bhupali raga, harmonium and tabla',
  'Lofi study beat, rainy night, soft piano',
];
const NAV_ICON: Record<View, string> = {
  discover: 'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  create: 'M12 5v14M5 12h14',
  mine: 'M9 18V5l11-2v13M9 18a3 3 0 11-6 0 3 3 0 016 0zm11-2a3 3 0 11-6 0 3 3 0 016 0z',
  costs: 'M4 20V10m6 10V4m6 16v-7m4 7H2',
  liked: 'M20.8 5.6a5 5 0 00-7.1 0L12 7.3l-1.7-1.7a5 5 0 00-7.1 7.1l1.7 1.7L12 21.5l7.1-7.1 1.7-1.7a5 5 0 000-7.1z',
};

const PlayIcon = () => <svg className="i" viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z" /></svg>;
const PauseIcon = () => <svg className="i" viewBox="0 0 24 24"><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></svg>;
const PrevIcon = () => <svg className="i" viewBox="0 0 24 24"><path d="M6 5h2v14H6zM20 5v14L9 12z" /></svg>;
const NextIcon = () => <svg className="i" viewBox="0 0 24 24"><path d="M16 5h2v14h-2zM4 5l11 7L4 19z" /></svg>;
const Heart = ({ on }: { on: boolean }) => (
  <svg viewBox="0 0 24 24" fill={on ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8"><path d={NAV_ICON.liked} /></svg>
);

function hash(s: string): number {
  let h = 2166136261;
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const tags = (t: Track) => [t.raga || t.genre, t.mood].filter(Boolean).join(' · ');

/** Generative cover: gradient + rings/rays seeded by the title; ragas get a mandala, others soft waves. */
function Cover({ t, children }: { t: Track; children?: ReactNode }) {
  const h = hash(t.title + t.raga);
  const a = h % 360, b = (a + 50 + ((h >> 8) % 90)) % 360;
  const id = `g${h}`;
  const rays = 12 + (h % 12);
  return (
    <div className="cover">
      <svg className="art" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" aria-hidden>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={`hsl(${a},75%,52%)`} /><stop offset="1" stopColor={`hsl(${b},70%,22%)`} />
          </linearGradient>
        </defs>
        <rect width="100" height="100" fill={`url(#${id})`} />
        {t.raga ? (
          <g stroke="#fff" fill="none" opacity=".5" transform="translate(50 46)">
            {[10, 20, 30, 40].map((r) => <circle key={r} r={r} strokeWidth=".5" />)}
            {Array.from({ length: rays }, (_, i) => <line key={i} x1="10" y1="0" x2="40" y2="0" strokeWidth=".35" transform={`rotate(${(360 / rays) * i})`} />)}
            <circle r="4" fill="#fff" stroke="none" opacity=".8" />
          </g>
        ) : (
          <g fill="none" stroke="#fff" opacity=".4">
            {[0, 1, 2, 3, 4].map((i) => <path key={i} strokeWidth=".6" d={`M0 ${30 + i * 9} Q 25 ${18 + i * 9 + (h % 12)} 50 ${30 + i * 9} T 100 ${30 + i * 9}`} />)}
          </g>
        )}
      </svg>
      {children}
    </div>
  );
}

interface Handlers { current: Track | null; playing: boolean; play: (t: Track, list: Track[]) => void; like: (t: Track) => void; remove: (t: Track) => void }

function Card({ t, list, h }: { t: Track; list: Track[]; h: Handlers }) {
  const active = h.current?.id === t.id;
  return (
    <div className={`card${active ? ' on' : ''}`} onClick={() => h.play(t, list)}>
      <Cover t={t}>
        {active && <span className={`eq${h.playing ? '' : ' off'}`}><i /><i /><i /></span>}
        <span className="badge">{t.raga || t.genre}</span>
        <button type="button" className="cplay" aria-label={active && h.playing ? 'Pause' : 'Play'}>{active && h.playing ? <PauseIcon /> : <PlayIcon />}</button>
      </Cover>
      <div className="meta">
        <div className="title">{t.title}</div>
        <div className="sub"><span>{t.mood}</span></div>
        <div className="sub">
          <span>{fmt(t.duration_seconds)} · {t.plays} plays</span>
          <button type="button" className={`like${t.liked ? ' on' : ''}`} aria-label="Like" onClick={(e) => { e.stopPropagation(); h.like(t); }}><Heart on={t.liked} />{t.likes}</button>
        </div>
        {t.can_delete && <div className="sub"><button type="button" className="del" aria-label="Delete song" onClick={(e) => { e.stopPropagation(); h.remove(t); }}>Delete</button></div>}
      </div>
    </div>
  );
}

function Row({ title, tracks, h }: { title: string; tracks: Track[]; h: Handlers }) {
  if (!tracks.length) return null;
  return (
    <section className="sec">
      <h2>{title}</h2>
      <div className="rowscroll">{tracks.map((t) => <Card key={t.id} t={t} list={tracks} h={h} />)}</div>
    </section>
  );
}

function Lyrics({ text }: { text: string }) {
  return (
    <div className="lyrics">
      {text.split('\n').map((l, i) => (/^\[.*\]$/.test(l.trim()) ? <em key={i}>{l.trim().slice(1, -1)}</em> : <div key={i}>{l || ' '}</div>))}
    </div>
  );
}

function Details({ t, open, onClose }: { t: Track | null; open: boolean; onClose: () => void }) {
  return (
    <aside className={`np${open && t ? ' open' : ''}`} aria-hidden={!open}>
      <button type="button" className="xbtn" onClick={onClose} aria-label="Close">✕</button>
      {t && (
        <>
          <Cover t={t} />
          <h2>{t.title}</h2>
          <p className="hint" style={{ margin: '4px 0 0' }}>{t.prompt}</p>
          <div className="facts">
            <div>Raga<b>{t.raga || '–'}</b></div><div>Taal<b>{t.raga ? t.taal : '–'}</b></div>
            <div>Tempo<b>{t.tempo_bpm} bpm</b></div>
            <div style={{ gridColumn: '1 / -1' }}>Instruments<b>{t.instruments.join(', ')}</b></div>
          </div>
          {t.lyrics ? <Lyrics text={t.lyrics} /> : <p className="hint">Instrumental: no lyrics.</p>}
          <p className="hint" style={{ marginTop: 12 }}>Planned by {t.brief_source === 'akanade' ? 'the Pecova music agent' : 'the offline fallback'}.</p>
        </>
      )}
    </aside>
  );
}

function Create({ initial, onDone }: { initial: string; onDone: (t: Track) => void }) {
  const [prompt, setPrompt] = useState(initial);
  const [mode, setMode] = useState<'simple' | 'custom'>('simple');
  const [lyrics, setLyrics] = useState('');
  const [title, setTitle] = useState('');
  const [instrumental, setInstrumental] = useState(false);
  const [duration, setDuration] = useState(60);
  const [isPublic, setIsPublic] = useState(true);
  const [language, setLanguage] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(''); setBusy(true); setStatus('Waiting in the queue…');
    try {
      const { job_id } = await generate({
        prompt, lyrics: mode === 'custom' ? lyrics : '', title: mode === 'custom' ? title : '',
        instrumental, duration_seconds: duration, public: isPublic, language,
      });
      for (;;) {
        await new Promise((r) => setTimeout(r, 1200));
        const job = await getJob(job_id);
        setStatus(job.status === 'PROCESSING' ? 'Composing the raga and rendering the audio…' : 'Waiting in the queue…');
        if (job.status === 'FAILED') throw new Error(job.error || 'Generation failed');
        if (job.status === 'COMPLETED' && job.track) { onDone(job.track); return; }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong');
    } finally { setBusy(false); }
  }

  if (busy) {
    return (
      <div className="make">
        <div className="bigeq">{[0, 1, 2, 3, 4, 5, 6].map((i) => <i key={i} style={{ animationDelay: `${i * 0.13}s` }} />)}</div>
        <h2>Creating your song</h2>
        <p className="hint">{status}</p>
        <p className="hint">“{prompt}”</p>
      </div>
    );
  }
  return (
    <div className="create">
      <div className="form">
        <div className="pagehead"><h1>Create</h1></div>
        <div className="seg">
          <button type="button" className={mode === 'simple' ? 'on' : ''} onClick={() => setMode('simple')}>Simple</button>
          <button type="button" className={mode === 'custom' ? 'on' : ''} onClick={() => setMode('custom')}>Custom</button>
        </div>
        <label className="field">Describe your song or raga
          <textarea rows={4} maxLength={1000} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="e.g. a calm Yaman raga with flute and tabla" />
        </label>
        <div className="chips">{EXAMPLES.map((x) => <button type="button" key={x} className="chip" onClick={() => setPrompt(x)}>{x}</button>)}</div>
        {mode === 'custom' && (
          <>
            <label className="field">Lyrics (leave empty to let the AI write them)
              <textarea rows={6} maxLength={3000} value={lyrics} disabled={instrumental} onChange={(e) => setLyrics(e.target.value)} placeholder={'[Mukhda]\nYour own words…'} />
            </label>
            <label className="field">Title
              <input type="text" maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Auto" />
            </label>
          </>
        )}
        <label className="field">Language of the vocals
          <select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={instrumental}>
            <option value="">Auto (from your description)</option>
            <option value="english">English</option><option value="hindi">Hindi</option>
            <option value="marathi">Marathi</option><option value="sanskrit">Sanskrit</option>
          </select>
        </label>
        <div className="opts">
          <label>Length {duration}s <input type="range" min={20} max={180} step={10} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></label>
          <label><input type="checkbox" checked={instrumental} onChange={(e) => setInstrumental(e.target.checked)} /> Instrumental</label>
          <label><input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> Public</label>
        </div>
        {error && <div className="err">{error}</div>}
        <div><button type="button" className="go" disabled={prompt.trim().length < 3} onClick={() => void submit()}>Create song</button></div>
      </div>
      <div className="side">
        <h3>Tips for better songs</h3>
        <ul>
          <li><b>Name a raga</b> (Yaman, Bhairav, Malkauns, Bhupali…) or give a time of day and mood.</li>
          <li><b>Pick a language</b> for the vocals: English, Hindi, Marathi or Sanskrit.</li>
          <li><b>Name instruments</b>: flute, sitar, harmonium, tabla, tanpura.</li>
          <li><b>Genres</b> work too: devotional, ghazal, lofi, cinematic.</li>
        </ul>
        <p className="hint" style={{ marginTop: 14 }}>Audio comes from an offline raga synthesizer: it plays the raga and taal but does not sing the lyrics.</p>
      </div>
    </div>
  );
}

/** Gate: shows the sign-in page until there is a valid session, then the studio. */
export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  useEffect(() => {
    if (getToken()) fetchMe().then(setMe).catch(() => setToken('')).finally(() => setChecking(false));
    const out = () => setMe(null);
    window.addEventListener(SIGNED_OUT, out);
    return () => window.removeEventListener(SIGNED_OUT, out);
  }, []);
  if (checking) return null;
  if (!me) return <SignIn onDone={setMe} />;
  return <Studio me={me} onSignOut={() => { setToken(''); setMe(null); }} />;
}

function Studio({ me, onSignOut }: { me: Me; onSignOut: () => void }) {
  const [view, setView] = useState<View>('discover');
  const [sort, setSort] = useState<'trending' | 'new' | 'top'>('trending');
  const [genre, setGenre] = useState('');
  const [q, setQ] = useState('');
  const [trending, setTrending] = useState<Track[]>([]);
  const [fresh, setFresh] = useState<Track[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [current, setCurrent] = useState<Track | null>(null);
  const [queue, setQueue] = useState<Track[]>([]);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [vol, setVol] = useState(0.9);
  const [panel, setPanel] = useState(false);
  const [seed, setSeed] = useState('');
  const [heroText, setHeroText] = useState('');
  const audio = useRef<HTMLAudioElement>(null);

  const browsing = view === 'discover' && !genre && !q.trim();

  const load = useCallback(async () => {
    if (view === 'create' || view === 'costs') return;
    setLoading(true);
    try {
      if (browsing) {
        const [a, b] = await Promise.all([listTracks({ sort: 'trending' }), listTracks({ sort: 'new' })]);
        setTrending(a); setFresh(b);
      } else {
        const p: Record<string, string> = { sort: view === 'discover' ? sort : 'new' };
        if (view === 'discover' && genre) p.genre = genre;
        if (view === 'discover' && q.trim()) p.q = q.trim();
        if (view === 'mine') p.mine = 'true';
        if (view === 'liked') p.liked = 'true';
        setTracks(await listTracks(p));
      }
      setError('');
    } catch (e) {
      setError(e instanceof Error ? `${e.message}. Is the aRaaga service running on port 9100?` : 'Could not load songs');
    } finally { setLoading(false); }
  }, [view, sort, genre, q, browsing]);
  useEffect(() => { const t = setTimeout(() => void load(), q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);
  useEffect(() => { if (audio.current) audio.current.volume = vol; }, [vol]);

  const patch = (t: Track) => {
    const up = (all: Track[]) => all.map((x) => (x.id === t.id ? t : x));
    setTracks(up); setTrending(up); setFresh(up); setQueue(up);
    setCurrent((c) => (c && c.id === t.id ? t : c));
  };
  function play(t: Track, list: Track[] = [t]) {
    const el = audio.current;
    if (!el) return;
    if (current?.id === t.id) { if (el.paused) void el.play(); else el.pause(); return; }
    setCurrent(t); setQueue(list); setPos(0);
    el.src = audioSrc(t);
    void el.play().then(() => countPlay(t.id).then(patch).catch(() => undefined)).catch(() => setPlaying(false));
  }
  const step = (d: number) => {
    if (!current || queue.length < 2) return;
    const i = queue.findIndex((x) => x.id === current.id);
    play(queue[(i + d + queue.length) % queue.length], queue);
  };
  const remove = (t: Track) => {
    if (!window.confirm(`Delete "${t.title}"? This cannot be undone.`)) return;
    void deleteTrack(t.id).then(() => {
      const keep = (all: Track[]) => all.filter((x) => x.id !== t.id);
      setTracks(keep); setTrending(keep); setFresh(keep); setQueue(keep);
      if (current?.id === t.id) { audio.current?.pause(); setCurrent(null); }
    }).catch((e: Error) => window.alert(e.message));
  };
  const like = (t: Track) => void toggleLike(t.id).then(patch).catch(() => undefined);
  const dur = current?.duration_seconds ?? 0;
  const peaks = current?.peaks ?? [];
  const h: Handlers = { current, playing, play, like, remove };
  const ragas = useMemo(() => trending.filter((t) => t.raga), [trending]);
  const goCreate = (text: string) => { setSeed(text); setView('create'); };
  const nav: [View, string][] = [['discover', 'Discover'], ['create', 'Create'], ['mine', 'Library'], ['liked', 'Liked'], ...(me.admin ? [['costs', 'Costs'] as [View, string]] : [])];

  return (
    <div className="app">
      <nav className="nav">
        <div className="brand"><img src="/raaga-logo.svg" alt="" /><b>{BRAND.name}</b></div>
        <p className="tagline">{BRAND.tagline}</p>
        {nav.map(([v, label]) => (
          <button type="button" key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>
            <svg viewBox="0 0 24 24"><path d={NAV_ICON[v]} /></svg>{label}
          </button>
        ))}
        <div className="navfoot">
          <div className="who"><span className="av">{me.name.slice(0, 1).toUpperCase()}</span><div><b>{me.name}</b><button type="button" onClick={onSignOut}>Sign out</button></div></div>
          {BRAND.poweredBy}
        </div>
      </nav>

      <main className="main">
        <div className="mobilebrand"><img src="/raaga-logo.svg" alt="" /><b>{BRAND.name}</b></div>
        {view === 'costs' ? (
          <CostsPage />
        ) : view === 'create' ? (
          <Create key={seed} initial={seed} onDone={(t) => { setView('mine'); play(t); setPanel(true); }} />
        ) : (
          <>
            {view === 'discover' && browsing && (
              <div className="hero">
                <h1>What do you want to hear today?</h1>
                <p>Describe a song, a raga or a mood. We compose it for you.</p>
                <form className="ask" onSubmit={(e) => { e.preventDefault(); if (heroText.trim().length >= 3) goCreate(heroText.trim()); }}>
                  <input value={heroText} onChange={(e) => setHeroText(e.target.value)} placeholder="A calm Yaman raga with flute…" />
                  <button type="submit" className="go" disabled={heroText.trim().length < 3}>Create</button>
                </form>
                <div className="chips">{EXAMPLES.slice(0, 3).map((x) => <button type="button" key={x} className="chip" onClick={() => goCreate(x)}>{x}</button>)}</div>
              </div>
            )}
            {view !== 'discover' && <div className="pagehead"><h1>{view === 'mine' ? 'Your library' : 'Liked songs'}</h1></div>}
            {view === 'discover' && (
              <>
                <input className="search" placeholder="Search songs, ragas, moods" value={q} onChange={(e) => setQ(e.target.value)} />
                <div className="chips" style={{ marginBottom: 22 }}>
                  {!browsing && (['trending', 'new', 'top'] as const).map((s) => (
                    <button type="button" key={s} className={`chip${sort === s ? ' on' : ''}`} onClick={() => setSort(s)}>{s[0].toUpperCase() + s.slice(1)}</button>
                  ))}
                  {GENRES.map((g) => <button type="button" key={g} className={`chip${genre === g ? ' on' : ''}`} onClick={() => setGenre(genre === g ? '' : g)}>{g}</button>)}
                </div>
              </>
            )}
            {error && <div className="err">{error}</div>}
            {loading && !error && <div className="grid">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="skel" />)}</div>}
            {!loading && !error && browsing && (
              <>
                <Row title="Trending now" tracks={trending.slice(0, 12)} h={h} />
                <Row title="New releases" tracks={fresh.slice(0, 12)} h={h} />
                <Row title="Ragas" tracks={ragas.slice(0, 12)} h={h} />
                {!trending.length && <div className="empty"><b>No songs yet</b>Be the first: describe one above.</div>}
              </>
            )}
            {!loading && !error && !browsing && (
              tracks.length ? <div className="grid">{tracks.map((t) => <Card key={t.id} t={t} list={tracks} h={h} />)}</div>
                : <div className="empty"><b>{view === 'liked' ? 'No liked songs yet' : view === 'mine' ? 'Your library is empty' : 'No matches'}</b>
                  {view === 'mine' ? 'Songs you create show up here.' : view === 'liked' ? 'Tap the heart on a song you love.' : 'Try another search or genre.'}</div>
            )}
          </>
        )}
      </main>

      <Details t={current} open={panel} onClose={() => setPanel(false)} />

      <footer className="bar">
        {current ? (
          <>
            <div className="now" onClick={() => setPanel((p) => !p)} title="Lyrics and details">
              <Cover t={current} />
              <div><div className="title">{current.title}</div><div className="sub"><span>{tags(current)}</span></div></div>
            </div>
            <div className="ctls">
              <button type="button" className="ctl prevnext" aria-label="Previous" onClick={() => step(-1)}><PrevIcon /></button>
              <button type="button" className="ctl big" aria-label={playing ? 'Pause' : 'Play'} onClick={() => play(current)}>{playing ? <PauseIcon /> : <PlayIcon />}</button>
              <button type="button" className="ctl prevnext" aria-label="Next" onClick={() => step(1)}><NextIcon /></button>
            </div>
            <div className="seek">
              <span className="time">{fmt(pos)}</span>
              <div className="wave" onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                if (audio.current && dur) audio.current.currentTime = ((e.clientX - r.left) / r.width) * dur;
              }}>
                {peaks.map((p, i) => <i key={i} className={i / peaks.length < pos / (dur || 1) ? 'done' : ''} style={{ height: `${Math.max(10, p * 100)}%` }} />)}
              </div>
              <span className="time">{fmt(dur)}</span>
            </div>
            <div className="vol">
              <button type="button" className={`like${current.liked ? ' on' : ''}`} aria-label="Like" onClick={() => like(current)}><Heart on={current.liked} /></button>
              <input type="range" min={0} max={1} step={0.05} value={vol} onChange={(e) => setVol(Number(e.target.value))} aria-label="Volume" />
            </div>
          </>
        ) : <div className="idle">Pick a song to start listening</div>}
        <audio ref={audio} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setPlaying(false); step(1); }}
          onTimeUpdate={(e) => setPos(e.currentTarget.currentTime)} />
      </footer>
    </div>
  );
}
