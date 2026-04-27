import { useState, useEffect } from 'react';
import { TrendingUp, Video, Download, Upload, RefreshCw, Play } from 'lucide-react';
import { API_BASE } from '../config';

interface TrendRow { status: string; count: string; }
interface AssetRow  { status: string; count: string; }
interface UploadRow { platform: string; status: string; count: string; }

interface Status {
    trends: TrendRow[];
    assets: AssetRow[];
    uploads: UploadRow[];
}

interface Asset {
    id: number;
    hashtag: string;
    youtube_title: string;
    youtube_url: string;
    duration_secs: number;
    file_size_mb: number;
    status: string;
}

export default function Arbitrage() {
    const [status, setStatus] = useState<Status | null>(null);
    const [assets, setAssets] = useState<Asset[]>([]);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState<string | null>(null);
    const [log, setLog] = useState<string[]>([]);
    
    // Manual YT to TikTok state
    const [manualUrl, setManualUrl] = useState('');
    const [manualCaption, setManualCaption] = useState('Epic YouTube Short');
    const [manualHashtags, setManualHashtags] = useState('fyp viral manga');

    const fetchStatus = async () => {
        try {
            const [statusRes, assetsRes] = await Promise.all([
                fetch(`${API_BASE}/arbitrage/status`),
                fetch(`${API_BASE}/arbitrage/assets`),
            ]);
            setStatus(await statusRes.json());
            const ad = await assetsRes.json();
            setAssets(ad.assets || []);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    useEffect(() => { fetchStatus(); }, []);

    const run = async (step: string, body: object = {}) => {
        setRunning(step);
        addLog(`▶ Running ${step}...`);
        try {
            const r = await fetch(`${API_BASE}/arbitrage/${step}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await r.json();
            const result = data.result || data;
            addLog(`✅ ${step}: ${JSON.stringify(result)}`);
            await fetchStatus();
        } catch (e: any) {
            addLog(`❌ ${step} failed: ${e.message}`);
        }
        setRunning(null);
    };

    const addLog = (msg: string) =>
        setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 50));

    const countByStatus = (rows: { status: string; count: string }[], s: string) =>
        parseInt(rows?.find(r => r.status === s)?.count || '0');

    if (loading) return (
        <div className="loading-container" style={{ minHeight: '400px' }}>
            <div className="loading-spinner"></div>
            <p>Loading arbitrage pipeline...</p>
        </div>
    );

    const trendNew      = countByStatus(status?.trends || [], 'new');
    const trendSourcing = countByStatus(status?.trends || [], 'sourcing');
    const trendDone     = countByStatus(status?.trends || [], 'done');
    const assetPending  = countByStatus(status?.assets || [], 'pending');
    const assetDl       = countByStatus(status?.assets || [], 'downloaded');
    const assetDist     = countByStatus(status?.assets || [], 'distributed');
    const uploadSuccess = (status?.uploads || []).filter(u => u.status === 'success').reduce((a, u) => a + parseInt(u.count), 0);

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <TrendingUp size={32} /> Arbitrage Pipeline
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
                        TikTok trend discovery → YouTube sourcing → multi-platform distribution
                    </p>
                </div>
                <button className="btn-secondary" onClick={fetchStatus}>
                    <RefreshCw size={18} className={loading ? 'spin' : ''} /> Refresh
                </button>
            </div>

            {/* Stats */}
            <div className="stats-grid" style={{ marginBottom: '24px' }}>
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--accent-primary)' }}>
                    <div className="stat-title">Trends</div>
                    <div className="stat-value">{trendNew + trendSourcing + trendDone}</div>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                        {trendNew} new · {trendSourcing} sourcing · {trendDone} done
                    </p>
                </div>
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--warning)' }}>
                    <div className="stat-title">Assets</div>
                    <div className="stat-value">{assetPending + assetDl + assetDist}</div>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                        {assetPending} pending · {assetDl} downloaded · {assetDist} distributed
                    </p>
                </div>
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--success)' }}>
                    <div className="stat-title">Uploads</div>
                    <div className="stat-value">{uploadSuccess}</div>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>successful uploads</p>
                </div>
            </div>

            {/* Pipeline Controls */}
            <div className="glass" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ fontWeight: 600, marginBottom: '16px' }}>Pipeline Controls</h3>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    {[
                        { step: 'discover-trends', label: 'Discover Trends', icon: <TrendingUp size={16} />, body: { region: 'US', limit: 20 } },
                        { step: 'source-assets',   label: 'Source YouTube',  icon: <Video size={16} />,      body: { limit: 5 } },
                        { step: 'download',        label: 'Download Videos', icon: <Download size={16} />,   body: { batch: 10 } },
                        { step: 'distribute',      label: 'Distribute',      icon: <Upload size={16} />,     body: { platforms: ['youtube'], batch: 5 } },
                    ].map(({ step, label, icon, body }) => (
                        <button
                            key={step}
                            className="btn-primary"
                            disabled={running !== null}
                            onClick={() => run(step, body)}
                            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                        >
                            {running === step ? <RefreshCw size={16} className="spin" /> : icon}
                            {label}
                        </button>
                    ))}
                    <button
                        className="btn-secondary"
                        disabled={running !== null}
                        onClick={async () => {
                            for (const [step, body] of [
                                ['discover-trends', { region: 'US', limit: 20 }],
                                ['source-assets',   { limit: 5 }],
                                ['download',        { batch: 10 }],
                                ['distribute',      { platforms: ['youtube'], batch: 5 }],
                            ] as [string, object][]) {
                                await run(step, body);
                            }
                        }}
                        style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        <Play size={16} /> Run Full Pipeline
                    </button>
                </div>
            </div>

            {/* Manual YT -> TikTok */}
            <div className="glass" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ fontWeight: 600, marginBottom: '16px' }}>Manual Transfer (YouTube ➔ TikTok)</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '600px' }}>
                    <input 
                        type="text" 
                        placeholder="YouTube URL" 
                        value={manualUrl} 
                        onChange={e => setManualUrl(e.target.value)} 
                        className="custom-input"
                    />
                    <input 
                        type="text" 
                        placeholder="Caption" 
                        value={manualCaption} 
                        onChange={e => setManualCaption(e.target.value)} 
                        className="custom-input"
                    />
                    <input 
                        type="text" 
                        placeholder="Hashtags (space separated, no #)" 
                        value={manualHashtags} 
                        onChange={e => setManualHashtags(e.target.value)} 
                        className="custom-input"
                    />
                    <button 
                        className="btn-primary" 
                        onClick={() => run('yt-to-tiktok', { url: manualUrl, caption: manualCaption, hashtags: manualHashtags.split(' ') })}
                        disabled={running !== null || !manualUrl}
                    >
                        {running === 'yt-to-tiktok' ? 'Processing...' : 'Transfer to TikTok'}
                    </button>
                </div>
            </div>

            {/* Log */}
            {log.length > 0 && (
                <div className="glass" style={{ padding: '16px', marginBottom: '24px', fontFamily: 'monospace', fontSize: '13px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <span style={{ fontWeight: 600 }}>Activity Log</span>
                        <button className="btn-secondary" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => setLog([])}>Clear</button>
                    </div>
                    <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {log.map((l, i) => (
                            <div key={i} style={{ color: l.includes('❌') ? 'var(--danger)' : l.includes('✅') ? 'var(--success)' : 'var(--text-secondary)' }}>
                                {l}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Assets Table */}
            <div className="glass table-container">
                <h3 style={{ padding: '24px', borderBottom: '1px solid var(--border-color)', fontWeight: 600 }}>
                    Asset Queue ({assets.length})
                </h3>
                {assets.length === 0 ? (
                    <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        No assets yet. Run "Discover Trends" then "Source YouTube" to populate.
                    </div>
                ) : (
                    <table className="custom-table">
                        <thead>
                            <tr>
                                <th>Trend</th>
                                <th>Title</th>
                                <th>Duration</th>
                                <th>Size</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {assets.map(a => (
                                <tr key={a.id}>
                                    <td><span className="badge active">{a.hashtag}</span></td>
                                    <td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        <a href={a.youtube_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)' }}>
                                            {a.youtube_title}
                                        </a>
                                    </td>
                                    <td>{a.duration_secs ? `${a.duration_secs}s` : '-'}</td>
                                    <td>{a.file_size_mb ? `${a.file_size_mb} MB` : '-'}</td>
                                    <td><span className={`badge ${a.status}`}>{a.status}</span></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </>
    );
}
