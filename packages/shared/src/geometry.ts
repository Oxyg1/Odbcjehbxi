import {
  POSITION_MAX,
  POSITION_MIN,
  ROTATION_SNAP_STEP,
  ROTATION_SNAP_THRESHOLD,
  SAFE_ZONE_BOTTOM,
  SAFE_ZONE_TOP,
  SCALE_MAX,
  SCALE_MIN,
} from './limits';

export interface Point {
  x: number;
  y: number;
}

export interface CanvasSize {
  width: number;
  height: number;
}

export interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export const clamp = (value: number, min: number, max: number): number =>
  value < min ? min : value > max ? max : value;

export const clampScale = (scale: number): number => clamp(scale, SCALE_MIN, SCALE_MAX);

export const clampPosition = (value: number): number =>
  clamp(value, POSITION_MIN, POSITION_MAX);

/** Приводит угол к диапазону -180..180, в котором живёт схема слоя. */
export function normalizeAngle(degrees: number): number {
  let angle = degrees % 360;
  if (angle > 180) angle -= 360;
  if (angle <= -180) angle += 360;
  return angle;
}

/**
 * Притягивает угол к ближайшему шагу в 15°, если он уже почти там.
 * Возвращает и сам угол, и признак срабатывания — по нему редактор даёт haptic.
 */
export function snapAngle(degrees: number): { angle: number; snapped: boolean } {
  const normalized = normalizeAngle(degrees);
  const nearest = Math.round(normalized / ROTATION_SNAP_STEP) * ROTATION_SNAP_STEP;
  if (Math.abs(normalized - nearest) <= ROTATION_SNAP_THRESHOLD) {
    return { angle: normalizeAngle(nearest), snapped: true };
  }
  return { angle: normalized, snapped: false };
}

/** Размер слоя в пикселях холста. */
export function layerSize(
  scale: number,
  assetAspect: number,
  canvas: CanvasSize,
): { width: number; height: number } {
  const width = scale * canvas.width;
  return { width, height: width / assetAspect };
}

export function rotatePoint(point: Point, degrees: number): Point {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return {
    x: point.x * cos - point.y * sin,
    y: point.x * sin + point.y * cos,
  };
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** Угол вектора a→b в градусах. */
export function angleBetween(a: Point, b: Point): number {
  return (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
}

/**
 * Габаритный прямоугольник повёрнутого слоя в пикселях холста.
 * Нужен, чтобы понять, заехал ли слой в защищённую зону.
 */
export function rotatedBounds(
  center: Point,
  size: { width: number; height: number },
  rotation: number,
): Box {
  const radians = (rotation * Math.PI) / 180;
  const cos = Math.abs(Math.cos(radians));
  const sin = Math.abs(Math.sin(radians));
  const halfWidth = (size.width * cos + size.height * sin) / 2;
  const halfHeight = (size.width * sin + size.height * cos) / 2;
  return {
    left: center.x - halfWidth,
    right: center.x + halfWidth,
    top: center.y - halfHeight,
    bottom: center.y + halfHeight,
  };
}

export interface SafeZoneHit {
  top: boolean;
  bottom: boolean;
}

/** Пересекает ли габарит слоя верхнюю или нижнюю защищённую зону. */
export function safeZoneHit(bounds: Box, canvas: CanvasSize): SafeZoneHit {
  return {
    top: bounds.top < canvas.height * SAFE_ZONE_TOP,
    bottom: bounds.bottom > canvas.height * (1 - SAFE_ZONE_BOTTOM),
  };
}

export const mergeSafeZoneHit = (a: SafeZoneHit, b: SafeZoneHit): SafeZoneHit => ({
  top: a.top || b.top,
  bottom: a.bottom || b.bottom,
});

export const NO_SAFE_ZONE_HIT: SafeZoneHit = { top: false, bottom: false };
