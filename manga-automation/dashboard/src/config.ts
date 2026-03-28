// API base URL: in dev mode hits localhost:3001 directly,
// in production (Docker/Nginx) uses relative paths that get proxied.
export const API_BASE = import.meta.env.DEV
    ? 'http://localhost:3001'
    : '';
