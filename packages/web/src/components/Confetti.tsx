import { useMemo } from 'react';
import { motion } from 'framer-motion';

/**
 * Lightweight confetti.
 *
 * Deliberately CSS/Framer only — a canvas particle system on a card that can
 * appear 50 times in one room would cost far more than the effect is worth.
 * Piece count scales with the donation tier.
 */
const TIER_PIECES = { MICRO: 10, MAJOR: 20, WHALE: 32 } as const;

export function Confetti({
  accent,
  tier = 'MICRO',
}: {
  accent: string;
  tier?: 'MICRO' | 'MAJOR' | 'WHALE';
}) {
  const count = TIER_PIECES[tier];

  // Randomised once per mount: re-rolling on every render would make the
  // pieces jitter instead of fly.
  const pieces = useMemo(
    () =>
      Array.from({ length: count }, (_, index) => ({
        id: index,
        x: (Math.random() - 0.5) * 150,
        y: -40 - Math.random() * 90,
        rotate: Math.random() * 540 - 270,
        delay: Math.random() * 0.16,
        size: 4 + Math.random() * 5,
        color:
          index % 3 === 0 ? accent : index % 3 === 1 ? '#ffffff' : 'color-mix(in srgb, ' + accent + ' 55%, white)',
        round: index % 2 === 0,
      })),
    [count, accent],
  );

  return (
    <div className="pointer-events-none absolute inset-0 z-9 flex items-center justify-center overflow-hidden">
      {pieces.map((piece) => (
        <motion.span
          key={piece.id}
          className="absolute"
          style={{
            width: piece.size,
            height: piece.size * (piece.round ? 1 : 1.7),
            background: piece.color,
            borderRadius: piece.round ? '50%' : '1px',
          }}
          initial={{ opacity: 1, x: 0, y: 6, rotate: 0, scale: 0.6 }}
          animate={{
            opacity: [1, 1, 0],
            x: piece.x,
            y: piece.y,
            rotate: piece.rotate,
            scale: 1,
          }}
          transition={{ duration: 1.1 + Math.random() * 0.5, delay: piece.delay, ease: 'easeOut' }}
        />
      ))}
    </div>
  );
}
