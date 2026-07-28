"use client";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, Input } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { adminMe, adminRoleOf, removePlatformAdmin } from "@/lib/api";

export default function AdminsPage() {
  const [email, setEmail] = useState("");
  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const lookup = useQuery({ queryKey: ["platform-admin", email], queryFn: () => adminRoleOf(email), enabled: email.includes("@") });
  const remove = useMutation({ mutationFn: () => removePlatformAdmin(email), onSuccess: () => lookup.refetch() });
  return <AppShell title="Platform Admins"><div className="mx-auto max-w-3xl space-y-5"><h1 className="text-2xl font-bold">Platform Admins</h1><p className="text-sm text-muted-foreground">Look up a platform administrator by exact email.</p><Input type="email" aria-label="Admin email" value={email} onChange={(event) => setEmail(event.target.value)} />{lookup.isError && <p role="alert" className="text-sm text-destructive">Admin lookup failed. <button className="underline" onClick={() => lookup.refetch()}>Retry</button></p>}{lookup.data && <Card><CardContent className="flex items-center justify-between py-4"><span>{lookup.data.email}</span><span>{lookup.data.role ?? "Not a platform admin"}</span></CardContent></Card>}{me.data?.role === "viewer" && <p role="status" className="text-sm text-muted-foreground">Read-only access.</p>}{me.data?.role === "super_admin" && lookup.data?.role === "viewer" && <Button variant="destructive" disabled={remove.isPending} onClick={() => window.confirm(`Remove ${email} from platform administration?`) && remove.mutate()}>Remove platform admin</Button>}{remove.isError && <p role="alert" className="text-sm text-destructive">Removal failed.</p>}</div></AppShell>;
}
