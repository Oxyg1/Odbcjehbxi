import { memo, useCallback } from 'react';
import type { Asset, CanvasSize, StandLayer } from '@plsdonate/shared';
import { layerBox } from './render';

interface LayerViewProps {
  layer: StandLayer;
  asset: Asset | undefined;
  canvas: CanvasSize;
  registerNode: (id: string, node: HTMLElement | null) => void;
}

/**
 * Слой не перерисовывается, пока не изменился его собственный объект в сторе.
 * Это важнее, чем кажется: во время жеста кадры пишет контроллер напрямую в DOM,
 * и лишний рендер React вернул бы старую трансформацию.
 */
function LayerViewBase({ layer, asset, canvas, registerNode }: LayerViewProps) {
  const ref = useCallback(
    (node: HTMLElement | null) => registerNode(layer.id, node),
    [layer.id, registerNode],
  );

  if (!asset) return null;

  const box = layerBox(layer, asset.aspect, canvas);

  return (
    <div
      ref={ref}
      className="layer"
      data-layer-id={layer.id}
      style={{
        width: box.width,
        height: box.height,
        transform: box.transform,
        zIndex: layer.zIndex + 1,
      }}
    >
      <img src={asset.src} alt={asset.title} draggable={false} decoding="async" />
    </div>
  );
}

export const LayerView = memo(LayerViewBase);
