import { useCallback, useEffect, useRef, useState } from "react";
import {
  PHONE_DISPLAY,
  PHONE_HREF,
} from "../data";
import {
  getOpenState,
  useEscapeKey,
  useFocusTrap,
  useNowByMinute,
  useScrollProgress,
} from "../hooks";
import { BagIcon, BurgerMenuIcon, CloseIcon, FlameSolid, PhoneIcon } from "./Icons";

interface HeaderProps {
  cartCount: number;
  onNav: (id: string) => void;
}

const NAV = [
  { id: "menu", label: "Меню" },
  { id: "craft", label: "Как готовим" },
  { id: "gallery", label: "Из огня" },
  { id: "reviews", label: "Отзывы" },
  { id: "contacts", label: "Контакты" },
];

export default function Header({ cartCount, onNav }: HeaderProps) {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const progress = useScrollProgress();
  const now = useNowByMinute();
  const { open: isOpen, label } = getOpenState(now);
  const burgerRef = useRef<HTMLButtonElement | null>(null);

  const close = useCallback(() => setOpen(false), []);
  useEscapeKey(open, close);
  const panelRef = useFocusTrap<HTMLDivElement>(open);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    // Компенсируем ширину скроллбара, иначе страница дёргается при открытии меню
    const gap = window.innerWidth - document.documentElement.clientWidth;
    const prevOverflow = document.body.style.overflow;
    const prevPadding = document.body.style.paddingRight;
    document.body.style.overflow = "hidden";
    if (gap > 0) document.body.style.paddingRight = `${gap}px`;
    return () => {
      document.body.style.overflow = prevOverflow;
      document.body.style.paddingRight = prevPadding;
    };
  }, [open]);

  return (
    <>
      <header
        className={`fixed top-0 inset-x-0 z-50 transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-500 ${
          scrolled
            ? "bg-coal/85 backdrop-blur-md border-b border-ash/50 py-2.5"
            : "bg-transparent py-4"
        }`}
      >
        {/* прогресс скролла */}
        <div
          className="absolute top-0 left-0 h-[2px] bg-flame transition-[width] duration-150 ease-out"
          style={{ width: `${progress * 100}%` }}
          aria-hidden="true"
        />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between gap-4">
          {/* логотип */}
          <button
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="group flex items-center gap-2.5 shrink-0"
            aria-label="Наверх"
          >
            <FlameSolid className="w-7 h-7 text-flame flicker group-hover:text-ember transition-colors" />
            <span className="leading-none text-left">
              <span className="block font-display font-800 tracking-tight text-lg sm:text-xl">
                КУТУЗА
              </span>
              <span className="block font-mono text-[10px] uppercase tracking-[0.28em] text-dim mt-0.5">
                street food
              </span>
            </span>
          </button>

          {/* навигация */}
          <nav className="hidden lg:flex items-center gap-7">
            {NAV.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => onNav(n.id)}
                className="font-mono text-[12px] uppercase tracking-[0.18em] text-parch hover:text-flame transition-colors relative py-2 after:absolute after:left-0 after:bottom-0.5 after:h-[2px] after:w-0 after:bg-flame after:transition-[color,background-color,border-color,box-shadow,transform,opacity] hover:after:w-full"
              >
                {n.label}
              </button>
            ))}
          </nav>

          {/* правая часть */}
          <div className="flex items-center gap-3">
            <span
              role="status"
              className={`hidden xl:flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider px-3 py-1.5 rounded-full border ${
                isOpen
                  ? "border-leaf/40 text-leaf"
                  : "border-flame/40 text-flame"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  isOpen ? "bg-leaf" : "bg-flame"
                }`}
                style={{ animation: isOpen ? "pulse-dot 2s infinite" : "pulse-dot-red 2s infinite" }}
              />
              {label}
            </span>
            <a
              href={PHONE_HREF}
              className="hidden md:flex items-center gap-2 font-mono text-[13px] text-parch hover:text-ember transition-colors py-1.5 min-h-[24px]"
            >
              <PhoneIcon className="w-4 h-4" />
              {PHONE_DISPLAY}
            </a>
            <button
              type="button"
              onClick={() => onNav("order")}
              className="relative flex items-center gap-2 bg-flame text-coal font-display font-700 text-[12px] sm:text-[13px] uppercase tracking-wide px-4 sm:px-5 py-2.5 rounded-sm hover:bg-ember active:scale-95 transition-[color,background-color,border-color,box-shadow,transform,opacity] shadow-[0_0_24px_rgba(255,92,38,0.35)]"
            >
              <BagIcon className="w-4 h-4" />
              <span className="hidden sm:inline">Предзаказ</span>
              {cartCount > 0 && (
                <span
                  key={cartCount}
                  className="bump absolute -top-2 -right-2 min-w-[20px] h-5 px-1 rounded-full bg-coal text-ember font-mono text-[11px] font-700 flex items-center justify-center border border-ember/60"
                >
                  {cartCount}
                </span>
              )}
            </button>
            <button
              ref={burgerRef}
              onClick={() => setOpen(true)}
              className="lg:hidden p-2 text-paper hover:text-flame transition-colors"
              aria-label="Открыть меню"
              aria-expanded={open}
              aria-controls="mobile-menu"
            >
              <BurgerMenuIcon />
            </button>
          </div>
        </div>
      </header>

      {/* мобильное меню */}
      <div
        id="mobile-menu"
        className={`fixed inset-0 z-[80] lg:hidden transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-500 ${
          open ? "visible opacity-100" : "invisible opacity-0"
        }`}
        // Закрытое меню не должно попадать ни в озвучку, ни в обход по Tab
        aria-hidden={!open}
        {...(open ? {} : { inert: "" })}
      >
        <div
          className="absolute inset-0 bg-coal/70 backdrop-blur-sm"
          onClick={close}
          aria-hidden="true"
        />
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label="Меню сайта"
          className={`absolute right-0 top-0 h-full w-[82%] max-w-sm bg-soot border-l border-ash p-7 flex flex-col transition-transform duration-500 ${
            open ? "translate-x-0" : "translate-x-full"
          }`}
        >
          <div className="flex items-center justify-between mb-10">
            <span className="flex items-center gap-2 font-display font-800 text-lg">
              <FlameSolid className="w-6 h-6 text-flame" /> КУТУЗА
            </span>
            <button
              onClick={close}
              className="p-2 text-parch hover:text-flame transition-colors"
              aria-label="Закрыть меню"
            >
              <CloseIcon />
            </button>
          </div>
          <nav className="flex flex-col gap-1.5">
            {[...NAV, { id: "order", label: "Предзаказ" }].map((n, i) => (
              <button
                key={n.id}
                onClick={() => {
                  close();
                  window.setTimeout(() => onNav(n.id), 60);
                }}
                className="text-left font-display font-700 text-2xl py-2.5 text-paper hover:text-flame transition-colors flex items-baseline gap-3"
              >
                <span className="font-mono text-[11px] text-dim">0{i + 1}</span>
                {n.label}
              </button>
            ))}
          </nav>
          <div className="mt-auto space-y-3 border-t border-dashed border-ash pt-6">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-dim">
              {isOpen ? (
                <span className="text-leaf">● {label}</span>
              ) : (
                <span className="text-flame">● {label}</span>
              )}
            </p>
            <a href={PHONE_HREF} className="flex items-center gap-2 text-parch font-mono text-sm py-1.5 min-h-[24px]">
              <PhoneIcon className="w-4 h-4 text-flame" /> {PHONE_DISPLAY}
            </a>
            <p className="font-mono text-[12px] text-dim leading-relaxed">
              Кутузовский проспект, 36 с13/14 · м. Кутузовская
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
