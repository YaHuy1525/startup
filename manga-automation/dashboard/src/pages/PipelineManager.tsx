import { useEffect, useState } from 'react';
import { Send, RefreshCw, Play, DollarSign, Flame, Search, Cpu, Clapperboard } from 'lucide-react';
import { apiGet, apiPost } from '../services/api';

interface WorkflowRow {
    id: number;
    workflow_name: string;
    status: string;
    started_at?: string;
    completed_at?: string;
    duration_ms?: number;
}

const PIPELINES = [
    { name: 'discover-publish', label: 'Discover & Publish', icon: <Search size={16} />, needsObjective: true },
    { name: 'anime-theory', label: 'Anime Theory', icon: <Clapperboard size={16} />, needsObjective: true, needsAnime: true },
    { name: 'finance', label: 'Finance Video', icon: <DollarSign size={16} />, needsObjective: false },
    { name: 'viral', label: 'Viral Video', icon: <Flame size={16} />, needsObjective: false },
    { name: 'full-ops', label: 'Full Ops', icon: <Cpu size={16} />, needsObjective: false },
];

export default function PipelineManager() {
    const [objective, setObjective] = useState('');
    const [anime, setAnime] = useState('');
    const [running, setRunning] = useState<string | null>(null);
    const [log, setLog] = useState<string[]>([]);
    const [workflows, setWorkflows] = useState<WorkflowRow[]>([]);
    const [loading, setLoading] = useState(true);

    const addLog = (msg: string) =>
        setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 60));

    const loadWorkflows = async () => {
        setLoading(true);
        try {
            const data = await apiGet<{ executions?: WorkflowRow[]; workflows?: WorkflowRow[] }>('/api/workflows', { limit: 20 });
            setWorkflows(data.executions || data.workflows || []);
        } catch (e: any) {
            addLog(`Failed to load workflows: ${e.message}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadWorkflows(); }, []);

    const run = async (name: string, needsObjective: boolean) => {
        setRunning(name);
        addLog(`Running ${name}…`);
        try {
            const body: any = {};
            if (needsObjective) {
                if (name === 'anime-theory') {
                    body.topic = objective;
                    body.objective = objective;
                    if (anime.trim()) body.anime = anime.trim();
                    body.publish = true;
                } else {
                    body.objective = objective;
                }
            }
            const data = await apiPost(`/agent/pipeline/${name}`, body);
            const r = data.result ?? data;
            const ok = r?.success !== false && r?.ok !== false;
            addLog(
                `${ok ? 'OK' : 'FAIL'} ${name}: ` +
                `file=${r?.filename ?? r?.file ?? '?'} ` +
                `published=${r?.published_count ?? r?.result?.published_count ?? (r?.published ? 'yes' : '?')} ` +
                `failed=${r?.failed_count ?? r?.result?.failed_count ?? '?'}`
            );
            await loadWorkflows();
        } catch (e: any) {
            addLog(`Error ${name}: ${e.message}`);
        } finally {
            setRunning(null);
        }
    };

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Send size={32} /> Pipelines
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
                        Run the agent's end-to-end pipelines and review recent runs.
                    </p>
                </div>
                <button className="btn-secondary" onClick={loadWorkflows}>
                    <RefreshCw size={18} className={loading ? 'spin' : ''} /> Refresh
                </button>
            </div>

            <div className="glass" style={{ padding: 24, marginBottom: 24 }}>
                <div className="form-group">
                    <label>Topic / Objective (Discover &amp; Publish, Anime Theory)</label>
                    <input
                        className="form-input"
                        value={objective}
                        onChange={e => setObjective(e.target.value)}
                        placeholder="e.g. How Yuta DESTROYED the Sendai Colony"
                    />
                </div>
                <div className="form-group">
                    <label>Anime series (optional, for Anime Theory)</label>
                    <input
                        className="form-input"
                        value={anime}
                        onChange={e => setAnime(e.target.value)}
                        placeholder="e.g. Jujutsu Kaisen"
                    />
                </div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {PIPELINES.map(p => (
                        <button
                            key={p.name}
                            className="btn-primary"
                            disabled={running !== null || (p.needsObjective && !objective.trim())}
                            onClick={() => run(p.name, p.needsObjective)}
                        >
                            {running === p.name ? <RefreshCw size={16} className="spin" /> : p.icon}
                            {p.label}
                        </button>
                    ))}
                </div>
            </div>

            {log.length > 0 && (
                <div className="glass" style={{ padding: 16, marginBottom: 24, fontFamily: 'monospace', fontSize: 13 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span style={{ fontWeight: 600 }}>Run Log</span>
                        <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: 12 }} onClick={() => setLog([])}>Clear</button>
                    </div>
                    <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
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
                    <Play size={18} /> Recent Runs ({workflows.length})
                </h3>
                {workflows.length === 0 ? (
                    <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-secondary)' }}>No runs recorded yet.</div>
                ) : (
                    <table className="custom-table">
                        <thead>
                            <tr><th>Workflow</th><th>Status</th><th>Started</th><th>Duration</th></tr>
                        </thead>
                        <tbody>
                            {workflows.map(w => (
                                <tr key={w.id}>
                                    <td>{w.workflow_name}</td>
                                    <td><span className={`badge ${w.status}`}>{w.status}</span></td>
                                    <td>{w.started_at ? new Date(w.started_at).toLocaleString() : '-'}</td>
                                    <td>{w.duration_ms ? `${(w.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </>
    );
}
