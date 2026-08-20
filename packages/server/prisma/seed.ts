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
      surface: palette.surface4,
      accent: palette.accent,
      accentSoft: 'rgba(73,223,100,0.24)',
      banner: gradients.accentGlow,
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
      surface: palette.surface2,
      accent: palette.mutedForeground,
      accentSoft: 'rgba(109,109,113,0.28)',
      banner: 'linear-gradient(180deg, rgba(109,109,113,0.22) 0%, rgba(109,109,113,0) 100%)',
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
      surface: '#1b2233',
      accent: '#b0e6ff',
      accentSoft: 'rgba(176,230,255,0.26)',
      banner: gradients.lowPoly,
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
      surface: '#160c33',
      accent: '#d90751',
      accentSoft: 'rgba(217,7,81,0.3)',
      banner: gradients.cyberpunk,
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
      surface: '#0d1a0f',
      accent: '#49df64',
      accentSoft: 'rgba(73,223,100,0.3)',
      banner: 'linear-gradient(160deg, #0d1a0f 0%, #1f5c2b 60%, #49df64 100%)',
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
      surface: '#0e1f2b',
      accent: palette.tifany,
      accentSoft: 'rgba(104,251,221,0.28)',
      banner: gradients.aurora,
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
      surface: '#2a1a05',
      accent: palette.gold,
      accentSoft: 'rgba(241,170,5,0.32)',
      banner: gradients.royalty,
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
