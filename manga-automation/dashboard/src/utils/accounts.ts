import type { Account } from '../types';

/** Normalize AiToEarn account payloads from worker / manga-agents. */
export function extractAccounts(data: unknown): Account[] {
    const d = data as Record<string, unknown> | null | undefined;
    if (!d) return [];

    const candidates = [
        d.accounts,
        (d.result as Record<string, unknown> | undefined)?.accounts,
        (d.result as Record<string, unknown> | undefined)?.result &&
            ((d.result as Record<string, unknown>).result as Record<string, unknown>)?.accounts,
    ];

    for (const c of candidates) {
        if (Array.isArray(c)) return c as Account[];
    }
    return [];
}

export function extractAccountsError(data: unknown): string | null {
    const d = data as Record<string, unknown> | null | undefined;
    if (!d) return null;
    const warning = String(
        d.warning
        ?? (d.result as Record<string, unknown> | undefined)?.warning
        ?? '',
    ).trim();
    const hint = String(
        d.hint
        ?? (d.result as Record<string, unknown> | undefined)?.hint
        ?? '',
    ).trim();
    if (warning === 'no_connected_accounts_found') {
        return hint || 'No connected accounts found in AiToEarn.';
    }
    return null;
}
