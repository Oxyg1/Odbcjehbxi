import type {
  DonationEventPayload,
  Leaderboard,
  LeaderboardScope,
  Listing,
  ListingKind,
  PublicUser,
  Room,
  Stand,
  StandTheme,
} from '@tgdonate/shared';
import { getInitData } from './telegram.js';

/**
 * Where the API lives.
 *
 * Default to same-origin (an empty base, so paths stay relative). The Mini App
 * is served by the same nginx that proxies /api and /ws to the backend, so no
 * configuration is needed for the normal deployment — and a same-origin request
 * can never be blocked as mixed content.
 *
 * VITE_API_URL is only for split deployments where the API sits on another
 * host. It is baked in at build time, so pointing it at localhost ships a
 * bundle that asks the *viewer's own device* for the API — which is what a
 * phone opening the Mini App would do.
 */
const API_BASE = resolveApiBase();

function resolveApiBase(): string {
  const configured = import.meta.env.VITE_API_URL?.trim();
  if (!configured) return '';

  const base = configured.replace(/\/$/, '');
  if (typeof window !== 'undefined' && isLoopback(base) && !isLoopback(window.location.origin)) {
    // Refusing to use it is better than a wall of failed requests: this build
    // cannot reach its API from anywhere except the machine that built it.
    console.error(
      `[tgdonate] VITE_API_URL is "${base}" but the app is served from ` +
        `"${window.location.origin}". A loopback address cannot be reached from ` +
        'a user device. Falling back to same-origin; set VITE_API_URL to your ' +
        'public URL (or leave it empty) and rebuild.',
    );
    return '';
  }
  return base;
}

export function isLoopback(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
  } catch {
    return false;
  }
}

/** The resolved API origin, or "same origin" when requests are relative. */
export const apiOrigin =
  API_BASE || (typeof window !== 'undefined' ? `${window.location.origin} (same origin)` : '');

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      'content-type': 'application/json',
      // Every request carries the signed launch payload; the server re-verifies
      // its HMAC on each call rather than issuing a session token.
      'x-telegram-init-data': getInitData(),
    },
    ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    ...(options.signal ? { signal: options.signal } : {}),
  });

  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const code = (payload as { error?: string } | null)?.error ?? 'UNKNOWN';
    const message =
      (payload as { message?: string } | null)?.message ?? `Request failed (${response.status})`;
    throw new ApiError(response.status, code, message);
  }
  return payload as T;
}

export interface MeResponse {
  user: PublicUser & {
    tonWallet: string | null;
    starsDonated: number;
    starsReceived: number;
    giftsDonated: number;
    giftsReceived: number;
  };
  unlockedThemeIds: string[];
  startParam: string | null;
}

export interface OwnedGift {
  id: string;
  telegramGiftId: string;
  slug: string;
  title: string;
  rarity: 'COMMON' | 'RARE' | 'EPIC' | 'LEGENDARY';
  previewUrl: string | null;
  attributes: Array<{ type: string; name: string; rarityPermille: number }>;
  state: string;
  listingId: string | null;
}

export const api = {
  me: () => request<MeResponse>('/api/me'),

  rooms: () => request<{ rooms: Room[] }>('/api/rooms'),
  room: (id: string) => request<{ room: Room; stands: Stand[] }>(`/api/rooms/${id}`),
  suggestRoom: () => request<{ roomId: string; slug: string }>('/api/rooms/suggest', { method: 'POST' }),

  myStand: () => request<{ stand: Stand }>('/api/stands/me'),
  stand: (id: string) => request<{ stand: Stand }>(`/api/stands/${id}`),
  trendingStands: () => request<{ stands: Stand[] }>('/api/stands/trending'),
  standSupporters: (id: string, limit = 20) =>
    request<{ donations: DonationEventPayload[] }>(`/api/stands/${id}/supporters?limit=${limit}`),

  updateStand: (body: {
    title?: string;
    goal?: string | null;
    goalTargetStars?: number | null;
    themeId?: string;
    bannerStyle?: string;
    roomId?: string | null;
    isPublished?: boolean;
  }) => request<{ stand: Stand }>('/api/stands/me', { method: 'PATCH', body }),

  createListing: (body: {
    kind: ListingKind;
    title: string;
    description?: string | null;
    priceStars?: number | null;
    priceNanoton?: string | null;
    supply?: number | null;
    giftId?: string | null;
  }) => request<{ listing: Listing }>('/api/stands/me/listings', { method: 'POST', body }),

  updateListing: (
    listingId: string,
    body: {
      title?: string;
      description?: string | null;
      priceStars?: number | null;
      supply?: number | null;
      status?: 'ACTIVE' | 'HIDDEN';
    },
  ) =>
    request<{ listing: Listing }>(`/api/stands/me/listings/${listingId}`, {
      method: 'PATCH',
      body,
    }),

  deleteListing: (listingId: string) =>
    request<void>(`/api/stands/me/listings/${listingId}`, { method: 'DELETE' }),

  reorderListings: (order: string[]) =>
    request<{ stand: Stand }>('/api/stands/me/listings/reorder', { method: 'POST', body: { order } }),

  themes: () => request<{ themes: StandTheme[] }>('/api/themes'),

  leaderboard: (scope: LeaderboardScope, limit = 50) =>
    request<{ leaderboard: Leaderboard }>(`/api/leaderboard?scope=${scope}&limit=${limit}`),

  activity: (limit = 30) =>
    request<{ donations: DonationEventPayload[] }>(`/api/activity?limit=${limit}`),

  myGifts: () => request<{ gifts: OwnedGift[] }>('/api/me/gifts'),
  syncGifts: () => request<{ synced: number }>('/api/me/gifts/sync', { method: 'POST' }),

  starsInvoice: (body: {
    standId: string;
    listingId?: string | null;
    amountStars: number;
    isAnonymous?: boolean;
    message?: string | null;
  }) =>
    request<{
      invoiceLink: string;
      transactionId: string;
      breakdown: { gross: number; fee: number; net: number; feeBps: number };
    }>('/api/payments/stars/invoice', { method: 'POST', body }),

  themeInvoice: (themeId: string) =>
    request<{ invoiceLink: string }>('/api/payments/stars/theme-invoice', {
      method: 'POST',
      body: { themeId },
    }),

  tonIntent: (body: {
    standId: string;
    listingId?: string | null;
    amountNanoton: string;
    isAnonymous?: boolean;
    message?: string | null;
  }) =>
    request<{
      transactionId: string;
      escrowAddress: string;
      amountNanoton: string;
      comment: string;
      validUntil: number;
    }>('/api/payments/ton/intent', { method: 'POST', body }),

  tonProofPayload: () =>
    request<{ payload: string }>('/api/wallet/ton-proof-payload', { method: 'POST' }),

  linkWallet: (body: {
    address: string;
    publicKey: string;
    proof: {
      timestamp: number;
      domain: { lengthBytes: number; value: string };
      signature: string;
      payload: string;
      stateInit?: string;
    };
  }) => request<{ walletRaw: string | null }>('/api/wallet/link', { method: 'POST', body }),

  fee: () => request<{ feeBps: number; feePercent: number }>('/api/payments/fee'),
};
