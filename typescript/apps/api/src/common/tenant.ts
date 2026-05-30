export const TENANT_HEADER = "x-tenant-id";

export function normalizeTenant(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) {
    return "public";
  }
  return value.trim();
}
