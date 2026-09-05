/**
 * Тонкая обёртка над Telegram WebApp SDK.
 *
 * Приложение открывается и в обычном браузере (разработка, превью стенда),
 * поэтому каждый вызов защищён проверкой: снаружи Telegram всё превращается
 * в no-op, а не в исключение.
 */

type HapticStyle = 'light' | 'medium' | 'rigid';

interface SafeAreaInset {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

interface TelegramWebApp {
  ready(): void;
  expand(): void;
  disableVerticalSwipes?(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  onEvent?(event: string, handler: () => void): void;
  offEvent?(event: string, handler: () => void): void;
  contentSafeAreaInset?: SafeAreaInset;
  safeAreaInset?: SafeAreaInset;
  initData?: string;
  HapticFeedback?: {
    impactOccurred(style: string): void;
    selectionChanged(): void;
    notificationOccurred(type: string): void;
  };
  BackButton?: {
    show(): void;
    hide(): void;
    onClick(handler: () => void): void;
    offClick(handler: () => void): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export const webApp = (): TelegramWebApp | undefined => window.Telegram?.WebApp;

export const isInsideTelegram = (): boolean => Boolean(webApp()?.initData);

/** Готовит окно под редактор: полный экран, свой тёмный chrome, без свайпа вниз. */
export function initTelegram(): void {
  const app = webApp();
  if (!app) return;
  app.ready();
  app.expand();
  // Свайп вниз закрывает мини-апп и ворует вертикальные жесты у холста.
  app.disableVerticalSwipes?.();
  app.setHeaderColor?.('#0F0F14');
  app.setBackgroundColor?.('#0F0F14');
}

/** Отступы под системную плашку и домашний индикатор, в px. */
export function applySafeAreaVars(): void {
  const app = webApp();
  const root = document.documentElement;
  const inset = app?.contentSafeAreaInset ?? app?.safeAreaInset;
  root.style.setProperty('--tg-top', `${inset?.top ?? 0}px`);
  root.style.setProperty('--tg-bottom', `${inset?.bottom ?? 0}px`);
}

export const haptic = {
  impact(style: HapticStyle = 'light'): void {
    webApp()?.HapticFeedback?.impactOccurred(style);
  },
  selection(): void {
    webApp()?.HapticFeedback?.selectionChanged();
  },
  success(): void {
    webApp()?.HapticFeedback?.notificationOccurred('success');
  },
  warning(): void {
    webApp()?.HapticFeedback?.notificationOccurred('warning');
  },
};

/** Подписка на системную кнопку "назад". Возвращает функцию отписки. */
export function bindBackButton(handler: (() => void) | null): () => void {
  const button = webApp()?.BackButton;
  if (!button) return () => {};
  if (!handler) {
    button.hide();
    return () => {};
  }
  button.onClick(handler);
  button.show();
  return () => {
    button.offClick(handler);
    button.hide();
  };
}
