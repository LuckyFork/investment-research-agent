import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f4f1ea",
        panel: "#fbfaf7",
        line: "#d8d2c7",
        text: "#1f2937",
        muted: "#6b7280",
        accent: "#0f4c5c",
        success: "#2d6a4f",
        warning: "#b7791f",
        danger: "#b42318"
      },
      boxShadow: {
        panel: "0 10px 30px rgba(15, 23, 42, 0.06)"
      },
      fontFamily: {
        display: ["IBM Plex Sans", "ui-sans-serif", "system-ui"],
        body: ["Source Sans 3", "ui-sans-serif", "system-ui"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"]
      }
    }
  },
  plugins: []
} satisfies Config;
