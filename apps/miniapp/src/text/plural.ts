/**
 * Русские формы числительных: 1 слой, 2 слоя, 5 слоёв.
 * Строки в интерфейсе динамические, поэтому форму нельзя зашивать одну.
 */
export function plural(count: number, one: string, few: string, many: string): string {
  const mod100 = Math.abs(count) % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = mod100 % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

export const layersWord = (count: number): string =>
  plural(count, 'слой', 'слоя', 'слоёв');
