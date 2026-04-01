import { Activity, TrendingUp, Users, Video } from 'lucide-react';
import { useState, useEffect } from 'react';
import { API_BASE } from '../config';

export default function Analytics() {
    const [stats, setStats] = useState({
        totalVideos: 0,
        totalAccounts: 0,
        activeAccounts: 0,
        loading: true
    });

    useEffect(() => {
        const fetchAnalytics = async () => {
            try {
                const [videosRes, accountsRes] = await Promise.all([
                    fetch(`${API_BASE}/dashboard/videos`),
                    fetch(`${API_BASE}/dashboard/tiktok-accounts`)
                ]);

                const videos = await videosRes.json();
                const accounts = await accountsRes.json();

                setStats({
                    totalVideos: videos.videos?.length || 0,
                    totalAccounts: accounts.accounts?.length || 0,
                    activeAccounts: accounts.accounts?.filter((a: any) => a.account_status === 'active').length || 0,
                    loading: false
                });
            } catch (error) {
                console.error('Failed to fetch analytics:', error);
                setStats(prev => ({ ...prev, loading: false }));
            }
        };

        fetchAnalytics();
    }, []);

    if (stats.loading) {
        return (
            <div className="loading-container" style={{ minHeight: '400px' }}>
                <div className="loading-spinner"></div>
                <p>Loading analytics...</p>
            </div>
        );
    }

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <Activity size={32} /> Global Analytics
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
                        Track TikTok performance, A/B test results, and audience growth across all accounts.
                    </p>
                </div>
            </div>

            <div className="stats-grid">
                <div className="glass stat-card" style={{ borderTop: '4px solid var(--accent-primary)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <h3 className="stat-title">Total Videos</h3>
                        <Video size={20} color="var(--accent-primary)" />
                    </div>
                    <p className="stat-value">{stats.totalVideos}</p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
                        Rendered and ready
                    </p>
                </div>

                <div className="glass stat-card" style={{ borderTop: '4px solid var(--success)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <h3 className="stat-title">Active Accounts</h3>
                        <Users size={20} color="var(--success)" />
                    </div>
                    <p className="stat-value">{stats.activeAccounts}</p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
                        Out of {stats.totalAccounts} total
                    </p>
                </div>

                <div className="glass stat-card" style={{ borderTop: '4px solid var(--warning)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <h3 className="stat-title">Analytics Status</h3>
                        <TrendingUp size={20} color="var(--warning)" />
                    </div>
                    <p style={{ fontSize: '18px', fontWeight: 600, marginTop: '8px' }}>Coming Soon</p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>
                        Performance tracking
                    </p>
                </div>
            </div>

            <div className="glass" style={{ 
                padding: '48px', 
                textAlign: 'center',
                minHeight: '300px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center'
            }}>
                <Activity size={48} color="var(--text-secondary)" style={{ marginBottom: '16px' }} />
                <p style={{ color: 'var(--text-secondary)', fontSize: '16px' }}>
                    Advanced analytics and A/B testing charts will be available here.
                </p>
                <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '8px' }}>
                    Connect your TikTok accounts and start publishing to see performance data.
                </p>
            </div>
        </>
    );
}
