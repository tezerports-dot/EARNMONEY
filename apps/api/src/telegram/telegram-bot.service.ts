import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class TelegramBotService {
  private readonly logger = new Logger(TelegramBotService.name);

  constructor(private readonly config: ConfigService) {}

  private get baseUrl(): string {
    const token = this.config.get<string>('telegram.botToken');
    if (!token) {
      throw new Error(
        'TELEGRAM_BOT_TOKEN is not set. Create a bot via https://t.me/BotFather and configure it before using Telegram features.',
      );
    }
    return `https://api.telegram.org/bot${token}`;
  }

  async getChatMember(chatId: bigint, telegramUserId: bigint): Promise<{ status: string } | null> {
    try {
      const res = await fetch(
        `${this.baseUrl}/getChatMember?chat_id=${chatId}&user_id=${telegramUserId}`,
      );
      const data = (await res.json()) as { ok: boolean; result?: { status: string } };
      if (!data.ok || !data.result) return null;
      return { status: data.result.status };
    } catch (err) {
      this.logger.error(`getChatMember failed for chat ${chatId}, user ${telegramUserId}: ${err}`);
      return null;
    }
  }

  async sendMessage(telegramUserId: bigint, text: string): Promise<void> {
    try {
      await fetch(`${this.baseUrl}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: telegramUserId.toString(), text }),
      });
    } catch (err) {
      this.logger.error(`sendMessage failed for user ${telegramUserId}: ${err}`);
    }
  }

  /**
   * Call this once, manually, after deploying, to point Telegram's servers
   * at your webhook endpoint. Not called automatically by the app.
   *   POST {baseUrl}/setWebhook  { url, secret_token }
   */
  async setWebhook(url: string, secretToken: string): Promise<void> {
    const res = await fetch(`${this.baseUrl}/setWebhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, secret_token: secretToken }),
    });
    const data = await res.json();
    this.logger.log(`setWebhook response: ${JSON.stringify(data)}`);
  }
}
