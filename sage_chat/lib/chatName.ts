// lib/chatName.ts
// Pure-TS extractive keyword scorer for generating chat names from a Q&A exchange.

const STOPWORDS = new Set([
  'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
  'from','up','about','into','through','during','is','are','was','were','be',
  'been','being','have','has','had','do','does','did','will','would','could',
  'should','may','might','shall','can','need','dare','ought','used',
  'i','you','he','she','it','we','they','me','him','her','us','them',
  'my','your','his','its','our','their','mine','yours','hers','ours','theirs',
  'this','that','these','those','what','which','who','whom','whose',
  'when','where','why','how','all','each','every','both','few','more',
  'most','other','some','such','no','not','only','same','so','than','too',
  'very','just','also','tell','get','make','let','like','know','think','want',
  'use','see','look','come','go','give','take','find','say','said',
]);

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length >= 4 && !STOPWORDS.has(w));
}

export function generateChatName(userMsg: string, assistantMsg: string): string {
  const userTokens = tokenize(userMsg);
  const assistantTokens = tokenize(assistantMsg.slice(0, 600));

  // Count frequency across both
  const freq = new Map<string, number>();
  for (const w of userTokens) freq.set(w, (freq.get(w) ?? 0) + 1.5); // user words boosted ×1.5
  for (const w of assistantTokens) freq.set(w, (freq.get(w) ?? 0) + 1);

  if (freq.size === 0) {
    return userMsg.slice(0, 40).trim() || 'Untitled';
  }

  // Sort by score descending, take top 4
  const top = Array.from(freq.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([w]) => w.charAt(0).toUpperCase() + w.slice(1));

  return top.join(' ');
}
