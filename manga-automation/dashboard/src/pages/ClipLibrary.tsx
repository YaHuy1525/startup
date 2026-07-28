import { useEffect, useState } from 'react';
import { Film, RefreshCw, Send, ExternalLink } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { apiGet } from '../services/api';
import type { Clip, SourceType } from '../types';
import PublishComposer from '../components/PublishComposer';

export default function ClipLibrary() {
    const [params] = useSearchParams();
    const initialSource = (params.get('source') as '' | SourceType) || '';
    const [clips, setClips] = useState<Clip[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [sourceFilter, setSourceFilter] = useState<'' | SourceType>(initialSource);
    const [statusFilter, setStatusFilter] = useState('');
    const [active, setActive] = useState<Clip | null>(null);

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await apiGet<{ clips: Clip[] }>('/dashboard/clips', {
                source: sourceFilter || undefined,
                status: statusFilter || undefined,
            });
            setClips(data.clips || []);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [sourceFilter, statusFilter]);

    const statuses = Array.from(new Set(clips.map(c => c.status).filter(Boolean)));

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Film size={32} /> Clip Library
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
                        Rendered videos, YouTube-sourced clips, and anime-theory Shorts from{' '}
                        <code style={{ fontSize: 12 }}>short-form-pipeline/out</code>.
                    </p>
                </div>
                <button className="btn-secondary" onClick={load}>
                    <RefreshCw size={18} className={loading ? 'spin' : ''} /> Refresh
                </button>
            </div>

            <div className="glass" style={{ padding: 16, marginBottom: 24, display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                <select className="form-input" value={sourceFilter} onChange={e => setSourceFilter(e.target.value as any)} style={{ maxWidth: 220 }}>
                    <option value="">All sources</option>
                    <option value="video">Rendered / ingested</option>
                    <option value="arbitrage">YouTube-sourced</option>
                    <option value="anime">Anime theory (out folder)</option>
                </select>
                <select className="form-input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ maxWidth: 200 }}>
                    <option value="">All statuses</option>
                    {statuses.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{clips.length} clips</span>
            </div>

            {error && <div className="error-message" style={{ marginBottom: 24 }}>{error}</div>}

            {loading ? (
                <div className="loading-container" style={{ minHeight: 300 }}>
                    <div className="loading-spinner"></div>
                    <p>Loading clips…</p>
                </div>
            ) : clips.length === 0 ? (
                <div className="glass" style={{ padding: 48, textAlign: 'center', color: 'var(--text-secondary)' }}>
                    No clips yet. Create one on Anime Theory, or use Agent Console / Arbitrage.
                </div>
            ) : (
                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
                    {clips.map(c => (
                        <div key={`${c.source_type}-${c.id}`} className="glass" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                                <span className="badge active" style={{ textTransform: 'capitalize' }}>{c.source_type}</span>
                                <span className={`badge ${c.status}`}>{c.status}</span>
                            </div>
                            <div style={{ fontWeight: 600, lineHeight: 1.4, minHeight: 42 }}>{c.title}</div>
                            <div style={{ color: 'var(--text-secondary)', fontSize: 13, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                                {c.duration_secs ? <span>{Math.round(Number(c.duration_secs))}s</span> : null}
                                {c.file_size_mb ? <span>{Number(c.file_size_mb).toFixed(1)} MB</span> : null}
                                {c.source_url && (
                                    <a href={c.source_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                        source <ExternalLink size={12} />
                                    </a>
                                )}
                            </div>
                            {c.published && c.published.length > 0 && (
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                    {c.published.map((p, i) => (
                                        <span key={i} className="badge published" style={{ textTransform: 'capitalize' }}>
                                            {p.url
                                                ? <a href={p.url} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>{p.platform}</a>
                                                : p.platform}
                                        </span>
                                    ))}
                                </div>
                            )}
                            <button className="btn-primary" style={{ marginTop: 'auto' }} onClick={() => setActive(c)}>
                                <Send size={16} /> Publish
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {active && (
                <PublishComposer
                    clip={active}
                    onClose={() => { setActive(null); load(); }}
                />
            )}
        </>
    );
}
