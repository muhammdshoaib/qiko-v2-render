"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { addTeamMember, createTeam, type Team } from "@/lib/api";

const ROLES = ["viewer", "editor", "admin"];

export default function TeamPage() {
  const [team, setTeam] = useState<Team | null>(null);
  const [owner, setOwner] = useState("");
  const [memberId, setMemberId] = useState("");
  const [role, setRole] = useState("editor");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true); setError(null);
    try { setTeam(await createTeam(owner)); } finally { setBusy(false); }
  }
  async function add() {
    setBusy(true); setError(null);
    try { setTeam(await addTeamMember(team!.team_id, memberId, role)); setMemberId(""); }
    catch { setError("Could not add member."); } finally { setBusy(false); }
  }

  return (
    <AppShell title="Team">
      <div className="mx-auto max-w-lg space-y-6">
        {!team ? (
          <Card>
            <CardHeader><CardTitle>Create your team</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5"><Label>Owner (your user id / email)</Label>
                <Input placeholder="owner@company.com" value={owner} onChange={(e) => setOwner(e.target.value)} /></div>
              <Button className="w-full" disabled={!owner || busy} onClick={create}>Create team</Button>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card>
              <CardHeader><CardTitle>Members</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(team.members).map(([uid, r]) => (
                  <div key={uid} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                    <span className="text-sm">{uid}</span>
                    <Badge variant={r === "owner" ? "default" : "muted"}>{r}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Invite a member</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5"><Label>User id / email</Label>
                  <Input placeholder="teammate@company.com" value={memberId} onChange={(e) => setMemberId(e.target.value)} /></div>
                <div className="space-y-1.5"><Label>Role</Label>
                  <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={role} onChange={(e) => setRole(e.target.value)}>
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select></div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button className="w-full" disabled={!memberId || busy} onClick={add}><UserPlus className="size-4" /> Add member</Button>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  );
}
