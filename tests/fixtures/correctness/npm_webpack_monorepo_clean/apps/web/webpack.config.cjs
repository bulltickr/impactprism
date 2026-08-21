const path = require("path");

module.exports = {
  resolve: {
    alias: [
      {
        find: "@ui/*",
        replacement: path.resolve(__dirname, "../../packages/ui/src/*")
      }
    ]
  }
};
