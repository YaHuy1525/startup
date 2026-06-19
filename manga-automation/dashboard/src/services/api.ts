import { API_BASE } from '../config';

async function handle<T>(res: Response): Promise<T> {
    const text = await res.text();
    let data: any = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
    if (!res.ok) {
        const msg = data?.error || data?.message || `Request failed (${res.status})`;
        throw new Error(msg);
    }
    return data as T;
}

export async function apiGet<T = any>(
    path: string,
    params?: Record<string, string | number | undefined>,
    timeoutMs?: number,
): Promise<T> {
    const qs = params
        ? '?' + Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
            .join('&')
        : '';
    const slow = path.includes('/publish/accounts') || path.includes('/accounts');
    const timeout = timeoutMs ?? (slow ? 120_000 : undefined);
    const init: RequestInit = {};
    if (timeout) {
        init.signal = AbortSignal.timeout(timeout);
    }
    const res = await fetch(`${API_BASE}${path}${qs}`, init);
    return handle<T>(res);
}

export async function apiPost<T = any>(path: string, body: object = {}, timeoutMs?: number): Promise<T> {
    const slow = path.includes('/agent/prompt') || path.includes('/agent/pipeline');
    const timeout = timeoutMs ?? (slow ? 600_000 : undefined);
    const init: RequestInit = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    };
    if (timeout) {
        init.signal = AbortSignal.timeout(timeout);
    }
    const res = await fetch(`${API_BASE}${path}`, init);
    return handle<T>(res);
}
