/**
 * Telegram WebApp bridge.
 *
 * `@telegram-apps/sdk-react` covers most of this, but the Mini App also needs a
 * few surfaces that are only exposed on the raw `window.Telegram.WebApp` object
 * (invoice opening, viewport insets, older haptic shapes). This module wraps
 * both behind one typed API and degrades to no-ops outside Telegram, so the app
 * still runs in a plain browser during development.
 */

export type HapticStyle = 'light' | 'medium' | 'heavy' | 'rigid' | 'soft';
export type HapticNotification = 'error' | 'success' | 'warning';
export type InvoiceStatus = 'paid' | 'cancelled' | 'failed' | 'pending';

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: Record<string, unknown>;
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  themeParams: Record<string, string>;
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
  ready(): void;
  expand(): void;
  close(): void;
  disableVerticalSwipes?(): void;
  enableClosingConfirmation?(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  openInvoice(url: string, callback?: (status: InvoiceStatus) => void): void;
  openTelegramLink(url: string): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  shareToStory?(mediaUrl: string, params?: Record<string, unknown>): void;
  switchInlineQuery?(query: string, chatTypes?: string[]): void;
  HapticFeedback: {
    impactOccurred(style: HapticStyle): void;
    notificationOccurred(type: HapticNotification): void;
    selectionChanged(): void;
  };
  MainButton: {
    text: string;
    isVisible: boolean;
    isActive: boolean;
    show(): void;
    hide(): void;
    enable(): void;
    disable(): void;
    setText(text: string): void;
    setParams(params: {
      text?: string;
      color?: string;
      text_color?: string;
      is_active?: boolean;
      is_visible?: boolean;
    }): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
    showProgress(leaveActive?: boolean): void;
    hideProgress(): void;
  };
  BackButton: {
    isVisible: boolean;
    show(): void;
    hide(): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
  };
  CloudStorage: {
    setItem(key: string, value: string, callback?: (error: Error | null, ok?: boolean) => void): void;
    getItem(key: string, callback: (error: Error | null, value?: string) => void): void;
    removeItem(key: string, callback?: (error: Error | null, ok?: boolean) => void): void;
  };
  BiometricManager?: {
    isInited: boolean;
    isBiometricAvailable: boolean;
    init(callback?: () => void): void;
    authenticate(
      params: { reason?: string },
      callback: (ok: boolean, token?: string) => void,
    ): void;
  };
  onEvent(event: string, handler: (...args: unknown[]) => void): void;
  offEvent(event: string, handler: (...args: unknown[]) => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function getWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null;
  return window.Telegram?.WebApp ?? null;
}

export function isInsideTelegram(): boolean {
  const webApp = getWebApp();
  return Boolean(webApp && webApp.initData.length > 0);
}

/** Raw initData string — the credential every backend call is signed with. */
export function getInitData(): string {
  const webApp = getWebApp();
  if (webApp?.initData) return webApp.initData;
  // Development escape hatch: a signed fixture can be injected via env so the
  // app is usable in a normal browser tab.
  return import.meta.env.VITE_DEV_INIT_DATA ?? '';
}

/**
 * One-time boot. Expands to full height, locks the swipe-to-close gesture
 * (which otherwise fights vertical scrolling inside rooms) and paints the
 * chrome to match our canvas.
 */
export function initTelegram(): void {
  const webApp = getWebApp();
  if (!webApp) return;

  webApp.ready();
  webApp.expand();
  webApp.disableVerticalSwipes?.();
  webApp.setHeaderColor?.('#141414');
  webApp.setBackgroundColor?.('#141414');

  syncViewportInsets();
  const onViewportChanged = () => syncViewportInsets();
  webApp.onEvent('viewportChanged', onViewportChanged);
  webApp.onEvent('safeAreaChanged', onViewportChanged);
}

/**
 * Mirror Telegram's safe-area insets onto the CSS custom properties the layout
 * reads. Telegram only sets these itself from Bot API 8.0 onward.
 */
function syncViewportInsets(): void {
  const webApp = getWebApp();
  if (!webApp || typeof document === 'undefined') return;

  const root = document.documentElement;
  const top = webApp.contentSafeAreaInset?.top ?? webApp.safeAreaInset?.top ?? 0;
  const bottom = webApp.safeAreaInset?.bottom ?? 0;

  root.style.setProperty('--tg-viewport-safe-area-inset-top', `${top}px`);
  root.style.setProperty('--tg-viewport-safe-area-inset-bottom', `${bottom}px`);
  root.style.setProperty('--tg-viewport-stable-height', `${webApp.viewportStableHeight}px`);
}

/* --------------------------------- haptics ------------------------------- */

export const haptics = {
  impact(style: HapticStyle = 'light'): void {
    getWebApp()?.HapticFeedback?.impactOccurred(style);
  },
  notify(type: HapticNotification): void {
    getWebApp()?.HapticFeedback?.notificationOccurred(type);
  },
  select(): void {
    getWebApp()?.HapticFeedback?.selectionChanged();
  },
};

/* -------------------------------- payments ------------------------------- */

/**
 * Open a Stars invoice and resolve with its terminal status. Telegram only
 * calls the callback once, so the promise is safe to await directly.
 */
export function openInvoice(url: string): Promise<InvoiceStatus> {
  return new Promise((resolve) => {
    const webApp = getWebApp();
    if (!webApp) {
      resolve('failed');
      return;
    }
    try {
      webApp.openInvoice(url, (status) => resolve(status));
    } catch {
      resolve('failed');
    }
  });
}

/* ------------------------------ cloud storage ---------------------------- */

export const cloudStorage = {
  get(key: string): Promise<string | null> {
    return new Promise((resolve) => {
      const storage = getWebApp()?.CloudStorage;
      if (!storage) {
        resolve(safeLocalGet(key));
        return;
      }
      storage.getItem(key, (error, value) => resolve(error ? null : value ?? null));
    });
  },
  set(key: string, value: string): Promise<boolean> {
    return new Promise((resolve) => {
      const storage = getWebApp()?.CloudStorage;
      if (!storage) {
        safeLocalSet(key, value);
        resolve(true);
        return;
      }
      storage.setItem(key, value, (error, ok) => resolve(!error && Boolean(ok)));
    });
  },
};

function safeLocalGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeLocalSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private mode or blocked storage: losing a UI preference is acceptable.
  }
}

/* --------------------------------- sharing -------------------------------- */

export function shareStand(standId: string, title: string): void {
  const botUsername = import.meta.env.VITE_BOT_USERNAME ?? 'tgdonate_bot';
  const link = `https://t.me/${botUsername}/app?startapp=stand_${standId}`;
  const text = `Support "${title}" on TgDonate`;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;

  const webApp = getWebApp();
  if (webApp) {
    webApp.openTelegramLink(shareUrl);
    return;
  }
  window.open(shareUrl, '_blank', 'noopener');
}
