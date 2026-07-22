import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "Cascadia Code", "Fira Code", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        bg: "#0B0E14",
        panel: "#151924",
        border: "#1E2A3A",
        primary: "#E6EDF7",
        muted: "#8B9BB4",
        bullish: "#10B981",
        bearish: "#F43F5E",
        warning: "#F59E0B",
        neutral: "#64748B",
        aiAccent: "#8B5CF6",
        info: "#00F0FF",
      },
    },
  },
  plugins: [],
};

export default config;