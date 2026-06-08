import { useEffect, useMemo, useState } from 'react';
import { X, Send, RefreshCw, CheckCircle2, XCircle } from 'lucide-react';
import { apiGet, apiPost } from '../services/api';
import type { Account, Clip, PublishResult } from '../types';

interface Props {
    clip: Clip;
    onClose: () => void;
}

function extractAccounts(d: any): Account[] {
    const candidates = [d?.result?.result?.accounts, d?.result?.accounts, d?.accounts];
    for (const c of candidates) if (Array.isArray(c)) return c as Account[];
    return [];
}

function extractPublish(d: any): PublishResult['result'] & { _flowIds: string[]; _error?: string } {
    const top = d?.result ?? d ?? {};
    const inner = top?.result ?? top ?? {};
    const rows = Array.isArray(inner?.results) ? inner.results : [];
    const flowIds = rows.map((r: any) => r?.flow_id).filter(Boolean);
    const error = inner?.error || top?.error || d?.error;
    return { ...inner, _flowIds: flowIds, _error: error };
}

export default function PublishComposer({ clip, onClose }: Props) {
    const [accounts, setAccounts] = useState<Account[]>([]);
    const [loadingAcc, setLoadingAcc] = useState(true);
    const [accError, setAccError] = useState<string | null>(null);
    const [selected, setSelected] = useState<Set<string>>(new Set());

    const [title, setTitle] = useState(clip.title || '');
    const [desc, setDesc] = useState('');
    const [hashtags, setHashtags] = useState('');
    const [coverUrl, setCoverUrl] = useState('');
    const [scheduleEnabled, setScheduleEnabled] = useState(false);
    const [scheduleLocal, setScheduleLocal] = useState('');
    const [ytPrivacy, setYtPrivacy] = useState<'public' | 'unlisted' | 'private'>('public');

    // datetime-local is in the browser's local time; AiToEarn needs UTC ISO ending in 'Z'.
    const scheduleUtc = scheduleEnabled && scheduleLocal
        ? new Date(scheduleLocal).toISOString()
        : '';
    const scheduleInvalid = scheduleEnabled && (!scheduleLocal || isNaN(new Date(scheduleLocal).getTime()) || new Date(scheduleLocal).getTime() <= Date.now());
    // Default the picker to ~1 hour ahead, formatted for datetime-local (no seconds/zone).
    const minLocal = (() => {
        const d = new Date(Date.now() + 5 * 60 * 1000);
        const pad = (n: number) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    })();

    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState<ReturnType<typeof extractPublish> | null>(null);
    const [scheduledAt, setScheduledAt] = useState<string | null>(null);
    const [submitError, setSubmitError] = useState<string | null>(null);

    useEffect(() => {
        (async () => {
            try {
                const data = await apiGet('/publish/accounts');
                setAccounts(extractAccounts(data));
            } catch (e: any) {
                setAccError(e.message);
            } finally {
                setLoadingAcc(false);
            }
        })();
    }, []);

    const grouped = useMemo(() => {
        const m: Record<string, Account[]> = {};
        for (const a of accounts) {
            const key = (a.type || 'unknown').toLowerCase();
            (m[key] = m[key] || []).push(a);
        }
        return m;
    }, [accounts]);

    const toggle = (id: string) => {
        setSelected(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const togglePlatform = (platform: string) => {
        const ids = (grouped[platform] || []).map(a => a.id);
        const allOn = ids.every(id => selected.has(id));
        setSelected(prev => {
            const next = new Set(prev);
            ids.forEach(id => (allOn ? next.delete(id) : next.add(id)));
            return next;
        });
    };

    const submit = async () => {
        setSubmitting(true);
        setSubmitError(null);
        setResult(null);
        setScheduledAt(null);
        // Build selected_accounts map: { platform: [ids] }
        const selectedMap: Record<string, string[]> = {};
        for (const a of accounts) {
            if (selected.has(a.id)) {
                const p = (a.type || '').toLowerCase();
                (selectedMap[p] = selectedMap[p] || []).push(a.id);
            }
        }
        const channels = Object.keys(selectedMap);
        try {
            const data = await apiPost('/publish', {
                clip_id: clip.id,
                source_type: clip.source_type,
                channels,
                selected_accounts: selectedMap,
                account_ids: Array.from(selected),
                title,
                desc,
                caption: desc,
                hashtags: hashtags.split(/[\s,]+/).map(h => h.trim()).filter(Boolean),
                cover_url: coverUrl || undefined,
                publish_time: scheduleUtc || undefined,
                yt_privacy: ytPrivacy,
            });
            const top = data?.result ?? data ?? {};
            const inner = top?.result ?? top ?? {};
            const hardError =
                data?.error
                || top?.error
                || inner?.error
                || (top?.ok === false ? 'Publish request failed' : '')
                || (data?.success === false ? 'Publish request failed' : '');
            const hasResults = Array.isArray(inner?.results);
            if (hardError && !hasResults) {
                throw new Error(String(hardError));
            }
            setResult(extractPublish(data));
            const sched = data?.result?.scheduled_for ?? data?.scheduled_for ?? (scheduleEnabled ? scheduleUtc : null);
            setScheduledAt(sched || null);
        } catch (e: any) {
            setSubmitError(e.message);
        } finally {
            setSubmitting(false);
        }
    };

    const selectedCount = selected.size;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div
                className="glass modal-content"
                style={{ maxWidth: 720, maxHeight: '90vh', overflowY: 'auto' }}
                onClick={e => e.stopPropagation()}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                    <h2 style={{ fontSize: 22, fontWeight: 700 }}>Publish Clip</h2>
                    <button className="logout-btn" onClick={onClose}><X size={20} /></button>
                </div>

                <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
                    {clip.source_type} #{clip.id} · {clip.title}
                </p>

                {/* Platform / account selection */}
                <div className="form-group">
                    <label>Platforms & Accounts (connected on AiToEarn)</label>
                    {loadingAcc && <p style={{ color: 'var(--text-secondary)' }}>Loading accounts…</p>}
                    {accError && <div className="error-message">{accError}</div>}
                    {!loadingAcc && !accError && accounts.length === 0 && (
                        <p style={{ color: 'var(--text-secondary)' }}>No connected accounts found.</p>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {Object.entries(grouped).map(([platform, accs]) => {
                            const ids = accs.map(a => a.id);
                            const allOn = ids.every(id => selected.has(id));
                            return (
                                <div key={platform} className="glass" style={{ padding: 12 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                        <span className="badge active" style={{ textTransform: 'capitalize' }}>{platform}</span>
                                        <button
                                            className="btn-secondary"
                                            style={{ padding: '4px 10px', fontSize: 12 }}
                                            onClick={() => togglePlatform(platform)}
                                        >
                                            {allOn ? 'Deselect all' : 'Select all'}
                                        </button>
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        {accs.map(a => (
                                            <label key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14 }}>
                                                <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} />
                                                <span>{a.account || a.id}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Editable post fields (AiToEarn-style) */}
                <div className="form-group">
                    <label>Title</label>
                    <input className="form-input" value={title} onChange={e => setTitle(e.target.value)} />
                </div>
                <div className="form-group">
                    <label>Description / Caption</label>
                    <textarea className="form-input" rows={3} value={desc} onChange={e => setDesc(e.target.value)} />
                </div>
                <div className="form-group">
                    <label>Hashtags / Topics (space or comma separated)</label>
                    <input className="form-input" value={hashtags} onChange={e => setHashtags(e.target.value)} placeholder="funny familyguy shorts" />
                </div>
                <div className="form-group">
                    <label>Cover image URL (optional)</label>
                    <input className="form-input" value={coverUrl} onChange={e => setCoverUrl(e.target.value)} />
                </div>

                <div className="form-group">
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                        <input
                            type="checkbox"
                            checked={scheduleEnabled}
                            onChange={e => setScheduleEnabled(e.target.checked)}
                        />
                        Schedule for later (otherwise publishes now)
                    </label>
                    {scheduleEnabled && (
                        <>
                            <input
                                type="datetime-local"
                                className="form-input"
                                value={scheduleLocal}
                                min={minLocal}
                                onChange={e => setScheduleLocal(e.target.value)}
                                style={{ marginTop: 8 }}
                            />
                            {scheduleInvalid ? (
                                <span style={{ color: 'var(--danger)', fontSize: 12 }}>
                                    Pick a date/time in the future.
                                </span>
                            ) : scheduleUtc ? (
                                <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                                    Will publish at {new Date(scheduleUtc).toLocaleString()} (your time) · sent as {scheduleUtc}
                                </span>
                            ) : null}
                        </>
                    )}
                </div>
                <div className="form-group">
                    <label>YouTube privacy</label>
                    <select className="form-input" value={ytPrivacy} onChange={e => setYtPrivacy(e.target.value as any)}>
                        <option value="public">public</option>
                        <option value="unlisted">unlisted</option>
                        <option value="private">private</option>
                    </select>
                </div>

                {submitError && <div className="error-message" style={{ marginBottom: 16 }}>{submitError}</div>}

                {result && (
                    <div className="glass" style={{ padding: 16, marginBottom: 16 }}>
                        {result._error && (
                            <div className="error-message" style={{ marginBottom: 8 }}>
                                {result._error}
                            </div>
                        )}
                        {scheduledAt && (
                            <div className="badge published" style={{ marginBottom: 8 }}>
                                Scheduled for {new Date(scheduledAt).toLocaleString()}
                            </div>
                        )}
                        <div style={{ fontWeight: 600, marginBottom: 8 }}>
                            {scheduledAt ? 'Queued' : 'Published'} {result.published_count ?? 0} · Failed {result.failed_count ?? 0}
                            {typeof result.confirmed_count === 'number' && ` · Confirmed ${result.confirmed_count}`}
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
                            {(result.results || []).map((r, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    {r.success
                                        ? <CheckCircle2 size={16} color="var(--success)" />
                                        : <XCircle size={16} color="var(--danger)" />}
                                    <span style={{ textTransform: 'capitalize' }}>{r.platform}</span>
                                    <span style={{ color: 'var(--text-secondary)' }}>{r.account || r.account_id}</span>
                                    {r.error && <span style={{ color: 'var(--danger)' }}>— {r.error}</span>}
                                    {r.verification && <span style={{ color: 'var(--text-secondary)' }}>({r.verification})</span>}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <div className="flex-row">
                    <button className="btn-secondary" onClick={onClose}>Close</button>
                    <button className="btn-primary" onClick={submit} disabled={submitting || selectedCount === 0 || scheduleInvalid}>
                        {submitting ? <RefreshCw size={16} className="spin" /> : <Send size={16} />}
                        {submitting
                            ? (scheduleEnabled ? 'Scheduling…' : 'Publishing…')
                            : `${scheduleEnabled ? 'Schedule' : 'Publish'} to ${selectedCount} account${selectedCount === 1 ? '' : 's'}`}
                    </button>
                </div>
            </div>
        </div>
    );
}
