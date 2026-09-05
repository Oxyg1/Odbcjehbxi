import { useEffect, useState } from 'react';
import {
  ANIMATION_BUDGET,
  MAX_LAYERS,
  type Asset,
  type AssetSource,
} from '@plsdonate/shared';
import { Sheet } from '../components/Sheet';
import { haptic } from '../telegram/webapp';
import { layersWord } from '../text/plural';

interface InventorySheetProps {
  open: boolean;
  assets: Asset[];
  animatedUsed: number;
  layerCount: number;
  onClose: () => void;
  onPick: (asset: Asset) => void;
}

const TABS: { id: AssetSource; label: string }[] = [
  { id: 'user', label: 'Мои' },
  { id: 'shop', label: 'Магазин' },
];

export function InventorySheet({
  open,
  assets,
  animatedUsed,
  layerCount,
  onClose,
  onPick,
}: InventorySheetProps) {
  const [tab, setTab] = useState<AssetSource>('user');
  const [pending, setPending] = useState<Asset | null>(null);

  // Закрытый лист забывает незавершённое предупреждение о бюджете.
  useEffect(() => {
    if (!open) setPending(null);
  }, [open]);

  const visible = assets.filter((asset) => asset.source === tab);
  const full = layerCount >= MAX_LAYERS;

  const pick = (asset: Asset) => {
    if (full) return;
    // Превышение бюджета не запрещено, но требует осознанного согласия.
    if (asset.animated && animatedUsed >= ANIMATION_BUDGET) {
      haptic.warning();
      setPending(asset);
      return;
    }
    onPick(asset);
  };

  const confirm = () => {
    if (!pending) return;
    onPick(pending);
    setPending(null);
  };

  return (
    <Sheet
      open={open}
      title="Инвентарь"
      meta={`Слоёв ${layerCount} из ${MAX_LAYERS}`}
      onClose={onClose}
    >
      <div className="tabs" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={tab === item.id ? 'tab is-active' : 'tab'}
            onClick={() => {
              setTab(item.id);
              setPending(null);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Молчаливый отказ на пределе читается как «приложение сломалось». */}
      {full && (
        <div className="notice">
          <p className="notice__text">
            На стенде уже {MAX_LAYERS} {layersWord(MAX_LAYERS)} — это предел.
            Удалите что-нибудь в «Слоях», чтобы добавить новое.
          </p>
        </div>
      )}

      <ul className="grid">
        {visible.map((asset) => (
          <li key={asset.id}>
            <button
              type="button"
              className={asset.source === 'shop' ? 'tile tile--foil' : 'tile'}
              disabled={full}
              onClick={() => pick(asset)}
            >
              <span className="tile__art">
                <img src={asset.src} alt="" loading="lazy" decoding="async" />
              </span>
              <span className="tile__title">{asset.title}</span>
              {asset.animated && <span className="tile__badge">анимация</span>}
            </button>
          </li>
        ))}
      </ul>

      {pending && (
        <div className="notice notice--confirm">
          <p className="notice__text">
            На стенде уже {animatedUsed} анимированных {layersWord(animatedUsed)}.
            Следующий будет подтормаживать у зрителей на недорогих телефонах.
          </p>
          <div className="notice__actions">
            <button type="button" className="button" onClick={() => setPending(null)}>
              Не надо
            </button>
            <button type="button" className="button button--quiet" onClick={confirm}>
              Всё равно добавить
            </button>
          </div>
        </div>
      )}

      {tab === 'user' && (
        <p className="hint">
          Новые стикеры появляются здесь после проверки: отправьте картинку
          боту-загрузчику.
        </p>
      )}
    </Sheet>
  );
}
