import { PrismaClient } from '@prisma/client';
import { gradients, palette } from '@tgdonate/shared';

/**
 * Seed data: the starter rooms and the theme catalogue.
 *
 * Palettes reuse the shared design tokens so a stand card always sits correctly
 * against the app's near-black canvas, whatever theme its owner picks.
 */
const prisma = new PrismaClient();

const rooms = [
  {
    slug: 'creators-hub',
    name: 'Creators Hub',
    description: 'Artists, editors and devs taking commissions.',
    emoji: '🎨',
    accent: palette.accent,
    capacity: 50,
    sortOrder: 0,
  },
  {
    slug: 'meme-lords',
    name: 'Meme Lords',
    description: 'Chaos, bits and questionable investments.',
    emoji: '🐸',
    accent: palette.gold,
    capacity: 50,
    sortOrder: 1,
  },
  {
    slug: 'crypto-whale-lounge',
    name: 'Crypto Whale Lounge',
    description: 'Big drops only. Minimum flex: 1000 ⭐.',
    emoji: '🐋',
    accent: palette.tifany,
    capacity: 30,
    sortOrder: 2,
  },
  {
    slug: 'gift-traders',
    name: 'Gift Traders',
    description: 'NFT Gift flips, swaps and floor watching.',
    emoji: '🎁',
    accent: palette.purple,
    capacity: 50,
    sortOrder: 3,
  },
  {
    slug: 'newcomers',
    name: 'Newcomers',
    description: 'Fresh stands. Everyone starts somewhere.',
    emoji: '🌱',
    accent: palette.primary,
    capacity: 50,
    sortOrder: 4,
  },
];

const themes = [
  {
    slug: 'midnight',
    name: 'Midnight',
    description: 'The house style. Clean glass on near-black.',
    rarity: 'FREE' as const,
    priceStars: 0,
    effect: 'NONE' as const,
    palette: {
      surface: '#1d2a20',
      accent: '#49df64',
      accentSoft: 'rgba(73,223,100,0.28)',
      banner: 'radial-gradient(120% 70% at 50% 0%, rgba(73,223,100,0.30) 0%, rgba(20,20,20,0) 65%)',
      foreground: palette.foreground,
    },
  },
  {
    slug: 'slate',
    name: 'Slate',
    description: 'Muted, quiet, lets your listings do the talking.',
    rarity: 'FREE' as const,
    priceStars: 0,
    effect: 'NONE' as const,
    palette: {
      surface: '#1c1c1c',
      accent: '#9aa0a6',
      accentSoft: 'rgba(154,160,166,0.26)',
      banner: 'radial-gradient(120% 70% at 50% 0%, rgba(154,160,166,0.22) 0%, rgba(20,20,20,0) 65%)',
      foreground: palette.foreground,
    },
  },
  {
    slug: 'ps1-low-poly',
    name: 'PS1 Low-Poly',
    description: 'Untextured polygons, warm haze, 1997 energy.',
    rarity: 'PREMIUM' as const,
    priceStars: 250,
    effect: 'LOW_POLY' as const,
    palette: {
      surface: '#243049',
      accent: '#7fd4ff',
      accentSoft: 'rgba(127,212,255,0.3)',
      banner:
        'linear-gradient(150deg, #2b4a7a 0%, #4d7bb5 38%, #b0e6ff 70%, #efe5d3 100%)',
      foreground: palette.foreground,
    },
  },
  {
    slug: 'cyberpunk',
    name: 'Cyberpunk',
    description: 'Magenta grid, deep violet, neon bleed.',
    rarity: 'PREMIUM' as const,
    priceStars: 350,
    effect: 'CYBERPUNK_GRID' as const,
    palette: {
      surface: '#1a0b33',
      accent: '#ff2e88',
      accentSoft: 'rgba(255,46,136,0.34)',
      banner:
        'linear-gradient(150deg, #0e0737 0%, #6d51de 45%, #ff2e88 100%)',
      foreground: palette.foreground,
    },
  },
  {
    slug: 'crt',
    name: 'CRT',
    description: 'Scanlines and phosphor green. Boots loud.',
    rarity: 'PREMIUM' as const,
    priceStars: 300,
    effect: 'CRT_SCANLINES' as const,
    palette: {
      surface: '#07160a',
      accent: '#39ff7a',
      accentSoft: 'rgba(57,255,122,0.32)',
      banner: 'linear-gradient(170deg, #07160a 0%, #10401d 55%, #39ff7a 100%)',
      foreground: palette.foreground,
    },
  },
  {
    slug: 'aurora',
    name: 'Aurora',
    description: 'Cold teal drifting into deep violet.',
    rarity: 'PREMIUM' as const,
    priceStars: 400,
    effect: 'AURORA' as const,
    palette: {
      surface: '#0d2430',
      accent: '#68fbdd',
      accentSoft: 'rgba(104,251,221,0.32)',
      banner:
        'linear-gradient(150deg, #68fbdd 0%, #1689ff 42%, #984995 78%, #0d2430 100%)',
      foreground: palette.foreground,
    },
  },
  {
    slug: 'gold-royalty',
    name: 'Gold Royalty',
    description: 'For stands that have already made it.',
    rarity: 'LEGENDARY' as const,
    priceStars: 1500,
    effect: 'GOLD_ROYALTY' as const,
    palette: {
      surface: '#332005',
      accent: '#ffcb45',
      accentSoft: 'rgba(255,203,69,0.36)',
      banner:
        'linear-gradient(150deg, #a43606 0%, #f1aa05 40%, #ffe823 72%, #332005 100%)',
      foreground: palette.foreground,
    },
  },
];

async function main(): Promise<void> {
  for (const room of rooms) {
    await prisma.room.upsert({
      where: { slug: room.slug },
      create: room,
      update: {
        name: room.name,
        description: room.description,
        emoji: room.emoji,
        accent: room.accent,
        capacity: room.capacity,
        sortOrder: room.sortOrder,
      },
    });
  }
  console.log(`seeded ${rooms.length} rooms`);

  for (const theme of themes) {
    await prisma.standTheme.upsert({
      where: { slug: theme.slug },
      create: { ...theme, palette: theme.palette as never },
      update: {
        name: theme.name,
        description: theme.description,
        rarity: theme.rarity,
        priceStars: theme.priceStars,
        effect: theme.effect,
        palette: theme.palette as never,
        isActive: true,
      },
    });
  }
  console.log(`seeded ${themes.length} stand themes`);
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(() => {
    void prisma.$disconnect();
  });
