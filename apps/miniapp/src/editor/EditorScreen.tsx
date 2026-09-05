import { useCallback, useEffect, useMemo, useState } from 'react';
import { countAnimated, type Asset } from '@plsdonate/shared';
import { AnimationBudget } from './AnimationBudget';
import { InventorySheet } from './InventorySheet';
import { LayersSheet } from './LayersSheet';
import { SelectionBar } from './SelectionBar';
import { StandCanvas } from './StandCanvas';
import { IconButton } from '../components/IconButton';
import { LayersIcon, PlusIcon, RedoIcon, UndoIcon } from '../components/icons';
import { FpsMeter, perfEnabled } from '../perf/FpsMeter';
import { ASSETS_BY_ID, MOCK_INVENTORY, getAsset } from '../mock/inventory';
import { haptic, bindBackButton } from '../telegram/webapp';
import { addLayer, loadDraft, redo, select, undo, useEditor } from './store';

type OpenSheet = 'inventory' | 'layers' | null;

export function EditorScreen() {
  const { doc, selectedId, canUndo, canRedo } = useEditor();
  const [sheet, setSheet] = useState<OpenSheet>(null);

  useEffect(() => {
    loadDraft();
  }, []);

  // Системная кнопка «назад» сначала закрывает лист, потом снимает выделение.
  useEffect(() => {
    const target = sheet ? () => setSheet(null) : selectedId ? () => select(null) : null;
    return bindBackButton(target);
  }, [sheet, selectedId]);

  const animatedUsed = useMemo(
    () => countAnimated(doc.layers, ASSETS_BY_ID),
    [doc.layers],
  );

  const handlePick = useCallback((asset: Asset) => {
    const result = addLayer(asset);
    if (result.ok) {
      haptic.impact('light');
      setSheet(null);
      return;
    }
    // Предел слоёв: лист остаётся открытым и объясняет себя сам.
    haptic.warning();
  }, []);

  const selected = doc.layers.find((layer) => layer.id === selectedId);
  const selectedTitle = selected ? getAsset(selected.assetId)?.title ?? 'Слой' : '';

  return (
    <div className="screen">
      <header className="topbar">
        <div className="topbar__title">
          <h1>Мой стенд</h1>
          <p className="topbar__state">
            {doc.layers.length > 0 ? 'Черновик сохранён' : 'Новый стенд'}
          </p>
        </div>
        <AnimationBudget used={animatedUsed} />
      </header>

      <main className="stage">
        <StandCanvas doc={doc} selectedId={selectedId} getAsset={getAsset} />
      </main>

      <footer className="dock">
        {selected && <SelectionBar layerId={selected.id} title={selectedTitle} />}
        <div className="toolbar">
          <div className="toolbar__history">
            <IconButton label="Отменить" onClick={undo} disabled={!canUndo}>
              <UndoIcon />
            </IconButton>
            <IconButton label="Повторить" onClick={redo} disabled={!canRedo}>
              <RedoIcon />
            </IconButton>
          </div>
          <button
            type="button"
            className="button button--wide"
            onClick={() => setSheet('inventory')}
          >
            <PlusIcon />
            <span className="button__label">Инвентарь</span>
          </button>
          <button type="button" className="button" onClick={() => setSheet('layers')}>
            <LayersIcon />
            <span className="button__label">Слои</span>
          </button>
        </div>
      </footer>

      <InventorySheet
        open={sheet === 'inventory'}
        assets={MOCK_INVENTORY}
        animatedUsed={animatedUsed}
        layerCount={doc.layers.length}
        onClose={() => setSheet(null)}
        onPick={handlePick}
      />
      <LayersSheet
        open={sheet === 'layers'}
        doc={doc}
        selectedId={selectedId}
        getAsset={getAsset}
        onClose={() => setSheet(null)}
      />

      {perfEnabled() && <FpsMeter />}
    </div>
  );
}
