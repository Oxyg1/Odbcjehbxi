import {
  layerSize,
  rotatedBounds,
  safeZoneHit,
  type CanvasSize,
  type SafeZoneHit,
} from '@plsdonate/shared';
import type { LayerTransform } from './store';

export interface LayerBox {
  width: number;
  height: number;
  transform: string;
}

/**
 * Единственная формула размещения слоя. React рисует по ней первый кадр,
 * жест переписывает её же прямо в DOM — расхождений между кадрами не бывает.
 *
 * Масштаб задаётся размером элемента, а не transform: scale(), чтобы браузер
 * растрировал картинку в её реальном размере. На слабых Android это разница
 * между восемью полноразмерными текстурами и восемью маленькими.
 */
export function layerBox(
  transform: LayerTransform,
  assetAspect: number,
  canvas: CanvasSize,
): LayerBox {
  const { width, height } = layerSize(transform.scale, assetAspect, canvas);
  const left = transform.x * canvas.width;
  const top = transform.y * canvas.height;
  return {
    width,
    height,
    transform: `translate3d(${left.toFixed(2)}px, ${top.toFixed(2)}px, 0) translate(-50%, -50%) rotate(${transform.rotation.toFixed(2)}deg)`,
  };
}

export function writeLayerBox(
  element: HTMLElement,
  box: LayerBox,
): void {
  element.style.width = `${box.width}px`;
  element.style.height = `${box.height}px`;
  element.style.transform = box.transform;
}

/** Заезжает ли слой в защищённые зоны сверху и снизу. */
export function transformSafeZoneHit(
  transform: LayerTransform,
  assetAspect: number,
  canvas: CanvasSize,
): SafeZoneHit {
  const size = layerSize(transform.scale, assetAspect, canvas);
  const bounds = rotatedBounds(
    { x: transform.x * canvas.width, y: transform.y * canvas.height },
    size,
    transform.rotation,
  );
  return safeZoneHit(bounds, canvas);
}
