import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark-first palette (IDE theme is dark).
        panel: "#161b22",
        panelb: "#1c2230",
        edge: "#30363d",
        accent: "#3b82f6",
      },
    },
  },
  plugins: [],
};

export default config;
