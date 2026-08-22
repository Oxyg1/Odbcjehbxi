import { memo } from 'react';
import { formatCompact, type DonationEventPayload } from '@tgdonate/shared';

/**
 * Marquee of recent donations.
 *
 * A quiet room is the thing that kills a social donation app — an empty floor
 * says "nobody is here, do not bother". A moving rail of real activity says the
 * opposite, and it keeps saying it even when this particular room is idle,
 * because it draws from the whole platform.
 *
 * The list is duplicated so the -50% translate loops seamlessly.
 */
export const DonationTicker = memo(function DonationTicker({
  donations,
}: {
  donations: DonationEventPayload[];
}) {
  if (donations.length === 0) return null;
  const loop = [...donations, ...donations];

  return (
    <div className="relative overflow-hidden py-1">
      {/* Fade the rail into the background at both ends. */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-2 w-8 bg-gradient-to-r from-background to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-2 w-8 bg-gradient-to-l from-background to-transparent" />

      <div className="ticker-track gap-2">
        {loop.map((donation, index) => (
          <span
            key={`${donation.id}-${index}`}
            className="glass-shadow flex shrink-0 items-center gap-1.5 rounded-full bg-surface-3/80 px-2.5 py-1"
          >
            <span className="text-[11px] font-bold whitespace-nowrap">
              {donation.isAnonymous ? 'Anon' : donation.donor?.displayName ?? 'Someone'}
            </span>
            <span className="text-[10px] text-alpha-3">→</span>
            <span className="max-w-[90px] truncate text-[11px] whitespace-nowrap text-alpha-1">
              {donation.standTitle}
            </span>
            <span
              className="text-[11px] font-black whitespace-nowrap"
              style={{
                color:
                  donation.tier === 'WHALE'
                    ? '#68fbdd'
                    : donation.tier === 'MAJOR'
                      ? '#ffc107'
                      : '#49df64',
              }}
            >
              {donation.gift ? '🎁' : `${formatCompact(donation.amountStars)}⭐`}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
});
