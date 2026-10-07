export const AUTH_MODE: "dev" | "clerk" =
  process.env.NEXT_PUBLIC_AUTH_MODE === "clerk" ? "clerk" : "dev";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** localStorage key remembering the last organization a user opened. */
export const LAST_ORG_KEY = "contraict.lastOrg";
