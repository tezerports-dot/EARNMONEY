/**
 * Custom server for the Railway "combined" deployment.
 *
 * RUN_MODE controls what this process does:
 *   - "web"      (default) — behaves exactly like `next start`. Use this
 *                 when web is its own service (Oracle VM / split Railway
 *                 services) — nothing else changes, same Dockerfile even.
 *   - "combined" — ALSO mounts the bot's webhook at POST /webhook and starts
 *                 the worker's cron scheduler in this same process. This is
 *                 what the Railway single-service deployment uses.
 *
 * Splitting back apart later needs ZERO code changes — just deploy
 * apps/bot's own dist/index.js and dist/worker.js as separate services
 * again (they still work standalone, see their require.main guards) and
 * set RUN_MODE=web here.
 */
const http = require('http');
const next = require('next');

const RUN_MODE = process.env.RUN_MODE || 'web';
const dev = process.env.NODE_ENV !== 'production';
const port = Number(process.env.PORT || 3000);

const app = next({ dev, dir: __dirname });
const nextHandler = app.getRequestHandler();

async function main() {
  await app.prepare();

  let webhookCallback = null;
  if (RUN_MODE === 'combined') {
    // Lazy-require so a plain "web" deployment never even loads telegraf.
    const { initWebhook } = require('@platform/bot');
    const { bootstrapWorker } = require('@platform/bot/dist/worker');

    const webhookUrl = process.env.BOT_WEBHOOK_URL;
    if (!webhookUrl) {
      throw new Error('BOT_WEBHOOK_URL is required when RUN_MODE=combined');
    }
    webhookCallback = await initWebhook(webhookUrl);
    console.log(`[combined] bot webhook mounted at ${webhookUrl}/webhook`);

    bootstrapWorker();
    console.log('[combined] worker scheduler started in-process');
  }

  const server = http.createServer((req, res) => {
    if (webhookCallback && req.url === '/webhook' && req.method === 'POST') {
      return webhookCallback(req, res);
    }
    return nextHandler(req, res);
  });

  server.listen(port, () => {
    console.log(`[${RUN_MODE}] server listening on port ${port}`);
  });
}

main().catch((err) => {
  console.error('Fatal error starting combined server:', err);
  process.exit(1);
});
