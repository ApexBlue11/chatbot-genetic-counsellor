/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "var(--border-color)",
        input: "var(--border-color)",
        ring: "var(--primary)",
        background: "var(--bg-main)",
        foreground: "var(--text-primary)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "var(--bg-surface)",
          foreground: "var(--text-primary)",
        },
        muted: {
          DEFAULT: "var(--bg-body)",
          foreground: "var(--text-secondary)",
        },
        accent: {
          DEFAULT: "var(--bg-surface)",
          foreground: "var(--text-primary)",
        },
      },
    },
  },
  plugins: [],
}
