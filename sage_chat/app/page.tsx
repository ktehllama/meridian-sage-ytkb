import ChatInterface from './components/ChatInterface';

export default function Home() {
  return (
    <main className="h-[100dvh] flex flex-col overflow-hidden bg-[var(--bg-base)]">
      <ChatInterface />
    </main>
  );
}
