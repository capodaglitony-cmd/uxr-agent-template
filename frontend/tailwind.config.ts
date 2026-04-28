import type { Config } from "tailwindcss";

// Color tokens lifted from the source lab widget so the cloud
// deployment matches the dev experience visually. Practitioners can
// override `accent` via config/profile.yaml -> branding.accent_color.

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#080c14",
        surface: "#0d1624",
        surface2: "#111c30",
        border1: "#1e2e46",
        border2: "#2a3a56",
        textmain: "#c8d4e8",
        textmuted: "#5a6a84",
        textdim: "#3a4a62",
        accent: "#2a5a8a",
        "accent-bright": "#3a7ab8",
        "accent-glow": "#1e4a72",
        "ok": "#1a4a2a",
        "ok-text": "#4aaa6a",
        "err": "#4a1a1a",
        "err-text": "#aa4a4a",
        "warn": "#3a2a0a",
        "warn-text": "#c8941a",
      },
      fontFamily: {
        mono: ['"SF Mono"', '"Fira Code"', '"Cascadia Code"', "monospace"],
        sans: ["-apple-system", '"Helvetica Neue"', "sans-serif"],
      },
      keyframes: {
        pulse_dot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
      },
      animation: {
        "pulse-dot": "pulse_dot 1s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
