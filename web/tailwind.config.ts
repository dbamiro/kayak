import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0b1220", 900: "#111827", 700: "#374151", 500: "#6b7280" },
        sea: { 600: "#0284c7", 500: "#0ea5e9" },
      },
    },
  },
  plugins: [],
};
export default config;
