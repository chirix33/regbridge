import { ThinkingOrb, type OrbSize, type OrbState } from "thinking-orbs";

type ThinkingStatusProps = {
  label: string;
  state?: OrbState;
  size?: OrbSize;
  speed?: number;
  dark?: boolean;
  paused?: boolean;
  className?: string;
};

export function ThinkingStatus({
  label,
  state = "working",
  size = 20,
  speed = 1,
  dark = false,
  paused = false,
  className = "",
}: ThinkingStatusProps) {
  const statusClass = ["thinking-status", size === 64 ? "thinking-status-large" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={statusClass} role="status" aria-live="polite">
      <ThinkingOrb
        state={state}
        size={size}
        speed={speed}
        paused={paused}
        theme={dark ? "dark" : "light"}
        aria-hidden="true"
      />
      <span>{label}</span>
    </span>
  );
}
