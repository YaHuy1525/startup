import type { Config } from "tailwindcss";

const config: Config = {
    content: ["./src/**/*.{ts,tsx}"],
    theme: {
        extend: {
            fontFamily: {
                sans: ["Inter", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
            },
            colors: {
                manga: {
                    bg: "#0a0a0a",
                    accent: "#e6245e",
                    gold: "#f5a623",
                },
            },
        },
    },
    plugins: [],
};

export default config;
