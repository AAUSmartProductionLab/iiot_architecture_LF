import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

/** Shared button. Use `variant` instead of ad-hoc className strings. */
export function Button({ variant = "primary", className = "", ...rest }: ButtonProps) {
  return <button className={`btn ${variant} ${className}`.trim()} {...rest} />;
}

/** Small status/protocol label. `tone` maps to the shared color tokens. */
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "bad" | "accent";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

/** Online/offline dot + label, used wherever liveness is shown. */
export function StatusDot({ online }: { online: boolean }) {
  return (
    <>
      <span className={`dot ${online ? "on" : "off"}`} />
      {online ? "online" : "offline"}
    </>
  );
}
