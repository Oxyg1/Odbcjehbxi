import { memo, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { formatCompact, type Stand, type ThemeEffect } from '@tgdonate/shared';
import { cn } from '../lib/cn.js';
import { useAppStore, type ActiveEffect } from '../store/app.store.js';
import { Avatar, Card, Pill, ProgressBar } from './ui/primitives.js';
import { Confetti } from './Confetti.js';

/**
 * A single booth in the room grid.
 *
 * The card owns three visual layers:
 *  1. the theme banner (gradient + optional decorative effect);
 *  2. the content (title, goal, totals, listing chips);
 *  3. the live layer — confetti, floating amounts, reaction bursts.
 */

const effectClass: Record<ThemeEffect, string> = {
  NONE: '',
  LOW_POLY: '',
  CYBERPUNK_GRID: 'fx-grid',
  GOLD_ROYALTY: '',
  CRT_SCANLINES: 'fx-scanlines',
  AURORA: '',
};

export const StandCard = memo(function StandCard({
  stand,
  onOpen,
}: {
  stand: Stand;
  onOpen: (standId: string) => void;
}) {
  const effects = useAppStore((state) => state.activeEffects);
  const reactions = useAppStore((state) => state.reactions);

  const myEffects = useMemo(
    () => effects.filter((effect) => effect.standId === stand.id),
    [effects, stand.id],
  );
  const myReactions = useMemo(
    () => reactions.filter((reaction) => reaction.standId === stand.id).slice(-4),
    [reactions, stand.id],
  );

  const topTier = myEffects.reduce<ActiveEffect['tier'] | null>((best, effect) => {
    if (effect.tier === 'WHALE') return 'WHALE';
    if (effect.tier === 'MAJOR' && best !== 'WHALE') return 'MAJOR';
    return best ?? effect.tier;
  }, null);

  const palette = stand.theme.palette;
  const donationTiers = stand.listings.filter((listing) => listing.kind === 'DONATION_TIER');
  const otherListings = stand.listings.filter((listing) => listing.kind !== 'DONATION_TIER');

  return (
    <motion.button
      type="button"
      onClick={() => onOpen(stand.id)}
      layout
      className="block w-full text-left"
      // A major/whale drop shakes the card it landed on.
      animate={
        topTier === 'MAJOR' || topTier === 'WHALE'
          ? { x: [0, -5, 4, -3, 2, 0], rotate: [0, -0.5, 0.4, -0.3, 0] }
          : { x: 0, rotate: 0 }
      }
      transition={{ duration: 0.5 }}
      whileTap={{ scale: 0.985 }}
    >
      <Card
        className={cn('flex h-full flex-col gap-2 p-3', effectClass[stand.theme.effect ?? 'NONE'])}
        style={{
          backgroundColor: `color-mix(in srgb, ${palette.surface} 72%, transparent)`,
          ...(topTier
            ? {
                boxShadow: `var(--glass-shadow), 0 0 0 1.5px ${palette.accent}, 0 0 28px -6px ${palette.accent}`,
              }
            : {}),
        }}
      >
        {/* Banner */}
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-[72px] opacity-70"
          style={{ backgroundImage: palette.banner, backgroundSize: 'cover' }}
        />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[72px] bg-gradient-to-b from-transparent to-[var(--card-surface)]"
          style={{ ['--card-surface' as string]: palette.surface }}
        />

        {/* Header */}
        <div className="relative z-2 flex items-center gap-2">
          <Avatar
            src={stand.owner.photoUrl}
            name={stand.owner.displayName}
            size={32}
            ring={stand.owner.badge ? badgeColor(stand.owner.badge.rank) : null}
          />
          <p className="min-w-0 flex-1 truncate text-[12px] leading-[14px] font-semibold text-muted">
            @{stand.owner.username ?? stand.owner.displayName}
          </p>
          {stand.isOwnerOnline ? (
            <span
              className="animate-pulse-ring h-1.5 w-1.5 shrink-0 rounded-full bg-accent"
              style={{ ['--pulse-color' as string]: 'rgba(73,223,100,0.5)' }}
            />
          ) : null}
        </div>

        {/* Title gets the full card width so it wraps to a second line rather
            than truncating — a half-width card cannot hold a name on one. */}
        <p className="relative z-2 line-clamp-2 text-[17px] leading-[21px] font-semibold">
          {stand.title}
        </p>

        {/* Goal */}
        {stand.goal ? (
          <p className="relative z-2 line-clamp-2 text-[12px] leading-[15px] text-alpha-1">
            {stand.goal}
          </p>
        ) : null}

        {stand.goalTargetStars ? (
          <div className="relative z-2 flex flex-col gap-1">
            <ProgressBar
              value={stand.totalStarsReceived}
              max={stand.goalTargetStars}
              accent={palette.accent}
            />
            <p className="text-[11px] font-semibold text-alpha-2">
              {formatCompact(stand.totalStarsReceived)} / {formatCompact(stand.goalTargetStars)} ⭐
            </p>
          </div>
        ) : null}

        {/* Totals */}
        <div className="relative z-2 mt-auto flex flex-wrap items-center gap-1">
          <Pill tone="accent">
            <span style={{ color: palette.accent }}>⭐ {formatCompact(stand.totalStarsReceived)}</span>
          </Pill>
          {stand.totalGiftsReceived > 0 ? <Pill tone="purple">🎁 {stand.totalGiftsReceived}</Pill> : null}
          <Pill>👥 {formatCompact(stand.supporterCount)}</Pill>
        </div>

        {/* Listing chips */}
        {(donationTiers.length > 0 || otherListings.length > 0) && (
          <div className="relative z-2 flex flex-wrap gap-1">
            {donationTiers.slice(0, 3).map((listing) => (
              <span
                key={listing.id}
                className="glass-shadow rounded-full px-2 py-1 text-[11px] font-bold"
                style={{
                  backgroundColor: `color-mix(in srgb, ${palette.accent} 16%, transparent)`,
                  color: palette.accent,
                }}
              >
                {listing.priceStars} ⭐
              </span>
            ))}
            {otherListings.length > 0 ? (
              <span className="glass-shadow rounded-full bg-white/10 px-2 py-1 text-[11px] font-bold">
                +{otherListings.length} offer{otherListings.length > 1 ? 's' : ''}
              </span>
            ) : null}
          </div>
        )}

        {/* Live layer */}
        <AnimatePresence>
          {myEffects.map((effect) => (
            <motion.div
              key={effect.id}
              className="pointer-events-none absolute inset-x-0 bottom-8 z-10 flex justify-center"
              initial={{ opacity: 0, y: 14, scale: 0.85 }}
              animate={{ opacity: 1, y: -26, scale: 1 }}
              exit={{ opacity: 0, y: -46 }}
              transition={{ duration: 0.9, ease: 'easeOut' }}
            >
              <span
                className="glass-shadow rounded-full px-2.5 py-1 text-[13px] font-black"
                style={{
                  backgroundColor: `color-mix(in srgb, ${palette.accent} 24%, transparent)`,
                  color: palette.accent,
                  textShadow: `0 0 12px ${palette.accent}`,
                }}
              >
                +{effect.amountStars} ⭐
              </span>
            </motion.div>
          ))}
        </AnimatePresence>

        {myEffects.length > 0 ? <Confetti accent={palette.accent} tier={topTier ?? 'MICRO'} /> : null}

        <AnimatePresence>
          {myReactions.map((reaction, index) => (
            <motion.span
              key={reaction.id}
              className="pointer-events-none absolute bottom-4 z-10 text-[18px]"
              style={{ right: 12 + index * 18 }}
              initial={{ opacity: 0, y: 0, scale: 0.6 }}
              animate={{ opacity: 1, y: -40, scale: 1 }}
              exit={{ opacity: 0, y: -60 }}
              transition={{ duration: 1.4, ease: 'easeOut' }}
            >
              {reaction.emoji}
            </motion.span>
          ))}
        </AnimatePresence>
      </Card>
    </motion.button>
  );
});

function badgeColor(rank: number): string {
  if (rank === 1) return '#f1aa05';
  if (rank === 2) return '#c5c5b9';
  if (rank === 3) return '#d88b6b';
  return '#6d51de';
}
