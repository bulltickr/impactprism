export async function loadRuntime() {
  return import("runtime-loader");
}

const packageName = "runtime-loader";
export function loadByVariable() {
  return import(packageName);
}
