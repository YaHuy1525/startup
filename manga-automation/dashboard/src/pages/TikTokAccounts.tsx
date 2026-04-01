import { useState, useEffect } from "react";
import { Users, Wifi, AlertTriangle, Plus, RefreshCw } from "lucide-react";
import { API_BASE } from '../config';

interface TikTokAccount {
    id: number;
    username: string;
    account_status: string;
    shadow_banned: boolean;
    total_posts: number;
    last_post_at: string | null;
    proxy_id: number | null;
    proxy_name: string | null;
    proxy_host: string | null;
    proxy_port: number | null;
}

export default function TikTokAccounts() {
    const [accounts, setAccounts] = useState<TikTokAccount[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchAccounts = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/tiktok-accounts?organization_id=1`);
            const data = await res.json();
            setAccounts(data.accounts || []);
        } catch (error) {
            console.error('Failed to fetch accounts:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchAccounts();
    }, []);

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <Users size={32} /> TikTok Accounts & Proxies
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
                        Manage connected accounts and their proxy routing.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button className="btn-secondary" onClick={fetchAccounts}>
                        <RefreshCw size={18} className={loading ? "spin" : ""} />
                        Refresh
                    </button>
                    <button className="btn-primary">
                        <Plus size={18} />
                        Add Account
                    </button>
                </div>
            </div>

            {loading ? (
                <div className="loading-container" style={{ minHeight: '400px' }}>
                    <div className="loading-spinner"></div>
                    <p>Loading accounts...</p>
                </div>
            ) : accounts.length === 0 ? (
                <div className="glass" style={{ padding: '48px', textAlign: 'center' }}>
                    <p style={{ color: 'var(--text-secondary)' }}>No TikTok accounts configured yet.</p>
                    <button className="btn-primary" style={{ marginTop: '16px' }}>
                        <Plus size={18} />
                        Add Your First Account
                    </button>
                </div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '24px' }}>
                    {accounts.map(acc => (
                        <div key={acc.id} className="glass" style={{ padding: '24px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '16px' }}>
                                <h3 style={{ fontSize: '20px', fontWeight: 600 }}>@{acc.username}</h3>
                                <span className={`badge ${acc.account_status}`}>
                                    {acc.account_status.toUpperCase()}
                                </span>
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: 'var(--text-secondary)' }}>
                                    <Users size={16} />
                                    <span>{acc.total_posts} posts</span>
                                </div>

                                {acc.proxy_host && (
                                    <div style={{ 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        gap: '8px', 
                                        fontSize: '14px', 
                                        color: 'var(--text-secondary)',
                                        background: 'rgba(0, 0, 0, 0.2)',
                                        padding: '8px 12px',
                                        borderRadius: '8px'
                                    }}>
                                        <Wifi size={16} color="var(--accent-primary)" />
                                        <span>Proxy: {acc.proxy_host}:{acc.proxy_port}</span>
                                    </div>
                                )}

                                {!acc.proxy_host && (
                                    <div style={{ 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        gap: '8px', 
                                        fontSize: '14px', 
                                        color: 'var(--warning)',
                                        background: 'rgba(245, 158, 11, 0.1)',
                                        padding: '8px 12px',
                                        borderRadius: '8px'
                                    }}>
                                        <AlertTriangle size={16} />
                                        <span>No proxy assigned</span>
                                    </div>
                                )}

                                {acc.shadow_banned && (
                                    <div style={{ 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        gap: '8px', 
                                        fontSize: '14px', 
                                        color: 'var(--danger)',
                                        background: 'rgba(239, 68, 68, 0.1)',
                                        padding: '8px 12px',
                                        borderRadius: '8px'
                                    }}>
                                        <AlertTriangle size={16} />
                                        <span>Account functionality restricted</span>
                                    </div>
                                )}
                            </div>

                            <div style={{ marginTop: '20px', display: 'flex', gap: '8px' }}>
                                <button className="btn-secondary" style={{ flex: 1, padding: '8px', fontSize: '13px' }}>
                                    Test Auth
                                </button>
                                <button className="btn-secondary" style={{ flex: 1, padding: '8px', fontSize: '13px' }}>
                                    Change Proxy
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </>
    );
}
