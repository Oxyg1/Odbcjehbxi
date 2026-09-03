import { useState } from "react";
import { MENU, type Dish, type DishTag } from "../data";
import { fmtPrice, plural } from "../hooks";
import Reveal from "./Reveal";
import SmartImage from "./SmartImage";
import { PlusIcon } from "./Icons";

interface MenuSectionProps {
  onAdd: (dish: Dish) => void;
}

const TAG_STYLE: Record<DishTag, string> = {
  хит: "bg-flame text-coal border-flame",
  новинка: "bg-ember text-coal border-ember",
  острое: "text-flame border-flame/70",
  веган: "text-leaf border-leaf/60",
};

function Tag({ tag }: { tag: DishTag }) {
  return (
    <span
      className={`font-mono text-[9.5px] uppercase tracking-[0.14em] px-1.5 py-0.5 border rounded-sm ${TAG_STYLE[tag]}`}
    >
      {tag}
    </span>
  );
}

export default function MenuSection({ onAdd }: MenuSectionProps) {
  const [activeId, setActiveId] = useState(MENU[0].id);
  const [lastAdded, setLastAdded] = useState<{ id: string; ts: number } | null>(null);
  const cat = MENU.find((c) => c.id === activeId) ?? MENU[0];

  const handleAdd = (dish: Dish) => {
    onAdd(dish);
    setLastAdded({ id: dish.id, ts: Date.now() });
  };

  return (
    <section id="menu" className="relative py-24 lg:py-32 scroll-mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        {/* заголовок */}
        <div className="grid lg:grid-cols-2 gap-6 lg:gap-12 items-end">
          <Reveal>
            <p className="font-mono text-[12px] uppercase tracking-[0.3em] text-ember mb-4">
              ( меню )
            </p>
            <h2 className="font-display font-800 tracking-tight text-4xl sm:text-5xl lg:text-6xl leading-[1.02]">
              Что сегодня
              <br />
              <span className="text-outline">в огне</span>
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="text-parch leading-relaxed max-w-md lg:ml-auto">
              Шесть разделов, всё готовится при тебе: угли, вок, свежая зелень.
              Цены честные, порции — без «аэропорта». Самовывозом{" "}
              <span className="text-ember font-600">скидка 10%</span>.
            </p>
          </Reveal>
        </div>

        {/* вкладки */}
        <Reveal delay={160}>
          <div className="mt-12 flex flex-wrap gap-2" role="group" aria-label="Разделы меню">
            {MENU.map((c) => {
              const active = c.id === activeId;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setActiveId(c.id)}
                  aria-pressed={active}
                  className={`font-mono text-[12px] uppercase tracking-[0.12em] px-4 py-2.5 rounded-sm border transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-300 active:scale-95 ${
                    active
                      ? "bg-ember text-coal border-ember font-700 shadow-[0_0_22px_rgba(255,176,46,0.3)]"
                      : "border-ash text-parch hover:border-ember/70 hover:text-paper"
                  }`}
                >
                  {c.label}
                  <span className={`ml-1.5 ${active ? "opacity-60" : "text-dim"}`}>
                    {c.dishes.length}
                  </span>
                  <span className="sr-only"> {plural(c.dishes.length, "блюдо", "блюда", "блюд")}</span>
                </button>
              );
            })}
          </div>
        </Reveal>

        {/* тело */}
        <div className="mt-10 grid lg:grid-cols-[330px_1fr] gap-10 lg:gap-14">
          {/* липкая карточка категории */}
          <aside className="hidden lg:block">
            <div className="sticky top-28">
              <Reveal variant="left">
                <figure className="relative border border-ash rounded-sm overflow-hidden group">
                  <SmartImage
                    key={cat.id}
                    src={cat.image}
                    alt={cat.label}
                    fallbackLabel={cat.label}
                    width={640}
                    height={800}
                    loading="lazy"
                    className="rise-in aspect-[4/5] w-full object-cover transition-transform duration-700 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-coal/85 via-transparent to-transparent" />
                  <figcaption className="absolute bottom-0 inset-x-0 p-5">
                    <p className="font-display font-700 text-2xl">{cat.label}</p>
                    <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-parch mt-1.5 leading-relaxed">
                      {cat.note}
                    </p>
                  </figcaption>
                </figure>
                <p className="font-mono text-[11px] text-dim mt-4 flex items-center gap-2">
                  <span className="w-6 h-px bg-flame inline-block" />
                  цены в рублях · с собой −10%
                </p>
              </Reveal>
            </div>
          </aside>

          {/* блюда */}
          <div key={cat.id} className="rise-in">
            <p className="lg:hidden font-mono text-[12px] uppercase tracking-[0.18em] text-ember mb-4">
              {cat.note}
            </p>
            <ul>
              {cat.dishes.map((dish, i) => {
                const justAdded = lastAdded?.id === dish.id;
                return (
                  <li
                    key={dish.id}
                    className="rise-in group flex items-center gap-4 py-4 border-b border-dashed border-ash/70 hover:bg-char/60 rounded-sm px-2 -mx-2 transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-300"
                    style={{ animationDelay: `${i * 45}ms` }}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <h3 className="font-600 text-[15.5px] text-paper group-hover:text-ember transition-colors">
                          {dish.name}
                        </h3>
                        {dish.tag && <Tag tag={dish.tag} />}
                      </div>
                      <p className="text-[13px] text-dim leading-snug mt-1">{dish.desc}</p>
                    </div>
                    <span className="dotted-leader hidden md:block flex-1 max-w-[120px] h-3 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                    <span className="font-mono font-700 text-[15px] text-ember whitespace-nowrap group-hover:text-flame transition-colors">
                      {fmtPrice(dish.price)}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleAdd(dish)}
                      aria-label={`Добавить ${dish.name} в заказ`}
                      className="w-9 h-9 shrink-0 rounded-full border border-ash flex items-center justify-center text-parch hover:bg-flame hover:border-flame hover:text-coal active:scale-90 transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200"
                    >
                      <span key={justAdded ? lastAdded.ts : dish.id} className={justAdded ? "bump flex" : "flex"}>
                        <PlusIcon />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="font-mono text-[11px] text-dim mt-6">
              + — добавить в предзаказ. Заберёшь у стойки через 7–10 минут, горячим.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
