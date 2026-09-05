import type { Asset } from '@plsdonate/shared';

/**
 * Временный инвентарь. Настоящий наполняется ботом-загрузчиком после модерации
 * (этап 3) — до этого редактор работает на этом наборе, чтобы конструктор можно
 * было довести и протестировать раньше загрузки.
 */
export const MOCK_INVENTORY: Asset[] = [
  { id: 'u_star', src: '/mock/star.svg', aspect: 1, animated: false, source: 'user', title: 'Звезда' },
  { id: 'u_heart', src: '/mock/heart.svg', aspect: 200 / 180, animated: false, source: 'user', title: 'Сердце' },
  { id: 'u_cat', src: '/mock/cat.svg', aspect: 200 / 190, animated: false, source: 'user', title: 'Кот' },
  { id: 'u_bubble', src: '/mock/bubble.svg', aspect: 240 / 160, animated: false, source: 'user', title: 'Облако реплики' },
  { id: 'u_arrow', src: '/mock/arrow.svg', aspect: 220 / 120, animated: false, source: 'user', title: 'Стрелка' },
  { id: 'u_crown', src: '/mock/crown.svg', aspect: 220 / 150, animated: false, source: 'user', title: 'Корона' },
  { id: 'u_sparkle', src: '/mock/sparkle-anim.svg', aspect: 1, animated: true, source: 'user', title: 'Искры' },
  { id: 'u_flame', src: '/mock/flame-anim.svg', aspect: 160 / 200, animated: true, source: 'user', title: 'Огонь' },
  { id: 'u_confetti', src: '/mock/confetti-anim.svg', aspect: 1, animated: true, source: 'user', title: 'Конфетти' },
  { id: 's_frame', src: '/mock/shop-frame.svg', aspect: 300 / 420, animated: false, source: 'shop', title: 'Рамка «Фольга»' },
  { id: 's_halo', src: '/mock/shop-halo-anim.svg', aspect: 1, animated: true, source: 'shop', title: 'Ореол' },
  { id: 's_backdrop', src: '/mock/shop-backdrop.svg', aspect: 360 / 640, animated: false, source: 'shop', title: 'Фон «Ночь»' },
];

export const ASSETS_BY_ID: ReadonlyMap<string, Asset> = new Map(
  MOCK_INVENTORY.map((asset) => [asset.id, asset]),
);

export const getAsset = (id: string): Asset | undefined => ASSETS_BY_ID.get(id);
