'use client';

import { useEffect, useMemo, useState } from 'react';

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

const API = process.env.NEXT_PUBLIC_MATCHLAB_API || 'http://localhost:8000';

function extractEventId(value: string) {
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) return trimmed;
  const match = trimmed.match(/(?:id:|event\/)(\d+)/i) || trimmed.match(/[?&#]id=(\d+)/i);
  if (!match) throw new Error('Could not find a SofaScore event ID in that URL.');
  return match[1];
}

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
  const [error, setError] = useState('');

  const refreshMatches = async (preferId?: string) => {
    const rows: Match[] = await fetch(`${API}/matches`).then(r => r.json());
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

  const importFromSofaScore = async () => {
    setImporting(true);
    setError('');
    try {
      const id = extractEventId(sofaUrl);
      const base = `https://api.sofascore.com/api/v1/event/${id}`;
      const [basicRes, statsRes, lineupsRes] = await Promise.all([
        fetch(base),
        fetch(`${base}/statistics`),
        fetch(`${base}/lineups`),
      ]);
      if (!basicRes.ok || !statsRes.ok || !lineupsRes.ok) {
        throw new Error('Your browser reached SofaScore, but one or more match-data requests were rejected.');
      }
      const bundle = {
        event_id: id,
        basic: await basicRes.json(),
        statistics: await statsRes.json(),
        lineups: await lineupsRes.json(),
      };
      const imported = await fetch(`${API}/matches/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bundle),
      });
      if (!imported.ok) throw new Error('MatchLab received the SofaScore data but could not save the match.');
      await refreshMatches(id);
      setMode('match');
    } catch (e: any) {
      setError(`${e.message} If this is a browser CORS restriction, we will switch the importer to the next ingestion method without changing the rest of MatchLab.`);
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

        <span className="sidebarLabel">SofaScore match</span>
        <input className="select" value={sofaUrl} onChange={e => setSofaUrl(e.target.value)} placeholder="Paste SofaScore URL or event ID" />
        <button className="importButton" onClick={importFromSofaScore} disabled={importing}>
          {importing ? 'Importing…' : 'Load Match'}
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
          MatchLab first asks your browser to retrieve the SofaScore JSON, then stores one clean match bundle in the MatchLab API. Graphics never need to scrape the same match again.
        </div>
      </aside>

      <main className="main">
        <h1 className="title">MatchLab</h1>
        <p className="sub">Match Statistics · Player Statistics · Metric Leaders</p>

        {error && <div className="status">{error}</div>}
        {data && <div className="status">Loaded · {data.match.home_name} {data.match.home_score}–{data.match.away_score} {data.match.away_name}</div>}

        <div className="tabs">
          <button className={`tab ${mode === 'match' ? 'active' : ''}`} onClick={() => setMode('match')}>Match Statistics</button>
          <button className={`tab ${mode === 'player' ? 'active' : ''}`} onClick={() => setMode('player')}>Player Statistics</button>
          <button className={`tab ${mode === 'leaders' ? 'active' : ''}`} onClick={() => setMode('leaders')}>Metric Leaders</button>
        </div>

        {!data ? <div className="card empty">Paste a SofaScore match URL on the left to import your first match.</div> : (
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
