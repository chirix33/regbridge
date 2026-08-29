import { ShieldAlert } from "iconoir-react";

interface DisclaimerProps {
  text: string;
}

export function Disclaimer({ text }: DisclaimerProps) {
  return (
    <aside className="disclaimer" aria-label="Research prototype disclaimer">
      <ShieldAlert aria-hidden="true" width={22} height={22} />
      <p>{text}</p>
    </aside>
  );
}
