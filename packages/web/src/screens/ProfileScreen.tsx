import { useEffect, useState } from 'react';
import { useTonAddress, useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { formatCompact } from '@tgdonate/shared';
import { api, ApiError, type MeResponse, type OwnedGift } from '../lib/api.js';
import { haptics } from '../lib/telegram.js';
import { useAppStore } from '../store/app.store.js';
import { Avatar, Button, Card, Pill, Skeleton } from '../components/ui/primitives.js';

/** Profile: identity, lifetime totals, wallet connection, gift inventory. */
export function ProfileScreen() {
  const setScreen = useAppStore((state) => state.setScreen);
  const setMe = useAppStore((state) => state.setMe);

  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [gifts, setGifts] = useState<OwnedGift[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [tonConnectUI] = useTonConnectUI();
  const wallet = useTonWallet();
  const friendlyAddress = useTonAddress();

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const [meResponse, giftResponse] = await Promise.all([
          api.me(),
          api.myGifts().catch(() => ({ gifts: [] as OwnedGift[] })),
        ]);
        if (cancelled) return;
        setProfile(meResponse);
        setMe(meResponse.user, meResponse.unlockedThemeIds);
        setGifts(giftResponse.gifts);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : 'Could not load your profile');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [setMe]);

  /**
   * Bind the wallet only after the backend verifies `ton_proof`. A connected
   * wallet on its own proves nothing — anyone can paste an address.
   */
  useEffect(() => {
    const connectItems = wallet?.connectItems?.tonProof;
    if (!wallet || !connectItems || !('proof' in connectItems)) return;

    void (async () => {
      try {
        await api.linkWallet({
          address: wallet.account.address,
          publicKey: wallet.account.publicKey ?? '',
          proof: {
            timestamp: connectItems.proof.timestamp,
            domain: connectItems.proof.domain,
            signature: connectItems.proof.signature,
            payload: connectItems.proof.payload,
          },
        });
        haptics.notify('success');
        const refreshed = await api.me();
        setProfile(refreshed);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : 'Could not verify your wallet');
      }
    })();
  }, [wallet]);

  /** Refresh the proof nonce before each connect so it can't be replayed. */
  const connectWallet = async () => {
    try {
      const { payload } = await api.tonProofPayload();
      tonConnectUI.setConnectRequestParameters({ state: 'ready', value: { tonProof: payload } });
      await tonConnectUI.openModal();
    } catch {
      setError('Could not start the wallet connection');
    }
  };

  const syncGifts = async () => {
    setSyncing(true);
    try {
      await api.syncGifts();
      const { gifts: refreshed } = await api.myGifts();
      setGifts(refreshed);
      haptics.notify('success');
    } catch {
      setError('Could not sync your gifts from Telegram');
    } finally {
      setSyncing(false);
    }
  };

  if (!profile) {
    return (
      <div className="safe-top flex flex-col gap-3 px-4">
        <Skeleton className="h-[110px] w-full squircle-3xl" />
        <Skeleton className="h-16 w-full squircle-3xl" />
      </div>
    );
  }

  return (
    <div className="safe-top safe-bottom flex flex-col gap-3 px-4">
      <Card className="flex items-center gap-3 p-4">
        <Avatar
          src={profile.user.photoUrl}
          name={profile.user.displayName}
          size={60}
          ring={profile.user.badge ? '#f1aa05' : null}
        />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[19px] leading-[23px] font-black">
            {profile.user.displayName}
          </h1>
          {profile.user.username ? (
            <p className="truncate text-[13px] text-alpha-2">@{profile.user.username}</p>
          ) : null}
          <div className="mt-1.5 flex flex-wrap gap-1">
            {profile.user.isPremium ? <Pill tone="primary">Premium</Pill> : null}
            {profile.user.badge ? (
              <Pill tone="gold">
                #{profile.user.badge.rank} {profile.user.badge.scope.toLowerCase().replace('_', ' ')}
              </Pill>
            ) : null}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-2">
        <StatCard label="Donated" value={`${formatCompact(profile.user.starsDonated)} ⭐`} accent="#49df64" />
        <StatCard label="Received" value={`${formatCompact(profile.user.starsReceived)} ⭐`} accent="#1689ff" />
        <StatCard label="Gifts sent" value={profile.user.giftsDonated.toString()} accent="#6d51de" />
        <StatCard label="Gifts got" value={profile.user.giftsReceived.toString()} accent="#f1aa05" />
      </div>

      <Button
        variant="accent"
        size="lg"
        shape="soft"
        fullWidth
        glow
        onClick={() => setScreen('editor')}
      >
        🎪 Manage my stand
      </Button>

      {/* TON wallet */}
      <Card className="flex flex-col gap-2.5 p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-bold">TON Wallet</h2>
          {profile.user.tonWallet ? <Pill tone="accent">Verified</Pill> : null}
        </div>
        {friendlyAddress ? (
          <p className="truncate font-mono text-[12px] text-alpha-1">{friendlyAddress}</p>
        ) : (
          <p className="text-[13px] text-alpha-2">
            Connect a wallet to receive TON payments and trade NFT gifts.
          </p>
        )}
        {wallet ? (
          <Button
            variant="ghost"
            fullWidth
            onClick={() => {
              void tonConnectUI.disconnect();
            }}
          >
            Disconnect
          </Button>
        ) : (
          <Button variant="tinted" shape="soft" fullWidth onClick={() => void connectWallet()}>
            Connect wallet
          </Button>
        )}
      </Card>

      {/* Gifts */}
      <Card className="flex flex-col gap-2.5 p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-bold">My gifts ({gifts.length})</h2>
          <Button size="sm" variant="ghost" disabled={syncing} onClick={() => void syncGifts()}>
            {syncing ? 'Syncing…' : 'Sync'}
          </Button>
        </div>
        {gifts.length === 0 ? (
          <p className="text-[13px] text-alpha-2">
            No gifts yet. Sync to pull your Telegram gift inventory.
          </p>
        ) : (
          <div className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
            {gifts.map((gift) => (
              <div key={gift.id} className="squircle glass-shadow shrink-0 bg-surface-4 p-2 text-center">
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
              </div>
            ))}
          </div>
        )}
      </Card>

      {error ? (
        <p className="squircle bg-destructive/15 px-3 py-2 text-[13px] text-destructive">{error}</p>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <Card className="flex flex-col gap-0.5 p-3">
      <span className="text-[18px] font-black" style={{ color: accent }}>
        {value}
      </span>
      <span className="text-[12px] font-semibold text-alpha-2">{label}</span>
    </Card>
  );
}
