import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "bg-base": "var(--color-bg-base)",
        "bg-surface": "var(--color-bg-surface)",
        "bg-elevated": "var(--color-bg-elevated)",
        "accent-primary": "var(--color-accent-primary)",
        "accent-success": "var(--color-accent-success)",
        "accent-danger": "var(--color-accent-danger)",
        "accent-info": "var(--color-accent-info)",
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        "text-disabled": "var(--color-text-disabled)",
        border: "var(--color-border)",
      },
    },
  },
  plugins: [],
};

export default config;
