import { IconButton } from '../components/IconButton';
import { ArrowDownIcon, ArrowUpIcon, CopyIcon, TrashIcon } from '../components/icons';
import { duplicateLayer, moveLayer, removeLayer } from './store';

interface SelectionBarProps {
  layerId: string;
  title: string;
}

export function SelectionBar({ layerId, title }: SelectionBarProps) {
  return (
    <div className="selection-bar">
      <span className="selection-bar__name">{title}</span>
      <div className="selection-bar__actions">
        <IconButton label="Слой вперёд" onClick={() => moveLayer(layerId, 1)}>
          <ArrowUpIcon size={18} />
        </IconButton>
        <IconButton label="Слой назад" onClick={() => moveLayer(layerId, -1)}>
          <ArrowDownIcon size={18} />
        </IconButton>
        <IconButton label="Дублировать" onClick={() => duplicateLayer(layerId)}>
          <CopyIcon size={18} />
        </IconButton>
        <IconButton label="Удалить" onClick={() => removeLayer(layerId)}>
          <TrashIcon size={18} />
        </IconButton>
      </div>
    </div>
  );
}
