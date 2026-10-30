import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#EDF5F0",
          100: "#DCEBE2",
          200: "#B9D6C5",
          400: "#5C9D7A",
          600: "#286648",
          800: "#173F2D",
        },
      },
    },
  },
  plugins: [],
};

export default config;
