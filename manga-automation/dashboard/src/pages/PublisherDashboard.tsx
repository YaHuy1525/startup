import { useState, useEffect } from 'react';
import { RefreshCw, Video, UserCheck, AlertTriangle } from 'lucide-react';
import { API_BASE } from '../config';

export default function PublisherDashboard() {
    const [accounts, setAccounts] = useState<any[]>([]);
    const [videos, setVideos] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [accRes, vidRes] = await Promise.all([
                fetch(`${API_BASE}/dashboard/tiktok-accounts`),
                fetch(`${API_BASE}/dashboard/videos`)
            ]);
            const accData = await accRes.json();
            const vidData = await vidRes.json();
            setAccounts(accData.accounts);
            setVideos(vidData.videos);
        } catch (error) {
            console.error('Failed to fetch dashboard data', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchData();
    }, []);

    if (loading) {
        return (
            <div className="header-container" style={{ justifyContent: 'center', marginTop: '100px' }}>
                <h2 className="page-title">Loading Dashboard...</h2>
            </div>
        );
    }

    return (
        <>
            <div className="header-container">
                <h2 className="page-title">TikTok Publisher</h2>
                <button className="btn-secondary" onClick={fetchData}>
                    <RefreshCw size={18} /> Refresh
                </button>
            </div>

            <div className="stats-grid">
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--success)' }}>
                    <div className="stat-title">Active Accounts</div>
                    <div className="stat-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <UserCheck size={32} color="var(--success)" />
                        {accounts.filter(a => a.account_status === 'active').length}
                    </div>
                </div>
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--warning)' }}>
                    <div className="stat-title">Videos Queue</div>
                    <div className="stat-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Video size={32} color="var(--warning)" />
                        {videos.filter(v => v.status === 'ready').length}
                    </div>
                </div>
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--danger)' }}>
                    <div className="stat-title">Shadow Banned</div>
                    <div className="stat-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <AlertTriangle size={32} color="var(--danger)" />
                        {accounts.filter(a => a.shadow_banned).length}
                    </div>
                </div>
            </div>

            <div className="glass table-container" style={{ marginBottom: '32px' }}>
                <h3 style={{ padding: '24px', borderBottom: '1px solid var(--border-color)', fontWeight: 600 }}>Tiktok Fleet Status</h3>
                <table className="custom-table">
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Status</th>
                            <th>Total Posts</th>
                            <th>Last Publish</th>
                            <th>Shadow Ban</th>
                        </tr>
                    </thead>
                    <tbody>
                        {accounts.map(acc => (
                            <tr key={acc.id}>
                                <td style={{ fontWeight: 500 }}>@{acc.username}</td>
                                <td><span className={`badge ${acc.account_status}`}>{acc.account_status}</span></td>
                                <td>{acc.total_posts}</td>
                                <td>{acc.last_post_at ? new Date(acc.last_post_at).toLocaleDateString() : 'Never'}</td>
                                <td>
                                    <span className={`badge ${acc.shadow_banned ? 'banned' : 'active'}`}>
                                        {acc.shadow_banned ? 'Banned' : 'Safe'}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="glass table-container">
                <h3 style={{ padding: '24px', borderBottom: '1px solid var(--border-color)', fontWeight: 600 }}>Recent Rendered Videos</h3>
                <table className="custom-table">
                    <thead>
                        <tr>
                            <th>Manga</th>
                            <th>Chapter</th>
                            <th>Duration</th>
                            <th>Status</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        {videos.map(vid => (
                            <tr key={vid.id}>
                                <td style={{ fontWeight: 500 }}>{vid.manga_title}</td>
                                <td>Chapter {vid.chapter_number}</td>
                                <td>{Math.floor(vid.duration_secs)}s</td>
                                <td><span className={`badge ${vid.status}`}>{vid.status}</span></td>
                                <td>{new Date(vid.created_at).toLocaleDateString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </>
    );
}
