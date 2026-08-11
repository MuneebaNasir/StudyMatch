import { useEffect, useState } from "react";

const STAGES = [
  { text: "Waking up the server...", emoji: "🐌", animationClass: "animate-snail-1" },
  { text: "Reading your query...", emoji: "🐌💨", animationClass: "animate-snail-2" },
  { text: "Matching programs...", emoji: "🐌💨💨", animationClass: "animate-snail-3" },
] as const;

interface TurboSnailLoaderProps {
  message?: string;
}

export function TurboSnailLoader({ message }: TurboSnailLoaderProps) {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (message) return;
    const timers = [
      setTimeout(() => setStage(1), 2000),
      setTimeout(() => setStage(2), 4000),
    ];
    return () => timers.forEach(clearTimeout);
  }, [message]);

  const current = message
    ? { text: message, emoji: "🐌", animationClass: "animate-snail-1" }
    : STAGES[stage];

  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center" data-testid="turbo-snail-loader">
      <span className={`text-4xl ${current.animationClass}`}>{current.emoji}</span>
      <p className="text-sm text-ink/70">{current.text}</p>
    </div>
  );
}
