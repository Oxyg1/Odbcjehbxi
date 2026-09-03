import { IMG } from "../data";
import Reveal from "./Reveal";
import SmartImage from "./SmartImage";

interface Shot {
  src: string;
  caption: string;
  alt: string;
  pos: string;
  rotate: string;
  delay: number;
}

const SHOTS: Shot[] = [
  {
    src: IMG.burger,
    caption: "«Зверь» — прямо с углей",
    alt: "Бургер «Зверь»",
    pos: "left-[1%] top-[2%] w-[31%]",
    rotate: "-rotate-3 hover:rotate-0",
    delay: 0,
  },
  {
    src: IMG.wok,
    caption: "вок, огонь, тянется лапша",
    alt: "Вок с лапшой на огне",
    pos: "left-[35%] top-[9%] w-[26%]",
    rotate: "rotate-2 hover:rotate-0",
    delay: 110,
  },
  {
    src: IMG.steak,
    caption: "свинина в пивной глазури",
    alt: "Стейк из свинины",
    pos: "right-[1%] top-[0%] w-[28%]",
    rotate: "rotate-3 hover:rotate-0",
    delay: 220,
  },
  {
    src: IMG.fries,
    caption: "фри с копчёной паприкой",
    alt: "Картофель фри",
    pos: "left-[12%] top-[52%] w-[27%]",
    rotate: "rotate-2 hover:rotate-0",
    delay: 330,
  },
  {
    src: IMG.coffee,
    caption: "капучино в крафте",
    alt: "Кофе с собой",
    pos: "right-[10%] top-[51%] w-[25%]",
    rotate: "-rotate-2 hover:rotate-0",
    delay: 440,
  },
];

function Postcard({ shot, mobile }: { shot: Shot; mobile?: boolean }) {
  const rotateClass = mobile ? shot.rotate.split(" ")[0] : shot.rotate;
  return (
    <figure
      className={`on-paper bg-paper p-2.5 pb-3.5 shadow-[0_22px_46px_rgba(0,0,0,0.5)] transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-500 hover:-translate-y-2 hover:shadow-[0_30px_60px_rgba(0,0,0,0.6)] ${rotateClass}`}
    >
      <div className="overflow-hidden">
        <SmartImage
          src={shot.src}
          alt={shot.alt}
          fallbackLabel={shot.alt}
          width={600}
          height={600}
          loading="lazy"
          className="aspect-square w-full object-cover transition-transform duration-700 hover:scale-110"
        />
      </div>
      <figcaption className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-coal/70 mt-2.5 px-1 flex items-center justify-between gap-2">
        {shot.caption}
        {/* был text-flame поверх светлой карточки — 2.6:1, не читалось */}
        <span className="text-flamedark" aria-hidden="true">
          ✶
        </span>
      </figcaption>
    </figure>
  );
}

export default function Gallery() {
  return (
    <section id="gallery" className="relative py-24 lg:py-32 border-t border-ash/40 scroll-mt-24 overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="grid lg:grid-cols-2 gap-6 lg:gap-12 items-end">
          <Reveal>
            <p className="font-mono text-[12px] uppercase tracking-[0.3em] text-ember mb-4">
              ( из огня )
            </p>
            <h2 className="font-display font-800 tracking-tight text-4xl sm:text-5xl lg:text-6xl leading-[1.02]">
              Еда, которая
              <br />
              <span className="text-outline">дымится</span>
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="text-parch leading-relaxed max-w-md lg:ml-auto">
              Пять вещей, ради которых к нам возвращаются с набережной, из офисов
              БП и из метро. Снято у нас на кухне — без фильтров, только жар.
            </p>
          </Reveal>
        </div>

        {/* разброс на десктопе */}
        <div className="hidden md:block relative mt-16 lg:mt-20 h-[640px] lg:h-[780px]">
          {SHOTS.map((shot) => (
            <Reveal key={shot.caption} delay={shot.delay} className={`${shot.pos} absolute`}>
              <Postcard shot={shot} />
            </Reveal>
          ))}
          <Reveal delay={520} className="absolute left-[44%] top-[58%] w-[16%] hidden lg:block">
            <div className="rotate-6 hover:rotate-0 transition-transform duration-500 border-2 border-dashed border-ash p-4 text-center">
              <p className="font-display font-800 text-3xl text-flame">4.8</p>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-dim mt-1.5">
                оценка гостей
              </p>
            </div>
          </Reveal>
        </div>

        {/* сетка на мобильных */}
        <div className="md:hidden grid grid-cols-2 gap-4 mt-12">
          {SHOTS.map((shot, i) => (
            <Reveal
              key={shot.caption}
              delay={i * 70}
              className={i % 2 === 1 ? "mt-8" : ""}
            >
              <Postcard shot={shot} mobile />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
