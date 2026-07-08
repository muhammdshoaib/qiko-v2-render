"use client";
import { Toaster as Sonner, type ToasterProps } from "sonner";

// Qiko is dark-theme-only today (no next-themes provider is set up anywhere in this app), so this
// is hardcoded rather than pulling in a theme-detection dependency just for one component.
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
