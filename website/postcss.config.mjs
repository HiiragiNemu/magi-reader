const postcssConfig = {
  plugins: {
    '@tailwindcss/postcss': {
      // Keep the authored standard backdrop-filter declaration. The production
      // optimizer otherwise emits only an unsupported WebKit-prefixed form in
      // current Chromium, removing the target whole-page low-fi diffusion.
      optimize: false,
    },
  },
};

export default postcssConfig;
