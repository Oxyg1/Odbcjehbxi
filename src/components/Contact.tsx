import {
  ADDRESS_LINE_1,
  ADDRESS_LINE_2,
  HOURS,
  PHONE_DISPLAY,
  PHONE_HREF,
  YANDEX_MAPS_URL,
} from "../data";
import Reveal from "./Reveal";
import { ArrowUpRight, ClockIcon, MetroIcon, PhoneIcon, PinIcon } from "./Icons";

function MiniMap() {
  return (
    <div className="relative border border-ash rounded-md overflow-hidden bg-soot shadow-[0_30px_70px_rgba(0,0,0,0.45)]">
      <svg viewBox="0 0 600 470" className="w-full h-auto block" role="img" aria-label="Схема проезда: метро Кутузовская, Кутузовский проспект, дом 36 строение 13/14">
        <rect width="600" height="470" fill="#191410" />
        {/* кварталы */}
        <g fill="#211a11" stroke="#14100b" strokeWidth="2">
          <rect x="30" y="30" width="130" height="80" rx="4" />
          <rect x="195" y="30" width="90" height="65" rx="4" />
          <rect x="320" y="42" width="80" height="60" rx="4" />
          <rect x="30" y="140" width="90" height="70" rx="4" />
          <rect x="150" y="130" width="110" height="80" rx="4" />
          <rect x="470" y="130" width="100" height="70" rx="4" />
          <rect x="480" y="300" width="90" height="70" rx="4" />
          <rect x="200" y="330" width="100" height="60" rx="4" />
        </g>
        {/* парк */}
        <g>
          <rect x="438" y="26" width="118" height="82" rx="10" fill="#20281b" />
          <circle cx="466" cy="50" r="8" fill="#2b3522" />
          <circle cx="494" cy="76" r="10" fill="#2b3522" />
          <circle cx="527" cy="48" r="7" fill="#2b3522" />
          {/* подпись стояла на самой кромке сквера и подрезалась выносными элементами */}
          <text x="497" y="99" textAnchor="middle" fontSize="9" fill="#5a6a48" fontFamily="JetBrains Mono, monospace" letterSpacing="2">
            СКВЕР
          </text>
        </g>
        {/* река */}
        <path d="M0 428 C 150 402, 320 452, 600 408 L 600 470 L 0 470 Z" fill="#1c2325" />
        <text x="120" y="452" fontSize="10" fill="#48565a" fontFamily="JetBrains Mono, monospace" letterSpacing="3">
          МОСКВА-РЕКА
        </text>
        {/* улицы */}
        <path d="M250 0 L 285 470" stroke="#262016" strokeWidth="13" />
        <path d="M0 130 L 600 96" stroke="#262016" strokeWidth="9" />
        <path d="M430 0 L 455 470" stroke="#262016" strokeWidth="11" />
        {/* Кутузовский проспект */}
        <path d="M-10 342 L 610 198" stroke="#2f2617" strokeWidth="30" strokeLinecap="round" />
        <path
          d="M-10 342 L 610 198"
          stroke="#8f8268"
          strokeWidth="2"
          strokeDasharray="12 14"
          opacity="0.5"
        />
        <text
          x="72"
          y="330"
          fontSize="11"
          fill="#6b5f4a"
          fontFamily="JetBrains Mono, monospace"
          letterSpacing="4"
          transform="rotate(-13 72 330)"
        >
          КУТУЗОВСКИЙ ПРОСПЕКТ
        </text>
        {/* маршрут от метро */}
        <path
          d="M124 302 C 210 288, 290 272, 368 252"
          stroke="#ff5c26"
          strokeWidth="2.5"
          strokeDasharray="6 8"
          fill="none"
          className="dash-flow"
        />
        {/* метро */}
        <circle cx="110" cy="308" r="14" fill="#14100b" stroke="#ffb02e" strokeWidth="2" />
        <text x="110" y="313.5" textAnchor="middle" fontSize="13" fill="#ffb02e" fontFamily="JetBrains Mono, monospace" fontWeight="700">
          М
        </text>
        <text x="110" y="340" textAnchor="middle" fontSize="10" fill="#8f8268" fontFamily="JetBrains Mono, monospace">
          м. Кутузовская
        </text>
        {/* здание */}
        <rect x="348" y="220" width="64" height="38" rx="3" fill="#2b2214" stroke="#ff5c26" strokeWidth="1.5" />
        <text x="380" y="210" textAnchor="middle" fontSize="10" fill="#c9bca1" fontFamily="JetBrains Mono, monospace" letterSpacing="1">
          БП «Кутузовский 36»
        </text>
        {/*
          Метка на здании. Была отдельным <div> поверх карты с координатами
          в процентах (63% / 45.5%) — из-за угла привязки и округления точка
          вставала выше дома, у подписи. Внутри SVG она в тех же координатах,
          что и здание, и остаётся на месте при любом размере карты.
        */}
        <g>
          <circle cx="380" cy="239" r="8" fill="#ff5c26" opacity="0.4" className="ping-map" />
          <circle cx="380" cy="239" r="5" fill="#ff5c26" />
          <circle cx="380" cy="239" r="9" fill="none" stroke="#ff5c26" strokeWidth="1" opacity="0.5" />
        </g>
        <rect x="354" y="264" width="52" height="17" rx="2" fill="#ff5c26" />
        <text x="380" y="276.5" textAnchor="middle" fontSize="10.5" fill="#14100b" fontFamily="JetBrains Mono, monospace" fontWeight="700">
          с13/14
        </text>
        {/* компас и масштаб */}
        {/* компас налезал на сквер — сдвинут правее, на свободное поле */}
        <g stroke="#8f8268" strokeWidth="1.4" opacity="0.7">
          <circle cx="578" cy="40" r="11" fill="none" />
          <path d="M578 47 L578 32 M578 32 l-3.5 6 M578 32 l3.5 6" fill="none" />
        </g>
        <text x="578" y="64" textAnchor="middle" fontSize="9" fill="#8f8268" fontFamily="JetBrains Mono, monospace">
          С
        </text>
        <path d="M30 396 h 70" stroke="#8f8268" strokeWidth="2" />
        <path d="M30 391 v 10 M100 391 v 10" stroke="#8f8268" strokeWidth="1.4" />
        <text x="65" y="388" textAnchor="middle" fontSize="9" fill="#8f8268" fontFamily="JetBrains Mono, monospace">
          200 м
        </text>
      </svg>

      <a
        href={YANDEX_MAPS_URL}
        target="_blank"
        rel="noreferrer"
        className="absolute bottom-3 right-3 group flex items-center gap-2 bg-coal/85 backdrop-blur-sm border border-ash px-3.5 py-2 rounded-sm font-mono text-[11px] uppercase tracking-[0.14em] text-parch hover:text-flame hover:border-flame/60 transition-colors"
      >
        открыть маршрут
        <ArrowUpRight className="w-3.5 h-3.5 text-flame group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
      </a>
    </div>
  );
}

export default function Contact() {
  return (
    <section id="contacts" className="relative py-24 lg:py-32 border-t border-ash/40 scroll-mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 grid lg:grid-cols-[1fr_1.15fr] gap-14 lg:gap-16 items-start">
        <div>
          <Reveal>
            <p className="font-mono text-[12px] uppercase tracking-[0.3em] text-ember mb-4">
              ( как добраться )
            </p>
            <h2 className="font-display font-800 tracking-tight text-4xl sm:text-5xl lg:text-[3.4rem] leading-[1.04]">
              Ищи дым
              <br />
              на <span className="text-outline-flame">Кутузовском</span>
            </h2>
          </Reveal>

          <div className="mt-10 space-y-5">
            <Reveal delay={80}>
              <div className="flex items-start gap-4 group">
                <span className="w-11 h-11 shrink-0 rounded-sm border border-ash flex items-center justify-center text-flame group-hover:bg-flame group-hover:text-coal transition-colors duration-300">
                  <PinIcon />
                </span>
                <div>
                  <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-dim">адрес</p>
                  <p className="font-600 text-[15px] mt-1">{ADDRESS_LINE_1}</p>
                  <p className="text-[13px] text-dim mt-0.5">{ADDRESS_LINE_2}</p>
                </div>
              </div>
            </Reveal>
            <Reveal delay={160}>
              <div className="flex items-start gap-4 group">
                <span className="w-11 h-11 shrink-0 rounded-sm border border-ash flex items-center justify-center text-flame group-hover:bg-flame group-hover:text-coal transition-colors duration-300">
                  <MetroIcon />
                </span>
                <div>
                  <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-dim">метро</p>
                  <p className="font-600 text-[15px] mt-1">«Кутузовская» — 5 минут пешком</p>
                  <p className="text-[13px] text-dim mt-0.5">
                    выход к проспекту, иди в сторону центра — увидишь вывеску с огнём
                  </p>
                </div>
              </div>
            </Reveal>
            <Reveal delay={240}>
              <div className="flex items-start gap-4 group">
                <span className="w-11 h-11 shrink-0 rounded-sm border border-ash flex items-center justify-center text-flame group-hover:bg-flame group-hover:text-coal transition-colors duration-300">
                  <PhoneIcon />
                </span>
                <div>
                  <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-dim">телефон</p>
                  <a
                    href={PHONE_HREF}
                    className="font-600 text-[15px] mt-1 inline-block py-1 min-h-[24px] hover:text-ember transition-colors"
                  >
                    {PHONE_DISPLAY}
                  </a>
                  <p className="text-[13px] text-dim mt-0.5">примем предзаказ и подскажем по меню</p>
                </div>
              </div>
            </Reveal>
            <Reveal delay={320}>
              <div className="flex items-start gap-4 group">
                <span className="w-11 h-11 shrink-0 rounded-sm border border-ash flex items-center justify-center text-flame group-hover:bg-flame group-hover:text-coal transition-colors duration-300">
                  <ClockIcon />
                </span>
                <div className="flex-1">
                  <p id="hours-label" className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-dim">
                    часы работы
                  </p>
                  <ul className="mt-2 space-y-1.5 max-w-xs" aria-labelledby="hours-label">
                    {HOURS.map((h) => (
                      <li key={h.days} className="flex items-baseline gap-2 text-[14px]">
                        <span className="text-parch">{h.days}</span>
                        <span className="dotted-leader flex-1 h-3" />
                        <span className="font-mono font-700 text-ember whitespace-nowrap">{h.time}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-[13px] text-dim mt-2">кухня принимает заказы за 30 минут до закрытия</p>
                </div>
              </div>
            </Reveal>
          </div>

          <Reveal delay={380}>
            <div className="mt-10 flex flex-wrap gap-4">
              <a
                href={YANDEX_MAPS_URL}
                target="_blank"
                rel="noreferrer"
                className="group flex items-center gap-3 bg-flame text-coal font-display font-700 text-[13px] uppercase tracking-wide px-6 py-3.5 rounded-sm hover:bg-ember active:scale-95 transition-[color,background-color,border-color,box-shadow,transform,opacity] shadow-[0_0_26px_rgba(255,92,38,0.35)]"
              >
                Мы на Яндекс Картах
                <ArrowUpRight className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </a>
              <a
                href={PHONE_HREF}
                className="flex items-center gap-3 border border-ash text-paper font-display font-500 text-[13px] uppercase tracking-wide px-6 py-3.5 rounded-sm hover:border-flame hover:text-flame active:scale-95 transition-[color,background-color,border-color,box-shadow,transform,opacity]"
              >
                <PhoneIcon className="w-4 h-4" />
                Позвонить
              </a>
            </div>
          </Reveal>
        </div>

        <Reveal variant="left" delay={140} className="lg:sticky lg:top-28">
          <MiniMap />
          <p className="font-mono text-[11px] text-dim mt-4 flex items-center gap-2">
            <span className="w-6 h-px bg-flame inline-block" />
            парковка для гостей — вдоль проспекта, заезд со стороны набережной
          </p>
        </Reveal>
      </div>
    </section>
  );
}
