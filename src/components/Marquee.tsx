import { FlameSolid } from "./Icons";

interface MarqueeProps {
  items: string[];
  reverse?: boolean;
  className?: string;
  itemClassName?: string;
}

function Row({ items, itemClassName }: { items: string[]; itemClassName?: string }) {
  return (
    <div className="flex items-center shrink-0">
      {items.map((item, i) => (
        <span key={i} className={`flex items-center ${itemClassName ?? ""}`}>
          <span className="whitespace-nowrap">{item}</span>
          <FlameSolid className="w-[0.72em] h-[0.72em] mx-[1.1em] opacity-70 shrink-0" />
        </span>
      ))}
    </div>
  );
}

export default function Marquee({ items, reverse, className = "", itemClassName }: MarqueeProps) {
  return (
    <div className={`overflow-hidden marquee-paused ${className}`}>
      <div className={`marquee-track ${reverse ? "rev" : ""}`}>
        <Row items={items} itemClassName={itemClassName} />
        <div aria-hidden="true" className="flex items-center shrink-0">
          <Row items={items} itemClassName={itemClassName} />
        </div>
      </div>
    </div>
  );
}
