import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CANVAS_ASPECT,
  NO_SAFE_ZONE_HIT,
  SAFE_ZONE_BOTTOM,
  SAFE_ZONE_TOP,
  mergeSafeZoneHit,
  type Asset,
  type CanvasSize,
  type SafeZoneHit,
  type StandDoc,
} from '@plsdonate/shared';
import { LayerView } from './LayerView';
import { SelectionFrame } from './SelectionFrame';
import { transformSafeZoneHit } from './render';
import { useCanvasGestures } from './useCanvasGestures';

interface StandCanvasProps {
  doc: StandDoc;
  selectedId: string | null;
  getAsset: (id: string) => Asset | undefined;
}

const EMPTY_SIZE: CanvasSize = { width: 0, height: 0 };

export function StandCanvas({ doc, selectedId, getAsset }: StandCanvasProps) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const layerNodes = useRef(new Map<string, HTMLElement>());
  const canvasSizeRef = useRef<CanvasSize>(EMPTY_SIZE);

  const [canvas, setCanvas] = useState<CanvasSize>(EMPTY_SIZE);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeHit, setActiveHit] = useState<SafeZoneHit | null>(null);

  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      canvasSizeRef.current = { width, height };
      setCanvas({ width, height });
    });
    observer.observe(surface);
    return () => observer.disconnect();
  }, []);

  const registerNode = useCallback((id: string, node: HTMLElement | null) => {
    if (node) layerNodes.current.set(id, node);
    else layerNodes.current.delete(id);
  }, []);

  const getAspect = useCallback(
    (assetId: string) => getAsset(assetId)?.aspect ?? 1,
    [getAsset],
  );

  useCanvasGestures({
    surfaceRef,
    frameRef,
    layerNodes,
    canvasSizeRef,
    getAspect,
    onActiveZoneHit: setActiveHit,
    onActiveLayerChange: setActiveId,
  });

  /** Зоны, занятые слоями, которых сейчас нет в руке. */
  const settledHit = useMemo(() => {
    if (canvas.width === 0) return NO_SAFE_ZONE_HIT;
    return doc.layers.reduce<SafeZoneHit>((hit, layer) => {
      if (layer.id === activeId) return hit;
      const asset = getAsset(layer.assetId);
      if (!asset) return hit;
      return mergeSafeZoneHit(hit, transformSafeZoneHit(layer, asset.aspect, canvas));
    }, NO_SAFE_ZONE_HIT);
  }, [doc.layers, activeId, canvas, getAsset]);

  const hit = activeHit ? mergeSafeZoneHit(settledHit, activeHit) : settledHit;
  // Подпись зоны появляется только пока слой в руке: постоянная надпись на
  // стенде превращается в шум и спорит с самим стендом.
  const zoneClass = (edge: 'top' | 'bottom'): string =>
    ['zone', `zone--${edge}`, hit[edge] ? 'is-hit' : '', activeHit?.[edge] ? 'is-live' : '']
      .filter(Boolean)
      .join(' ');

  const selected = doc.layers.find((layer) => layer.id === selectedId);
  const selectedAsset = selected ? getAsset(selected.assetId) : undefined;

  return (
    <div className="canvas-frame" style={{ aspectRatio: CANVAS_ASPECT }}>
      <div
        ref={surfaceRef}
        className="canvas-surface"
        style={{ background: doc.background }}
      >
        {canvas.width > 0 &&
          doc.layers.map((layer) => (
            <LayerView
              key={layer.id}
              layer={layer}
              asset={getAsset(layer.assetId)}
              canvas={canvas}
              registerNode={registerNode}
            />
          ))}

        {selected && selectedAsset && canvas.width > 0 && (
          <SelectionFrame
            ref={frameRef}
            layer={selected}
            asset={selectedAsset}
            canvas={canvas}
          />
        )}

        <div
          className={zoneClass('top')}
          style={{ height: `${SAFE_ZONE_TOP * 100}%` }}
        >
          <span className="zone__label">Плашка Telegram</span>
        </div>
        <div
          className={zoneClass('bottom')}
          style={{ height: `${SAFE_ZONE_BOTTOM * 100}%` }}
        >
          <span className="zone__label">Кнопка доната</span>
        </div>

        {doc.layers.length === 0 && (
          <p className="canvas-empty">
            Пустой стенд.
            <br />
            Возьмите стикер из инвентаря и поставьте его сюда.
          </p>
        )}
      </div>
    </div>
  );
}
