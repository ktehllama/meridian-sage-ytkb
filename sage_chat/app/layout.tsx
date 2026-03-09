import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Meridian — Knowledge Base',
  description: 'Search and synthesize insights from a curated video knowledge base.',
  icons: { icon: '/favicon.svg' },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem('meridian_theme');if(t==='light')document.documentElement.dataset.theme='light';}catch(e){}` }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="preconnect" href="https://cdn.jsdelivr.net" crossOrigin="anonymous" />
        <link rel="dns-prefetch" href="https://cdn.jsdelivr.net" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="h-full bg-[#0f0f0f] text-[#f0f0f0]">{children}</body>
    </html>
  );
}
