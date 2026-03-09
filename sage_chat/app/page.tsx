import ChatInterface from './components/ChatInterface';

export default function Home() {
  return (
    <main className="h-screen flex flex-col overflow-hidden bg-[var(--bg-base)]">
      <ChatInterface />
    </main>
  );
}
