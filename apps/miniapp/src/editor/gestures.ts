import {
  angleBetween,
  clampPosition,
  clampScale,
  distance,
  rotatePoint,
  snapAngle,
  type CanvasSize,
  type Point,
} from '@plsdonate/shared';
import type { LayerTransform } from './store';

/** Слепок пары пальцев в момент начала жеста. */
export interface PinchAnchor {
  center: Point;
  spread: number;
  angle: number;
}

export const pinchAnchor = (a: Point, b: Point): PinchAnchor => ({
  center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
  spread: Math.max(distance(a, b), 1),
  angle: angleBetween(a, b),
});

const toPx = (transform: LayerTransform, canvas: CanvasSize): Point => ({
  x: transform.x * canvas.width,
  y: transform.y * canvas.height,
});

const toNormalized = (point: Point, canvas: CanvasSize): { x: number; y: number } => ({
  x: clampPosition(point.x / canvas.width),
  y: clampPosition(point.y / canvas.height),
});

/** Перетаскивание одним пальцем: меняется только позиция. */
export function applyDrag(
  start: LayerTransform,
  delta: Point,
  canvas: CanvasSize,
): LayerTransform {
  const origin = toPx(start, canvas);
  return {
    ...start,
    ...toNormalized({ x: origin.x + delta.x, y: origin.y + delta.y }, canvas),
  };
}

/**
 * Двумя пальцами — перенос, поворот и масштаб одним движением.
 * Слой едет вместе с центром жеста, поэтому картинка не «убегает» из-под пальцев.
 */
export function applyPinch(
  start: LayerTransform,
  anchor: PinchAnchor,
  current: PinchAnchor,
  canvas: CanvasSize,
): { transform: LayerTransform; snapped: boolean } {
  const ratio = current.spread / anchor.spread;
  const turn = current.angle - anchor.angle;
  const origin = toPx(start, canvas);
  const arm = rotatePoint(
    { x: origin.x - anchor.center.x, y: origin.y - anchor.center.y },
    turn,
  );
  const moved = {
    x: anchor.center.x + arm.x * ratio + (current.center.x - anchor.center.x),
    y: anchor.center.y + arm.y * ratio + (current.center.y - anchor.center.y),
  };
  const { angle, snapped } = snapAngle(start.rotation + turn);
  return {
    transform: {
      ...toNormalized(moved, canvas),
      scale: clampScale(start.scale * ratio),
      rotation: angle,
    },
    snapped,
  };
}

/**
 * Угловая ручка: поворот и масштаб одним пальцем вокруг центра слоя.
 * Нужна там, где второй палец недоступен — например, при работе одной рукой.
 */
export function applyHandle(
  start: LayerTransform,
  grab: Point,
  pointer: Point,
  canvas: CanvasSize,
): { transform: LayerTransform; snapped: boolean } {
  const center = toPx(start, canvas);
  const grabReach = Math.max(distance(center, grab), 1);
  const reach = distance(center, pointer);
  const turn = angleBetween(center, pointer) - angleBetween(center, grab);
  const { angle, snapped } = snapAngle(start.rotation + turn);
  return {
    transform: {
      ...start,
      scale: clampScale(start.scale * (reach / grabReach)),
      rotation: angle,
    },
    snapped,
  };
}
