import { useEffect, useRef, type ReactNode } from 'react';
import { CloseIcon } from './icons';

interface SheetProps {
  open: boolean;
  title: string;
  /** Короткая правда о состоянии: счётчик, лимит. Не заголовок. */
  meta?: string;
  onClose: () => void;
  children: ReactNode;
}

export function Sheet({ open, title, meta, onClose, children }: SheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Фокус уходит в лист и возвращается туда, откуда его открыли.
  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    sheetRef.current?.focus();
    return () => restoreTo.current?.focus?.();
  }, [open]);

  if (!open) return null;

  return (
    <div className="sheet-layer">
      {/* Подложка закрывает лист по тапу, но не притворяется кнопкой для
          скринридера: выход даёт Escape и кнопка закрытия в шапке. */}
      <div className="sheet-backdrop" onClick={onClose} aria-hidden="true" />
      <section
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={sheetRef}
      >
        <header className="sheet__head">
          <div className="sheet__heading">
            <h2 className="sheet__title">{title}</h2>
            {meta && <p className="sheet__meta">{meta}</p>}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Закрыть">
            <CloseIcon />
          </button>
        </header>
        <div className="sheet__body">{children}</div>
      </section>
    </div>
  );
}
