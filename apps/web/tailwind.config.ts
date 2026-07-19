import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0F14",
        panel: "#121A24",
        border: "#233044",
        primary: "#E6EDF7",
        muted: "#8B9BB4",
        bullish: "#22C55E",
        bearish: "#EF4444",
        warning: "#F59E0B",
        neutral: "#64748B",
        aiAccent: "#8B5CF6",
        info: "#38BDF8",
      },
    },
  },
  plugins: [],
};

export default config;
