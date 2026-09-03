import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ADDRESS_LINE_1,
  LAST_ORDER_BEFORE_CLOSE_MIN,
  PHONE_DISPLAY,
  PHONE_HREF,
  SCHEDULE,
  type Dish,
} from "../data";
import {
  fmtPrice,
  getMoscowMoment,
  getNextOpening,
  getOpenState,
  plural,
  useNowByMinute,
} from "../hooks";
import Reveal from "./Reveal";
import { ArrowRight, BagIcon, CheckIcon, MinusIcon, PlusIcon } from "./Icons";

export interface CartLine {
  dish: Dish;
  qty: number;
}

interface OrderFormProps {
  lines: CartLine[];
  onInc: (id: string) => void;
  onDec: (id: string) => void;
  onClear: () => void;
  onNav: (id: string) => void;
}

const SLOT_STEP_MIN = 20;
/** Сколько минут нужно кухне на самый быстрый заказ */
const PREP_MIN = 25;
const DAY_NAMES_PREP = [
  "в воскресенье",
  "в понедельник",
  "во вторник",
  "в среду",
  "в четверг",
  "в пятницу",
  "в субботу",
];

interface SlotPlan {
  slots: string[];
  /** «», «завтра», «в субботу» — к какому дню относятся слоты */
  dayLabel: string;
  /** Можно ли отдать «как можно скорее»: кухня сейчас работает и принимает */
  acceptingNow: boolean;
}

const hhmm = (minutes: number) =>
  `${String(Math.floor(minutes / 60) % 24).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/**
 * Слоты самовывоза по московскому расписанию.
 *
 * Раньше список строился от «сейчас» и обрывался на закрытии: вечером и ночью
 * он оказывался пустым, а «как можно скорее» оставалось единственным вариантом —
 * сайт принимал заказ «прямо сейчас» у закрытой кухни. Теперь, если мы уже
 * закрылись или ещё не открылись, слоты берутся с ближайшего рабочего дня,
 * а «как можно скорее» предлагается только когда кухня действительно работает.
 */
function buildSlotPlan(now: Date): SlotPlan {
  const { day, minutes } = getMoscowMoment(now);
  const today = SCHEDULE[day];
  const openMin = today.open * 60;
  const lastOrderMin = today.close * 60 - LAST_ORDER_BEFORE_CLOSE_MIN;

  const collect = (from: number, until: number) => {
    const out: string[] = [];
    for (let t = from; t <= until && out.length < 5; t += SLOT_STEP_MIN) out.push(hhmm(t));
    return out;
  };

  // Кухня работает и ещё принимает заказы
  if (minutes >= openMin && minutes < lastOrderMin) {
    const first = Math.ceil((minutes + PREP_MIN) / SLOT_STEP_MIN) * SLOT_STEP_MIN;
    return { slots: collect(first, lastOrderMin), dayLabel: "", acceptingNow: true };
  }

  // Сегодня ещё не открылись — первый слот вскоре после открытия
  if (minutes < openMin) {
    return { slots: collect(openMin + 15, lastOrderMin), dayLabel: "", acceptingNow: false };
  }

  // Уже закрылись (или добираем последние 30 минут) — переносим на следующий рабочий день
  const next = getNextOpening(day);
  const nextDay = SCHEDULE[next.day];
  const nextLastOrder = nextDay.close * 60 - LAST_ORDER_BEFORE_CLOSE_MIN;
  return {
    slots: collect(nextDay.open * 60 + 15, nextLastOrder),
    dayLabel: next.inDays === 1 ? "завтра" : DAY_NAMES_PREP[next.day],
    acceptingNow: false,
  };
}

interface DoneState {
  id: string;
  name: string;
  time: string;
  items: { name: string; qty: number; sum: number }[];
  total: number;
}

export default function OrderForm({ lines, onInc, onDec, onClear, onNav }: OrderFormProps) {
  const now = useNowByMinute();
  // Пересобираем каждую минуту: вкладку часто оставляют открытой, а слоты
  // «на 12:40» к вечеру превращаются в неправду.
  const plan = useMemo(() => buildSlotPlan(now), [now]);
  const { slots, dayLabel, acceptingNow } = plan;
  // Зал ещё открыт, но кухня уже не берёт новые заказы — это разные состояния
  const kitchenOpen = getOpenState(now).open;

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [time, setTime] = useState<string>(() => (acceptingNow ? "asap" : ""));
  const [comment, setComment] = useState("");
  const [errors, setErrors] = useState<{ name?: string; phone?: string }>({});
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<DoneState | null>(null);
  const timerRef = useRef(0);
  const doneRef = useRef<HTMLDivElement | null>(null);

  // Выбранное время могло «протухнуть», пока страница была открыта
  useEffect(() => {
    const fallback = acceptingNow ? "asap" : (slots[0] ?? "");
    if (time === "asap" && acceptingNow) return;
    if (time !== "" && slots.includes(time)) return;
    setTime(fallback);
  }, [slots, acceptingNow, time]);

  // Таймер «отправки» не должен пережить размонтирование секции
  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  // Чек появляется вместо формы — уводим на него фокус, иначе с клавиатуры
  // и со скринридером результат отправки оставался незамеченным
  useEffect(() => {
    if (done) doneRef.current?.focus();
  }, [done]);

  const count = lines.reduce((s, l) => s + l.qty, 0);
  const subtotal = lines.reduce((s, l) => s + l.dish.price * l.qty, 0);
  const discount = Math.round(subtotal * 0.1);
  const total = subtotal - discount;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next: { name?: string; phone?: string } = {};
    if (name.trim().length < 2) next.name = "Как к тебе обращаться?";
    // Раньше проверялся только нижний предел: «12345678901234567890» проходило
    const digits = phone.replace(/\D/g, "");
    if (digits.length < 10 || digits.length > 11) next.phone = "Нужен телефон из 10–11 цифр";
    setErrors(next);
    if (Object.keys(next).length > 0) {
      const firstBad = next.name ? "of-name" : "of-phone";
      document.getElementById(firstBad)?.focus();
      return;
    }
    setSending(true);
    timerRef.current = window.setTimeout(() => {
      setDone({
        id: `KZ-${Math.floor(1000 + Math.random() * 9000)}`,
        name: name.trim(),
        time:
          time === "asap"
            ? "как можно скорее"
            : `${dayLabel ? `${dayLabel} ` : ""}к ${time}`.trim(),
        items: lines.map((l) => ({ name: l.dish.name, qty: l.qty, sum: l.dish.price * l.qty })),
        total: lines.length > 0 ? total : 0,
      });
      setSending(false);
      onClear();
      setName("");
      setPhone("");
      setComment("");
      setTime(acceptingNow ? "asap" : (slots[0] ?? ""));
    }, 900);
  };

  return (
    <section id="order" className="relative py-24 lg:py-32 border-t border-ash/40 scroll-mt-24">
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(70% 60% at 78% 30%, rgba(255,92,38,0.07) 0%, rgba(20,16,11,0) 60%)",
        }}
        aria-hidden="true"
      />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 grid lg:grid-cols-2 gap-14 lg:gap-20">
        {/* левая колонка */}
        <div>
          <Reveal>
            <p className="font-mono text-[12px] uppercase tracking-[0.3em] text-ember mb-4">
              ( предзаказ )
            </p>
            <h2 className="font-display font-800 tracking-tight text-4xl sm:text-5xl lg:text-[3.4rem] leading-[1.04]">
              Заберёшь —<br />
              <span className="text-flame">горячим</span>
            </h2>
            <p className="text-parch leading-relaxed mt-6 max-w-md">
              Собери заказ из меню, оставь имя и телефон — поставим на огонь к
              твоему приходу. Без предоплаты, оплата на кассе.
            </p>
          </Reveal>

          <div className="mt-10 space-y-6">
            {[
              ["01", "Собираешь заказ здесь или по телефону"],
              ["02", "Подтверждаем по SMS или звонком, если что-то пойдёт не так"],
              ["03", "Забираешь у стойки через 7–10 минут — и на набережную"],
            ].map(([num, text], i) => (
              <Reveal key={num} delay={i * 100}>
                <div className="flex items-start gap-5 group">
                  {/* был text-char — 1.1:1 на угле, цифры шагов не читались */}
                  <span className="font-display font-800 text-2xl text-dim group-hover:text-flame transition-colors leading-none pt-0.5">
                    {num}
                  </span>
                  <p className="text-parch text-[15px] leading-relaxed border-b border-dashed border-ash/60 pb-5 flex-1 group-hover:border-flame/40 transition-colors">
                    {text}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal delay={280}>
            <div className="mt-10 border border-dashed border-ash p-5 rounded-md max-w-md">
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-dim mb-2">
                или просто позвони
              </p>
              <a
                href={PHONE_HREF}
                className="font-display font-700 text-2xl sm:text-3xl text-paper hover:text-ember transition-colors inline-block py-1"
              >
                {PHONE_DISPLAY}
              </a>
              <p className="font-mono text-[11px] text-dim mt-3 leading-relaxed">
                Оплата на кассе: карта, наличные, СБП. Самовывоз — всегда −10%.
              </p>
            </div>
          </Reveal>
        </div>

        {/* правая колонка: заказ */}
        <Reveal variant="left" delay={120}>
          <div className="border border-ash bg-soot/80 rounded-md p-6 sm:p-8 shadow-[0_30px_70px_rgba(0,0,0,0.45)]">
            {done ? (
              <div
                ref={doneRef}
                tabIndex={-1}
                role="status"
                aria-live="polite"
                className="on-paper bg-paper text-coal font-mono text-[13px] p-6 sm:p-7 rotate-1 hover:rotate-0 transition-transform duration-500 shadow-[0_20px_50px_rgba(0,0,0,0.4)] outline-none"
              >
                <div className="flex items-center gap-3 border-b border-dashed border-coal/40 pb-4">
                  <span className="w-10 h-10 rounded-full bg-flame text-paper flex items-center justify-center">
                    <CheckIcon className="w-5 h-5" />
                  </span>
                  <div>
                    <p className="font-display font-800 text-lg tracking-tight">Предзаказ принят</p>
                    <p className="text-[11px] uppercase tracking-[0.22em] text-coal/60 mt-0.5">
                      заказ {done.id}
                    </p>
                  </div>
                </div>
                <ul className="py-4 space-y-2 border-b border-dashed border-coal/40">
                  {done.items.length > 0 ? (
                    done.items.map((it) => (
                      <li key={it.name} className="flex items-baseline gap-2">
                        <span>
                          {it.name} <span className="text-coal/50">× {it.qty}</span>
                        </span>
                        <span className="dotted-leader flex-1 h-3" />
                        <span>{fmtPrice(it.sum)}</span>
                      </li>
                    ))
                  ) : (
                    <li className="text-coal/60">Заказ уточним по телефону</li>
                  )}
                </ul>
                <div className="py-4 space-y-1.5 border-b border-dashed border-coal/40 text-[12px]">
                  <p className="flex justify-between">
                    <span className="text-coal/60">Имя</span>
                    <span className="font-700">{done.name}</span>
                  </p>
                  <p className="flex justify-between">
                    <span className="text-coal/60">Время</span>
                    <span className="font-700">{done.time}</span>
                  </p>
                  {done.total > 0 && (
                    <p className="flex justify-between text-[14px] pt-1">
                      <span className="uppercase tracking-[0.18em] text-[11px]">Итого, на кассе</span>
                      <span className="font-700">{fmtPrice(done.total)}</span>
                    </p>
                  )}
                </div>
                <p className="text-center text-[11px] uppercase tracking-[0.2em] text-coal/60 mt-4">
                  покажи этот экран на кассе
                </p>
                <p className="text-center text-[11px] text-coal/50 mt-1">{ADDRESS_LINE_1}</p>
                <button
                  onClick={() => setDone(null)}
                  className="mt-5 w-full bg-coal text-paper font-display font-700 text-[13px] uppercase tracking-wide py-3.5 rounded-sm hover:bg-flamedark transition-colors active:scale-[0.98]"
                >
                  Оформить ещё один
                </button>
              </div>
            ) : (
              <form onSubmit={submit} noValidate>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-mono text-[12px] uppercase tracking-[0.22em] text-parch flex items-center gap-2.5">
                    <BagIcon className="w-4 h-4 text-flame" />
                    Твой заказ
                    {count > 0 && (
                      <span className="text-ember">
                        · {count} {plural(count, "позиция", "позиции", "позиций")}
                      </span>
                    )}
                  </h3>
                  {lines.length > 0 && (
                    <button
                      type="button"
                      onClick={onClear}
                      className="font-mono text-[11px] text-dim hover:text-flame underline decoration-dotted underline-offset-4 transition-colors"
                    >
                      очистить
                    </button>
                  )}
                </div>

                {lines.length > 0 ? (
                  <>
                    <ul className="divide-y divide-dashed divide-ash/70">
                      {lines.map((l) => (
                        <li key={l.dish.id} className="flex items-center gap-3 py-3">
                          <span className="flex-1 min-w-0">
                            <span className="block text-[14px] font-600 truncate">{l.dish.name}</span>
                            <span className="block font-mono text-[11px] text-dim">
                              {fmtPrice(l.dish.price)} / шт
                            </span>
                          </span>
                          <span className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => onDec(l.dish.id)}
                              aria-label={`Убрать ${l.dish.name}`}
                              className="w-7 h-7 rounded-full border border-ash flex items-center justify-center text-parch hover:border-flame hover:text-flame active:scale-90 transition-[color,background-color,border-color,box-shadow,transform,opacity]"
                            >
                              <MinusIcon className="w-3.5 h-3.5" />
                            </button>
                            <span key={l.qty} className="bump font-mono font-700 w-6 text-center text-ember">
                              {l.qty}
                            </span>
                            <button
                              type="button"
                              onClick={() => onInc(l.dish.id)}
                              aria-label={`Ещё ${l.dish.name}`}
                              className="w-7 h-7 rounded-full border border-ash flex items-center justify-center text-parch hover:border-flame hover:text-flame active:scale-90 transition-[color,background-color,border-color,box-shadow,transform,opacity]"
                            >
                              <PlusIcon className="w-3.5 h-3.5" />
                            </button>
                          </span>
                          <span className="font-mono font-700 text-[14px] w-16 text-right whitespace-nowrap">
                            {fmtPrice(l.dish.price * l.qty)}
                          </span>
                        </li>
                      ))}
                    </ul>
                    <div className="font-mono text-[13px] space-y-1.5 py-4 border-t border-dashed border-ash/70">
                      <p className="flex justify-between text-parch">
                        <span>Подытог</span>
                        <span>{fmtPrice(subtotal)}</span>
                      </p>
                      <p className="flex justify-between text-leaf">
                        <span>Самовывоз, −10%</span>
                        <span>−{fmtPrice(discount)}</span>
                      </p>
                      <p className="flex justify-between items-baseline pt-1">
                        <span className="text-[11px] uppercase tracking-[0.2em] text-dim">Итого</span>
                        <span className="font-display font-800 text-2xl text-ember">{fmtPrice(total)}</span>
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="border border-dashed border-ash rounded-md p-6 text-center mb-6">
                    <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-dim">
                      В пакете пока пусто
                    </p>
                    <button
                      type="button"
                      onClick={() => onNav("menu")}
                      className="group mt-3 inline-flex items-center gap-2 font-display font-700 text-[13px] uppercase tracking-wide text-flame hover:text-ember transition-colors py-1.5 min-h-[24px]"
                    >
                      выбрать из меню
                      <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                    </button>
                  </div>
                )}

                <div className="grid sm:grid-cols-2 gap-4 mt-2">
                  <div>
                    <label htmlFor="of-name" className="font-mono text-[11px] uppercase tracking-[0.16em] text-dim block mb-1.5">
                      Имя
                    </label>
                    <input
                      id="of-name"
                      name="name"
                      value={name}
                      onChange={(e) => {
                        setName(e.target.value);
                        // Ошибка гасла только после повторной отправки
                        if (errors.name) setErrors((p) => ({ ...p, name: undefined }));
                      }}
                      placeholder="Как тебя зовут?"
                      autoComplete="given-name"
                      aria-invalid={Boolean(errors.name)}
                      aria-describedby={errors.name ? "of-name-error" : undefined}
                      className={`w-full bg-char/60 border rounded-sm px-4 py-3 text-[14px] text-paper placeholder:text-dim/70 outline-none transition-colors focus:border-flame ${
                        errors.name ? "border-flame" : "border-ash"
                      }`}
                    />
                    {errors.name && (
                      <p id="of-name-error" className="font-mono text-[11px] text-flame mt-1.5">
                        {errors.name}
                      </p>
                    )}
                  </div>
                  <div>
                    <label htmlFor="of-phone" className="font-mono text-[11px] uppercase tracking-[0.16em] text-dim block mb-1.5">
                      Телефон
                    </label>
                    <input
                      id="of-phone"
                      name="phone"
                      type="tel"
                      value={phone}
                      onChange={(e) => {
                        setPhone(e.target.value);
                        if (errors.phone) setErrors((p) => ({ ...p, phone: undefined }));
                      }}
                      placeholder="+7 ___ ___-__-__"
                      inputMode="tel"
                      autoComplete="tel"
                      aria-invalid={Boolean(errors.phone)}
                      aria-describedby={errors.phone ? "of-phone-error" : undefined}
                      className={`w-full bg-char/60 border rounded-sm px-4 py-3 text-[14px] text-paper placeholder:text-dim/70 outline-none transition-colors focus:border-flame ${
                        errors.phone ? "border-flame" : "border-ash"
                      }`}
                    />
                    {errors.phone && (
                      <p id="of-phone-error" className="font-mono text-[11px] text-flame mt-1.5">
                        {errors.phone}
                      </p>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <label htmlFor="of-time" className="font-mono text-[11px] uppercase tracking-[0.16em] text-dim block mb-1.5">
                    Когда заберёшь?
                  </label>
                  <select
                    id="of-time"
                    value={time}
                    onChange={(e) => setTime(e.target.value)}
                    className="w-full bg-char/60 border border-ash rounded-sm px-4 py-3 text-[14px] text-paper outline-none focus:border-flame transition-colors appearance-none"
                    style={{
                      backgroundImage:
                        "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%23ff5c26' stroke-width='1.6' fill='none' stroke-linecap='round'/%3E%3C/svg%3E\")",
                      backgroundRepeat: "no-repeat",
                      backgroundPosition: "right 16px center",
                    }}
                  >
                    {acceptingNow && <option value="asap">Как можно скорее (≈ 10 минут)</option>}
                    {slots.map((s) => (
                      <option key={s} value={s}>
                        {dayLabel ? `${dayLabel[0].toUpperCase()}${dayLabel.slice(1)}, к ${s}` : `К ${s}`} (мск)
                      </option>
                    ))}
                  </select>
                  {!acceptingNow && (
                    <p className="font-mono text-[11px] text-ember mt-2 leading-relaxed">
                      {kitchenOpen
                        ? "Заказы на сегодня мы уже закрыли"
                        : "Сейчас закрыто"}
                      {" — примем предзаказ"}
                      {dayLabel ? ` ${dayLabel}` : " к открытию"} и позвоним для подтверждения.
                    </p>
                  )}
                </div>

                <div className="mt-4">
                  <label htmlFor="of-comment" className="font-mono text-[11px] uppercase tracking-[0.16em] text-dim block mb-1.5">
                    Комментарий <span className="normal-case tracking-normal">(не обязательно)</span>
                  </label>
                  <input
                    id="of-comment"
                    name="comment"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Без лука, соус отдельно, нас трое…"
                    className="w-full bg-char/60 border border-ash rounded-sm px-4 py-3 text-[14px] text-paper placeholder:text-dim/70 outline-none focus:border-flame transition-colors"
                  />
                </div>

                <button
                  type="submit"
                  disabled={sending}
                  aria-busy={sending}
                  className="group mt-6 w-full bg-flame text-coal font-display font-700 text-[14px] uppercase tracking-wide py-4 rounded-sm hover:bg-ember active:scale-[0.98] transition-[color,background-color,border-color,box-shadow,transform,opacity] shadow-[0_0_30px_rgba(255,92,38,0.35)] disabled:opacity-70 flex items-center justify-center gap-3"
                >
                  {sending ? (
                    <>
                      <svg viewBox="0 0 24 24" className="w-5 h-5 animate-spin" fill="none" aria-hidden="true">
                        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
                        <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                      </svg>
                      Принимаем заказ…
                    </>
                  ) : (
                    <>
                      Отдать на огонь
                      <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                    </>
                  )}
                </button>
                <p className="font-mono text-[10.5px] text-dim text-center mt-3">
                  Нажимая, ты соглашаешься на звонок нашего повара. Никакого спама.
                </p>
              </form>
            )}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
