import { CRAFT_STEPS, IMG, MENU, RATING, REVIEW_COUNT } from "../data";
import { useCountUp, useInViewOnce, plural } from "../hooks";
import Reveal from "./Reveal";
import SmartImage from "./SmartImage";

function Stat({
  value,
  decimals = 0,
  suffix = "",
  label,
  started,
  delay,
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  label: string;
  started: boolean;
  delay: number;
}) {
  const v = useCountUp(value, started);
  return (
    <Reveal delay={delay}>
      <div>
        <p className="font-display font-800 text-4xl lg:text-5xl tracking-tight text-paper">
          {/* Скринридеру и поиску — итоговое число, глазам — анимация счётчика */}
          <span className="sr-only">
            {value.toFixed(decimals)}
            {suffix}
          </span>
          <span aria-hidden="true">
            {v.toFixed(decimals)}
            <span className="text-flame">{suffix}</span>
          </span>
        </p>
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-dim mt-2">{label}</p>
      </div>
    </Reveal>
  );
}

/** Позиций в меню — считаем, а не держим числом, которое разъедется с меню */
const DISH_COUNT = MENU.reduce((n, c) => n + c.dishes.length, 0);

export default function Craft() {
  const { ref, inView } = useInViewOnce<HTMLDivElement>(0.3);

  const reviews = Math.round(useCountUp(REVIEW_COUNT, inView));

  return (
    <section id="craft" className="relative py-24 lg:py-32 border-t border-ash/40 scroll-mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 grid lg:grid-cols-2 gap-14 lg:gap-20">
        {/* липкая левая колонка */}
        <div className="lg:sticky lg:top-28 self-start">
          <Reveal>
            <p className="font-mono text-[12px] uppercase tracking-[0.3em] text-ember mb-4">
              ( как мы готовим )
            </p>
            <h2 className="font-display font-800 tracking-tight text-4xl sm:text-5xl lg:text-[3.4rem] leading-[1.04]">
              Быстро —<br />
              <span className="text-flame">не значит</span>
              <br />
              на бегу
            </h2>
            <p className="text-parch leading-relaxed mt-6 max-w-md">
              Мы — маленькая кухня у проспекта, и нам некуда спешить, кроме как к
              тебе. Поэтому всё просто: живой огонь, свои заготовки и никаких
              заготовок «с прошлой недели».
            </p>
          </Reveal>

          <div ref={ref} className="grid grid-cols-2 gap-x-8 gap-y-9 mt-12">
            <Stat value={RATING} decimals={1} label="рейтинг на Яндекс Картах" started={inView} delay={0} />
            <Stat
              value={REVIEW_COUNT}
              suffix="+"
              label={`${plural(reviews, "отзыв", "отзыва", "отзывов")} гостей`}
              started={inView}
              delay={90}
            />
            <Stat value={7} label="минут до готовности" started={inView} delay={180} />
            <Stat
              value={DISH_COUNT}
              label={plural(DISH_COUNT, "позиция в меню", "позиции в меню", "позиций в меню")}
              started={inView}
              delay={270}
            />
          </div>
        </div>

        {/* шаги */}
        <div className="relative">
          <span
            className="absolute left-[27px] top-3 bottom-24 w-px bg-ash/80 hidden sm:block"
            aria-hidden="true"
          />
          <ol className="space-y-0">
            {CRAFT_STEPS.map((step, i) => (
              <Reveal as="li" key={step.num} delay={i * 90} className="relative flex gap-6 pb-12 last:pb-8">
                <span className="relative z-10 w-14 h-14 shrink-0 rounded-full border border-ash bg-soot flex items-center justify-center font-mono font-700 text-sm text-ember">
                  {step.num}
                </span>
                <div className="pt-2">
                  <h3 className="font-display font-700 text-xl lg:text-2xl">{step.title}</h3>
                  <p className="text-parch text-[15px] leading-relaxed mt-3 max-w-md">{step.text}</p>
                </div>
              </Reveal>
            ))}
          </ol>

          <Reveal variant="tilt" tilt={2} className="max-w-md">
            <figure className="relative border border-ash rounded-sm overflow-hidden group shadow-[0_24px_50px_rgba(0,0,0,0.45)]">
              <SmartImage
                src={IMG.wok}
                alt="Вок на живом огне"
                fallbackLabel="вок на огне"
                width={800}
                height={600}
                loading="lazy"
                className="aspect-[4/3] w-full object-cover transition-transform duration-700 group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-coal/80 via-transparent to-transparent" />
              <figcaption className="absolute bottom-0 inset-x-0 p-5 flex items-center gap-3">
                <span className="w-2 h-2 rounded-full bg-flame flicker" />
                <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-parch">
                  вок на живом огне — каждый день с 10:00
                </span>
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
