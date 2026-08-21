import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  formatCompact,
  splitStars,
  type DonationEventPayload,
  type Listing,
  type Stand,
} from '@tgdonate/shared';
import { api, ApiError } from '../lib/api.js';
import { cn } from '../lib/cn.js';
import { haptics, openInvoice, shareStand } from '../lib/telegram.js';
import { useStandSubscription } from '../hooks/useRealtime.js';
import { useBackButton } from '../hooks/useTelegramUI.js';
import { useAppStore } from '../store/app.store.js';
import {
  Avatar,
  Button,
  Card,
  Pill,
  ProgressBar,
  Sheet,
  Skeleton,
} from '../components/ui/primitives.js';

const QUICK_AMOUNTS = [10, 50, 100, 500, 1000] as const;

export function StandScreen() {
  const standId = useAppStore((state) => state.focusedStandId);
  const standsInRoom = useAppStore((state) => state.stands);
  const setScreen = useAppStore((state) => state.setScreen);
  const me = useAppStore((state) => state.me);

  const [fetched, setFetched] = useState<Stand | null>(null);
  const [supporters, setSupporters] = useState<DonationEventPayload[]>([]);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null);
  const [amount, setAmount] = useState<number>(50);
  const [message, setMessage] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useStandSubscription(standId);
  useBackButton(true, () => setScreen('room'));

  // Prefer the live copy from the room grid: it is patched by every WS frame,
  // so counters stay correct without another fetch.
  const liveStand = useMemo(
    () => standsInRoom.find((candidate) => candidate.id === standId) ?? null,
    [standsInRoom, standId],
  );
  const stand = liveStand ?? fetched;

  useEffect(() => {
    if (!standId) return;
    let cancelled = false;

    void (async () => {
      try {
        const [standResponse, supportersResponse] = await Promise.all([
          api.stand(standId),
          api.standSupporters(standId, 15),
        ]);
        if (cancelled) return;
        setFetched(standResponse.stand);
        setSupporters(supportersResponse.donations);
      } catch {
        // The live copy may already be enough; leave the screen usable.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [standId]);

  const isOwnStand = stand !== null && me !== null && stand.ownerId === me.id;

  const openDonateSheet = (listing: Listing | null) => {
    if (isOwnStand) return;
    haptics.impact('medium');
    setSelectedListing(listing);
    setAmount(listing?.priceStars ?? 50);
    setError(null);
    setSheetOpen(true);
  };

  const pay = async () => {
    if (!stand || paying) return;
    setPaying(true);
    setError(null);

    try {
      const { invoiceLink } = await api.starsInvoice({
        standId: stand.id,
        listingId: selectedListing?.id ?? null,
        amountStars: selectedListing?.priceStars ?? amount,
        isAnonymous: anonymous,
        message: message.trim() || null,
      });

      const status = await openInvoice(invoiceLink);

      if (status === 'paid') {
        // The settlement broadcast updates the counters; closing the sheet is
        // all this screen needs to do.
        haptics.notify('success');
        setSheetOpen(false);
        setMessage('');
      } else if (status === 'failed') {
        haptics.notify('error');
        setError('The payment did not go through. Nothing was charged.');
      } else if (status === 'cancelled') {
        haptics.impact('light');
      }
    } catch (caught) {
      haptics.notify('error');
      setError(
        caught instanceof ApiError ? caught.message : 'Could not start the payment. Try again.',
      );
    } finally {
      setPaying(false);
    }
  };

  if (!stand) {
    return (
      <div className="safe-top flex flex-col gap-3 px-4">
        <Skeleton className="h-[120px] w-full squircle-3xl" />
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-20 w-full squircle-3xl" />
      </div>
    );
  }

  const palette = stand.theme.palette;
  const split = splitStars(selectedListing?.priceStars ?? amount);

  return (
    <div className="safe-bottom flex flex-col gap-3">
      {/* Banner */}
      <div className="relative h-[150px] overflow-hidden rounded-b-[32px]">
        <div className="absolute inset-0" style={{ backgroundImage: palette.banner }} />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 flex items-end gap-3 px-4 pb-3">
          <Avatar
            src={stand.owner.photoUrl}
            name={stand.owner.displayName}
            size={56}
            ring={stand.owner.badge ? '#f1aa05' : null}
          />
          <div className="min-w-0 flex-1 pb-1">
            <h1 className="truncate text-[20px] leading-[24px] font-black tracking-[-0.5px]">
              {stand.title}
            </h1>
            <p className="truncate text-[13px] text-alpha-1">
              @{stand.owner.username ?? stand.owner.displayName}
              {stand.owner.badge ? (
                <span className="ml-1 font-bold text-gold">
                  · #{stand.owner.badge.rank} {stand.owner.badge.scope.toLowerCase()}
                </span>
              ) : null}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              haptics.impact('light');
              shareStand(stand.id, stand.title);
            }}
            className="glass-shadow glass mb-1 flex h-9 w-9 items-center justify-center rounded-full bg-white/12"
          >
            ↗
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3 px-4">
        {stand.goal ? (
          <Card className="p-3">
            <p className="text-[14px] leading-[19px] text-alpha-1">{stand.goal}</p>
            {stand.goalTargetStars ? (
              <div className="mt-3 flex flex-col gap-1.5">
                <ProgressBar
                  value={stand.totalStarsReceived}
                  max={stand.goalTargetStars}
                  accent={palette.accent}
                />
                <div className="flex justify-between text-[12px] font-bold">
                  <span style={{ color: palette.accent }}>
                    {formatCompact(stand.totalStarsReceived)} ⭐
                  </span>
                  <span className="text-alpha-2">
                    goal {formatCompact(stand.goalTargetStars)} ⭐
                  </span>
                </div>
              </div>
            ) : null}
          </Card>
        ) : null}

        <div className="grid grid-cols-3 gap-2">
          <StatTile label="Raised" value={`${formatCompact(stand.totalStarsReceived)} ⭐`} accent={palette.accent} />
          <StatTile label="Gifts" value={stand.totalGiftsReceived.toString()} accent="#6d51de" />
          <StatTile label="Supporters" value={formatCompact(stand.supporterCount)} accent="#1689ff" />
        </div>

        {/* Listings */}
        {stand.listings.length > 0 ? (
          <section className="flex flex-col gap-2">
            <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">
              On this stand
            </h2>
            {stand.listings.map((listing) => (
              <ListingRow
                key={listing.id}
                listing={listing}
                accent={palette.accent}
                disabled={isOwnStand}
                onSelect={() => openDonateSheet(listing)}
              />
            ))}
          </section>
        ) : null}

        {/* Free-amount donation */}
        {!isOwnStand ? (
          <Button
            variant="accent"
            size="lg"
            shape="soft"
            fullWidth
            glow
            tint={palette.accent}
            haptic="medium"
            onClick={() => openDonateSheet(null)}
            style={{ backgroundColor: palette.accent }}
          >
            Send Stars ⭐
          </Button>
        ) : (
          <Button
            variant="tinted"
            size="lg"
            shape="soft"
            fullWidth
            tint={palette.accent}
            onClick={() => setScreen('editor')}
          >
            Edit my stand
          </Button>
        )}

        {/* Supporters */}
        {supporters.length > 0 ? (
          <section className="flex flex-col gap-2 pb-4">
            <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">
              Recent supporters
            </h2>
            <Card variant="flat" glass={false} className="divide-y divide-white/6 p-0">
              {supporters.map((donation) => (
                <div key={donation.id} className="flex items-center gap-2.5 px-3 py-2.5">
                  <Avatar
                    src={donation.donor?.photoUrl ?? null}
                    name={donation.isAnonymous ? 'Anonymous' : donation.donor?.displayName ?? '?'}
                    size={30}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-bold">
                      {donation.isAnonymous
                        ? 'Anonymous'
                        : donation.donor?.displayName ?? 'Someone'}
                    </p>
                    {donation.message ? (
                      <p className="truncate text-[12px] text-alpha-2">{donation.message}</p>
                    ) : null}
                  </div>
                  <span
                    className={cn(
                      'shrink-0 text-[13px] font-black',
                      donation.tier === 'WHALE'
                        ? 'text-tifany'
                        : donation.tier === 'MAJOR'
                          ? 'text-gold'
                          : 'text-accent',
                    )}
                  >
                    {donation.gift ? '🎁' : `${formatCompact(donation.amountStars)} ⭐`}
                  </span>
                </div>
              ))}
            </Card>
          </section>
        ) : null}
      </div>

      {/* Donation sheet */}
      <AnimatePresence>
        {sheetOpen ? (
          <Sheet
            open
            onClose={() => setSheetOpen(false)}
            title={selectedListing ? selectedListing.title : `Support ${stand.title}`}
          >
            <div className="flex flex-col gap-3">
              {!selectedListing ? (
                <>
                  <div className="grid grid-cols-5 gap-1.5">
                    {QUICK_AMOUNTS.map((value) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => {
                          haptics.select();
                          setAmount(value);
                        }}
                        className={cn(
                          'glass-shadow squircle h-11 text-[14px] font-bold transition-transform active:scale-95',
                          amount === value ? 'text-[#0b0b0b]' : 'bg-surface-4 text-white',
                        )}
                        style={amount === value ? { backgroundColor: palette.accent } : undefined}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={100000}
                    value={amount}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      setAmount(Number.isFinite(next) ? Math.max(1, Math.floor(next)) : 1);
                    }}
                    className="glass-shadow squircle h-12 bg-surface-2 px-3 text-center text-[18px] font-black outline-none"
                    placeholder="Custom amount"
                  />
                </>
              ) : (
                <div className="glass-shadow squircle bg-surface-2 p-3">
                  <p className="text-[15px] font-bold">{selectedListing.title}</p>
                  {selectedListing.description ? (
                    <p className="mt-1 text-[13px] text-alpha-2">{selectedListing.description}</p>
                  ) : null}
                  <p className="mt-2 text-[20px] font-black" style={{ color: palette.accent }}>
                    {selectedListing.priceStars} ⭐
                  </p>
                </div>
              )}

              <input
                type="text"
                maxLength={280}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Add a message (optional)"
                className="glass-shadow squircle h-12 bg-surface-2 px-3 text-[14px] outline-none placeholder:text-alpha-3"
              />

              <button
                type="button"
                onClick={() => {
                  haptics.select();
                  setAnonymous((current) => !current);
                }}
                className="glass-shadow squircle flex items-center justify-between bg-surface-2 px-3 py-3"
              >
                <span className="text-[14px] font-semibold">Donate anonymously</span>
                <span
                  className={cn(
                    'flex h-6 w-10 items-center rounded-full p-0.5 transition-colors',
                    anonymous ? 'bg-accent' : 'bg-white/15',
                  )}
                >
                  <motion.span
                    className="h-5 w-5 rounded-full bg-white"
                    animate={{ x: anonymous ? 16 : 0 }}
                    transition={{ type: 'spring', damping: 22, stiffness: 320 }}
                  />
                </span>
              </button>

              <div className="flex justify-between px-1 text-[12px] text-alpha-2">
                <span>Creator receives</span>
                <span className="font-bold text-white">{split.net} ⭐</span>
              </div>
              <div className="flex justify-between px-1 text-[12px] text-alpha-3">
                <span>Platform fee ({split.feeBps / 100}%)</span>
                <span>{split.fee} ⭐</span>
              </div>

              {error ? (
                <p className="squircle bg-destructive/15 px-3 py-2 text-[13px] text-destructive">
                  {error}
                </p>
              ) : null}

              <Button
                variant="accent"
                size="lg"
                shape="soft"
                fullWidth
                glow
                tint={palette.accent}
                disabled={paying}
                onClick={() => void pay()}
                style={{ backgroundColor: palette.accent }}
              >
                {paying ? 'Opening…' : `Pay ${selectedListing?.priceStars ?? amount} ⭐`}
              </Button>
            </div>
          </Sheet>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function StatTile({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <Card className="flex flex-col items-center gap-0.5 px-2 py-2.5">
      <span className="text-[15px] font-black" style={{ color: accent }}>
        {value}
      </span>
      <span className="text-[11px] font-semibold text-alpha-2">{label}</span>
    </Card>
  );
}

function ListingRow({
  listing,
  accent,
  disabled,
  onSelect,
}: {
  listing: Listing;
  accent: string;
  disabled: boolean;
  onSelect: () => void;
}) {
  const soldOut = listing.supply !== null && listing.soldCount >= listing.supply;

  return (
    <button
      type="button"
      disabled={disabled || soldOut}
      onClick={onSelect}
      className="text-left disabled:opacity-50"
    >
      <Card className="flex items-center gap-3 p-3">
        {listing.gift?.previewUrl ? (
          <img
            src={listing.gift.previewUrl}
            alt=""
            className="squircle h-12 w-12 shrink-0 object-cover"
          />
        ) : (
          <div
            className="squircle flex h-12 w-12 shrink-0 items-center justify-center text-[20px]"
            style={{ backgroundColor: `color-mix(in srgb, ${accent} 16%, transparent)` }}
          >
            {listing.kind === 'DONATION_TIER' ? '⭐' : listing.kind === 'SERVICE_OFFER' ? '🛠' : '🎁'}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-bold">{listing.title}</p>
          {listing.description ? (
            <p className="line-clamp-2 text-[12px] text-alpha-2">{listing.description}</p>
          ) : null}
          <div className="mt-1 flex items-center gap-1.5">
            {listing.gift ? <Pill tone="purple">{listing.gift.rarity}</Pill> : null}
            {listing.supply !== null ? (
              <Pill tone={soldOut ? 'danger' : 'neutral'}>
                {soldOut ? 'Sold out' : `${listing.supply - listing.soldCount} left`}
              </Pill>
            ) : null}
          </div>
        </div>
        <span className="shrink-0 text-[15px] font-black" style={{ color: accent }}>
          {listing.priceStars !== null ? `${listing.priceStars} ⭐` : 'TON'}
        </span>
      </Card>
    </button>
  );
}
