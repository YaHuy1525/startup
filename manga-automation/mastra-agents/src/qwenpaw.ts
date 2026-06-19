/**
 * QwenPaw Console client — chat, agents, status via python-worker proxy.
 */

const WORKER_URL = process.env.PYTHON_WORKER_URL || 'http://python-worker:8080';

async function callWorker(path: string, body: object = {}): Promise<any> {
    const r = await fetch(`${WORKER_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(Number(process.env.QWENPAW_CHAT_TIMEOUT || 600_000)),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
        throw new Error(data?.error || data?.result?.error || `Worker error (${r.status})`);
    }
    return data;
}

export const isQwenPawBackend = (): boolean =>
    (process.env.SUMMON_BACKEND || 'qwenpaw').toLowerCase() === 'qwenpaw';

export async function qwenpawChat(body: Record<string, unknown>): Promise<any> {
    const resp = await callWorker('/qwenpaw/chat', body);
    const inner = resp?.result ?? resp;
    return {
        success: inner?.success !== false,
        backend: 'qwenpaw',
        route: `qwenpaw/${body.agent_id || 'pipeline-manager'}`,
        result: inner,
        text: inner?.text,
        published_count: inner?.published_count ?? 0,
        failed_count: inner?.failed_count ?? 0,
    };
}

export async function qwenpawStatus(): Promise<any> {
    const resp = await callWorker('/qwenpaw/status', {});
    return { backend: 'qwenpaw', ...(resp?.result ?? resp) };
}

export async function qwenpawAgents(): Promise<any> {
    const resp = await callWorker('/qwenpaw/agents', {});
    return resp?.result ?? resp;
}
