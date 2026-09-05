import { z } from 'zod';
import {
  MAX_LAYERS,
  POSITION_MAX,
  POSITION_MIN,
  SCALE_MAX,
  SCALE_MIN,
} from './limits';

/**
 * Стенд хранится списком слоёв, а не растром: так его можно перерисовать под
 * любое разрешение, отредактировать без потери качества и позже ремикснуть.
 *
 * Система координат нормализована по холсту, поэтому JSON не зависит от
 * размера экрана:
 *   x, y      — центр слоя в долях ширины/высоты холста (0..1 — внутри холста);
 *   scale     — ширина слоя в долях ширины холста (высота берётся из пропорций ассета);
 *   rotation  — поворот в градусах, любой угол;
 *   zIndex    — порядок слоёв, больше значит выше.
 */
export const standLayerSchema = z.object({
  id: z.string().min(1).max(64),
  assetId: z.string().min(1).max(64),
  x: z.number().min(POSITION_MIN).max(POSITION_MAX),
  y: z.number().min(POSITION_MIN).max(POSITION_MAX),
  scale: z.number().min(SCALE_MIN).max(SCALE_MAX),
  rotation: z.number().min(-180).max(180),
  zIndex: z.number().int().min(0).max(MAX_LAYERS * 4),
});

export type StandLayer = z.infer<typeof standLayerSchema>;

/** Версия формата. Растёт при несовместимых изменениях схемы слоёв. */
export const STAND_DOC_VERSION = 1;

export const standDocSchema = z.object({
  version: z.literal(STAND_DOC_VERSION),
  /** Фон холста под всеми слоями. Ассет-фон кладётся отдельным слоем. */
  background: z.string().regex(/^#[0-9a-fA-F]{6}$/),
  layers: z.array(standLayerSchema).max(MAX_LAYERS),
});

export type StandDoc = z.infer<typeof standDocSchema>;

export const DEFAULT_BACKGROUND = '#14141B';

export function emptyStand(): StandDoc {
  return { version: STAND_DOC_VERSION, background: DEFAULT_BACKGROUND, layers: [] };
}

/**
 * Ассет из инвентаря. Инвентарь наполняется ботом-загрузчиком (пользовательские
 * стикеры) и магазином (фирменные ассеты за Stars).
 */
export type AssetSource = 'user' | 'shop';

export interface Asset {
  id: string;
  src: string;
  /** Отношение ширины к высоте исходника. */
  aspect: number;
  /** Анимированный ассет расходует бюджет анимации. */
  animated: boolean;
  source: AssetSource;
  title: string;
}

/** Компактифицирует zIndex до 0..n-1, сохраняя текущий порядок. */
export function normalizeZ(layers: StandLayer[]): StandLayer[] {
  return [...layers]
    .sort((a, b) => a.zIndex - b.zIndex)
    .map((layer, index) => (layer.zIndex === index ? layer : { ...layer, zIndex: index }));
}

/** Сколько анимированных слоёв стоит на стенде. */
export function countAnimated(
  layers: StandLayer[],
  assets: ReadonlyMap<string, Asset>,
): number {
  let total = 0;
  for (const layer of layers) {
    if (assets.get(layer.assetId)?.animated) total += 1;
  }
  return total;
}
