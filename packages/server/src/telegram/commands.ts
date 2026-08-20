import { InlineKeyboard, type Bot } from 'grammy';
import { formatCompact } from '@tgdonate/shared';
import { logger } from '../lib/logger.js';
import { prisma } from '../lib/prisma.js';
import { leaderboardService } from '../services/leaderboard.service.js';
import { userService } from '../services/user.service.js';
import { buildMiniAppLink, type TgDonateContext } from './bot.js';

/**
 * Bot-side surface. The Mini App is the product; the bot exists to hand out
 * deep links, deliver notifications and answer the two or three questions
 * people ask in chat.
 */
export function registerCommandHandlers(instance: Bot<TgDonateContext>): void {
  instance.command('start', async (ctx) => {
    const startPayload = ctx.match?.trim();
    const link = buildMiniAppLink(startPayload || undefined);

    // `/start stand_<id>` from a shared stand link lands the user on that stand.
    const keyboard = new InlineKeyboard().url(
      startPayload?.startsWith('stand_') ? '🎪 Open this stand' : '🚀 Open TgDonate',
      link,
    );

    await ctx.reply(
      [
        '*TgDonate* — set up a stand, get supported in Stars and NFT Gifts.',
        '',
        '• Build a booth and list donation tiers, services or gifts',
        '• Hang out in live rooms and watch donations land in real time',
        '• Break 1000 ⭐ and your drop is broadcast to every room at once',
      ].join('\n'),
      { parse_mode: 'Markdown', reply_markup: keyboard },
    );
  });

  instance.command('stand', async (ctx) => {
    const telegramId = ctx.from?.id;
    if (!telegramId) return;

    const user = await userService.findByTelegramId(telegramId);
    const stand = user
      ? await prisma.stand.findUnique({ where: { ownerId: user.id } })
      : null;

    if (!stand) {
      await ctx.reply('You have no stand yet — open the app to build one.', {
        reply_markup: new InlineKeyboard().url('Build my stand', buildMiniAppLink()),
      });
      return;
    }

    await ctx.reply(
      [
        `*${escapeMarkdown(stand.title)}*`,
        stand.goal ? `_${escapeMarkdown(stand.goal)}_` : null,
        '',
        `⭐ ${formatCompact(stand.totalStarsReceived)} received`,
        `🎁 ${stand.totalGiftsReceived} gifts`,
        `👥 ${stand.supporterCount} supporters`,
      ]
        .filter(Boolean)
        .join('\n'),
      {
        parse_mode: 'Markdown',
        reply_markup: new InlineKeyboard().url(
          'Open my stand',
          buildMiniAppLink(`stand_${stand.id}`),
        ),
      },
    );
  });

  instance.command('top', async (ctx) => {
    const board = await leaderboardService.get('DAILY', { limit: 10 });
    if (board.rows.length === 0) {
      await ctx.reply('No donations yet today. Be the first whale. 🐋');
      return;
    }

    const medals = ['🥇', '🥈', '🥉'];
    const lines = board.rows.map((row, index) => {
      const marker = medals[index] ?? `${row.rank}.`;
      return `${marker} ${escapeMarkdown(row.user.displayName)} — ${formatCompact(row.starsDonated)} ⭐`;
    });

    await ctx.reply([`*Today's top donors*`, '', ...lines].join('\n'), {
      parse_mode: 'Markdown',
      reply_markup: new InlineKeyboard().url('See full board', buildMiniAppLink('leaderboard')),
    });
  });

  instance.command('help', async (ctx) => {
    await ctx.reply(
      [
        '*TgDonate commands*',
        '',
        '/stand — your booth and its totals',
        '/top — today’s top donors',
        '/start — open the Mini App',
        '',
        `Platform fee is ${(500 / 100).toFixed(0)}% on Stars transactions.`,
      ].join('\n'),
      { parse_mode: 'Markdown' },
    );
  });

  /** Shared stands render as an inline result, which is how the loop spreads. */
  instance.on('inline_query', async (ctx) => {
    const query = ctx.inlineQuery.query.trim().slice(0, 64);
    const stands = await prisma.stand.findMany({
      where: {
        isPublished: true,
        ...(query ? { title: { contains: query, mode: 'insensitive' as const } } : {}),
      },
      orderBy: { totalStarsReceived: 'desc' },
      take: 10,
      include: { owner: { select: { displayName: true, photoUrl: true } } },
    });

    await ctx
      .answerInlineQuery(
        stands.map((stand) => ({
          type: 'article' as const,
          id: stand.id,
          title: stand.title,
          description:
            stand.goal ?? `${formatCompact(stand.totalStarsReceived)} ⭐ raised so far`,
          ...(stand.owner.photoUrl ? { thumbnail_url: stand.owner.photoUrl } : {}),
          input_message_content: {
            message_text: [
              `*${escapeMarkdown(stand.title)}*`,
              stand.goal ? `_${escapeMarkdown(stand.goal)}_` : null,
              '',
              `⭐ ${formatCompact(stand.totalStarsReceived)} raised by ${stand.supporterCount} supporters`,
            ]
              .filter(Boolean)
              .join('\n'),
            parse_mode: 'Markdown' as const,
          },
          reply_markup: new InlineKeyboard().url(
            'Support this stand',
            buildMiniAppLink(`stand_${stand.id}`),
          ),
        })),
        { cache_time: 30, is_personal: false },
      )
      .catch((error) => logger.debug({ err: error }, 'inline query answer failed'));
  });
}

/** Escapes the characters that break Telegram's legacy Markdown parser. */
function escapeMarkdown(value: string): string {
  return value.replace(/([_*`[\]])/g, '\\$1');
}
