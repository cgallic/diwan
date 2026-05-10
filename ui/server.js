// Diwan UI — D1 stub. Real Next.js implementation lands D5 (T6.1+).
// For now: minimal HTTP server reading the SQLite ledger, listing trace_ids.

import { createServer } from 'node:http';
import Database from 'better-sqlite3';

const PORT = process.env.PORT || 3000;
const LEDGER_PATH = process.env.LEDGER_PATH || '/data/diwan.db';

let db;
try {
  db = new Database(LEDGER_PATH, { readonly: true, fileMustExist: false });
} catch (err) {
  console.error(`[ui-stub] cannot open ledger at ${LEDGER_PATH}:`, err.message);
}

const server = createServer((req, res) => {
  if (req.url === '/' || req.url === '/health') {
    res.setHeader('content-type', 'application/json');

    if (!db) {
      res.statusCode = 503;
      res.end(JSON.stringify({
        service: 'diwan-ui',
        status: 'ledger-unavailable',
        ledger_path: LEDGER_PATH,
        note: 'D1 stub. Real Next.js UI lands D5.',
      }));
      return;
    }

    let trace_count = 0;
    let latest_trace = null;
    try {
      const row = db.prepare('SELECT count(DISTINCT trace_id) AS n FROM verdict').get();
      trace_count = row.n;
      const latest = db.prepare('SELECT trace_id, max(ts) AS ts FROM verdict GROUP BY trace_id ORDER BY ts DESC LIMIT 1').get();
      latest_trace = latest;
    } catch (err) {
      // schema may not be applied yet
    }

    res.end(JSON.stringify({
      service: 'diwan-ui',
      status: 'ok',
      ledger_path: LEDGER_PATH,
      trace_count,
      latest_trace,
      note: 'D1 stub. Real Next.js UI (Preflight scoreboard, per-trace timeline, HUMAN_REVIEW queue) lands D5.',
    }, null, 2));
    return;
  }

  res.statusCode = 404;
  res.end('not found');
});

server.listen(PORT, () => {
  console.log(`[ui-stub] listening on :${PORT}, ledger=${LEDGER_PATH}`);
});
