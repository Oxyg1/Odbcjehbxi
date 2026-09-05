import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react';
import type { CanvasSize, Point, SafeZoneHit } from '@plsdonate/shared';
import { haptic } from '../telegram/webapp';
import { applyDrag, applyHandle, applyPinch, pinchAnchor, type PinchAnchor } from './gestures';
import { layerBox, transformSafeZoneHit, writeLayerBox } from './render';
import { findLayer, select, updateTransform, type LayerTransform } from './store';

type Mode = 'drag' | 'pinch' | 'handle';

interface Session {
  layerId: string;
  aspect: number;
  mode: Mode;
  /** Точка отсчёта текущего режима: при смене числа пальцев берётся заново. */
  base: LayerTransform;
  live: LayerTransform;
  origin: Point;
  anchor: PinchAnchor | null;
  pointers: Map<number, Point>;
  snapped: boolean;
  moved: boolean;
}

interface GestureDeps {
  surfaceRef: RefObject<HTMLElement>;
  frameRef: RefObject<HTMLElement>;
  layerNodes: MutableRefObject<Map<string, HTMLElement>>;
  canvasSizeRef: MutableRefObject<CanvasSize>;
  getAspect: (assetId: string) => number;
  /** Живое состояние защищённых зон под слоем, который сейчас в руке. */
  onActiveZoneHit: (hit: SafeZoneHit | null) => void;
  onActiveLayerChange: (layerId: string | null) => void;
}

const TAP_SLOP = 6;

const toTransform = (layer: {
  x: number;
  y: number;
  scale: number;
  rotation: number;
}): LayerTransform => ({
  x: layer.x,
  y: layer.y,
  scale: layer.scale,
  rotation: layer.rotation,
});

/**
 * Жесты холста: перетаскивание, поворот и масштаб.
 *
 * Во время жеста стор не трогается вообще — кадры пишутся прямо в DOM, а
 * React получает одно обновление на отпускание пальца. Иначе на среднем Android
 * каждый кадр превращается в перерисовку всего дерева слоёв.
 */
export function useCanvasGestures(deps: GestureDeps): void {
  const depsRef = useRef(deps);
  depsRef.current = deps;

  useEffect(() => {
    const surface = depsRef.current.surfaceRef.current;
    if (!surface) return;

    let session: Session | null = null;
    let rect = surface.getBoundingClientRect();
    let frame = 0;
    let reportedHit: SafeZoneHit | null = null;

    /** Захват может быть недоступен (эмуляция, редкие WebView) — жест это переживает. */
    const capture = (pointerId: number): void => {
      try {
        surface.setPointerCapture(pointerId);
      } catch {
        // Без захвата палец за пределами холста просто отпустит слой.
      }
    };

    const pointFor = (event: PointerEvent): Point => ({
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    });

    const flush = (): void => {
      frame = 0;
      if (!session) return;
      const { layerNodes, canvasSizeRef, frameRef, onActiveZoneHit } = depsRef.current;
      const box = layerBox(session.live, session.aspect, canvasSizeRef.current);
      const node = layerNodes.current.get(session.layerId);
      if (node) writeLayerBox(node, box);
      if (frameRef.current) writeLayerBox(frameRef.current, box);

      // Состояние зон отдаём в React только когда оно действительно изменилось,
      // иначе перерисовка холста шла бы каждый кадр жеста.
      const hit = transformSafeZoneHit(session.live, session.aspect, canvasSizeRef.current);
      if (!reportedHit || reportedHit.top !== hit.top || reportedHit.bottom !== hit.bottom) {
        reportedHit = hit;
        onActiveZoneHit(hit);
      }
    };

    const schedule = (): void => {
      if (frame) return;
      frame = requestAnimationFrame(flush);
    };

    const setLive = (next: LayerTransform, snapped: boolean): void => {
      if (!session) return;
      if (snapped && !session.snapped) haptic.selection();
      session.snapped = snapped;
      session.live = next;
      session.moved = true;
      schedule();
    };

    const endSession = (): void => {
      if (!session) return;
      const { onActiveZoneHit, onActiveLayerChange, layerNodes } = depsRef.current;
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
      layerNodes.current.get(session.layerId)?.classList.remove('layer--active');
      if (session.moved) updateTransform(session.layerId, session.live);
      session = null;
      reportedHit = null;
      onActiveZoneHit(null);
      onActiveLayerChange(null);
    };

    const onPointerDown = (event: PointerEvent): void => {
      const target = event.target as HTMLElement | null;
      if (!target) return;

      if (session) {
        // Второй палец: тот же слой переходит в режим поворота с масштабом.
        if (session.pointers.size === 1 && session.mode !== 'handle') {
          session.pointers.set(event.pointerId, pointFor(event));
          const [a, b] = [...session.pointers.values()];
          if (a && b) {
            session.mode = 'pinch';
            session.base = session.live;
            session.anchor = pinchAnchor(a, b);
          }
          capture(event.pointerId);
        }
        return;
      }

      const handle = target.closest<HTMLElement>('[data-handle]');
      const host = handle
        ? depsRef.current.frameRef.current?.dataset.layerId
        : target.closest<HTMLElement>('[data-layer-id]')?.dataset.layerId;

      if (!host) {
        select(null);
        return;
      }

      const layer = findLayer(host);
      if (!layer) return;
      const { layerNodes } = depsRef.current;

      rect = surface.getBoundingClientRect();
      const origin = pointFor(event);
      select(host);
      depsRef.current.onActiveLayerChange(host);

      session = {
        layerId: host,
        aspect: depsRef.current.getAspect(layer.assetId),
        mode: handle ? 'handle' : 'drag',
        base: toTransform(layer),
        live: toTransform(layer),
        origin,
        anchor: null,
        pointers: new Map([[event.pointerId, origin]]),
        snapped: false,
        moved: false,
      };
      capture(event.pointerId);
      layerNodes.current.get(host)?.classList.add('layer--active');
      event.preventDefault();
    };

    const onPointerMove = (event: PointerEvent): void => {
      if (!session || !session.pointers.has(event.pointerId)) return;
      const point = pointFor(event);
      session.pointers.set(event.pointerId, point);
      const canvas = depsRef.current.canvasSizeRef.current;

      if (session.mode === 'pinch') {
        const [a, b] = [...session.pointers.values()];
        if (!a || !b || !session.anchor) return;
        const result = applyPinch(session.base, session.anchor, pinchAnchor(a, b), canvas);
        setLive(result.transform, result.snapped);
        return;
      }

      if (session.mode === 'handle') {
        const result = applyHandle(session.base, session.origin, point, canvas);
        setLive(result.transform, result.snapped);
        return;
      }

      const delta = { x: point.x - session.origin.x, y: point.y - session.origin.y };
      if (!session.moved && Math.hypot(delta.x, delta.y) < TAP_SLOP) return;
      setLive(applyDrag(session.base, delta, canvas), false);
    };

    const onPointerUp = (event: PointerEvent): void => {
      if (!session || !session.pointers.has(event.pointerId)) return;
      session.pointers.delete(event.pointerId);

      if (session.pointers.size === 1 && session.mode === 'pinch') {
        // Остался один палец: продолжаем как перетаскивание, без рывка.
        const [remaining] = [...session.pointers.values()];
        if (remaining) {
          session.mode = 'drag';
          session.base = session.live;
          session.origin = remaining;
          session.anchor = null;
        }
        return;
      }

      if (session.pointers.size === 0) endSession();
    };

    const onResize = (): void => {
      rect = surface.getBoundingClientRect();
    };

    surface.addEventListener('pointerdown', onPointerDown);
    surface.addEventListener('pointermove', onPointerMove);
    surface.addEventListener('pointerup', onPointerUp);
    surface.addEventListener('pointercancel', onPointerUp);
    window.addEventListener('resize', onResize);
    window.addEventListener('scroll', onResize, true);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      surface.removeEventListener('pointerdown', onPointerDown);
      surface.removeEventListener('pointermove', onPointerMove);
      surface.removeEventListener('pointerup', onPointerUp);
      surface.removeEventListener('pointercancel', onPointerUp);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('scroll', onResize, true);
    };
  }, []);
}
