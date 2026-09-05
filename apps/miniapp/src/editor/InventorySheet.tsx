import { useEffect, useState } from 'react';
import { ANIMATION_BUDGET, type Asset, type AssetSource } from '@plsdonate/shared';
import { Sheet } from '../components/Sheet';
import { haptic } from '../telegram/webapp';

interface InventorySheetProps {
  open: boolean;
  assets: Asset[];
  animatedUsed: number;
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

  const pick = (asset: Asset) => {
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
    <Sheet open={open} title="Инвентарь" onClose={onClose}>
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

      {pending && (
        <div className="notice">
          <p className="notice__text">
            На стенде уже {animatedUsed} анимированных слоя. Следующий будет
            подтормаживать у зрителей на недорогих телефонах.
          </p>
          <div className="notice__actions">
            <button type="button" className="button button--quiet" onClick={() => setPending(null)}>
              Не надо
            </button>
            <button type="button" className="button" onClick={confirm}>
              Всё равно добавить
            </button>
          </div>
        </div>
      )}

      <ul className="grid">
        {visible.map((asset) => (
          <li key={asset.id}>
            <button
              type="button"
              className={asset.source === 'shop' ? 'tile tile--foil' : 'tile'}
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

      {tab === 'user' && (
        <p className="hint">
          Новые стикеры появляются здесь после проверки: отправьте картинку
          боту-загрузчику.
        </p>
      )}
    </Sheet>
  );
}
