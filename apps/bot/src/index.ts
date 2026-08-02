import 'dotenv/config';
import { Telegraf } from 'telegraf';
import { BotContext } from './context';
import { sessionMiddleware } from './session';
import { maintenanceMiddleware } from './middleware/maintenance';
import { handleStart } from './handlers/start';
import { handleContact } from './handlers/contact';
import { handleVerifyMembership } from './handlers/verifyMembership';
import { startBankDetails, continueBankDetails } from './handlers/bankDetails';
import { handleStatus } from './handlers/status';

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) {
  throw new Error('BOT_TOKEN is required. Set it in your .env file.');
}

export const bot = new Telegraf<BotContext>(BOT_TOKEN);

// Maintenance check runs FIRST — before session/DB is ever touched.
bot.use(maintenanceMiddleware);
bot.use(sessionMiddleware);

bot.start(handleStart);
bot.on('contact', handleContact);
bot.action('verify_membership', handleVerifyMembership);
bot.command('bankdetails', startBankDetails);
bot.command('status', handleStatus);

// Any plain text message might be a step in an in-progress /bankdetails flow.
bot.on('text', async (ctx, next) => {
  const handled = await continueBankDetails(ctx);
  if (!handled) return next();
});

bot.catch((err, ctx) => {
  console.error(`Unhandled bot error for update ${ctx.update.update_id}:`, err);
});

/**
 * Registers the webhook with Telegram and returns Telegraf's request
 * handler so a HOST http server (this file's own, OR a combined server
 * that also serves the website) can mount it at POST /webhook.
 *
 * This does NOT start its own http server — that's what makes the bot
 * embeddable inside apps/web/server.js for the Railway "combined" runtime.
 */
export async function initWebhook(webhookUrl: string) {
  await bot.telegram.setWebhook(`${webhookUrl}/webhook`);
  return bot.webhookCallback('/webhook');
}

export async function startPollingMode(): Promise<void> {
  await bot.launch();
  console.log('Bot started with long polling (development mode).');
  process.once('SIGINT', () => bot.stop('SIGINT'));
  process.once('SIGTERM', () => bot.stop('SIGTERM'));
}

/** Standalone entry point — only runs when this file is executed directly
 *  (`node dist/index.js`), i.e. the "split services" deployment (Oracle VM,
 *  or Railway with bot as its own service). When imported by the combined
 *  server instead, none of this runs automatically. */
async function main() {
  const webhookUrl = process.env.BOT_WEBHOOK_URL;
  const port = Number(process.env.PORT ?? 3001);

  if (webhookUrl) {
    const http = await import('http');
    const callback = await initWebhook(webhookUrl);
    http.createServer(callback).listen(port, () => {
      console.log(`Bot listening on webhook at ${webhookUrl}/webhook (port ${port})`);
    });
  } else {
    await startPollingMode();
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error('Fatal error starting bot:', err);
    process.exit(1);
  });
}
