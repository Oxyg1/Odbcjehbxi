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
  variant?: 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger' | 'gold' | 'tinted';
  size?: 'sm' | 'md' | 'lg';
  /** Pill by default; `soft` is the 24px-radius shape the reference uses for
   *  full-width CTAs and inline price buttons. */
  shape?: 'pill' | 'soft';
  fullWidth?: boolean;
  /** Throws a coloured glow beneath the button. Primary CTAs only. */
  glow?: boolean;
  /** Hue for `tinted` and for the glow. Defaults to the variant's own colour. */
  tint?: string;
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
  tinted: 'tinted-surface',
};

/** Default glow hue per variant, so `glow` needs no extra configuration. */
const variantTint: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary: '#1689ff',
  accent: '#49df64',
  secondary: '#282727',
  ghost: '#ffffff',
  danger: '#df494d',
  gold: '#f1aa05',
  tinted: '#1689ff',
};

const buttonSizes: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'h-9 px-3 text-[13px]',
  md: 'h-11 px-4 text-[15px]',
  lg: 'h-[52px] px-5 text-[15px]',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = 'accent',
    size = 'md',
    shape = 'pill',
    fullWidth,
    glow,
    tint,
    haptic = 'light',
    onClick,
    style,
    ...props
  },
  ref,
) {
  const hue = tint ?? variantTint[variant];

  return (
    <button
      ref={ref}
      onClick={(event) => {
        if (haptic) haptics.impact(haptic);
        onClick?.(event);
      }}
      className={cn(
        'pressable inline-flex items-center justify-center gap-2 font-semibold',
        'disabled:pointer-events-none disabled:opacity-40',
        shape === 'pill' ? 'rounded-full' : 'rounded-3xl',
        variant !== 'tinted' && 'glass-shadow',
        glow && 'cta-glow',
        buttonVariants[variant],
        buttonSizes[size],
        fullWidth && 'w-full',
        className,
      )}
      style={{
        ...(glow ? { ['--glow' as string]: `color-mix(in srgb, ${hue} 38%, transparent)` } : {}),
        ...(variant === 'tinted' ? { ['--tint' as string]: hue } : {}),
        ...style,
      }}
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

/* -------------------------------- TextTabs -------------------------------- */

/**
 * Section switcher.
 *
 * The reference app does not use a pill segmented control for these — it sets
 * the section names in the same size as a page heading and dims the inactive
 * ones almost to the background. The active label reads as the page title, so
 * switching sections feels like navigating rather than toggling a filter.
 */
export function TextTabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: ReadonlyArray<{ id: T; label: string }>;
  value: T;
  onChange: (id: T) => void;
  className?: string;
}) {
  return (
    <div className={cn('no-scrollbar flex gap-3 overflow-x-auto', className)}>
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => {
              if (active) return;
              haptics.select();
              onChange(tab.id);
            }}
            className={cn(
              'shrink-0 text-[20px] leading-[24px] font-bold tracking-[-0.5px]',
              'transition-colors duration-150',
              active ? 'text-white' : 'text-surface-6',
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------- FilterChip ------------------------------- */

/**
 * Dropdown-style filter chip. Translucent input surface, glass bevel, bold
 * white label with the affordance chevron kept in muted grey so the row of
 * chips reads as labels first and controls second.
 */
export function FilterChip({
  label,
  value,
  active,
  onClick,
}: {
  label: string;
  value?: string | null;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        haptics.select();
        onClick();
      }}
      className={cn(
        'pressable glass-shadow flex w-fit min-w-0 shrink-0 items-center gap-2',
        'rounded-full p-2 text-[14px] font-semibold',
        active ? 'bg-accent/20' : 'bg-surface-2/80',
      )}
    >
      <span
        className={cn(
          'truncate pl-3 font-bold',
          active ? 'text-accent' : 'text-white',
        )}
      >
        {value ?? label}
      </span>
      <svg
        width="8"
        height="5"
        viewBox="0 0 8 5"
        fill="none"
        aria-hidden="true"
        className="mr-1 shrink-0 text-muted"
      >
        <path d="M1 1L4 4L7 1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </button>
  );
}

/* ------------------------------ PriceButton ------------------------------- */

/**
 * The buy affordance on a card: a filled, bold, soft-cornered button whose
 * label is the price itself with the currency glyph inline at a smaller size.
 */
export function PriceButton({
  amount,
  currency = '⭐',
  onClick,
  disabled,
  tint,
  className,
}: {
  amount: string | number;
  currency?: string;
  onClick?: () => void;
  disabled?: boolean;
  tint?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        haptics.impact('medium');
        onClick?.();
      }}
      className={cn(
        'pressable glass-shadow flex flex-1 items-center justify-center gap-1',
        'rounded-2xl px-2 py-2 text-[14px] font-bold',
        'disabled:pointer-events-none disabled:opacity-40',
        className,
      )}
      style={{
        backgroundColor: tint ?? 'var(--color-primary)',
        color: tint ? '#0b0b0b' : '#ffffff',
      }}
    >
      {amount}
      <span className="text-[11px] leading-none">{currency}</span>
    </button>
  );
}

/* ------------------------------- EmptyState ------------------------------- */

/**
 * Empty states in the reference always offer the next action rather than just
 * reporting the absence — an empty inventory points at the marketplace.
 */
export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: string;
  title: string;
  body?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <Card className="flex flex-col items-center gap-2 px-5 py-7 text-center">
      <span className="text-[30px] leading-none">{icon}</span>
      <p className="text-[16px] leading-[20px] font-bold">{title}</p>
      {body ? <p className="text-[13px] leading-[17px] text-alpha-2">{body}</p> : null}
      {action ? (
        <Button variant="accent" size="sm" glow className="mt-2" onClick={action.onClick}>
          {action.label}
        </Button>
      ) : null}
    </Card>
  );
}

/* ------------------------------- LoadFailed ------------------------------- */

/**
 * Terminal state for a screen whose initial fetch failed.
 *
 * Screens guard their render on the loaded object, so an error stored in state
 * alongside a still-null object is unreachable — the guard returns the skeleton
 * first and the user waits forever on a screen that has already given up. This
 * component is what that guard must return instead: the actual reason, plus a
 * way out.
 */
export function LoadFailed({
  title = 'Could not load this screen',
  message,
  endpoint,
  onRetry,
}: {
  title?: string;
  message?: string | null;
  /** Which host the request went to — the fastest way to spot misconfiguration. */
  endpoint?: string | null;
  onRetry?: () => void;
}) {
  return (
    <div className="safe-top flex flex-col gap-3 px-4">
      <Card className="flex flex-col items-center gap-2 px-5 py-7 text-center">
        <span className="text-[30px] leading-none">😕</span>
        <p className="text-[16px] leading-[20px] font-bold">{title}</p>
        {message ? (
          <p className="text-[13px] leading-[17px] text-alpha-2">{message}</p>
        ) : null}
        {endpoint ? (
          <p className="mt-1 font-mono text-[11px] break-all text-alpha-3">{endpoint}</p>
        ) : null}
        {onRetry ? (
          <Button variant="accent" size="sm" glow className="mt-2" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </Card>
    </div>
  );
}

/* ------------------------------- Motion card ------------------------------ */

export const MotionCard = motion.create(Card);

export type { HTMLMotionProps };
