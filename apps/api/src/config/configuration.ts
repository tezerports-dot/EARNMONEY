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

  telegram: {
    botToken: process.env.TELEGRAM_BOT_TOKEN,
    webhookSecret: process.env.TELEGRAM_WEBHOOK_SECRET,
    // Configure these once the institute's actual channel/group is created.
    // Numeric Telegram chat IDs are negative for groups/channels.
    requiredChatIds: (process.env.TELEGRAM_REQUIRED_CHAT_IDS || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => BigInt(s)),
  },
});
