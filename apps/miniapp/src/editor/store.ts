import { useSyncExternalStore } from 'react';
import {
  MAX_LAYERS,
  SCALE_DEFAULT,
  emptyStand,
  normalizeZ,
  standDocSchema,
  type Asset,
  type StandDoc,
  type StandLayer,
} from '@plsdonate/shared';

export interface LayerTransform {
  x: number;
  y: number;
  scale: number;
  rotation: number;
}

export interface EditorState {
  doc: StandDoc;
  selectedId: string | null;
  canUndo: boolean;
  canRedo: boolean;
}

const HISTORY_LIMIT = 50;
const DRAFT_KEY = 'plsdonate:draft:v1';

let doc: StandDoc = emptyStand();
let selectedId: string | null = null;
let past: StandDoc[] = [];
let future: StandDoc[] = [];

let snapshot: EditorState = { doc, selectedId, canUndo: false, canRedo: false };
const listeners = new Set<() => void>();

function publish(): void {
  snapshot = {
    doc,
    selectedId,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
  };
  for (const listener of listeners) listener();
}

/** Изменение документа с записью в историю. */
function commit(next: StandDoc): void {
  past = [...past.slice(-(HISTORY_LIMIT - 1)), doc];
  future = [];
  doc = next;
  saveDraft();
  publish();
}

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

const getSnapshot = (): EditorState => snapshot;

export function useEditor(): EditorState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

export const getState = (): EditorState => snapshot;

export const findLayer = (id: string | null): StandLayer | undefined =>
  id ? doc.layers.find((layer) => layer.id === id) : undefined;

const nextZ = (): number =>
  doc.layers.reduce((max, layer) => Math.max(max, layer.zIndex + 1), 0);

const makeId = (): string =>
  `l_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export function select(id: string | null): void {
  if (selectedId === id) return;
  selectedId = id;
  publish();
}

export type AddLayerResult =
  | { ok: true; layer: StandLayer }
  | { ok: false; reason: 'limit' };

/** Добавляет ассет по центру холста, поверх остальных слоёв. */
export function addLayer(asset: Asset): AddLayerResult {
  if (doc.layers.length >= MAX_LAYERS) return { ok: false, reason: 'limit' };
  const layer: StandLayer = {
    id: makeId(),
    assetId: asset.id,
    x: 0.5,
    y: 0.44,
    scale: SCALE_DEFAULT,
    rotation: 0,
    zIndex: nextZ(),
  };
  commit({ ...doc, layers: [...doc.layers, layer] });
  select(layer.id);
  return { ok: true, layer };
}

export function updateTransform(id: string, transform: LayerTransform): void {
  const current = doc.layers.find((layer) => layer.id === id);
  if (!current) return;
  const unchanged =
    current.x === transform.x &&
    current.y === transform.y &&
    current.scale === transform.scale &&
    current.rotation === transform.rotation;
  if (unchanged) return;
  commit({
    ...doc,
    layers: doc.layers.map((layer) =>
      layer.id === id ? { ...layer, ...transform } : layer,
    ),
  });
}

export function removeLayer(id: string): void {
  if (!doc.layers.some((layer) => layer.id === id)) return;
  commit({
    ...doc,
    layers: normalizeZ(doc.layers.filter((layer) => layer.id !== id)),
  });
  if (selectedId === id) select(null);
}

export function duplicateLayer(id: string): void {
  const source = doc.layers.find((layer) => layer.id === id);
  if (!source || doc.layers.length >= MAX_LAYERS) return;
  const copy: StandLayer = {
    ...source,
    id: makeId(),
    x: source.x + 0.05,
    y: source.y + 0.03,
    zIndex: nextZ(),
  };
  commit({ ...doc, layers: [...doc.layers, copy] });
  select(copy.id);
}

/** Сдвиг слоя на одну позицию в стопке. direction: 1 — вперёд, -1 — назад. */
export function moveLayer(id: string, direction: 1 | -1): void {
  const ordered = [...doc.layers].sort((a, b) => a.zIndex - b.zIndex);
  const index = ordered.findIndex((layer) => layer.id === id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= ordered.length) return;
  const swapped = [...ordered];
  const moving = swapped[index]!;
  swapped[index] = swapped[target]!;
  swapped[target] = moving;
  commit({ ...doc, layers: normalizeZ(swapped.map((layer, i) => ({ ...layer, zIndex: i }))) });
}

export function undo(): void {
  const previous = past[past.length - 1];
  if (!previous) return;
  past = past.slice(0, -1);
  future = [doc, ...future].slice(0, HISTORY_LIMIT);
  doc = previous;
  if (selectedId && !doc.layers.some((layer) => layer.id === selectedId)) selectedId = null;
  saveDraft();
  publish();
}

export function redo(): void {
  const next = future[0];
  if (!next) return;
  future = future.slice(1);
  past = [...past.slice(-(HISTORY_LIMIT - 1)), doc];
  doc = next;
  if (selectedId && !doc.layers.some((layer) => layer.id === selectedId)) selectedId = null;
  saveDraft();
  publish();
}

/**
 * Черновик живёт в localStorage до появления API (этап 2). Формат тот же самый,
 * поэтому синхронизация с сервером сведётся к замене транспорта.
 */
function saveDraft(): void {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(doc));
  } catch {
    // Приватный режим WebView может запрещать запись — черновик не критичен.
  }
}

export function loadDraft(): void {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    const parsed = standDocSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return;
    doc = parsed.data;
    past = [];
    future = [];
    publish();
  } catch {
    // Битый черновик — начинаем с пустого стенда.
  }
}
