export default () => ({
  port: parseInt(process.env.PORT || '3001', 10),
  nodeEnv: process.env.NODE_ENV || 'development',
  corsOrigin: process.env.CORS_ORIGIN || 'http://localhost:3000',

  database: {
    url: process.env.DATABASE_URL,
  },

  redis: {
    url: process.env.REDIS_URL || 'redis://localhost:6379',
  },

  jwt: {
    accessSecret: process.env.JWT_ACCESS_SECRET,
    accessTtl: process.env.JWT_ACCESS_TTL || '15m',
    refreshSecret: process.env.JWT_REFRESH_SECRET,
    refreshTtlDays: parseInt(process.env.JWT_REFRESH_TTL_DAYS || '30', 10),
  },

  cookies: {
    secure: (process.env.COOKIE_SECURE ?? 'true') === 'true',
    domain: process.env.COOKIE_DOMAIN || undefined,
  },

  argon2: {
    // Tuned for a small VPS (KVM 2, 8GB RAM). Raise memoryCost if you move to
    // a larger plan; keep an eye on request latency and RAM headroom under load.
    memoryCost: parseInt(process.env.ARGON2_MEMORY_COST || '19456', 10), // ~19 MB
    timeCost: parseInt(process.env.ARGON2_TIME_COST || '2', 10),
    parallelism: parseInt(process.env.ARGON2_PARALLELISM || '1', 10),
  },

  rateLimit: {
    ttlSeconds: parseInt(process.env.RATE_LIMIT_TTL_SECONDS || '60', 10),
    limit: parseInt(process.env.RATE_LIMIT_MAX || '20', 10),
  },

  captcha: {
    turnstileSecret: process.env.TURNSTILE_SECRET_KEY,
  },

  identityProvider: {
    apiKey: process.env.IDENTITY_PROVIDER_API_KEY,
    webhookSecret: process.env.IDENTITY_PROVIDER_WEBHOOK_SECRET,
  },

  identity: {
    // Keys the Aadhaar HMAC. Must be set, must never be committed, and must
    // never be rotated casually — changing it invalidates every stored hash
    // and so breaks duplicate detection for all existing users.
    aadhaarHashPepper: process.env.AADHAAR_HASH_PEPPER,
  },

  telegram: {
    botToken: process.env.TELEGRAM_BOT_TOKEN,
    // Used to build the t.me deep link the app shows. Without it the link is
    // unusable, so the Telegram endpoints refuse to serve one rather than
    // handing out a broken URL.
    botUsername: process.env.TELEGRAM_BOT_USERNAME,
    webhookSecret: process.env.TELEGRAM_WEBHOOK_SECRET,

    // The two chats every candidate must be in before verification completes.
    // Numeric Telegram chat IDs, negative for groups/channels.
    //  - public: normal join, membership shows up as `member` straight away.
    //  - private: invite-link-with-approval, so a pending join REQUEST is
    //    accepted as satisfying this step (a human admin approves later).
    publicChatId: process.env.TELEGRAM_PUBLIC_CHAT_ID
      ? BigInt(process.env.TELEGRAM_PUBLIC_CHAT_ID)
      : undefined,
    privateChatId: process.env.TELEGRAM_PRIVATE_CHAT_ID
      ? BigInt(process.env.TELEGRAM_PRIVATE_CHAT_ID)
      : undefined,
    publicChatInviteLink: process.env.TELEGRAM_PUBLIC_CHAT_INVITE_LINK,
    privateChatInviteLink: process.env.TELEGRAM_PRIVATE_CHAT_INVITE_LINK,

    // Separate from the two above: the group for candidates who have finished
    // BOTH counters and been selected. Served only to qualified users.
    selectedGroupInviteLink: process.env.TELEGRAM_SELECTED_GROUP_INVITE_LINK,
  },
});
