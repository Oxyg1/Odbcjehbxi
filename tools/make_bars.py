"""
Полоски статов из премиум-эмодзи: режет исходную картинку на кусочки.

Исходник — assets/bars/source.jpg: шесть полосок одна под другой на белом
фоне, слева подписи (их отрезаем). Порядок сверху вниз — BAR_KEYS.

Для каждой полоски:
  1. вырезается из листа, белый фон становится прозрачным;
  2. приводится к 800×BAR_H и ставится по центру полосы 800×100;
  3. режется на 8 квадратов 100×100 — размер статичного эмодзи Telegram;
  4. у каждого кусочка три вида: f — полный, h — левая половина полная,
     правая пустая, e — пустой. Пустой — та же картинка, где заливка внутри
     обводки стала тёмным «стеклом», а рамка (и кости у окорока) осталась
     цветной. Поэтому полный, половина и пустой совпадают пиксель в пиксель.

Результат: assets/bars/<ключ>/<позиция><вид>.png (0f.png … 7e.png) и
preview.png — как полоски выглядят строкой в тёмной и светлой теме.

Запуск:
    python3 tools/make_bars.py [исходник]
Нужны Pillow, numpy, scipy (только на машине, где режут; боту не нужны).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "bars")
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "source.jpg")

BAR_KEYS = ["xp", "food", "happy", "health", "clean", "energy"]
TILES = 8           # кусочков в полоске
TILE = 100          # статичное эмодзи — 100×100
BAR_H = 86          # высота полоски внутри кусочка


def find_bars(a: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Рамки полосок (x0, y0, x1, y1): полосы строк, в каждой — самый правый кусок."""
    ink = a.min(axis=2) < 225
    rows = ink[:, a.shape[1] // 3:].any(axis=1)
    bands, start = [], None
    for y, v in enumerate(rows):
        if v and start is None:
            start = y
        elif not v and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, len(rows)))
    boxes = []
    for y0, y1 in bands:
        xs = np.nonzero(ink[y0:y1].any(axis=0))[0]
        # подпись слева отделена от полоски пустым промежутком
        gaps = np.nonzero(np.diff(xs) > 15)[0]
        x0 = xs[gaps[-1] + 1] if len(gaps) else xs[0]
        boxes.append((int(x0), y0, int(xs[-1]) + 1, y1))
    return boxes


def fix_health(a: np.ndarray, box) -> None:
    """
    У «Здоровья» в исходнике правый конец заливки затемнён полупрозрачным
    прямоугольником (генератор нарисовал полоску не до конца). Ободок и
    обводку он не задел. Чиним:
      - середину — продолжаем каждую строку чистым столбцом перед затемнением:
        заливка, блик и ровная линия пульса там однородны по горизонтали;
      - закруглённый конец — отражением левого конца, и только там, где
        пиксель темнее, чем в отражении (ободок не трогаем).
    """
    x0, y0, x1, y1 = box
    lum = a.astype(float) @ [0.299, 0.587, 0.114]
    h = y1 - y0
    cap = x1 - h * 3 // 4                           # дальше — закругление
    # Начало затемнения: первый столбец, после которого заливка до самого
    # закругления темнее, чем перед ним. Медиана по средним строкам — чтобы
    # линия пульса и блик не сбивали.
    col = np.median(lum[y0 + h // 5:y1 - h // 5], axis=0)
    start = None
    for x in range(x0 + (x1 - x0) * 3 // 5, cap - 10):
        if col[x - 32:x - 2].min() - col[x + 2:cap].max() > 10:
            start = x - 1
            break
    if start is None:
        return                                      # затемнения нет — чинить нечего
    ref = a[y0:y1, start - 6].copy()
    ref_l = lum[y0:y1, start - 6]
    for x in range(start, cap):
        dark = lum[y0:y1, x] < ref_l - 5
        a[y0:y1, x][dark] = ref[dark]
    for x in range(cap, x1):
        mx = x0 + x1 - 1 - x
        m = a[y0:y1, mx]
        dark = lum[y0:y1, x] < (m.astype(float) @ [0.299, 0.587, 0.114]) - 8
        a[y0:y1, x][dark] = m[dark]


def cut_bar(a: np.ndarray, box) -> Image.Image:
    """Полоска с прозрачным фоном: заливка от краёв по почти-белому + мягкий край."""
    x0, y0, x1, y1 = box
    pad = 6
    sub = a[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad].astype(float)
    light = sub.min(axis=2)
    near_white = light > 228
    # Фон — только то, что связано с краем: белые блики внутри полоски остаются
    lab, _ = ndimage.label(near_white)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = np.isin(lab, list(edge))
    alpha = np.where(bg, 0.0, 1.0)
    # Полоса сглаживания по краю: белое, подмешанное к тёмной обводке
    band = ndimage.binary_dilation(bg, iterations=3) & ~bg
    outline = np.median(sub[~bg & ~ndimage.binary_dilation(band, iterations=2) &
                            ndimage.binary_dilation(bg, iterations=8)], axis=0)
    o_light = float(outline.min())
    a_band = np.clip((255 - light) / max(1.0, 255 - o_light), 0, 1)
    alpha[band] = a_band[band]
    rgb = sub.copy()
    rgb[band] = outline                       # цвет края — цвет обводки
    rgba = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA")
    return im.crop(im.getbbox())


def fill_mask(bar: np.ndarray) -> np.ndarray:
    """
    Заливка — всё, что внутри обводки капсулы. Ищем от центра полоски по
    непрозрачным и не тёмным точкам, затем закрываем дыры (пятна, насечки,
    линия пульса). Кости окорока за обводкой в маску не попадают.
    """
    alpha = bar[..., 3] > 200
    lum = bar[..., :3].astype(float) @ [0.299, 0.587, 0.114]
    h, w = lum.shape
    ring = alpha & ~ndimage.binary_erosion(alpha, iterations=4)
    o_lum = np.percentile(lum[ring], 30)
    inner = alpha & (lum > o_lum + 28)
    lab, _ = ndimage.label(inner)
    # метка в центре — внутренность капсулы
    cy, cx = h // 2, w // 2
    centre = lab[cy - 3:cy + 4, cx - 40:cx + 41]
    vals, counts = np.unique(centre[centre > 0], return_counts=True)
    m = lab == vals[np.argmax(counts)]
    m = ndimage.binary_fill_holes(m)
    return ndimage.binary_dilation(m, iterations=1) & alpha


def empty_version(bar: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Пустая полоска: заливка — тёмное стекло с призраком узора, рамка как была."""
    out = bar.copy()
    lum = bar[..., :3].astype(float) @ [0.299, 0.587, 0.114]
    v = 46 + 0.20 * lum
    glass = np.dstack([v - 2, v + 1, v + 9]).clip(0, 255)
    out[..., :3][mask] = glass[mask].astype(np.uint8)
    return out


def tiles_for(bar_img: Image.Image) -> dict[str, Image.Image]:
    bar_img = bar_img.convert("RGBa").resize((TILES * TILE, BAR_H), Image.LANCZOS).convert("RGBA")
    full = np.asarray(bar_img).copy()
    mask = fill_mask(full)
    empty = empty_version(full, mask)
    strip_f = np.zeros((TILE, TILES * TILE, 4), np.uint8)
    strip_e = np.zeros_like(strip_f)
    top = (TILE - BAR_H) // 2
    strip_f[top:top + BAR_H] = full
    strip_e[top:top + BAR_H] = empty
    out = {}
    for i in range(TILES):
        sl = slice(i * TILE, (i + 1) * TILE)
        f, e = strip_f[:, sl], strip_e[:, sl]
        h = e.copy()
        h[:, :TILE // 2] = f[:, :TILE // 2]
        out[f"{i}f"] = Image.fromarray(f, "RGBA")
        out[f"{i}h"] = Image.fromarray(h, "RGBA")
        out[f"{i}e"] = Image.fromarray(e, "RGBA")
    return out


def bar_states(value: int) -> list[str]:
    """Какие кусочки ставить для value% — так же считает бот (stat_bar в bot.py)."""
    steps = round(max(0, min(100, value)) / 100 * TILES * 2)
    if value > 0 and steps == 0:
        steps = 1
    if value < 100 and steps == TILES * 2:
        steps -= 1
    return [f"{i}{'f' if steps >= 2 * (i + 1) else 'h' if steps == 2 * i + 1 else 'e'}"
            for i in range(TILES)]


def preview(all_tiles: dict, path: str) -> None:
    """Строки как в карточке лягушки: тёмная и светлая тема, в размер экрана и крупно."""
    values = {"xp": 87, "food": 83, "happy": 50, "health": 100, "clean": 19, "energy": 4}
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    panels = []
    for bg, fg in (((24, 34, 45), (230, 235, 240)), ((255, 255, 255), (20, 20, 20))):
        for size in (22, 44):
            line_h = int(size * 1.3)
            w = size * (TILES + 1) + 140
            p = Image.new("RGBA", (w, line_h * len(BAR_KEYS) + 20), bg + (255,))
            d = ImageDraw.Draw(p)
            for r, key in enumerate(BAR_KEYS):
                y = 10 + r * line_h
                for i, st in enumerate(bar_states(values[key])):
                    t = all_tiles[key][st].resize((size, size), Image.LANCZOS)
                    p.alpha_composite(t, (size // 2 + i * size, y))
                fsz = font if size == 22 else ImageFont.truetype(font.path, 26) if hasattr(font, "path") else font
                d.text((size // 2 + TILES * size + 8, y + size // 2), f"{values[key]}%",
                       fill=fg, font=fsz, anchor="lm")
            panels.append(p)
    cw = max(p.width for p in panels) + 10
    ch = [max(panels[0].height, panels[2].height), max(panels[1].height, panels[3].height)]
    sheet = Image.new("RGBA", (cw * 2 + 10, ch[0] + ch[1] + 30), (128, 128, 128, 255))
    for col, (small, big) in enumerate(((panels[0], panels[1]), (panels[2], panels[3]))):
        sheet.alpha_composite(small, (10 + col * cw, 10))
        sheet.alpha_composite(big, (10 + col * cw, 20 + ch[0]))
    sheet.convert("RGB").save(path)


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    a = np.asarray(src).copy()
    boxes = find_bars(a)
    if len(boxes) != len(BAR_KEYS):
        sys.exit(f"нашёл {len(boxes)} полосок, а нужно {len(BAR_KEYS)}")
    fix_health(a, boxes[BAR_KEYS.index("health")])
    all_tiles = {}
    for key, box in zip(BAR_KEYS, boxes):
        tiles = tiles_for(cut_bar(a, box))
        os.makedirs(os.path.join(OUT, key), exist_ok=True)
        for name, im in tiles.items():
            im.save(os.path.join(OUT, key, f"{name}.png"), optimize=True)
        all_tiles[key] = tiles
        print(f"{key}: {box} → {len(tiles)} кусочков")
    preview(all_tiles, os.path.join(OUT, "preview.png"))
    print("превью:", os.path.join(OUT, "preview.png"))


if __name__ == "__main__":
    main()
