import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export { toTitleFromSlug } from "./stringUtils";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
