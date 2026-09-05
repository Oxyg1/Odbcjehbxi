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

/**
 * Наибольший прямоугольник в пропорциях Stories, помещающийся в отведённое место.
 * Считаем сами: связка height/aspect-ratio/max-width в CSS ломает пропорции,
 * как только по ширине не хватает места — холст остаётся высоким, и стенд
 * компонуется в кадре, который зрителю не покажут.
 */
function fitStandBox(available: CanvasSize): CanvasSize {
  if (available.width === 0 || available.height === 0) return EMPTY_SIZE;
  const width = Math.min(available.width, available.height * CANVAS_ASPECT);
  return { width, height: width / CANVAS_ASPECT };
}

export function StandCanvas({ doc, selectedId, getAsset }: StandCanvasProps) {
  const fitRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const layerNodes = useRef(new Map<string, HTMLElement>());
  const canvasSizeRef = useRef<CanvasSize>(EMPTY_SIZE);

  const [canvas, setCanvas] = useState<CanvasSize>(EMPTY_SIZE);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeHit, setActiveHit] = useState<SafeZoneHit | null>(null);

  useEffect(() => {
    const fit = fitRef.current;
    if (!fit) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const box = fitStandBox(entry.contentRect);
      canvasSizeRef.current = box;
      setCanvas(box);
    });
    observer.observe(fit);
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
    hostRef,
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
  // Пока слой в руке, подпись зоны раскрывается полностью: это момент,
  // когда правило нужно объяснить. В покое достаточно приглушённой.
  const zoneClass = (edge: 'top' | 'bottom'): string =>
    ['zone', `zone--${edge}`, hit[edge] ? 'is-hit' : '', activeHit?.[edge] ? 'is-live' : '']
      .filter(Boolean)
      .join(' ');

  const selected = doc.layers.find((layer) => layer.id === selectedId);
  const selectedAsset = selected ? getAsset(selected.assetId) : undefined;

  return (
    <div className="canvas-fit" ref={fitRef}>
      <div
        className="canvas-frame"
        ref={hostRef}
        style={{ width: canvas.width || undefined, height: canvas.height || undefined }}
      >
        <div className="canvas-surface" style={{ background: doc.background }}>
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
              Откройте инвентарь и поставьте первый стикер.
            </p>
          )}
        </div>

        {/*
          Рамка выделения живёт вне холста: у слоя на самом краю ручку
          иначе срезало бы overflow, и слой стало бы нечем масштабировать.
        */}
        {selected && selectedAsset && canvas.width > 0 && (
          <SelectionFrame
            ref={frameRef}
            layer={selected}
            asset={selectedAsset}
            canvas={canvas}
          />
        )}
      </div>
    </div>
  );
}
