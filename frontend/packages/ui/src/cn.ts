import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind-aware class merge. Lives in its own file so the component modules can use it without
 *  importing from index, which re-exports them and would make the graph circular. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
