import { memo } from 'react';
import type { ThemeEffect } from '@tgdonate/shared';

/**
 * The booth's canopy.
 *
 * A stand has to read as a *stall on a floor*, not a list row — that is the
 * whole PLS DONATE metaphor. This draws the storefront: a scalloped awning, its
 * shadow on the counter below, and a hanging sign board.
 *
 * Each theme gets a genuinely different silhouette and material, because the
 * themes are sold for Stars: if PS1 Low-Poly looked like Midnight with another
 * accent nobody would buy it.
 */

export interface AwningProps {
  /** Primary hue — the awning's stripes and sign glow. */
  accent: string;
  /** Card surface, used to blend the canopy into the body. */
  surface: string;
  effect: ThemeEffect;
  /** Rendered on the sign board. */
  label?: string;
  height?: number;
}

const SCALLOPS = 7;

/** Scalloped lower edge, the classic fairground awning silhouette. */
function scallopPath(width: number, top: number, depth: number): string {
  const step = width / SCALLOPS;
  let d = `M0 ${top}`;
  for (let i = 0; i < SCALLOPS; i += 1) {
    const x = i * step;
    d += ` Q ${x + step / 2} ${top + depth} ${x + step} ${top}`;
  }
  return `${d} L${width} 0 L0 0 Z`;
}

export const StandAwning = memo(function StandAwning({
  accent,
  surface,
  effect,
  label,
  height = 46,
}: AwningProps) {
  const W = 200;
  const canopy = height * 0.62;
  const id = `aw-${effect}-${accent.replace(/[^a-z0-9]/gi, '')}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-x-0 top-0 z-3 h-[46px] w-full"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.95" />
          <stop offset="100%" stopColor={accent} stopOpacity="0.62" />
        </linearGradient>
        {/* Alternating stripes: the single strongest "this is a stall" cue. */}
        <pattern id={`${id}-stripe`} width={W / SCALLOPS} height={height} patternUnits="userSpaceOnUse">
          <rect width={W / SCALLOPS / 2} height={height} fill="#ffffff" fillOpacity="0.22" />
        </pattern>
        <linearGradient id={`${id}-shade`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#000" stopOpacity="0.45" />
          <stop offset="100%" stopColor={surface} stopOpacity="0" />
        </linearGradient>
      </defs>

      {effect === 'CYBERPUNK_GRID' ? (
        <NeonSign id={id} accent={accent} width={W} height={height} label={label} />
      ) : effect === 'LOW_POLY' ? (
        <PixelAwning id={id} accent={accent} width={W} canopy={canopy} />
      ) : effect === 'CRT_SCANLINES' ? (
        <CrtAwning id={id} accent={accent} width={W} canopy={canopy} />
      ) : (
        <>
          <path d={scallopPath(W, canopy, height * 0.2)} fill={`url(#${id}-fill)`} />
          <path d={scallopPath(W, canopy, height * 0.2)} fill={`url(#${id}-stripe)`} />
          {effect === 'GOLD_ROYALTY' ? <Fringe width={W} y={canopy + height * 0.2} /> : null}
        </>
      )}

      {/* Contact shadow the canopy throws onto the counter. */}
      <rect x="0" y={canopy} width={W} height={height - canopy} fill={`url(#${id}-shade)`} />
    </svg>
  );
});

/** Cyberpunk: a neon tube sign instead of fabric. */
function NeonSign({
  id,
  accent,
  width,
  height,
  label,
}: {
  id: string;
  accent: string;
  width: number;
  height: number;
  label?: string;
}) {
  return (
    <>
      <defs>
        <filter id={`${id}-glow`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect x="6" y="5" width={width - 12} height={height * 0.5} rx="6" fill="#0b0620" fillOpacity="0.85" />
      <rect
        x="6"
        y="5"
        width={width - 12}
        height={height * 0.5}
        rx="6"
        fill="none"
        stroke={accent}
        strokeWidth="1.6"
        filter={`url(#${id}-glow)`}
      />
      {label ? (
        <text
          x={width / 2}
          y={height * 0.34}
          textAnchor="middle"
          fontSize="11"
          fontWeight="800"
          fill={accent}
          filter={`url(#${id}-glow)`}
          letterSpacing="1"
        >
          {label.slice(0, 16).toUpperCase()}
        </text>
      ) : null}
    </>
  );
}

/** PS1 Low-Poly: blocky, untextured, hard edges — no curves anywhere. */
function PixelAwning({
  accent,
  width,
  canopy,
}: {
  id: string;
  accent: string;
  width: number;
  canopy: number;
}) {
  // Chunky, flat-shaded blocks with a stair-stepped hem — no gradients and no
  // curves, so it reads as untextured geometry rather than cloth.
  const cols = 8;
  const step = width / cols;
  const shades = ['#ffffff', '#000000'];
  return (
    <>
      <rect x="0" y="0" width={width} height={canopy} fill={accent} />
      {Array.from({ length: cols }, (_, i) => (
        <rect
          key={i}
          x={i * step}
          y="0"
          width={step}
          height={canopy}
          fill={shades[i % 2] as string}
          fillOpacity={i % 2 === 0 ? 0.3 : 0.22}
        />
      ))}
      {/* Hem descends in hard steps, two block heights alternating. */}
      {Array.from({ length: cols }, (_, i) => (
        <rect
          key={`h${i}`}
          x={i * step}
          y={canopy}
          width={step}
          height={i % 2 === 0 ? 7 : 3}
          fill={accent}
        />
      ))}
      {/* Specular block: one lit facet, the classic low-poly cue. */}
      <rect x={step} y="0" width={step} height={canopy * 0.5} fill="#fff" fillOpacity="0.4" />
    </>
  );
}

/** CRT: phosphor bar with scanlines burned across it. */
function CrtAwning({
  id,
  accent,
  width,
  canopy,
}: {
  id: string;
  accent: string;
  width: number;
  canopy: number;
}) {
  return (
    <>
      <defs>
        <pattern id={`${id}-scan`} width="3" height="3" patternUnits="userSpaceOnUse">
          <rect width="3" height="1.4" fill="#000" fillOpacity="0.5" />
        </pattern>
      </defs>
      <rect x="0" y="0" width={width} height={canopy} fill={`url(#${id}-fill)`} />
      <rect x="0" y="0" width={width} height={canopy} fill={`url(#${id}-scan)`} />
      <rect x="0" y={canopy - 2} width={width} height="2" fill={accent} />
    </>
  );
}

/** Gold Royalty: bullion fringe hanging off the hem. */
function Fringe({ width, y }: { width: number; y: number }) {
  const count = 24;
  const step = width / count;
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <circle key={i} cx={i * step + step / 2} cy={y} r="1.6" fill="#ffe9a8" fillOpacity="0.9" />
      ))}
    </>
  );
}
