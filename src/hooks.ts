import { useEffect, useMemo, useRef, useState } from "react";
import { LAST_ORDER_BEFORE_CLOSE_MIN, SCHEDULE } from "./data";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** Текущее время; обновляется раз в секунду */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

/**
 * Текущее время, но тикает раз в минуту.
 * Статус «открыто/закрыто» меняется по часам, поэтому пересчитывать его
 * (и перерисовывать шапку с первым экраном) каждую секунду незачем.
 */
export function useNowByMinute(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let id = 0;
    const tick = () => {
      const d = new Date();
      setNow(d);
      // Просыпаемся ровно на границе минуты, а не каждые 60 с от монтирования
      id = window.setTimeout(tick, 60000 - (d.getSeconds() * 1000 + d.getMilliseconds()));
    };
    id = window.setTimeout(tick, 60000 - (Date.now() % 60000));
    return () => window.clearTimeout(id);
  }, []);
  return now;
}

const moscowFmt = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

/** Разбор момента времени в московские день недели / часы / минуты */
const moscowPartsFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "Europe/Moscow",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

export interface MoscowMoment {
  /** День недели: 0 — воскресенье, 6 — суббота */
  day: number;
  hour: number;
  minute: number;
  /** Минут с полуночи */
  minutes: number;
}

/**
 * Московские день и время для произвольного момента.
 * Через Intl, а не арифметикой с getTimezoneOffset(), — чтобы переход на
 * летнее время у гостя (или сервера) не сдвигал расписание кухни.
 */
export function getMoscowMoment(d: Date): MoscowMoment {
  const parts = moscowPartsFmt.formatToParts(d);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  const day = WEEKDAY_INDEX[get("weekday")] ?? d.getDay();
  // en-US с hour12:false отдаёт полночь как "24"
  const hour = Number(get("hour")) % 24;
  const minute = Number(get("minute"));
  return { day, hour, minute, minutes: hour * 60 + minute };
}

export function getMoscowTimeString(d: Date): string {
  return moscowFmt.format(d);
}

const DAY_NAMES_PREP = ["в воскресенье", "в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу"];

export interface OpenState {
  open: boolean;
  label: string;
  /** Принимаем ли сейчас заказы: за 30 минут до закрытия кухня уже не берёт */
  acceptingOrders: boolean;
}

/**
 * Открыто ли сейчас по московскому времени, по расписанию из SCHEDULE.
 * «Откроется завтра» смотрит на расписание именно завтрашнего дня:
 * в пятницу вечером мы открываемся в 11:00 (суббота), а не в 10:00.
 */
export function getOpenState(d: Date): OpenState {
  const { day, minutes } = getMoscowMoment(d);
  const today = SCHEDULE[day];
  const openMin = today.open * 60;
  const closeMin = today.close * 60;

  if (minutes >= openMin && minutes < closeMin) {
    const acceptingOrders = minutes < closeMin - LAST_ORDER_BEFORE_CLOSE_MIN;
    return {
      open: true,
      label: acceptingOrders
        ? `Открыто до ${today.close}:00`
        : `Закрываемся в ${today.close}:00`,
      acceptingOrders,
    };
  }

  if (minutes < openMin) {
    return { open: false, label: `Откроется в ${today.open}:00`, acceptingOrders: false };
  }

  // Уже закрылись — ищем ближайший день, когда снова откроемся
  const next = getNextOpening(day);
  const when = next.inDays === 1 ? "завтра" : DAY_NAMES_PREP[next.day];
  return {
    open: false,
    label: `Откроется ${when} в ${SCHEDULE[next.day].open}:00`,
    acceptingOrders: false,
  };
}

/** Ближайший рабочий день после указанного (по индексу дня недели) */
export function getNextOpening(fromDay: number): { day: number; inDays: number } {
  for (let i = 1; i <= 7; i += 1) {
    const day = (fromDay + i) % 7;
    if (SCHEDULE[day].close > SCHEDULE[day].open) return { day, inDays: i };
  }
  return { day: (fromDay + 1) % 7, inDays: 1 };
}

const SCRAMBLE_CHARS = "▓▒░#/\\<>%&@×+=КУТЗА0123456789";

/** Эффект «расшифровки» заголовка */
export function useScramble(target: string, delay = 0): string {
  const reduced = usePrefersReducedMotion();
  const [text, setText] = useState(reduced ? target : "");
  const frame = useRef(0);

  useEffect(() => {
    if (reduced) {
      setText(target);
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const totalFrames = 46;
    const tick = (t: number) => {
      if (start === null) start = t + delay;
      if (t < start) {
        raf = requestAnimationFrame(tick);
        return;
      }
      frame.current += 1;
      const progress = Math.min(frame.current / totalFrames, 1);
      const settled = Math.floor(progress * target.length);
      let out = target.slice(0, settled);
      for (let i = settled; i < target.length; i += 1) {
        const ch = target[i];
        out += ch === " " ? " " : SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
      }
      setText(out);
      if (progress < 1) raf = requestAnimationFrame(tick);
      else setText(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, delay, reduced]);

  return text;
}

/** Плавный счётчик до target, когда started === true */
export function useCountUp(target: number, started: boolean, duration = 1600): number {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!started) return;
    if (reduced) {
      setValue(target);
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const tick = (t: number) => {
      if (start === null) start = t;
      const p = Math.min((t - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(target * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, started, duration, reduced]);
  return value;
}

/** true, когда элемент попал во вьюпорт (один раз) */
export function useInViewOnce<T extends HTMLElement>(threshold = 0.25) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return { ref, inView };
}

export function useScrollProgress(): number {
  const [p, setP] = useState(0);
  useEffect(() => {
    const onScroll = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      setP(max > 0 ? Math.min(h.scrollTop / max, 1) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    // Полоса прогресса врала после смены ориентации или разворачивания меню:
    // высота документа менялась, а доля прокрутки оставалась старой.
    window.addEventListener("resize", onScroll);
    const ro = new ResizeObserver(onScroll);
    ro.observe(document.body);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      ro.disconnect();
    };
  }, []);
  return p;
}

/** Форматирование цены: 490 → «490 ₽» */
export function fmtPrice(n: number): string {
  return `${n.toLocaleString("ru-RU")} ₽`;
}

/** Склонение: 1 отзыв, 2 отзыва, 5 отзывов */
export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title;
  }, [title]);
}

/**
 * Прокрутка к секции с поправкой на фиксированную шапку.
 * Высоту шапки меряем, а не держим константой: она разная до и после скролла
 * и на разных экранах, из-за чего заголовок секции уезжал под шапку.
 */
export function useAnchorOffset(): (id: string) => void {
  return useMemo(
    () => (id: string) => {
      const el = document.getElementById(id);
      if (!el) return;
      const header = document.querySelector("header");
      const offset = (header?.getBoundingClientRect().height ?? 72) + 16;
      const y = el.getBoundingClientRect().top + window.scrollY - offset;
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: Math.max(y, 0), behavior: reduced ? "auto" : "smooth" });
    },
    [],
  );
}

/** Закрытие по Escape — для мобильного меню и любых оверлеев */
export function useEscapeKey(active: boolean, onEscape: () => void) {
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onEscape();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [active, onEscape]);
}

/**
 * Держит фокус внутри открытой панели и возвращает его на кнопку при закрытии.
 * Без этого Tab из открытого меню уходил на ссылки под затемнением.
 */
export function useFocusTrap<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T | null>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) return;
    const node = ref.current;
    if (!node) return;
    restoreTo.current = document.activeElement as HTMLElement | null;

    const focusables = () =>
      Array.from(
        node.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);

    focusables()[0]?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    node.addEventListener("keydown", onKey);
    return () => {
      node.removeEventListener("keydown", onKey);
      restoreTo.current?.focus?.();
    };
  }, [active]);

  return ref;
}
