import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#FBF9F6",
        ink: "#2B2622",
        accent: {
          DEFAULT: "#C1622B",
          soft: "#F3E2D6",
        },
        line: "#E7E0D8",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
