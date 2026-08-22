import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  MAX_LISTINGS_PER_STAND,
  type BannerStyle,
  type ListingKind,
  type Room,
  type Stand,
  type StandTheme,
} from '@tgdonate/shared';
import { api, ApiError, apiOrigin, type OwnedGift } from '../lib/api.js';
import { cn } from '../lib/cn.js';
import { socket } from '../lib/socket.js';
import { haptics, openInvoice } from '../lib/telegram.js';
import { useBackButton } from '../hooks/useTelegramUI.js';
import { useAppStore } from '../store/app.store.js';
import { StandCard } from '../components/StandCard.js';
import {
  Button, Card, LoadFailed, Pill, Sheet, Skeleton,
} from '../components/ui/primitives.js';

const BANNER_STYLES: BannerStyle[] = ['SOLID', 'GRADIENT', 'HOLOGRAM', 'MARQUEE', 'PIXEL'];

/**
 * My Stand editor.
 *
 * Edits are optimistic against a local draft, persisted with PATCH, then
 * re-broadcast over the socket so anyone standing in the room sees the change
 * without a refresh.
 */
export function EditorScreen() {
  const myStand = useAppStore((state) => state.myStand);
  const setMyStand = useAppStore((state) => state.setMyStand);
  const unlockedThemeIds = useAppStore((state) => state.unlockedThemeIds);
  const setScreen = useAppStore((state) => state.setScreen);
  const rooms = useAppStore((state) => state.rooms);

  const [draft, setDraft] = useState<Stand | null>(myStand);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [themes, setThemes] = useState<StandTheme[]>([]);
  const [gifts, setGifts] = useState<OwnedGift[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listingSheetOpen, setListingSheetOpen] = useState(false);

  useBackButton(true, () => setScreen('rooms'));

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const [standResponse, themeResponse, giftResponse] = await Promise.all([
          api.myStand(),
          api.themes(),
          api.myGifts().catch(() => ({ gifts: [] as OwnedGift[] })),
        ]);
        if (cancelled) return;
        setDraft(standResponse.stand);
        setMyStand(standResponse.stand);
        setThemes(themeResponse.themes);
        setGifts(giftResponse.gifts);
      } catch (caught) {
        if (cancelled) return;
        setLoadFailed(true);
        setError(
          caught instanceof ApiError
            ? `${caught.message} (${[caught.code, caught.reason].filter(Boolean).join(' / ')}, HTTP ${caught.status})`
            : 'Could not reach the server',
        );
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [setMyStand, reloadKey]);

  const patch = async (body: Parameters<typeof api.updateStand>[0]) => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const { stand } = await api.updateStand(body);
      setDraft(stand);
      setMyStand(stand);
      // Tell everyone in the room the booth changed.
      socket.publishStandUpdate(stand.id);
      haptics.notify('success');
    } catch (caught) {
      haptics.notify('error');
      setError(caught instanceof ApiError ? caught.message : 'Could not save that change');
    } finally {
      setSaving(false);
    }
  };

  const buyTheme = async (theme: StandTheme) => {
    try {
      haptics.impact('medium');
      const { invoiceLink } = await api.themeInvoice(theme.id);
      const status = await openInvoice(invoiceLink);
      if (status === 'paid') {
        haptics.notify('success');
        // The unlock lands server-side on successful_payment; re-read so the
        // theme becomes selectable straight away.
        const me = await api.me();
        useAppStore.getState().setMe(me.user, me.unlockedThemeIds);
        await patch({ themeId: theme.id });
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not open the theme invoice');
    }
  };

  if (loadFailed) {
    return (
      <LoadFailed
        title="Could not load your stand"
        message={error}
        endpoint={apiOrigin}
        onRetry={() => {
          setLoadFailed(false);
          setError(null);
          setReloadKey((key) => key + 1);
        }}
      />
    );
  }

  if (!draft) {
    return (
      <div className="safe-top flex flex-col gap-3 px-4">
        <Skeleton className="h-[190px] w-full squircle-3xl" />
        <Skeleton className="h-11 w-full squircle" />
        <Skeleton className="h-11 w-full squircle" />
      </div>
    );
  }

  return (
    <div className="safe-top safe-bottom flex flex-col gap-4 px-4">
      <header>
        <h1 className="text-[24px] leading-[28px] font-black tracking-[-0.6px]">My Stand</h1>
        <p className="text-[13px] text-alpha-2">Everything here is live the moment you save.</p>
      </header>

      {/* Live preview — the same component the room grid renders. */}
      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">Preview</h2>
        <div className="mx-auto w-[calc(50%+8px)] min-w-[176px]">
          <StandCard stand={draft} onOpen={() => undefined} />
        </div>
      </section>

      {error ? (
        <p className="squircle bg-destructive/15 px-3 py-2 text-[13px] text-destructive">{error}</p>
      ) : null}

      {/* Text */}
      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">Booth text</h2>
        <LabeledInput
          label="Title"
          value={draft.title}
          maxLength={64}
          onChange={(title) => setDraft({ ...draft, title })}
          onCommit={(title) => void patch({ title })}
        />
        <LabeledInput
          label="Goal"
          value={draft.goal ?? ''}
          maxLength={140}
          placeholder="Saving for a Rare Pepe gift…"
          onChange={(goal) => setDraft({ ...draft, goal })}
          onCommit={(goal) => void patch({ goal: goal || null })}
        />
        <LabeledInput
          label="Target (Stars)"
          value={draft.goalTargetStars?.toString() ?? ''}
          numeric
          placeholder="No target"
          onChange={(value) =>
            setDraft({ ...draft, goalTargetStars: value ? Number(value) : null })
          }
          onCommit={(value) =>
            void patch({ goalTargetStars: value ? Math.max(1, Number(value)) : null })
          }
        />
      </section>

      {/* Themes */}
      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">Theme</h2>
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          {themes.map((theme) => {
            const owned = theme.priceStars === 0 || unlockedThemeIds.includes(theme.id);
            const active = draft.theme.id === theme.id;
            return (
              <button
                key={theme.id}
                type="button"
                onClick={() => {
                  haptics.select();
                  if (owned) void patch({ themeId: theme.id });
                  else void buyTheme(theme);
                }}
                className="shrink-0"
              >
                <div
                  className={cn(
                    'squircle-lg glass-shadow relative h-[86px] w-[110px] overflow-hidden',
                    active && 'ring-2 ring-accent',
                  )}
                  style={{ backgroundImage: theme.palette.banner }}
                >
                  <div className="absolute inset-x-0 bottom-0 bg-black/55 px-1.5 py-1">
                    <p className="truncate text-[11px] font-bold">{theme.name}</p>
                    <p className="text-[10px] text-alpha-2">
                      {owned ? (active ? 'Active' : 'Owned') : `${theme.priceStars} ⭐`}
                    </p>
                  </div>
                  {!owned ? (
                    <span className="absolute top-1.5 right-1.5 text-[13px]">🔒</span>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Banner style */}
      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">
          Banner style
        </h2>
        <div className="flex flex-wrap gap-1.5">
          {BANNER_STYLES.map((style) => (
            <button
              key={style}
              type="button"
              onClick={() => {
                haptics.select();
                setDraft({ ...draft, bannerStyle: style });
                void patch({ bannerStyle: style });
              }}
              className={cn(
                'glass-shadow rounded-full px-3 py-2 text-[12px] font-bold transition-transform active:scale-95',
                draft.bannerStyle === style ? 'bg-accent text-[#0b0b0b]' : 'bg-surface-4 text-white',
              )}
            >
              {style.toLowerCase()}
            </button>
          ))}
        </div>
      </section>

      {/* Room placement */}
      <section className="flex flex-col gap-2">
        <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">Room</h2>
        <div className="flex flex-wrap gap-1.5">
          {rooms.map((room: Room) => (
            <button
              key={room.id}
              type="button"
              onClick={() => {
                haptics.select();
                void patch({ roomId: room.id });
              }}
              className={cn(
                'glass-shadow flex items-center gap-1 rounded-full px-3 py-2 text-[12px] font-bold',
                'transition-transform active:scale-95',
                draft.roomId === room.id ? 'bg-accent text-[#0b0b0b]' : 'bg-surface-4 text-white',
              )}
            >
              <span>{room.emoji}</span>
              {room.name}
            </button>
          ))}
        </div>
      </section>

      {/* Listings */}
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-bold text-alpha-2 uppercase tracking-[0.4px]">
            Listings ({draft.listings.length}/{MAX_LISTINGS_PER_STAND})
          </h2>
          <Button
            size="sm"
            variant="ghost"
            disabled={draft.listings.length >= MAX_LISTINGS_PER_STAND}
            onClick={() => setListingSheetOpen(true)}
          >
            + Add
          </Button>
        </div>

        <AnimatePresence initial={false}>
          {draft.listings.map((listing) => (
            <motion.div
              key={listing.id}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
            >
              <Card className="flex items-center gap-3 p-3">
                <div className="squircle flex h-10 w-10 shrink-0 items-center justify-center bg-white/8 text-[18px]">
                  {listing.kind === 'DONATION_TIER' ? '⭐' : listing.kind === 'SERVICE_OFFER' ? '🛠' : '🎁'}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-bold">{listing.title}</p>
                  <p className="truncate text-[12px] text-alpha-2">
                    {listing.priceStars !== null ? `${listing.priceStars} ⭐` : 'TON'}
                    {listing.supply !== null ? ` · ${listing.supply - listing.soldCount} left` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    haptics.impact('medium');
                    try {
                      await api.deleteListing(listing.id);
                      const { stand } = await api.myStand();
                      setDraft(stand);
                      setMyStand(stand);
                      socket.publishStandUpdate(stand.id);
                    } catch {
                      setError('Could not remove that listing');
                    }
                  }}
                  className="shrink-0 rounded-full bg-destructive/15 px-2.5 py-1.5 text-[12px] font-bold text-destructive"
                >
                  Remove
                </button>
              </Card>
            </motion.div>
          ))}
        </AnimatePresence>

        {draft.listings.length === 0 ? (
          <Card className="p-4 text-center">
            <p className="text-[13px] text-alpha-2">
              No listings yet. Add a donation tier so people know what to send.
            </p>
          </Card>
        ) : null}
      </section>

      {/* Publish toggle */}
      <Button
        variant={draft.isPublished ? 'tinted' : 'accent'}
        size="lg"
        shape="soft"
        fullWidth
        glow={!draft.isPublished}
        onClick={() => void patch({ isPublished: !draft.isPublished })}
      >
        {draft.isPublished ? 'Unpublish stand' : 'Publish stand'}
      </Button>

      <AnimatePresence>
        {listingSheetOpen ? (
          <ListingSheet
            gifts={gifts}
            onClose={() => setListingSheetOpen(false)}
            onCreated={(stand) => {
              setDraft(stand);
              setMyStand(stand);
              socket.publishStandUpdate(stand.id);
              setListingSheetOpen(false);
            }}
          />
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  onCommit,
  placeholder,
  maxLength,
  numeric,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onCommit: (value: string) => void;
  placeholder?: string;
  maxLength?: number;
  numeric?: boolean;
}) {
  return (
    <label className="glass-shadow squircle flex flex-col gap-1 bg-surface-2 px-3 py-2.5">
      <span className="text-[11px] font-bold text-alpha-2 uppercase tracking-[0.4px]">{label}</span>
      <input
        type={numeric ? 'number' : 'text'}
        inputMode={numeric ? 'numeric' : 'text'}
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        // Commit on blur rather than per-keystroke: one PATCH and one broadcast
        // per edit instead of one per character.
        onBlur={(event) => onCommit(event.target.value)}
        className="bg-transparent text-[15px] font-semibold outline-none placeholder:text-alpha-3"
      />
    </label>
  );
}

function ListingSheet({
  gifts,
  onClose,
  onCreated,
}: {
  gifts: OwnedGift[];
  onClose: () => void;
  onCreated: (stand: Stand) => void;
}) {
  const [kind, setKind] = useState<ListingKind>('DONATION_TIER');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priceStars, setPriceStars] = useState(50);
  const [supply, setSupply] = useState<string>('');
  const [giftId, setGiftId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const availableGifts = gifts.filter((gift) => gift.state === 'HELD_BY_OWNER' && !gift.listingId);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.createListing({
        kind,
        title: title.trim() || defaultTitle(kind, priceStars),
        description: description.trim() || null,
        priceStars,
        supply: supply ? Math.max(1, Number(supply)) : null,
        giftId: kind === 'NFT_GIFT_SALE' ? giftId : null,
      });
      const { stand } = await api.myStand();
      haptics.notify('success');
      onCreated(stand);
    } catch (caught) {
      haptics.notify('error');
      setError(caught instanceof ApiError ? caught.message : 'Could not create that listing');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open onClose={onClose} title="New listing">
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-3 gap-1.5">
          {(['DONATION_TIER', 'SERVICE_OFFER', 'NFT_GIFT_SALE'] as ListingKind[]).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                haptics.select();
                setKind(option);
              }}
              className={cn(
                'glass-shadow squircle px-2 py-2.5 text-[12px] font-bold',
                kind === option ? 'bg-accent text-[#0b0b0b]' : 'bg-surface-4 text-white',
              )}
            >
              {option === 'DONATION_TIER' ? '⭐ Tier' : option === 'SERVICE_OFFER' ? '🛠 Service' : '🎁 Gift'}
            </button>
          ))}
        </div>

        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={80}
          placeholder={defaultTitle(kind, priceStars)}
          className="glass-shadow squircle h-12 bg-surface-2 px-3 text-[15px] font-semibold outline-none placeholder:text-alpha-3"
        />

        {kind !== 'DONATION_TIER' ? (
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={280}
            rows={3}
            placeholder="What exactly are you offering?"
            className="glass-shadow squircle resize-none bg-surface-2 px-3 py-2.5 text-[14px] outline-none placeholder:text-alpha-3"
          />
        ) : null}

        {kind === 'NFT_GIFT_SALE' ? (
          availableGifts.length > 0 ? (
            <div className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
              {availableGifts.map((gift) => (
                <button
                  key={gift.id}
                  type="button"
                  onClick={() => {
                    haptics.select();
                    setGiftId(gift.id);
                  }}
                  className={cn(
                    'squircle glass-shadow shrink-0 bg-surface-4 p-2 text-center',
                    giftId === gift.id && 'ring-2 ring-accent',
                  )}
                >
                  {gift.previewUrl ? (
                    <img src={gift.previewUrl} alt="" className="squircle mb-1 h-14 w-14 object-cover" />
                  ) : (
                    <div className="squircle mb-1 flex h-14 w-14 items-center justify-center text-[22px]">
                      🎁
                    </div>
                  )}
                  <p className="max-w-[64px] truncate text-[11px] font-bold">{gift.title}</p>
                  <Pill tone="purple" className="mt-0.5">
                    {gift.rarity}
                  </Pill>
                </button>
              ))}
            </div>
          ) : (
            <Card className="p-3 text-center">
              <p className="text-[13px] text-alpha-2">
                No transferable gifts found. Sync your inventory from your profile first.
              </p>
            </Card>
          )
        ) : null}

        <div className="flex gap-2">
          <label className="glass-shadow squircle flex flex-1 flex-col gap-0.5 bg-surface-2 px-3 py-2">
            <span className="text-[11px] font-bold text-alpha-2 uppercase">Price ⭐</span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              value={priceStars}
              onChange={(event) => setPriceStars(Math.max(1, Number(event.target.value) || 1))}
              className="bg-transparent text-[16px] font-black outline-none"
            />
          </label>
          <label className="glass-shadow squircle flex flex-1 flex-col gap-0.5 bg-surface-2 px-3 py-2">
            <span className="text-[11px] font-bold text-alpha-2 uppercase">Supply</span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              value={supply}
              placeholder="∞"
              onChange={(event) => setSupply(event.target.value)}
              className="bg-transparent text-[16px] font-black outline-none placeholder:text-alpha-3"
            />
          </label>
        </div>

        {error ? (
          <p className="squircle bg-destructive/15 px-3 py-2 text-[13px] text-destructive">{error}</p>
        ) : null}

        <Button
          variant="accent"
          size="lg"
          shape="soft"
          fullWidth
          glow
          disabled={busy || (kind === 'NFT_GIFT_SALE' && !giftId)}
          onClick={() => void submit()}
        >
          {busy ? 'Creating…' : 'Add to my stand'}
        </Button>
      </div>
    </Sheet>
  );
}

function defaultTitle(kind: ListingKind, priceStars: number): string {
  if (kind === 'DONATION_TIER') return `Send ${priceStars} Stars`;
  if (kind === 'SERVICE_OFFER') return 'Custom service';
  return 'NFT gift for sale';
}
