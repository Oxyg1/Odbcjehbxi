/**
 * Design tokens.
 *
 * Values are lifted verbatim from the reference Portals Mini App builds so the
 * two products read as one family: same near-black canvas, same layered
 * elevation ramp, same "liquid glass" inner-shadow recipe, same 16px squircle
 * radius scale, same SF Pro Text stack.
 */

export const palette = {
  /** Canvas. */
  background: '#141414',
  /** Elevation ramp, darkest -> lightest. */
  surface1: '#191919',
  surface2: '#1c1c1c',
  surface3: '#212020',
  surface4: '#282727',
  surface5: '#363636',
  surface6: '#3a3a3a',
  border: '#454545',

  foreground: '#ffffff',
  mutedForeground: '#6d6d71',

  /** Text opacity ramp used for hierarchy inside cards. */
  textAlpha1: '#ffffffb3',
  textAlpha2: '#ffffff66',
  textAlpha3: '#ffffff3d',

  /** Semantic accents. */
  primary: '#1689ff',
  accent: '#49df64',
  gold: '#f1aa05',
  purple: '#6d51de',
  destructive: '#df494d',
  destructiveSecondary: '#ff3f46',
  tifany: '#68fbdd',
  coral: '#d88b6b',

  positive: '#49df64',
  negative: '#df494d',
  neutral: '#6d6d71',
} as const;

export const gradients = {
  gold: 'linear-gradient(94.02deg, #fac297 1.95%, #ffc386 50.42%, #ca8e52 100%)',
  goldSecondary:
    'linear-gradient(95.81deg, #f1aa05 0.35%, #fbae61 49.03%, #e6b94e 100%)',
  accentGlow:
    'linear-gradient(180deg, rgba(73,223,100,0.24) 0%, rgba(73,223,100,0) 100%)',
  whale:
    'linear-gradient(94deg, #6d51de 0%, #1689ff 48%, #68fbdd 100%)',
  cyberpunk:
    'linear-gradient(160deg, #0e0737 0%, #6d51de 55%, #d90751 100%)',
  lowPoly:
    'linear-gradient(160deg, #2b4a7a 0%, #b0e6ff 60%, #efe5d3 100%)',
  royalty:
    'linear-gradient(160deg, #a43606 0%, #f1aa05 45%, #ffe823 100%)',
  aurora:
    'linear-gradient(160deg, #68fbdd 0%, #1689ff 45%, #984995 100%)',
} as const;

/**
 * The Portals "liquid glass" box-shadow. Two variants: `modern` uses
 * `color-mix` so it re-tints against whatever `--c-light` / `--c-dark` are, and
 * `fallback` is a flattened rgba version for engines without `color-mix`.
 */
export const glassShadow = {
  fallback: [
    'inset 0 0 0 1px rgba(255,255,255,.03)',
    'inset 1.8px 3px 0px -2px rgba(255,255,255,.27)',
    'inset -2px -2px 0px -2px rgba(255,255,255,.24)',
    'inset -3px -8px 1px -6px rgba(255,255,255,.18)',
    'inset -.3px -1px 4px 0px rgba(0,0,0,.24)',
    'inset -1.5px 2.5px 0px -2px rgba(0,0,0,.4)',
    'inset 0px 3px 4px -2px rgba(0,0,0,.4)',
    'inset 2px -6.5px 1px -4px rgba(0,0,0,.2)',
    '0px 1px 5px 0px rgba(0,0,0,.2)',
    '0px 6px 16px 0px rgba(0,0,0,.16)',
  ].join(','),
  blur: 'blur(8px) saturate(140%)',
} as const;

/** Corner radii. Paired with `corner-shape: squircle` where supported. */
export const radii = {
  sm: '10px',
  md: '16px',
  lg: '20px',
  xl: '24px',
  '2xl': '26px',
  '3xl': '28px',
  '4xl': '32px',
  full: '9999px',
} as const;

export const typography = {
  fontSans:
    '"SFProText", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif',
  fontMono: '"SFMono-Regular", ui-monospace, "JetBrains Mono", monospace',
  tracking: {
    tight: '-0.6px',
    snug: '-0.5px',
    normal: '0',
  },
  leading: {
    xs: '14px',
    sm: '18px',
    md: '22px',
    lg: '24px',
  },
} as const;

/** Fixed chrome dimensions, matching the reference tab bar. */
export const layout = {
  tabBarHeight: '62px',
  /** Scroll clearance under the floating tab bar. */
  tabBarClearance: '84px',
  sheetRadius: '24px',
  headerRadius: '32px',
  /** The Mini App column is capped and centred on wide clients. */
  maxWidth: '512px',
} as const;

/**
 * Press physics. The reference transitions transform and filter together and
 * keeps the scale shallow, so a tap reads as mechanical rather than rubbery.
 */
export const interaction = {
  duration: '150ms',
  easing: 'ease-out',
  activeScale: 0.985,
  activeBrightness: 0.95,
  hoverBrightness: 1.05,
  /** Alpha of a primary CTA's coloured lift. */
  ctaGlowAlpha: 0.38,
  ctaGlowOffset: '0 10px 30px',
} as const;

/** Per-tier presentation of a donation event. */
export const tierStyle = {
  MICRO: {
    label: 'Donation',
    accent: palette.accent,
    glow: 'rgba(73,223,100,0.35)',
    haptic: 'light',
  },
  MAJOR: {
    label: 'Big Drop',
    accent: palette.gold,
    glow: 'rgba(241,170,5,0.45)',
    haptic: 'medium',
  },
  WHALE: {
    label: 'WHALE ALERT',
    accent: palette.tifany,
    glow: 'rgba(104,251,221,0.55)',
    haptic: 'heavy',
  },
} as const;
