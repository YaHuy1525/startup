const { Pool } = require('pg');

const rawDbUrl = process.env.DATABASE_URL || 'postgresql://manga_user:150205@localhost:5434/manga_automation';
const safeDbUrl = rawDbUrl.replace(/:([^:@/]*?)#([^@]*)@/, ':$1%23$2@');

const db = new Pool({
    connectionString: safeDbUrl,
    max: 10,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000,
});

async function run() {
    try {
        console.log("Connecting to", safeDbUrl);
        await db.query('SELECT 1');
        console.log("Success!");
        process.exit(0);
    } catch (err) {
        console.error("DB Error:", err);
        process.exit(1);
    }
}
run();
