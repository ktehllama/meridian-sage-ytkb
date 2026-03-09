'use client';

/**
 * MeridianLogo — 4 arc lines radiating from a bottom focal point,
 * like meridian lines on a globe (or waves expanding from source).
 * Ocean-to-indigo gradient. Reused in header + chat avatar.
 *
 * Pass a unique `gradientId` per usage to avoid SVG ID conflicts.
 */
interface MeridianLogoProps {
  size?: number;
  gradientId?: string;
  className?: string;
}

export default function MeridianLogo({ size = 24, gradientId = 'mlg', className }: MeridianLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
    >
      <defs>
        {/* Radial gradient: light lavender at center → blurple at edges */}
        <radialGradient id={gradientId} cx="12" cy="12" r="10" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#c4b5fd" />
          <stop offset="100%" stopColor="#6570fc" />
        </radialGradient>
      </defs>

      {/* Center dot */}
      <circle cx="12" cy="12" r="1.5" fill={`url(#${gradientId})`} />

      {/* Cardinal spokes — N S E W */}
      <line x1="12" y1="12" x2="12" y2="3.5"  stroke={`url(#${gradientId})`} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="12" x2="12" y2="20.5" stroke={`url(#${gradientId})`} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="12" x2="20.5" y2="12" stroke={`url(#${gradientId})`} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="12" x2="3.5"  y2="12" stroke={`url(#${gradientId})`} strokeWidth="1.5" strokeLinecap="round" />

      {/* Diagonal spokes — NE SE SW NW (shorter) */}
      <line x1="12" y1="12" x2="17"  y2="7"  stroke={`url(#${gradientId})`} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="12" y1="12" x2="17"  y2="17" stroke={`url(#${gradientId})`} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="12" y1="12" x2="7"   y2="17" stroke={`url(#${gradientId})`} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="12" y1="12" x2="7"   y2="7"  stroke={`url(#${gradientId})`} strokeWidth="1.2" strokeLinecap="round" />

      {/* Crossbars on cardinal spokes — subtle branches */}
      <line x1="10"  y1="6.5"  x2="14"  y2="6.5"  stroke={`url(#${gradientId})`} strokeWidth="1"   strokeLinecap="round" />
      <line x1="10"  y1="17.5" x2="14"  y2="17.5"  stroke={`url(#${gradientId})`} strokeWidth="1"   strokeLinecap="round" />
      <line x1="17.5" y1="10"  x2="17.5" y2="14"   stroke={`url(#${gradientId})`} strokeWidth="1"   strokeLinecap="round" />
      <line x1="6.5"  y1="10"  x2="6.5"  y2="14"   stroke={`url(#${gradientId})`} strokeWidth="1"   strokeLinecap="round" />
    </svg>
  );
}
