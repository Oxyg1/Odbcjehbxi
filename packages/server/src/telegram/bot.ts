import { Bot, GrammyError, HttpError, type Context } from 'grammy';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';
import { registerPaymentHandlers } from './payments.js';
import { registerCommandHandlers } from './commands.js';

export type TgDonateContext = Context;

/**
 * The bot instance is created eagerly (so `createInvoiceLink` is callable from
 * the API layer) but only *started* on nodes with ENABLE_BOT=true. Running two
 * long-pollers against one token drops updates at random.
 */
export const bot = new Bot<TgDonateContext>(env.TELEGRAM_BOT_TOKEN);

let started = false;

export async function startBot(): Promise<void> {
  if (!env.ENABLE_BOT) {
    logger.info('bot disabled on this node (ENABLE_BOT=false)');
    return;
  }
  if (started) return;

  registerCommandHandlers(bot);
  registerPaymentHandlers(bot);

  bot.catch((error) => {
    const context = error.ctx;
    const err = error.error;
    if (err instanceof GrammyError) {
      logger.error(
        { updateId: context.update.update_id, description: err.description },
        'telegram API error',
      );
    } else if (err instanceof HttpError) {
      logger.error({ err }, 'could not reach Telegram');
    } else {
      logger.error({ err }, 'unhandled bot error');
    }
  });

  await bot.init();
  started = true;

  if (env.BOT_MODE === 'webhook') {
    const url = `${env.PUBLIC_API_URL.replace(/\/$/, '')}/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`;
    await bot.api.setWebhook(url, {
      allowed_updates: [
        'message',
        'callback_query',
        'pre_checkout_query',
        'inline_query',
        'chat_member',
      ],
      drop_pending_updates: false,
      secret_token: env.TELEGRAM_WEBHOOK_SECRET,
    });
    logger.info({ url }, 'telegram webhook registered');
  } else {
    // Long polling: fire-and-forget, grammY manages its own loop.
    await bot.api.deleteWebhook({ drop_pending_updates: false }).catch(() => undefined);
    void bot.start({
      onStart: (info) => logger.info({ username: info.username }, 'bot polling started'),
    });
  }
}

export async function stopBot(): Promise<void> {
  if (!started) return;
  if (env.BOT_MODE === 'polling') {
    await bot.stop();
  }
  started = false;
}

/** Deep link into the Mini App, optionally landing on a specific stand/room. */
export function buildMiniAppLink(startParam?: string): string {
  const base = `https://t.me/${env.BOT_USERNAME}/app`;
  return startParam ? `${base}?startapp=${encodeURIComponent(startParam)}` : base;
}
