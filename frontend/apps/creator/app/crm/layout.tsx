import type { ReactNode } from "react";
import { redirect } from "next/navigation";

export default function CrmLayout({ children: _children }: { children: ReactNode }) {
  redirect("/studio");
}
