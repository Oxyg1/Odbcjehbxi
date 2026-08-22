import { memo, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { formatCompact, type Stand, type ThemeEffect } from '@tgdonate/shared';
import { cn } from '../lib/cn.js';
import { haptics } from '../lib/telegram.js';
import { useAppStore, type ActiveEffect } from '../store/app.store.js';
import { Avatar } from './ui/primitives.js';
import { Confetti } from './Confetti.js';
import { StandAwning } from './StandAwning.js';

/**
 * A booth on the floor.
 *
 * Built to read as a market stall rather than a list row: canopy on top, a
 * lit counter under it, the goal meter, and the donate tiers sitting right on
 * the card. Tapping a tier starts a payment immediately — the fewer taps
 * between wanting to give and giving, the more people give.
 */

/** Per-theme decoration applied to the card body. */
const bodyEffect: Record<ThemeEffect, string> = {
  NONE: '',
  LOW_POLY: '',
  CYBERPUNK_GRID: 'fx-grid',
  GOLD_ROYALTY: '',
  CRT_SCANLINES: 'fx-scanlines',
  AURORA: '',
};

const QUICK_TIERS = [10, 50, 100] as const;

export const StandCard = memo(function StandCard({
  stand,
  onOpen,
  onQuickDonate,
}: {
  stand: Stand;
  onOpen: (standId: string) => void;
  /** Fires a one-tap donation. Omitted on the editor's own preview. */
  onQuickDonate?: (standId: string, amountStars: number) => void;
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
  const effect = stand.theme.effect ?? 'NONE';
  const goalPct = stand.goalTargetStars
    ? Math.min(100, (stand.totalStarsReceived / stand.goalTargetStars) * 100)
    : null;

  // Tiers the owner configured, falling back to sensible defaults so a fresh
  // stand is still donatable — an empty booth that cannot take money is dead
  // weight on the floor.
  const tiers = useMemo(() => {
    const configured = stand.listings
      .filter((l) => l.kind === 'DONATION_TIER' && l.priceStars !== null)
      .map((l) => l.priceStars as number);

    // Always offer three. A single tier gives the eye nothing to choose
    // between, and choosing between amounts is most of what makes someone
    // pick the middle one instead of leaving.
    const merged = [...new Set([...configured, ...QUICK_TIERS])];
    return merged.slice(0, 3).sort((a, b) => a - b);
  }, [stand.listings]);

  return (
    <motion.div
      layout
      className="relative"
      animate={
        topTier === 'MAJOR' || topTier === 'WHALE'
          ? { x: [0, -5, 4, -3, 2, 0], rotate: [0, -0.6, 0.5, -0.3, 0] }
          : { x: 0, rotate: 0 }
      }
      transition={{ duration: 0.5 }}
    >
      <div
        className={cn(
          'squircle-3xl relative flex h-full flex-col overflow-hidden',
          'glass-shadow transition-shadow duration-300',
          bodyEffect[effect],
        )}
        style={{
          background: `linear-gradient(180deg,
            color-mix(in srgb, ${palette.surface} 92%, #000) 0%,
            color-mix(in srgb, ${palette.surface} 74%, transparent) 100%)`,
          ...(topTier
            ? {
                boxShadow: `var(--glass-shadow), 0 0 0 1.5px ${palette.accent}, 0 0 30px -6px ${palette.accent}`,
              }
            : {}),
        }}
      >
        {/* Theme wash behind everything. */}
        <div
          className="pointer-events-none absolute inset-0 opacity-45"
          style={{ backgroundImage: palette.banner, backgroundSize: 'cover' }}
        />

        <StandAwning
          accent={palette.accent}
          surface={palette.surface}
          effect={effect}
          label={stand.title}
        />

        {/* Body sits below the canopy. */}
        <button
          type="button"
          onClick={() => onOpen(stand.id)}
          className="relative z-4 flex flex-1 flex-col gap-1.5 px-2.5 pt-[42px] pb-2 text-left"
        >
          <div className="flex items-center gap-1.5">
            <Avatar
              src={stand.owner.photoUrl}
              name={stand.owner.displayName}
              size={22}
              ring={stand.owner.badge ? badgeColor(stand.owner.badge.rank) : null}
            />
            <span className="min-w-0 flex-1 truncate text-[11px] leading-[13px] font-semibold text-alpha-2">
              @{stand.owner.username ?? stand.owner.displayName}
            </span>
            {stand.isOwnerOnline ? (
              <span
                className="animate-pulse-ring h-1.5 w-1.5 shrink-0 rounded-full"
                style={{
                  backgroundColor: palette.accent,
                  ['--pulse-color' as string]: `color-mix(in srgb, ${palette.accent} 50%, transparent)`,
                }}
              />
            ) : null}
          </div>

          <p className="line-clamp-2 text-[15px] leading-[18px] font-bold tracking-[-0.3px]">
            {stand.title}
          </p>

          {stand.goal ? (
            <p className="line-clamp-1 text-[11px] leading-[14px] text-alpha-2">{stand.goal}</p>
          ) : null}

          {/* Goal meter — the progress bar is the card's heartbeat. */}
          {goalPct !== null ? (
            <div className="mt-auto flex flex-col gap-1 pt-1">
              <div className="h-[7px] w-full overflow-hidden rounded-full bg-black/55">
                <motion.div
                  className="h-full rounded-full"
                  style={{
                    background: `linear-gradient(90deg, ${palette.accent}, color-mix(in srgb, ${palette.accent} 55%, #fff))`,
                    boxShadow: `0 0 10px -1px ${palette.accent}`,
                  }}
                  initial={false}
                  animate={{ width: `${goalPct}%` }}
                  transition={{ type: 'spring', damping: 26, stiffness: 200 }}
                />
              </div>
              <div className="flex items-baseline justify-between">
                <span
                  className="text-[13px] leading-none font-black"
                  style={{ color: palette.accent }}
                >
                  {formatCompact(stand.totalStarsReceived)}
                  <span className="ml-0.5 text-[10px]">⭐</span>
                </span>
                <span className="text-[10px] font-semibold text-alpha-3">
                  {Math.round(goalPct)}%
                </span>
              </div>
            </div>
          ) : (
            <div className="mt-auto flex items-baseline gap-2 pt-1">
              <span className="text-[15px] leading-none font-black" style={{ color: palette.accent }}>
                {formatCompact(stand.totalStarsReceived)}
                <span className="ml-0.5 text-[10px]">⭐</span>
              </span>
              <span className="text-[10px] font-semibold text-alpha-3">
                {formatCompact(stand.supporterCount)} 👥
              </span>
            </div>
          )}
        </button>

        {/* One-tap donate rail. Sits outside the open-stand button so a tap
            here pays instead of navigating. */}
        {onQuickDonate ? (
          <div className="relative z-4 flex gap-1 px-2 pb-2">
            {tiers.map((amount) => (
              <button
                key={amount}
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  haptics.impact('medium');
                  onQuickDonate(stand.id, amount);
                }}
                className={cn(
                  'stars-button pressable flex-1 rounded-xl py-1.5',
                  'text-[12px] leading-none font-black',
                )}
              >
                {amount}
                <span className="ml-0.5 text-[9px]">⭐</span>
              </button>
            ))}
          </div>
        ) : null}

        {/* Live layer */}
        <AnimatePresence>
          {myEffects.map((fx) => (
            <motion.div
              key={fx.id}
              className="pointer-events-none absolute inset-x-0 top-1/2 z-10 flex justify-center"
              initial={{ opacity: 0, y: 10, scale: 0.8 }}
              animate={{ opacity: 1, y: -30, scale: 1.1 }}
              exit={{ opacity: 0, y: -52 }}
              transition={{ duration: 0.95, ease: 'easeOut' }}
            >
              <span
                className="rounded-full px-3 py-1 text-[15px] font-black"
                style={{
                  background: 'var(--stars-gradient)',
                  color: '#3a2500',
                  boxShadow: `0 0 22px -2px var(--stars-glow)`,
                }}
              >
                +{fx.amountStars} ⭐
              </span>
            </motion.div>
          ))}
        </AnimatePresence>

        {myEffects.length > 0 ? (
          <Confetti accent={palette.accent} tier={topTier ?? 'MICRO'} />
        ) : null}

        <AnimatePresence>
          {myReactions.map((reaction, index) => (
            <motion.span
              key={reaction.id}
              className="pointer-events-none absolute bottom-10 z-10 text-[17px]"
              style={{ right: 10 + index * 17 }}
              initial={{ opacity: 0, y: 0, scale: 0.6 }}
              animate={{ opacity: 1, y: -42, scale: 1 }}
              exit={{ opacity: 0, y: -62 }}
              transition={{ duration: 1.4, ease: 'easeOut' }}
            >
              {reaction.emoji}
            </motion.span>
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  );
});

function badgeColor(rank: number): string {
  if (rank === 1) return '#ffc107';
  if (rank === 2) return '#c5c5b9';
  if (rank === 3) return '#d88b6b';
  return '#6d51de';
}
