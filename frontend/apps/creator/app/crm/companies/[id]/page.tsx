"use client";

import { useParams } from "next/navigation";
import { CrmCompanyPage } from "@/components/crm/company-page";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <CrmCompanyPage companyId={id} />;
}
