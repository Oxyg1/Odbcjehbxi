import type { Asset, StandDoc } from '@plsdonate/shared';
import { Sheet } from '../components/Sheet';
import { IconButton } from '../components/IconButton';
import { ArrowDownIcon, ArrowUpIcon, TrashIcon } from '../components/icons';
import { moveLayer, removeLayer, select } from './store';

interface LayersSheetProps {
  open: boolean;
  doc: StandDoc;
  selectedId: string | null;
  getAsset: (id: string) => Asset | undefined;
  onClose: () => void;
}

/** Полный контроль над стопкой: то, что на канвасе делается только соседними шагами. */
export function LayersSheet({ open, doc, selectedId, getAsset, onClose }: LayersSheetProps) {
  const ordered = [...doc.layers].sort((a, b) => b.zIndex - a.zIndex);

  return (
    <Sheet
      open={open}
      title="Слои"
      meta={ordered.length > 0 ? `Сверху — передний план` : undefined}
      onClose={onClose}
    >
      {ordered.length === 0 ? (
        <p className="hint">Слоёв пока нет.</p>
      ) : (
        <ul className="layer-list">
          {ordered.map((layer, index) => {
            const asset = getAsset(layer.assetId);
            return (
              <li
                key={layer.id}
                className={layer.id === selectedId ? 'layer-row is-selected' : 'layer-row'}
              >
                <button
                  type="button"
                  className="layer-row__main"
                  onClick={() => select(layer.id)}
                >
                  <span className="layer-row__art">
                    {asset && <img src={asset.src} alt="" loading="lazy" />}
                  </span>
                  <span className="layer-row__name">{asset?.title ?? 'Слой'}</span>
                  {asset?.animated && <span className="tile__badge">анимация</span>}
                </button>
                <div className="layer-row__actions">
                  <IconButton
                    label="Поднять"
                    disabled={index === 0}
                    onClick={() => moveLayer(layer.id, 1)}
                  >
                    <ArrowUpIcon size={18} />
                  </IconButton>
                  <IconButton
                    label="Опустить"
                    disabled={index === ordered.length - 1}
                    onClick={() => moveLayer(layer.id, -1)}
                  >
                    <ArrowDownIcon size={18} />
                  </IconButton>
                  <IconButton label="Удалить" onClick={() => removeLayer(layer.id)}>
                    <TrashIcon size={18} />
                  </IconButton>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Sheet>
  );
}
