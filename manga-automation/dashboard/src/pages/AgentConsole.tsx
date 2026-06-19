import { useEffect, useMemo, useState } from 'react';
import { Bot, Send, RefreshCw, Terminal, Activity } from 'lucide-react';
import { apiGet, apiPost } from '../services/api';
import type { Account } from '../types';
import { extractAccounts, extractAccountsError } from '../utils/accounts';

type PublishRow = {
    platform?: string;
    account_id?: string;
    account?: string;
    success?: boolean;
    verification?: string;
    flow_id?: string;
    error?: string;
    status?: {
        status_raw?: string;
        error_msg?: string;
        work_link?: string;
    } | null;
};

type PlatformStats = {
    success: number;
    failed: number;
};

type PublishSummary = {
    publishedCount: number;
    failedCount: number;
    confirmedCount: number;
    unverifiedCount: number;
    channels: Record<string, PlatformStats>;
    rows: PublishRow[];
};

function toInt(value: unknown, fallback = 0): number {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizePlatform(value: unknown): string {
    return String(value || '').trim().toLowerCase();
}

function formatPlatform(platform: string): string {
    if (!platform) return 'unknown';
    return platform.replace(/_/g, ' ');
}

function extractPublishSummary(steps: any[], published: number, failed: number): PublishSummary | null {
    const publishStep = Array.isArray(steps)
        ? steps.find((s: any) => s?.step === 'publish')
        : null;
    const publishResult = publishStep && typeof publishStep.result === 'object' ? publishStep.result : null;

    const rawRows = Array.isArray(publishResult?.results) ? publishResult.results : [];
    const rows = rawRows.filter((row: unknown) => row && typeof row === 'object') as PublishRow[];

    const channels: Record<string, PlatformStats> = {};
    const rawChannels = publishResult?.channels;
    if (rawChannels && typeof rawChannels === 'object') {
        Object.entries(rawChannels as Record<string, unknown>).forEach(([platform, value]) => {
            if (!value || typeof value !== 'object') return;
            const stats = value as Record<string, unknown>;
            const key = normalizePlatform(platform);
            if (!key) return;
            channels[key] = {
                success: toInt(stats.success, 0),
                failed: toInt(stats.failed, 0),
            };
        });
    }

    if (Object.keys(channels).length === 0 && rows.length > 0) {
        rows.forEach((row) => {
            const platform = normalizePlatform(row.platform);
            if (!platform) return;
            if (!channels[platform]) channels[platform] = { success: 0, failed: 0 };
            if (row.success) channels[platform].success += 1;
            else channels[platform].failed += 1;
        });
    }

    if (rows.length === 0 && Object.keys(channels).length === 0 && published === 0 && failed === 0) {
        return null;
    }

    return {
        publishedCount: toInt(publishStep?.succeeded ?? publishResult?.published_count, published),
        failedCount: toInt(publishStep?.failed ?? publishResult?.failed_count, failed),
        confirmedCount: toInt(publishStep?.confirmed ?? publishResult?.confirmed_count, 0),
        unverifiedCount: toInt(publishStep?.unverified ?? publishResult?.unverified_count, 0),
        channels,
        rows,
    };
}

export default function AgentConsole() {
    const [prompt, setPrompt] = useState('');
    const [agentId, setAgentId] = useState('pipeline-manager');
    const [agents, setAgents] = useState<{ id: string; name?: string }[]>([]);
    const [channels, setChannels] = useState<Set<string>>(new Set());
    const [accounts, setAccounts] = useState<Account[]>([]);
    const [accountsError, setAccountsError] = useState<string | null>(null);
    const [loadingAccounts, setLoadingAccounts] = useState(true);
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    const [status, setStatus] = useState<any>(null);
    const [logs, setLogs] = useState<string>('');
    const [loadingSide, setLoadingSide] = useState(false);

    const loadAccounts = async () => {
        setLoadingAccounts(true);
        setAccountsError(null);
        try {
            const data = await apiGet('/publish/accounts');
            const rows = extractAccounts(data);
            setAccounts(rows);
            if (rows.length === 0) {
                setAccountsError(extractAccountsError(data) || 'No connected accounts found.');
            }
        } catch (e: any) {
            setAccounts([]);
            setAccountsError(e?.message || 'Failed to load accounts.');
        } finally {
            setLoadingAccounts(false);
        }
    };

    useEffect(() => {
        loadAccounts();
        refreshSide();
        apiGet('/agent/agents')
            .then((data: any) => {
                const rows = Array.isArray(data?.agents) ? data.agents : [];
                const filtered = rows.filter((a: any) => a?.id && a.id !== 'default');
                if (filtered.length) setAgents(filtered);
            })
            .catch(() => {});
    }, []);

    const platforms = useMemo(
        () => Array.from(new Set(accounts.map(a => (a.type || '').toLowerCase()).filter(Boolean))),
        [accounts]
    );

    const toggleChannel = (p: string) => {
        setChannels(prev => {
            const next = new Set(prev);
            next.has(p) ? next.delete(p) : next.add(p);
            return next;
        });
    };

    const run = async () => {
        if (!prompt.trim()) return;
        setRunning(true);
        setError(null);
        setResult(null);
        try {
            const body: any = { prompt, agent_id: agentId };
            if (channels.size) body.channels = Array.from(channels);
            const data = await apiPost('/agent/prompt', body);
            setResult(data);
            refreshSide();
        } catch (e: any) {
            setError(e.message);
        } finally {
            setRunning(false);
        }
    };

    const refreshSide = async () => {
        setLoadingSide(true);
        try {
            const [s, l] = await Promise.all([
                apiGet('/agent/status').catch(() => null),
                apiGet('/agent/logs', { lines: 120 }).catch(() => null),
            ]);
            setStatus(s);
            const content = (l as any)?.result?.content ?? (l as any)?.content ?? '';
            setLogs(typeof content === 'string' ? content : JSON.stringify(content, null, 2));
        } finally {
            setLoadingSide(false);
        }
    };

    const payload = result?.result ?? result;
    const steps = payload?.steps || [];
    const published = toInt(payload?.published_count, 0);
    const failed = toInt(payload?.failed_count, 0);
    const publishSummary = useMemo(
        () => extractPublishSummary(steps, published, failed),
        [steps, published, failed]
    );
    const successfulRows = useMemo(
        () => (publishSummary?.rows || []).filter((row) => row.success),
        [publishSummary]
    );
    const failedRows = useMemo(
        () => (publishSummary?.rows || []).filter((row) => !row.success),
        [publishSummary]
    );

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Bot size={32} /> Agent Console
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
                        Powered by QwenPaw — describe what you want and the pipeline agent runs trend, source, publish, and engagement skills.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn-secondary" onClick={loadAccounts} disabled={loadingAccounts}>
                        <RefreshCw size={18} className={loadingAccounts ? 'spin' : ''} /> Accounts
                    </button>
                    <button className="btn-secondary" onClick={refreshSide}>
                        <RefreshCw size={18} className={loadingSide ? 'spin' : ''} /> Status
                    </button>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 24 }}>
                {/* Left: prompt + result */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                    <div className="glass" style={{ padding: 24 }}>
                        <div className="form-group">
                            <label>Agent</label>
                            <select
                                className="form-input"
                                value={agentId}
                                onChange={e => setAgentId(e.target.value)}
                            >
                                {(agents.length ? agents : [{ id: 'pipeline-manager', name: 'Pipeline Manager' }]).map(a => (
                                    <option key={a.id} value={a.id}>{a.name || a.id}</option>
                                ))}
                            </select>
                        </div>
                        <div className="form-group">
                            <label>Your order</label>
                            <textarea
                                className="form-input"
                                rows={4}
                                value={prompt}
                                onChange={e => setPrompt(e.target.value)}
                                placeholder="e.g. find and post a funny Family Guy Vietnamese dub short on tiktok and youtube"
                            />
                        </div>
                        <div className="form-group">
                            <label>Target platforms (optional — defaults to the agent's choice)</label>
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                                {loadingAccounts && <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading accounts…</span>}
                                {!loadingAccounts && accountsError && (
                                    <span style={{ color: 'var(--danger, #f87171)', fontSize: 13 }}>{accountsError}</span>
                                )}
                                {!loadingAccounts && !accountsError && platforms.length === 0 && (
                                    <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No connected accounts detected.</span>
                                )}
                                {platforms.map(p => (
                                    <button
                                        key={p}
                                        className={channels.has(p) ? 'btn-primary' : 'btn-secondary'}
                                        style={{ padding: '6px 14px', textTransform: 'capitalize' }}
                                        onClick={() => toggleChannel(p)}
                                    >
                                        {p}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <button className="btn-primary" onClick={run} disabled={running || !prompt.trim()}>
                            {running ? <RefreshCw size={16} className="spin" /> : <Send size={16} />}
                            {running ? 'Running agent…' : 'Run Agent'}
                        </button>
                    </div>

                    {error && <div className="error-message">{error}</div>}

                    {result && (
                        <div className="glass" style={{ padding: 24 }}>
                            <h3 style={{ fontWeight: 600, marginBottom: 12 }}>
                                Result {result.route ? `(${result.route})` : ''}
                                {result.backend ? ` · ${result.backend}` : ''}
                            </h3>
                            {payload?.text && (
                                <div style={{ marginBottom: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                                    {payload.text}
                                </div>
                            )}
                            {(published !== undefined || failed !== undefined) && (
                                <div style={{ marginBottom: 12 }}>
                                    <span className="badge published">Published {published ?? 0}</span>{' '}
                                    <span className="badge failed">Failed {failed ?? 0}</span>
                                </div>
                            )}
                            {publishSummary && (
                                <div
                                    style={{
                                        marginBottom: 12,
                                        padding: 12,
                                        borderRadius: 8,
                                        background: 'rgba(0,0,0,0.22)',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        gap: 8,
                                    }}
                                >
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                        <span className="badge published">Published {publishSummary.publishedCount}</span>
                                        <span className="badge failed">Failed {publishSummary.failedCount}</span>
                                        <span className="badge running">Confirmed {publishSummary.confirmedCount}</span>
                                        <span className="badge running">Unverified {publishSummary.unverifiedCount}</span>
                                    </div>

                                    {Object.keys(publishSummary.channels).length > 0 && (
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                            {Object.entries(publishSummary.channels).map(([platform, stats]) => (
                                                <span key={platform} className="badge running">
                                                    {formatPlatform(platform)}: +{stats.success} / -{stats.failed}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    {publishSummary.rows.length > 0 && (
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                            <div>
                                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                                                    Successful posts ({successfulRows.length})
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                                    {successfulRows.length === 0 && (
                                                        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>None</span>
                                                    )}
                                                    {successfulRows.map((row, i) => (
                                                        <div key={`ok-${i}`} style={{ fontSize: 12, lineHeight: 1.4 }}>
                                                            <span className="badge published">{formatPlatform(normalizePlatform(row.platform))}</span>{' '}
                                                            {row.account || row.account_id || 'unknown account'}
                                                            {row.verification ? ` (${row.verification})` : ''}
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                            <div>
                                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                                                    Failed posts ({failedRows.length})
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                                    {failedRows.length === 0 && (
                                                        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>None</span>
                                                    )}
                                                    {failedRows.map((row, i) => (
                                                        <div key={`fail-${i}`} style={{ fontSize: 12, lineHeight: 1.4 }}>
                                                            <span className="badge failed">{formatPlatform(normalizePlatform(row.platform))}</span>{' '}
                                                            {row.account || row.account_id || 'unknown account'}
                                                            {' — '}
                                                            {row.error || row.status?.error_msg || row.status?.status_raw || 'unknown error'}
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                            {Array.isArray(steps) && steps.length > 0 && (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
                                    {steps.map((s: any, i: number) => (
                                        <div key={i} style={{ display: 'flex', gap: 8, fontSize: 13 }}>
                                            <span className={`badge ${s.status === 'ok' ? 'published' : s.status === 'error' ? 'failed' : 'running'}`}>
                                                {s.step}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <pre style={{ background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 8, fontSize: 12, overflowX: 'auto', maxHeight: 280 }}>
                                {JSON.stringify(payload, null, 2)}
                            </pre>
                        </div>
                    )}
                </div>

                {/* Right: status + logs */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                    <div className="glass" style={{ padding: 20 }}>
                        <h3 style={{ fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Activity size={18} /> Pipeline Status
                        </h3>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 8, fontSize: 12, overflowX: 'auto', maxHeight: 240 }}>
                            {status ? JSON.stringify(status.result ?? status, null, 2) : 'No status yet.'}
                        </pre>
                    </div>
                    <div className="glass" style={{ padding: 20 }}>
                        <h3 style={{ fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Terminal size={18} /> Agent Logs
                        </h3>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 8, fontSize: 11, overflowX: 'auto', maxHeight: 360, whiteSpace: 'pre-wrap' }}>
                            {logs || 'No logs yet.'}
                        </pre>
                    </div>
                </div>
            </div>
        </>
    );
}
