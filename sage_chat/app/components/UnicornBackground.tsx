'use client';

import { useEffect, useRef } from 'react';
import unicornEmbed from '../../lib/unicornEmbed';

const SNIPPET = '<div style="width:1440px;height:900px" data-us-project="qFZJmsATe1qivAJHWPuL"></div>';

export default function UnicornBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    unicornEmbed(SNIPPET, containerRef.current, { cropPx: 85 });
  }, []);

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  );
}
