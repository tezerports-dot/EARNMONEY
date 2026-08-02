import { Middleware } from 'telegraf';
import { BotContext, SessionData, defaultSession } from './context';

// In-memory session store keyed by Telegram user id. This is sufficient for
// a single bot process. If you run multiple bot replicas behind the same
// webhook, back this with Redis instead (BullMQ's ioredis connection can be
// reused here) so conversation state is shared across instances.
const store = new Map<number, SessionData>();

export const sessionMiddleware: Middleware<BotContext> = async (ctx, next) => {
  const id = ctx.from?.id;
  if (id === undefined) {
    ctx.session = defaultSession();
    return next();
  }
  if (!store.has(id)) store.set(id, defaultSession());
  ctx.session = store.get(id)!;
  await next();
  store.set(id, ctx.session);
};
