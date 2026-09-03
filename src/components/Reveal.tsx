import { useEffect, useRef, type ReactNode } from "react";

interface RevealProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  variant?: "up" | "left" | "tilt";
  tilt?: number;
  as?: "div" | "section" | "li" | "article" | "figure";
}

export default function Reveal({
  children,
  className = "",
  delay = 0,
  variant = "up",
  tilt = 0,
  as: Tag = "div",
}: RevealProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          el.classList.add("in");
          io.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const base =
    variant === "left" ? "reveal-left" : variant === "tilt" ? "reveal-tilt" : "reveal";

  return (
    <Tag
      ref={ref as never}
      className={`${base} ${className}`}
      style={{
        transitionDelay: `${delay}ms`,
        ["--tilt" as string]: `${tilt}deg`,
      }}
    >
      {children}
    </Tag>
  );
}
