import { forwardRef, memo } from 'react';
import type { Asset, CanvasSize, StandLayer } from '@plsdonate/shared';
import { layerBox } from './render';

interface SelectionFrameProps {
  layer: StandLayer;
  asset: Asset;
  canvas: CanvasSize;
}

/**
 * Рамка выделения живёт вне трансформации слоя: толщина линии и размер ручки
 * не зависят от масштаба, поэтому мелкий стикер остаётся ухватываемым.
 */
export const SelectionFrame = memo(
  forwardRef<HTMLDivElement, SelectionFrameProps>(function SelectionFrame(
    { layer, asset, canvas },
    ref,
  ) {
    const box = layerBox(layer, asset.aspect, canvas);
    return (
      <div
        ref={ref}
        className="selection"
        data-layer-id={layer.id}
        style={{ width: box.width, height: box.height, transform: box.transform }}
      >
        <span className="selection__edge" />
        <button
          type="button"
          className="selection__handle"
          data-handle="transform"
          aria-label="Повернуть и изменить размер"
        />
      </div>
    );
  }),
);
