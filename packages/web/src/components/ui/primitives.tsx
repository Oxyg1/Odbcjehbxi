import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from 'react';
import { motion, type HTMLMotionProps } from 'framer-motion';
import { cn } from '../../lib/cn.js';
import { haptics } from '../../lib/telegram.js';

/**
 * Primitives.
 *
 * Everything here leans on the same three ingredients as the reference app: a
 * translucent surface, the `glass-shadow` bevel, and a squircle corner. Colour
 * comes from the theme tokens, never from ad-hoc hex values.
 */

/* --------------------------------- Card ---------------------------------- */

type CardProps = HTMLAttributes<HTMLDivElement> & {
  variant?: 'surface' | 'raised' | 'flat';
  glass?: boolean;
};

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { className, variant = 'surface', glass = true, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        'squircle-3xl relative overflow-hidden',
        variant === 'surface' && 'bg-surface-4/65',
        variant === 'raised' && 'bg-surface-5/70',
        variant === 'flat' && 'bg-surface-2',
        glass && 'glass-shadow glass',
        className,
      )}
      {...props}
    />
  );
});

/* -------------------------------- Button --------------------------------- */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger' | 'gold';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  /** Haptic style fired on press; pass null to stay silent. */
  haptic?: 'light' | 'medium' | 'heavy' | null;
};

const buttonVariants: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary: 'bg-primary text-white',
  accent: 'bg-accent text-[#0b0b0b]',
  secondary: 'bg-surface-4/80 text-white',
  ghost: 'bg-white/8 text-white',
  danger: 'bg-destructive/90 text-white',
  gold: 'bg-gold text-[#231703]',
};

const buttonSizes: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'h-9 px-3 text-[13px]',
  md: 'h-11 px-4 text-[15px]',
  lg: 'h-13 px-5 text-[16px]',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = 'accent', size = 'md', fullWidth, haptic = 'light', onClick, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      onClick={(event) => {
        if (haptic) haptics.impact(haptic);
        onClick?.(event);
      }}
      className={cn(
        'glass-shadow inline-flex items-center justify-center gap-2 rounded-full font-semibold',
        'transition-transform duration-150 active:scale-[0.97]',
        'disabled:pointer-events-none disabled:opacity-40',
        buttonVariants[variant],
        buttonSizes[size],
        fullWidth && 'w-full',
        className,
      )}
      {...props}
    />
  );
});

/* --------------------------------- Pill ---------------------------------- */

export function Pill({
  children,
  className,
  tone = 'neutral',
}: {
  children: ReactNode;
  className?: string;
  tone?: 'neutral' | 'accent' | 'gold' | 'primary' | 'danger' | 'tifany' | 'purple';
}) {
  const tones: Record<string, string> = {
    neutral: 'bg-white/10 text-white',
    accent: 'bg-accent/18 text-accent',
    gold: 'bg-gold/18 text-gold',
    primary: 'bg-primary/18 text-primary',
    danger: 'bg-destructive/18 text-destructive',
    tifany: 'bg-tifany/18 text-tifany',
    purple: 'bg-purple/22 text-[#b7a6ff]',
  };
  return (
    <span
      className={cn(
        'glass-shadow inline-flex min-w-0 items-center gap-1 rounded-full px-2 py-1',
        'text-[12px] leading-none font-bold whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------- Avatar --------------------------------- */

export function Avatar({
  src,
  name,
  size = 36,
  ring,
  className,
}: {
  src?: string | null;
  name: string;
  size?: number;
  /** Badge colour drawn as a ring — the "whale rank" tell. */
  ring?: string | null;
  className?: string;
}) {
  const initials = name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <div
      className={cn('relative shrink-0 overflow-hidden rounded-full bg-surface-5', className)}
      style={{
        width: size,
        height: size,
        boxShadow: ring ? `0 0 0 2px ${ring}, 0 0 12px -2px ${ring}` : undefined,
      }}
    >
      {src ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover"
          // A broken avatar URL should fall back to initials, not a torn image.
          onError={(event) => {
            event.currentTarget.style.display = 'none';
          }}
        />
      ) : null}
      <span
        className="absolute inset-0 flex items-center justify-center font-bold text-white/70"
        style={{ fontSize: size * 0.36 }}
      >
        {initials || '?'}
      </span>
    </div>
  );
}

/* -------------------------------- Sheet ---------------------------------- */

export function Sheet({
  open,
  onClose,
  children,
  title,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: string;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end">
      <motion.div
        className="absolute inset-0 bg-black/60"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />
      <motion.div
        className={cn(
          'glass-shadow glass relative w-full bg-surface-1',
          'rounded-t-[24px] px-4 pt-4',
          'pb-[calc(var(--tg-viewport-safe-area-inset-bottom)+20px)]',
          'max-h-[85dvh] overflow-y-auto no-scrollbar',
        )}
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 320 }}
      >
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-white/20" />
        {title ? <h2 className="mb-3 text-[17px] font-bold">{title}</h2> : null}
        {children}
      </motion.div>
    </div>
  );
}

/* ------------------------------ Progress ring ---------------------------- */

export function ProgressBar({
  value,
  max,
  accent,
  className,
}: {
  value: number;
  max: number;
  accent: string;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-black/40', className)}>
      <motion.div
        className="h-full rounded-full"
        style={{ background: accent }}
        initial={false}
        animate={{ width: `${pct}%` }}
        transition={{ type: 'spring', damping: 26, stiffness: 200 }}
      />
    </div>
  );
}

/* -------------------------------- Skeleton -------------------------------- */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-shimmer squircle bg-surface-4',
        'bg-[linear-gradient(90deg,transparent_0%,rgba(255,255,255,0.06)_50%,transparent_100%)]',
        className,
      )}
    />
  );
}

/* ------------------------------- Motion card ------------------------------ */

export const MotionCard = motion.create(Card);

export type { HTMLMotionProps };
