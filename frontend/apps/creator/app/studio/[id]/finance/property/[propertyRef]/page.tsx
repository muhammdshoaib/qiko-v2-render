"use client";

import { useParams, useSearchParams } from "next/navigation";
import { PropertyDetail } from "@/components/finance/property-detail";

export default function PropertyPage() {
  const params = useParams<{ propertyRef: string }>();
  const searchParams = useSearchParams();
  const propertyRef = decodeURIComponent(params.propertyRef);
  const unitRef = searchParams.get("unit") ?? undefined;
  const from = searchParams.get("from");
  return <PropertyDetail propertyRef={propertyRef} unitRef={unitRef} from={from} />;
}
