import { RATING, REVIEW_COUNT, REVIEWS, YANDEX_MAPS_URL } from "../data";
import { plural } from "../hooks";
import Reveal from "./Reveal";
import { ArrowUpRight, StarSolid } from "./Icons";

export default function Reviews() {
  return (
    <section id="reviews" className="relative py-24 lg:py-32 border-t border-ash/40 scroll-mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="grid lg:grid-cols-[1fr_auto] gap-8 items-end">
          <Reveal>
            <p className="font-mono text-[12px] uppercase tracking-[0.3em] text-ember mb-4">
              ( отзывы )
            </p>
            <h2 className="font-display font-800 tracking-tight text-4xl sm:text-5xl lg:text-6xl leading-[1.02]">
              Сарафанное
              <br />
              <span className="text-outline">радио</span>
            </h2>
          </Reveal>
          <Reveal delay={140}>
            <a
              href={YANDEX_MAPS_URL}
              target="_blank"
              rel="noreferrer"
              className="group flex items-center gap-5 lg:justify-end"
            >
              <span className="font-display font-800 text-6xl lg:text-7xl text-paper group-hover:text-ember transition-colors">
                {RATING}
              </span>
              <span>
                <span className="flex text-ember gap-0.5" aria-hidden="true">
                  {[...Array(5)].map((_, i) => (
                    <span key={i} className={i === 4 ? "opacity-35" : ""}>
                      <StarSolid className="w-4 h-4" />
                    </span>
                  ))}
                </span>
                <span className="font-mono text-[12px] text-dim mt-2 flex items-center gap-1.5 group-hover:text-parch transition-colors">
                  {REVIEW_COUNT} {plural(REVIEW_COUNT, "отзыв", "отзыва", "отзывов")} на Яндекс
                  Картах
                  <ArrowUpRight className="w-3.5 h-3.5 text-flame" />
                </span>
              </span>
            </a>
          </Reveal>
        </div>

        <div className="mt-14 columns-1 md:columns-2 xl:columns-3 gap-5">
          {REVIEWS.map((r, i) => (
            <Reveal key={r.name + i} delay={(i % 3) * 90} className="mb-5 break-inside-avoid">
              <article className="group border border-ash bg-soot/75 p-6 rounded-md hover:border-flame/50 hover:-translate-y-1.5 transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-300">
                <div className="flex items-center justify-between">
                  <span className="flex text-ember gap-0.5">
                    <span className="sr-only">Оценка: {r.rating} из 5</span>
                    {[...Array(5)].map((_, s) => (
                      <StarSolid
                        key={s}
                        className={`w-3.5 h-3.5 ${s >= r.rating ? "opacity-25" : ""}`}
                      />
                    ))}
                  </span>
                  <span
                    aria-hidden="true"
                    className="font-display font-800 text-3xl text-ash select-none leading-none group-hover:text-dim transition-colors"
                  >
                    „
                  </span>
                </div>
                <p className="text-[15px] leading-relaxed text-parch mt-2">{r.text}</p>
                <footer className="mt-5 pt-4 border-t border-dashed border-ash/70 flex items-center gap-3">
                  <span className="w-9 h-9 rounded-full bg-char border border-ash flex items-center justify-center font-display font-700 text-[13px] text-ember">
                    {r.name[0]}
                  </span>
                  <span>
                    <span className="block font-600 text-sm">{r.name}</span>
                    <span className="block font-mono text-[10.5px] text-dim mt-0.5">{r.date}</span>
                  </span>
                  <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.1em] border border-ash px-2 py-1 rounded-sm text-dim whitespace-nowrap">
                    {r.dish}
                  </span>
                </footer>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal delay={120}>
          <p className="font-mono text-[12px] text-dim mt-8 text-center">
            хочешь добавить свой отзыв?{" "}
            <a
              href={YANDEX_MAPS_URL}
              target="_blank"
              rel="noreferrer"
              className="text-flame underline decoration-dotted underline-offset-4 hover:text-ember transition-colors"
            >
              расскажи на Яндекс Картах
            </a>{" "}
            — мы читаем каждый
          </p>
        </Reveal>
      </div>
    </section>
  );
}
