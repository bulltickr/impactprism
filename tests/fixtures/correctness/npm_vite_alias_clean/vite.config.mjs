import path from "node:path";

export default {
  resolve: {
    alias: [
      { find: "@components", replacement: path.resolve(__dirname, "src/components") },
      { find: "@lib", replacement: "./src/lib" }
    ]
  }
};
