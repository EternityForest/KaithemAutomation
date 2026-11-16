const result = await Bun.build({
  entrypoints: ["./index.html"],
  outdir: "./dist",
  target: "browser",
  format: "esm",
  splitting: true,
  minify: true,
  sourcemap: "linked",
});

if (!result.success) {
  console.error("Build failed:", result.logs);
  process.exit(1);
}
