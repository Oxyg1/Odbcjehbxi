import { useState, type ImgHTMLAttributes } from "react";
import { FlameSolid } from "./Icons";

interface SmartImageProps extends ImgHTMLAttributes<HTMLImageElement> {
  /** Может отсутствовать: у некоторых разделов своего снимка ещё нет */
  src?: string;
  alt: string;
  /** Подпись на подложке, когда фото нет или оно не загрузилось */
  fallbackLabel?: string;
  /** Классы для обёртки-подложки (обычно те же пропорции, что у фото) */
  className?: string;
}

/**
 * Картинка, которая не оставляет дыру.
 *
 * Все снимки на сайте лежат на внешнем CDN. Если он отвечает ошибкой —
 * а это уже случалось, — обычный <img> показывает пустое место или
 * иконку «битого файла» поверх тёмного фона. Здесь вместо этого рисуется
 * подложка в цветах сайта с названием раздела.
 */
export default function SmartImage({
  src,
  alt,
  fallbackLabel,
  className = "",
  ...rest
}: SmartImageProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div
        className={`char-plate flex flex-col items-center justify-center gap-2 text-center px-4 ${className}`}
        role="img"
        aria-label={alt}
      >
        <FlameSolid className="w-7 h-7 text-flame/70 flicker" />
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-parch">
          {fallbackLabel ?? alt}
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      decoding="async"
      className={className}
      {...rest}
    />
  );
}
