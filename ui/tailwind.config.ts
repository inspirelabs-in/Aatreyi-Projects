import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Light theme tokens
        ink: "#f6f7f9",      // page background
        panel: "#ffffff",     // cards / surfaces
        field: "#f8fafc",     // input backgrounds
        edge: "#e5e7eb",      // borders / dividers
        brand: "#2563eb",     // accent (blue-600)
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
