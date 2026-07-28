import { useEffect, useState } from 'react';
import { Clapperboard, RefreshCw, Play, Film } from 'lucide-react';
import { apiGet, apiPost } from '../services/api';
import { Link } from 'react-router-dom';

interface AnimeRun {
    id: number;
    topic?: string;
    title?: string;
    anime?: string;
    file_path?: string;
    size_mb?: number;
    status?: string;
    publish_ok?: boolean;
    published_count?: number;
    created_at?: string;
    video_id?: number;
}

export default function AnimeTheory() {
    const [topic, setTopic] = useState('');
    const [anime, setAnime] = useState('Jujutsu Kaisen');
    const [context, setContext] = useState('');
    const [longForm, setLongForm] = useState(false);
    const [publish, setPublish] = useState(true);
    const [running, setRunning] = useState(false);
    const [log, setLog] = useState<string[]>([]);
    const [runs, setRuns] = useState<AnimeRun[]>([]);
    const [loadingRuns, setLoadingRuns] = useState(true);

    const addLog = (msg: string) =>
        setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 40));

    const loadRuns = async () => {
        setLoadingRuns(true);
        try {
            const data = await apiGet<{ runs?: AnimeRun[] }>('/dashboard/anime-theory/runs', { limit: 20 });
            setRuns(data.runs || []);
        } catch (e: any) {
            addLog(`Failed to load runs: ${e.message}`);
        } finally {
            setLoadingRuns(false);
        }
    };

    useEffect(() => { loadRuns(); }, []);

    const run = async () => {
        if (!topic.trim()) return;
        setRunning(true);
        addLog(`Starting anime-theory: ${topic.trim()}`);
        try {
            const data = await apiPost('/agent/pipeline/anime-theory', {
                topic: topic.trim(),
                objective: topic.trim(),
                anime: anime.trim() || undefined,
                context: context.trim() || undefined,
                long: longForm,
                publish,
            });
            const r = data.result ?? data;
            const ok = r?.success !== false && r?.ok !== false;
            addLog(
                `${ok ? 'OK' : 'FAIL'}: file=${r?.filename ?? r?.file ?? '?'} ` +
                `size=${r?.size_mb ?? '?'}MB published=${r?.published_count ?? (r?.published ? 'yes' : 'no')} ` +
                `db_run=${r?.run_id ?? r?.db?.run_id ?? '?'}`
            );
            if (r?.error) addLog(`Error detail: ${r.error}`);
            await loadRuns();
        } catch (e: any) {
            addLog(`Error: ${e.message}`);
        } finally {
            setRunning(false);
        }
    };

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Clapperboard size={32} /> Anime Theory
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
                        Topic → script → Safebooru stills → voice → Remotion → caption → AiToEarn.
                        Finished MP4s also show in{' '}
                        <Link to="/clips?source=anime" style={{ color: 'var(--accent-primary)' }}>Clip Library</Link>.
                    </p>
                </div>
                <button className="btn-secondary" onClick={loadRuns} disabled={loadingRuns}>
                    <RefreshCw size={18} className={loadingRuns ? 'spin' : ''} /> Refresh
                </button>
            </div>

            <div className="glass" style={{ padding: 24, marginBottom: 24 }}>
                <div className="form-group">
                    <label>Topic / hook</label>
                    <input
                        className="form-input"
                        value={topic}
                        onChange={e => setTopic(e.target.value)}
                        placeholder="e.g. How Yuta DESTROYED the Sendai Colony"
                        disabled={running}
                    />
                </div>
                <div className="form-group">
                    <label>Anime series</label>
                    <input
                        className="form-input"
                        value={anime}
                        onChange={e => setAnime(e.target.value)}
                        placeholder="Jujutsu Kaisen"
                        disabled={running}
                    />
                </div>
                <div className="form-group">
                    <label>Extra context (optional)</label>
                    <textarea
                        className="form-input"
                        value={context}
                        onChange={e => setContext(e.target.value)}
                        rows={3}
                        placeholder="Fight details, spoilers OK, characters to emphasize…"
                        disabled={running}
                        style={{ resize: 'vertical' }}
                    />
                </div>
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                        <input type="checkbox" checked={longForm} onChange={e => setLongForm(e.target.checked)} disabled={running} />
                        Long-form (~3 min)
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                        <input type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} disabled={running} />
                        Auto-publish (caption + thumbnail → TikTok/IG/FB)
                    </label>
                </div>
                <button
                    className="btn-primary"
                    disabled={running || !topic.trim()}
                    onClick={run}
                >
                    {running ? <RefreshCw size={16} className="spin" /> : <Play size={16} />}
                    {running ? 'Generating…' : 'Create Anime Theory Video'}
                </button>
            </div>

            {log.length > 0 && (
                <div className="glass" style={{ padding: 16, marginBottom: 24, fontFamily: 'monospace', fontSize: 13 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span style={{ fontWeight: 600 }}>Run Log</span>
                        <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => setLog([])}>Clear</button>
                    </div>
                    <div style={{ maxHeight: 180, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {log.map((l, i) => (
                            <div key={i} style={{ color: l.includes('Error') || l.includes('FAIL') ? 'var(--danger)' : l.includes('OK') ? 'var(--success)' : 'var(--text-secondary)' }}>
                                {l}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="glass table-container">
                <h3 style={{ padding: 24, borderBottom: '1px solid var(--border-color)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Film size={18} /> Recent Anime Theory Runs ({runs.length})
                </h3>
                {runs.length === 0 ? (
                    <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-secondary)' }}>
                        No runs yet. Create your first video above.
                    </div>
                ) : (
                    <table className="custom-table">
                        <thead>
                            <tr>
                                <th>Title</th>
                                <th>Anime</th>
                                <th>Size</th>
                                <th>Status</th>
                                <th>Published</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                            {runs.map(r => (
                                <tr key={r.id}>
                                    <td>{r.title || r.topic || `#${r.id}`}</td>
                                    <td>{r.anime || '—'}</td>
                                    <td>{r.size_mb != null ? `${Number(r.size_mb).toFixed(1)} MB` : '—'}</td>
                                    <td><span className={`badge ${r.status}`}>{r.status}</span></td>
                                    <td>{r.publish_ok ? `yes (${r.published_count ?? 0})` : '—'}</td>
                                    <td>{r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </>
    );
}
