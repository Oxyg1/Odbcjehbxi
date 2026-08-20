import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { formatCompact } from '@tgdonate/shared';
import { haptics } from '../lib/telegram.js';
import { useAppStore } from '../store/app.store.js';
import { Avatar, Button } from './ui/primitives.js';

/**
 * "The Megaphone" — the whale-tier global broadcast.
 *
 * Every online user sees this, in every room, the moment someone drops over
 * 1000 Stars or a legendary gift. It is the app's status engine: the reason to
 * spend big is that everyone watches it happen.
 */
export function MegaphoneOverlay() {
  const broadcast = useAppStore((state) => state.globalBroadcast);
  const dismiss = useAppStore((state) => state.dismissGlobalBroadcast);
  const focusStand = useAppStore((state) => state.focusStand);
  const setScreen = useAppStore((state) => state.setScreen);

  // A second heavy tap as the overlay lands, so it registers even if the user
  // is looking away from the screen.
  useEffect(() => {
    if (!broadcast) return;
    haptics.impact('heavy');
  }, [broadcast?.id]);

  return (
    <AnimatePresence>
      {broadcast ? (
        <motion.div
          key={broadcast.id}
          className="fixed inset-0 z-[100] flex items-center justify-center px-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
        >
          {/* Scrim */}
          <motion.div
            className="absolute inset-0 bg-black/78 backdrop-blur-[6px]"
            onClick={dismiss}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />

          {/* Sweeping light behind the card */}
          <motion.div
            className="pointer-events-none absolute inset-x-0 h-[320px]"
            style={{
              background:
                'linear-gradient(94deg, rgba(109,81,222,0.45) 0%, rgba(22,137,255,0.5) 48%, rgba(104,251,221,0.45) 100%)',
              filter: 'blur(60px)',
            }}
            initial={{ opacity: 0, scaleX: 0.4 }}
            animate={{ opacity: 1, scaleX: 1 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />

          <motion.div
            className="glass-shadow glass squircle-4xl relative w-full max-w-[380px] overflow-hidden bg-surface-2/90 p-5"
            initial={{ scale: 0.7, y: 40, rotateX: 18 }}
            animate={{ scale: 1, y: 0, rotateX: 0 }}
            exit={{ scale: 0.85, y: 24, opacity: 0 }}
            transition={{ type: 'spring', damping: 20, stiffness: 260 }}
          >
            {/* Animated top rail */}
            <motion.div
              className="absolute inset-x-0 top-0 h-[3px]"
              style={{
                background:
                  'linear-gradient(94deg, #6d51de 0%, #1689ff 48%, #68fbdd 100%)',
              }}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.45, ease: 'easeOut' }}
            />

            <motion.p
              className="mb-3 text-center text-[11px] font-black tracking-[2px] text-tifany uppercase"
              animate={{ opacity: [0.55, 1, 0.55] }}
              transition={{ duration: 1.6, repeat: Infinity }}
            >
              🐋 Whale Alert
            </motion.p>

            <div className="mb-4 flex items-center justify-center gap-3">
              <div className="flex flex-col items-center gap-1">
                <Avatar
                  src={broadcast.donation.donor?.photoUrl ?? null}
                  name={
                    broadcast.donation.isAnonymous
                      ? 'Anonymous'
                      : broadcast.donation.donor?.displayName ?? 'Someone'
                  }
                  size={52}
                  ring="#68fbdd"
                />
                <span className="max-w-[92px] truncate text-[12px] font-bold">
                  {broadcast.donation.isAnonymous
                    ? 'Anonymous'
                    : broadcast.donation.donor?.displayName ?? 'Someone'}
                </span>
              </div>

              <motion.div
                className="flex flex-col items-center px-1"
                animate={{ x: [0, 5, 0] }}
                transition={{ duration: 1.1, repeat: Infinity }}
              >
                <span className="text-[22px]">→</span>
              </motion.div>

              <div className="flex flex-col items-center gap-1">
                <Avatar
                  src={broadcast.donation.receiver.photoUrl}
                  name={broadcast.donation.receiver.displayName}
                  size={52}
                  ring="#f1aa05"
                />
                <span className="max-w-[92px] truncate text-[12px] font-bold">
                  {broadcast.donation.receiver.displayName}
                </span>
              </div>
            </div>

            <motion.p
              className="text-center text-[38px] leading-none font-black"
              style={{
                background: 'linear-gradient(94deg, #68fbdd 0%, #ffffff 50%, #f1aa05 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
              initial={{ scale: 0.6 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', damping: 12, stiffness: 220, delay: 0.1 }}
            >
              {broadcast.donation.gift
                ? broadcast.donation.gift.title
                : `${formatCompact(broadcast.donation.amountStars)} ⭐`}
            </motion.p>

            {broadcast.donation.gift ? (
              <p className="mt-1 text-center text-[12px] font-bold text-gold uppercase">
                {broadcast.donation.gift.rarity} gift
              </p>
            ) : null}

            {broadcast.donation.message ? (
              <p className="mt-3 line-clamp-3 text-center text-[13px] text-alpha-1 italic">
                “{broadcast.donation.message}”
              </p>
            ) : null}

            <p className="mt-2 text-center text-[12px] text-alpha-2">
              on <span className="font-bold text-white">{broadcast.donation.standTitle}</span>
            </p>

            <div className="mt-5 flex gap-2">
              <Button variant="ghost" fullWidth onClick={dismiss} haptic="light">
                Dismiss
              </Button>
              <Button
                variant="accent"
                fullWidth
                haptic="medium"
                onClick={() => {
                  focusStand(broadcast.jump.standId);
                  setScreen('stand');
                  dismiss();
                }}
              >
                Jump to stand
              </Button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/** Room-scoped banner for MAJOR-tier drops. Lighter than the global overlay. */
export function RoomBanner() {
  const banner = useAppStore((state) => state.roomBanner);
  const dismiss = useAppStore((state) => state.dismissRoomBanner);

  return (
    <AnimatePresence>
      {banner ? (
        <motion.button
          key={banner.id}
          type="button"
          onClick={dismiss}
          className={[
            'glass-shadow glass fixed left-1/2 z-[80] w-[calc(100%-32px)] max-w-[420px]',
            'squircle-xl overflow-hidden bg-surface-3/92 px-3 py-2.5',
          ].join(' ')}
          style={{ top: 'calc(var(--tg-viewport-safe-area-inset-top) + 56px)' }}
          initial={{ y: -80, opacity: 0, x: '-50%' }}
          animate={{ y: 0, opacity: 1, x: '-50%' }}
          exit={{ y: -80, opacity: 0, x: '-50%' }}
          transition={{ type: 'spring', damping: 24, stiffness: 300 }}
        >
          <div
            className="absolute inset-x-0 top-0 h-[2px]"
            style={{ background: 'linear-gradient(95.81deg,#f1aa05 .35%,#fbae61 49%,#e6b94e 100%)' }}
          />
          <div className="flex items-center gap-2.5">
            <Avatar
              src={banner.donation.donor?.photoUrl ?? null}
              name={banner.donation.donor?.displayName ?? 'Anonymous'}
              size={32}
              ring="#f1aa05"
            />
            <div className="min-w-0 flex-1 text-left">
              <p className="truncate text-[13px] leading-[16px] font-bold">
                {banner.donation.isAnonymous
                  ? 'Anonymous'
                  : banner.donation.donor?.displayName ?? 'Someone'}
                <span className="font-normal text-alpha-2"> → </span>
                {banner.donation.standTitle}
              </p>
              {banner.donation.message ? (
                <p className="truncate text-[11px] text-alpha-2">{banner.donation.message}</p>
              ) : null}
            </div>
            <span className="shrink-0 text-[15px] font-black text-gold">
              {banner.donation.gift ? '🎁' : `${formatCompact(banner.donation.amountStars)} ⭐`}
            </span>
          </div>
        </motion.button>
      ) : null}
    </AnimatePresence>
  );
}
