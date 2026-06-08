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

export async function apiGet<T = any>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const qs = params
        ? '?' + Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
            .join('&')
        : '';
    const res = await fetch(`${API_BASE}${path}${qs}`);
    return handle<T>(res);
}

export async function apiPost<T = any>(path: string, body: object = {}): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return handle<T>(res);
}
