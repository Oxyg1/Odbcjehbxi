import { IMG, RATING, REVIEW_COUNT, TICKER_ITEMS, YANDEX_MAPS_URL } from "../data";
import {
  fmtPrice,
  getMoscowTimeString,
  getOpenState,
  plural,
  useNow,
  useNowByMinute,
  useScramble,
} from "../hooks";
import Marquee from "./Marquee";
import SmartImage from "./SmartImage";
import { ArrowRight, FlameSolid, StarSolid } from "./Icons";

/**
 * Часы вынесены в отдельный компонент.
 * Они тикают раз в секунду, и раньше вместе с ними каждую секунду
 * перерисовывался весь первый экран — угольки, чек, бегущая строка.
 */
function MoscowClock() {
  const now = useNow();
  return <>{getMoscowTimeString(now)}</>;
}

interface HeroProps {
  onNav: (id: string) => void;
}

const RECEIPT = [
  { name: "Бургер «Зверь»", price: 490 },
  { name: "Фри «Кутуза»", price: 190 },
  { name: "Капучино", price: 230 },
];

const EMBERS = [
  { left: "8%", delay: "0s", size: 4, color: "#ffb02e" },
  { left: "22%", delay: "2.6s", size: 3, color: "#ff5c26" },
  { left: "37%", delay: "1.2s", size: 5, color: "#ffb02e" },
  { left: "58%", delay: "3.4s", size: 3, color: "#ff5c26" },
  { left: "71%", delay: "0.8s", size: 4, color: "#ffb02e" },
  { left: "86%", delay: "4.1s", size: 3, color: "#ff5c26" },
  { left: "48%", delay: "5.2s", size: 4, color: "#ffb02e" },
  { left: "93%", delay: "2s", size: 3, color: "#ffb02e" },
];

export default function Hero({ onNav }: HeroProps) {
  const title = useScramble("КУТУЗА", 250);
  const now = useNowByMinute();
  const { open: isOpen, label } = getOpenState(now);
  const total = RECEIPT.reduce((s, r) => s + r.price, 0);

  return (
    <section className="relative min-h-screen flex flex-col overflow-hidden">
      {/* фото на фоне справа */}
      <div className="absolute inset-y-0 right-0 w-full md:w-[56%] hidden sm:block">
        <div className="absolute inset-0 overflow-hidden">
          <SmartImage
            src={IMG.burger}
            alt="Бургер «Зверь» на углях"
            fallbackLabel="бургер на углях"
            width={1200}
            height={1600}
            fetchPriority="high"
            className="kenburns w-full h-full object-cover object-center opacity-50 md:opacity-70"
          />
        </div>
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, #14100b 0%, rgba(20,16,11,0.72) 34%, rgba(20,16,11,0.12) 78%, rgba(20,16,11,0.4) 100%)",
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(0deg, #14100b 2%, rgba(20,16,11,0) 30%, rgba(20,16,11,0) 80%, rgba(20,16,11,0.7) 100%)",
          }}
        />
      </div>

      {/* тлеющие угольки */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        {EMBERS.map((e, i) => (
          <span
            key={i}
            className="absolute bottom-[18%] rounded-full blur-[1px]"
            style={{
              left: e.left,
              width: e.size,
              height: e.size,
              background: e.color,
              animation: `ember-rise ${7 + (i % 4) * 1.7}s linear ${e.delay} infinite`,
            }}
          />
        ))}
      </div>

      {/* контент */}
      <div className="relative z-10 max-w-7xl mx-auto w-full px-4 sm:px-6 pt-32 sm:pt-36 lg:pt-40 pb-40 flex-1 grid lg:grid-cols-12 gap-10 lg:gap-6 items-start">
        <div className="lg:col-span-8">
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <span
              role="status"
              className={`flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] px-3 py-1.5 rounded-full border ${
                isOpen ? "border-leaf/40 text-leaf" : "border-flame/40 text-flame"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${isOpen ? "bg-leaf" : "bg-flame"}`}
                style={{
                  animation: isOpen ? "pulse-dot 2s infinite" : "pulse-dot-red 2s infinite",
                }}
              />
              {label}
            </span>
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-dim">
              Москва · сейчас <MoscowClock />
            </span>
          </div>

          <p className="font-mono text-[12px] sm:text-[13px] uppercase tracking-[0.34em] text-ember mb-4">
            стрит-фуд / бургеры / вок / гриль
          </p>

          {/*
            Эффект «расшифровки» — чисто визуальный, поэтому он в aria-hidden
            span'е, а доступное имя заголовка задано через aria-label.
            Иначе скринридер зачитывал промежуточный мусор вида «<+#К<<».
          */}
          <h1
            aria-label="Кутуза"
            className="font-display font-900 tracking-tight leading-[0.94] text-[17.5vw] sm:text-[15vw] lg:text-[8.6rem] xl:text-[10rem]"
          >
            <span aria-hidden="true">{title || "КУТУЗА"}</span>
          </h1>
          <p className="font-display font-300 text-outline text-[6.4vw] sm:text-[4.6vw] lg:text-4xl xl:text-5xl tracking-tight -mt-1 lg:-mt-2">
            НА КУТУЗОВСКОМ
          </p>

          <p className="mt-7 max-w-xl text-parch text-base sm:text-lg leading-relaxed">
            Бургеры на берёзовых углях, вок с живым огнём и кофе с собой — в пяти
            минутах от метро. Горячее уходит с кухни{" "}
            <span className="text-ember font-600">за 7 минут</span>, дым — настоящий,
            всё как на улице, только теплее.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              onClick={() => onNav("menu")}
              className="group flex items-center gap-3 bg-flame text-coal font-display font-700 text-sm uppercase tracking-wide px-7 py-4 rounded-sm hover:bg-ember active:scale-95 transition-[color,background-color,border-color,box-shadow,transform,opacity] shadow-[0_0_34px_rgba(255,92,38,0.4)]"
            >
              Смотреть меню
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </button>
            <button
              onClick={() => onNav("order")}
              className="group flex items-center gap-3 border border-ash text-paper font-display font-500 text-sm uppercase tracking-wide px-7 py-4 rounded-sm hover:border-flame hover:text-flame active:scale-95 transition-[color,background-color,border-color,box-shadow,transform,opacity]"
            >
              Забрать самовывозом
            </button>
          </div>

          <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2">
            <a
              href={YANDEX_MAPS_URL}
              target="_blank"
              rel="noreferrer"
              className="group flex items-center gap-2"
            >
              <span className="flex text-ember" aria-hidden="true">
                {[...Array(5)].map((_, i) => (
                  <StarSolid key={i} className="w-4 h-4" />
                ))}
              </span>
              <span className="font-display font-700 text-lg">{RATING}</span>
              <span className="font-mono text-[12px] text-dim group-hover:text-parch transition-colors underline decoration-dotted underline-offset-4">
                {REVIEW_COUNT}+ {plural(REVIEW_COUNT, "отзыв", "отзыва", "отзывов")} на Яндекс
                Картах
              </span>
            </a>
          </div>
        </div>

        {/* чек */}
        <div className="lg:col-span-4 lg:pt-6 hidden sm:block">
          <div className="relative max-w-[320px] ml-auto rotate-2 hover:rotate-0 transition-transform duration-500">
            <div className="absolute -inset-6 bg-flame/10 blur-2xl rounded-full" aria-hidden="true" />
            <div className="on-paper relative bg-paper text-coal shadow-[0_30px_60px_rgba(0,0,0,0.55)] px-6 pt-6 pb-5 font-mono text-[13px]">
              <div className="text-center border-b border-dashed border-coal/40 pb-4 mb-4">
                <p className="font-display font-800 text-lg tracking-tight">КУТУЗА</p>
                <p className="text-[10px] uppercase tracking-[0.3em] text-coal/60 mt-1">
                  street food · чек №001
                </p>
                <p className="text-[10px] text-coal/50 mt-1">кутузовский, 36 с13/14</p>
              </div>
              <ul className="space-y-2.5">
                {RECEIPT.map((r) => (
                  <li key={r.name} className="flex items-baseline gap-2">
                    <span className="font-600">{r.name}</span>
                    <span className="dotted-leader flex-1 h-3" />
                    <span>{fmtPrice(r.price)}</span>
                  </li>
                ))}
              </ul>
              <div className="border-t border-dashed border-coal/40 mt-4 pt-3 flex items-baseline gap-2">
                <span className="uppercase tracking-[0.2em] text-[11px]">Итого</span>
                <span className="dotted-leader flex-1 h-3" />
                <span className="font-700 text-[15px]">{fmtPrice(total)}</span>
              </div>
              <p className="text-center text-[10px] uppercase tracking-[0.24em] text-coal/60 mt-4">
                ★ спасибо, ждём в гости ★
              </p>
              {/* штрих-код */}
              <svg viewBox="0 0 200 26" className="w-full mt-3" aria-hidden="true">
                {[...Array(38)].map((_, i) => (
                  <rect
                    key={i}
                    x={i * 5.3}
                    y="0"
                    width={(i * 7) % 3 === 0 ? 3 : (i * 5) % 4 === 0 ? 1 : 2}
                    height="26"
                    fill="#14100b"
                    opacity={0.85}
                  />
                ))}
              </svg>
              <p className="text-center text-[9px] tracking-[0.4em] text-coal/50 mt-1">
                KUTUZA·ST·FOOD
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* подсказка скролла */}
      <div className="relative z-10 max-w-7xl mx-auto w-full px-4 sm:px-6 pb-24 hidden md:flex items-center gap-3 text-dim">
        <span className="font-mono text-[11px] uppercase tracking-[0.28em]">листай вниз</span>
        <span className="relative h-px w-24 bg-ash overflow-hidden">
          <span className="absolute inset-y-0 left-0 w-8 bg-flame animate-[marquee_2.2s_linear_infinite]" />
        </span>
        <FlameSolid className="w-3.5 h-3.5 text-flame flicker" />
      </div>

      {/* бегущая строка */}
      <div className="absolute bottom-0 inset-x-0 z-20 -rotate-[1.1deg] scale-[1.02]">
        <Marquee
          items={TICKER_ITEMS}
          className="bg-flame text-coal border-y-2 border-flamedark/60"
          itemClassName="font-display font-700 text-[13px] sm:text-[15px] uppercase tracking-wide py-3 sm:py-3.5"
        />
      </div>
    </section>
  );
}
