import { useEffect, useRef } from 'react';
import { getWebApp } from '../lib/telegram.js';

/**
 * Drives Telegram's native MainButton from React.
 *
 * The button is a singleton owned by the client, so the handler is kept in a
 * ref and re-registered only when the button's identity changes — otherwise
 * every render would detach and reattach a listener, and a tap landing between
 * the two would be dropped.
 */
export function useMainButton(options: {
  text: string;
  visible: boolean;
  enabled?: boolean;
  loading?: boolean;
  color?: string;
  onClick: () => void;
}): void {
  const handlerRef = useRef(options.onClick);
  handlerRef.current = options.onClick;

  useEffect(() => {
    const webApp = getWebApp();
    if (!webApp) return;
    const button = webApp.MainButton;

    const handler = () => handlerRef.current();
    button.onClick(handler);

    return () => {
      button.offClick(handler);
      button.hide();
    };
  }, []);

  useEffect(() => {
    const webApp = getWebApp();
    if (!webApp) return;
    const button = webApp.MainButton;

    if (!options.visible) {
      button.hide();
      return;
    }

    button.setParams({
      text: options.text,
      color: options.color ?? '#49df64',
      text_color: '#0b0b0b',
      is_active: options.enabled !== false,
      is_visible: true,
    });

    if (options.loading) button.showProgress(false);
    else button.hideProgress();
  }, [options.text, options.visible, options.enabled, options.loading, options.color]);
}

/** Shows Telegram's native back button and routes it to `onBack`. */
export function useBackButton(visible: boolean, onBack: () => void): void {
  const handlerRef = useRef(onBack);
  handlerRef.current = onBack;

  useEffect(() => {
    const webApp = getWebApp();
    if (!webApp) return;
    const button = webApp.BackButton;

    const handler = () => handlerRef.current();
    button.onClick(handler);

    return () => {
      button.offClick(handler);
      button.hide();
    };
  }, []);

  useEffect(() => {
    const webApp = getWebApp();
    if (!webApp) return;
    if (visible) webApp.BackButton.show();
    else webApp.BackButton.hide();
  }, [visible]);
}
