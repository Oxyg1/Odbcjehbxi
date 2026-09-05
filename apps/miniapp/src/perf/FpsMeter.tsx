import { useEffect, useState } from 'react';

/**
 * Счётчик кадров для проверки сценария с 5–8 анимированными слоями.
 * Включается вручную через ?perf=1 и в обычной сессии не монтируется.
 */
export function FpsMeter() {
  const [fps, setFps] = useState(0);

  useEffect(() => {
    let frames = 0;
    let since = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      frames += 1;
      if (now - since >= 500) {
        setFps(Math.round((frames * 1000) / (now - since)));
        frames = 0;
        since = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <div className="fps">{fps} fps</div>;
}

export const perfEnabled = (): boolean =>
  new URLSearchParams(window.location.search).get('perf') === '1';
