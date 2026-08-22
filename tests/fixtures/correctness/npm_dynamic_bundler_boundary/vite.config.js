function makeAlias() {
  throw new Error("repository configuration must not execute");
}

export default {
  resolve: {
    alias: {
      "@dynamic": makeAlias()
    }
  }
};
