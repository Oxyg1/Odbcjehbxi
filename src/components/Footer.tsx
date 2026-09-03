import {
  ADDRESS_LINE_1,
  ADDRESS_LINE_2,
  HOURS,
  MARQUEE_CATEGORIES,
  PHONE_DISPLAY,
  PHONE_HREF,
  RATING,
  YANDEX_MAPS_URL,
} from "../data";
import Marquee from "./Marquee";
import { ArrowUpRight, FlameSolid } from "./Icons";

interface FooterProps {
  onNav: (id: string) => void;
}

const NAV = [
  { id: "menu", label: "Меню" },
  { id: "craft", label: "Как готовим" },
  { id: "gallery", label: "Из огня" },
  { id: "reviews", label: "Отзывы" },
  { id: "order", label: "Предзаказ" },
  { id: "contacts", label: "Контакты" },
];

export default function Footer({ onNav }: FooterProps) {
  return (
    <footer className="relative border-t border-ash/40 overflow-hidden">
      <Marquee
        items={MARQUEE_CATEGORIES}
        reverse
        className="border-b border-ash/40 py-3.5"
        itemClassName="font-mono text-[12px] uppercase tracking-[0.28em] text-dim"
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-14 pb-6 grid gap-10 md:grid-cols-[1.5fr_1fr_1.2fr]">
        <div>
          <button
            type="button"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="group flex items-center gap-2.5"
            aria-label="Наверх"
          >
            <FlameSolid className="w-7 h-7 text-flame flicker group-hover:text-ember transition-colors" />
            <span className="font-display font-800 text-xl tracking-tight">КУТУЗА</span>
          </button>
          <p className="text-parch text-[14px] leading-relaxed mt-4 max-w-xs">
            Стрит-фуд на Кутузовском: угли, вок и кофе с собой. Горячее — за семь
            минут, дым — настоящий.
          </p>
          <a
            href={YANDEX_MAPS_URL}
            target="_blank"
            rel="noreferrer"
            className="group inline-flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.16em] text-flame hover:text-ember transition-colors mt-6 py-1 min-h-[24px]"
          >
            ★ {RATING} · отзывы на Яндекс Картах
            <ArrowUpRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </a>
        </div>

        <nav className="flex flex-col gap-1.5" aria-label="Разделы сайта">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-dim mb-2">разделы</p>
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => onNav(n.id)}
              className="text-left font-600 text-[14.5px] text-parch hover:text-flame transition-colors w-fit py-1 min-h-[24px]"
            >
              {n.label}
            </button>
          ))}
        </nav>

        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-dim mb-2">контакты</p>
          <a
            href={PHONE_HREF}
            className="font-display font-700 text-xl text-paper hover:text-ember transition-colors inline-block py-1 min-h-[24px]"
          >
            {PHONE_DISPLAY}
          </a>
          <p className="text-[14px] text-parch mt-3 leading-relaxed">
            {ADDRESS_LINE_1}
            <br />
            <span className="text-dim text-[13px]">{ADDRESS_LINE_2}</span>
          </p>
          <ul className="mt-4 space-y-1">
            {HOURS.map((h) => (
              <li key={h.days} className="font-mono text-[12px] text-dim flex gap-3">
                <span>{h.days}:</span>
                <span className="text-parch">{h.time}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* водяной знак */}
      <div className="relative select-none pointer-events-none" aria-hidden="true">
        <p className="font-display font-900 text-outline-dim leading-[0.78] text-center text-[21vw] -mb-[5vw] whitespace-nowrap">
          КУТУЗА
        </p>
      </div>

      <div className="relative border-t border-ash/40 bg-coal/70">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p className="font-mono text-[11px] text-dim">
            © {new Date().getFullYear()} Kutuza Street Food · Москва, Кутузовский, 36
          </p>
          <p className="font-mono text-[11px] text-dim flex items-center gap-1.5">
            сделано с огнём
            <FlameSolid className="w-3 h-3 text-flame" />
            и дымом
          </p>
        </div>
      </div>
    </footer>
  );
}
