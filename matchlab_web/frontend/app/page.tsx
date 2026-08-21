'use client';

import { ChangeEvent, useEffect, useMemo, useState } from 'react';

type Match = {
  event_id: string;
  home_name: string;
  away_name: string;
  home_score: string;
  away_score: string;
  tournament: string;
  date_text: string;
};

type Player = { id: string | number; name: string; team: string; opponent: string; side: string };
type Metric = { key: string; label: string };
type Leader = { name: string; team: string; display: string; value?: number };
type MatchPayload = { match: Match; players: Player[]; metrics: Metric[]; statistics: any[] };
type MatchBundle = {
  event_id: string;
  basic: Record<string, any>;
  statistics: Record<string, any>;
  lineups: Record<string, any>;
};

const API = process.env.NEXT_PUBLIC_MATCHLAB_API || 'http://localhost:8000';

export default function Home() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [eventId, setEventId] = useState('');
  const [data, setData] = useState<MatchPayload | null>(null);
  const [mode, setMode] = useState<'match' | 'player' | 'leaders'>('match');
  const [playerId, setPlayerId] = useState('');
  const [scope, setScope] = useState('all');
  const [metricKey, setMetricKey] = useState('');
  const [leaders, setLeaders] = useState<Leader[]>([]);
  const [sofaUrl, setSofaUrl] = useState('https://www.sofascore.com/football/match/arsenal-west-ham-united/MR#id:14023942,tab:lineups');
  const [importing, setImporting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refreshMatches = async (preferId?: string) => {
    const response = await fetch(`${API}/matches`);
    if (!response.ok) throw new Error('Could not reach the MatchLab API.');
    const rows: Match[] = await response.json();
    setMatches(rows);
    if (preferId) setEventId(preferId);
    else if (!eventId && rows[0]) setEventId(rows[0].event_id);
  };

  useEffect(() => {
    refreshMatches().catch(() => setError('Could not reach the MatchLab API.'));
  }, []);

  useEffect(() => {
    if (!eventId) return;
    setError('');
    fetch(`${API}/matches/${eventId}`).then(async r => {
      if (!r.ok) throw new Error((await r.json()).detail || 'Match unavailable');
      return r.json();
    }).then((payload: MatchPayload) => {
      setData(payload);
      setPlayerId(String(payload.players[0]?.id || ''));
      setMetricKey(payload.metrics[0]?.key || '');
    }).catch(e => setError(e.message));
  }, [eventId]);

  useEffect(() => {
    if (mode !== 'leaders' || !eventId || !metricKey) return;
    fetch(`${API}/matches/${eventId}/leaders/${metricKey}?scope=${scope}`)
      .then(r => r.json()).then(x => setLeaders(x.rows || [])).catch(() => setLeaders([]));
  }, [mode, eventId, metricKey, scope]);

  const importJsonFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setUploading(true);
    setError('');
    setNotice('');
    try {
      const text = await file.text();
      const bundle = JSON.parse(text) as MatchBundle;
      if (!bundle?.event_id || !bundle?.basic || !bundle?.statistics || !bundle?.lineups) {
        throw new Error('That file is not a MatchLab match JSON. It must contain event_id, basic, statistics and lineups.');
      }

      const response = await fetch(`${API}/matches/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bundle),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || 'MatchLab could not upload this JSON file.');

      await refreshMatches(String(result.event_id));
      setMode('match');
      setNotice(`Uploaded ${file.name}`);
    } catch (e: any) {
      setError(e.message || 'JSON upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const importFromSofaScore = async () => {
    setImporting(true);
    setError('');
    setNotice('');
    try {
      const imported = await fetch(`${API}/matches/import-sofascore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: sofaUrl }),
      });
      const result = await imported.json().catch(() => ({}));
      if (!imported.ok) {
        throw new Error(result.detail || 'Hosted SofaScore import is unavailable. Use Upload Match JSON instead.');
      }
      await refreshMatches(String(result.event_id));
      setMode('match');
    } catch (e: any) {
      setError(e.message || 'Hosted import failed. Use Upload Match JSON instead.');
    } finally {
      setImporting(false);
    }
  };

  const selectedPlayer = useMemo(
    () => data?.players.find(p => String(p.id) === playerId),
    [data, playerId]
  );

  let imageUrl = '';
  if (eventId && mode === 'match') imageUrl = `${API}/matches/${eventId}/graphics/match.png`;
  if (eventId && mode === 'player' && playerId) imageUrl = `${API}/matches/${eventId}/graphics/player/${playerId}.png`;
  if (eventId && mode === 'leaders' && metricKey) imageUrl = `${API}/matches/${eventId}/graphics/leaders/${metricKey}.png?scope=${scope}`;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">MatchLab V2</div>
        <div className="muted">Football performance graphics</div>

        <span className="sidebarLabel">Upload match data</span>
        <label className="importButton" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: uploading ? 'wait' : 'pointer'}}>
          {uploading ? 'Uploading…' : 'Upload Match JSON'}
          <input type="file" accept="application/json,.json" onChange={importJsonFile} disabled={uploading} style={{display: 'none'}} />
        </label>
        <div className="muted" style={{fontSize: 12, lineHeight: 1.45, marginTop: 8}}>
          Recommended: create the JSON with the local MatchLab exporter on your Mac, then upload it here.
        </div>

        <span className="sidebarLabel">Hosted SofaScore import · fallback</span>
        <input className="select" value={sofaUrl} onChange={e => setSofaUrl(e.target.value)} placeholder="Paste SofaScore URL or event ID" />
        <button className="importButton" onClick={importFromSofaScore} disabled={importing}>
          {importing ? 'Trying…' : 'Try Hosted Import'}
        </button>

        <span className="sidebarLabel">Imported matches</span>
        <select className="select" value={eventId} onChange={e => setEventId(e.target.value)}>
          {!matches.length && <option value="">No imported matches</option>}
          {matches.map(m => (
            <option key={m.event_id} value={m.event_id}>
              {m.home_name} {m.home_score}–{m.away_score} {m.away_name}
            </option>
          ))}
        </select>

        <span className="sidebarLabel">How this works</span>
        <div className="muted" style={{fontSize: 14, lineHeight: 1.55}}>
          Scrape the match locally on your Mac, upload the generated MatchLab JSON here once, then use the stored match for graphics, player statistics and metric leaders without scraping it again.
        </div>
      </aside>

      <main className="main">
        <h1 className="title">MatchLab</h1>
        <p className="sub">Match Statistics · Player Statistics · Metric Leaders</p>

        {error && <div className="status">{error}</div>}
        {notice && <div className="status">{notice}</div>}
        {data && <div className="status">Loaded · {data.match.home_name} {data.match.home_score}–{data.match.away_score} {data.match.away_name}</div>}

        <div className="tabs">
          <button className={`tab ${mode === 'match' ? 'active' : ''}`} onClick={() => setMode('match')}>Match Statistics</button>
          <button className={`tab ${mode === 'player' ? 'active' : ''}`} onClick={() => setMode('player')}>Player Statistics</button>
          <button className={`tab ${mode === 'leaders' ? 'active' : ''}`} onClick={() => setMode('leaders')}>Metric Leaders</button>
        </div>

        {!data ? <div className="card empty">Upload a MatchLab JSON file on the left to import your first match.</div> : (
          <div className="grid">
            <section className="card">
              {imageUrl && <img className="preview" src={imageUrl} alt="MatchLab 1080 by 1350 graphic preview" />}
            </section>

            <aside className="card controls">
              {mode === 'match' && <>
                <h2>Match Statistics</h2>
                <div className="muted">Full-time performance numbers for both teams.</div>
              </>}

              {mode === 'player' && <>
                <h2>Player Statistics</h2>
                <div className="control">
                  <label>Player</label>
                  <select className="select" value={playerId} onChange={e => setPlayerId(e.target.value)}>
                    {data.players.map(p => <option key={String(p.id)} value={String(p.id)}>{p.name} · {p.team}</option>)}
                  </select>
                </div>
                {selectedPlayer && <div className="muted">Performance Numbers v {selectedPlayer.opponent}</div>}
              </>}

              {mode === 'leaders' && <>
                <h2>Metric Leaders</h2>
                <div className="control">
                  <label>Players</label>
                  <select className="select" value={scope} onChange={e => setScope(e.target.value)}>
                    <option value="all">All Players</option>
                    <option value="home">Team A · {data.match.home_name}</option>
                    <option value="away">Team B · {data.match.away_name}</option>
                  </select>
                </div>
                <div className="control">
                  <label>Metric</label>
                  <select className="select" value={metricKey} onChange={e => setMetricKey(e.target.value)}>
                    {data.metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                  </select>
                </div>
                <table className="table">
                  <thead><tr><th>#</th><th>Player</th><th>Team</th><th>Value</th></tr></thead>
                  <tbody>
                    {leaders.slice(0, 5).map((row, i) => <tr key={`${row.name}-${i}`}>
                      <td className={i === 0 ? 'rank1' : i === 1 ? 'rank2' : i === 2 ? 'rank3' : ''}>{i + 1}</td>
                      <td>{row.name}</td><td>{row.team}</td><td>{row.display}</td>
                    </tr>)}
                  </tbody>
                </table>
              </>}

              {imageUrl && <a className="download" href={imageUrl} download>Download 1080 × 1350 PNG</a>}
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
