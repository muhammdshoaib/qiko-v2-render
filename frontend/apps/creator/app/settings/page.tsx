"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { ArrowRight, Cookie, CreditCard, KeyRound, Link2, Search, Settings2, Shield, ShieldCheck, Trash2, User, UserPlus, Users } from "lucide-react";
import { Badge, Button, Input, Label, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  ASSIGNABLE_ROLES,
  ROLE_LABELS,
  cancelInvite,
  getTeamsWebhookStatus,
  inviteUser,
  listTenantUsers,
  me,
  regenerateBackupCodes,
  removeUser,
  subscriptionStatus,
  twofaSetup,
  twofaVerify,
  updateProfile,
  updateUserRole,
  type TenantRole,
  type TenantUser,
} from "@/lib/api";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";

const SETTINGS_TABS = [
  { id: "general", label: "General", icon: Settings2 },
  { id: "team", label: "Team", icon: Users },
  { id: "security", label: "Security", icon: Shield },
] as const;

function SettingsCard({ icon: Icon, iconColor, title, children }: {
  icon: React.ComponentType<{ className?: string }>; iconColor: string; title: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] py-6">
      <div className="px-6">
        <div className="flex items-center gap-2 font-semibold leading-none text-white">
          <Icon className={cn("size-5", iconColor)} /> {title}
        </div>
      </div>
      <div className="px-6 pt-6">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof SETTINGS_TABS)[number]["id"]>("general");
  const account = useQuery({ queryKey: ["me"], queryFn: me });

  return (
    <AppShell title="Settings">
      <div className="p-6 lg:p-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-8">
            <h1 className="mb-2 text-2xl font-bold lg:text-3xl" style={{
              fontFamily: "var(--font-display)",
              background: "linear-gradient(135deg, #fff 0%, #6366F1 50%, #22D3EE 100%)",
              WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent",
            }}>
              Settings
            </h1>
            <p className="text-slate-400">Manage your account and preferences</p>
          </div>

          <div className="mb-6 inline-flex h-12 w-fit items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.015] p-1.5">
            {SETTINGS_TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined}
                className={cn("inline-flex h-full items-center justify-center gap-1.5 rounded-xl border px-6 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                  tab === id ? "border-cyan-500/30 bg-cyan-500/10 text-white" : "border-transparent text-slate-300 hover:text-white")}>
                <Icon className={cn("size-4", tab === id ? "text-cyan-400" : "text-slate-500")} /> {label}
              </button>
            ))}
          </div>

          {tab === "general" && (
            <div className="space-y-6">
              <div>
                <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
                  <User className="size-6 text-cyan-400" /> General Settings
                </h2>
                <p className="mt-1 text-slate-400">Manage your account and preferences.</p>
              </div>

              {account.data && (
                <ProfilePanel key={account.data.id} email={account.data.email}
                  initialName={account.data.name ?? account.data.email.split("@")[0]} />
              )}

              <BillingCard />

              <IntegrationsCard />

              <SettingsCard icon={KeyRound} iconColor="text-amber-400" title="Change Password">
                <p className="mb-4 text-sm text-slate-400">Update your account password securely.</p>
                <Button onClick={() => (window.location.href = "/forgot-password")}
                  className="w-full border-0 bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-lg shadow-violet-900/30 hover:shadow-violet-800/50">
                  <KeyRound className="size-4" /> Change Password <ArrowRight className="size-4" />
                </Button>
              </SettingsCard>

              <SettingsCard icon={Cookie} iconColor="text-cyan-400" title="Privacy choices">
                <p className="mb-4 text-sm text-slate-400">Review or withdraw optional analytics and marketing consent.</p>
                <ConsentSettingsButton className="inline-flex min-h-10 w-full items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 text-sm font-medium text-cyan-200 hover:bg-cyan-500/20" />
              </SettingsCard>
            </div>
          )}

          {tab === "team" && <TeamPanel />}
          {tab === "security" && <SecurityPanel />}
        </div>
      </div>
    </AppShell>
  );
}

function ProfilePanel({ email, initialName }: { email: string; initialName: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState(initialName);
  const save = useMutation({
    mutationFn: () => updateProfile(name.trim()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  const unchanged = name.trim() === initialName.trim() || name.trim().length === 0;
  return (
    <SettingsCard icon={User} iconColor="text-[#6366F1]" title="Profile">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (!unchanged) save.mutate(); }}>
        <div>
          <Label htmlFor="profile-name" className="text-sm text-slate-400">Name</Label>
          <Input id="profile-name" value={name} maxLength={255} placeholder="Your name"
            onChange={(e) => setName(e.target.value)} className="mt-1" />
        </div>
        <div>
          <Label className="text-sm text-slate-400">Email</Label>
          <p className="mt-1 text-white">{email}</p>
        </div>
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={unchanged || save.isPending}
            className="border-0 bg-gradient-to-r from-indigo-600 to-cyan-600 text-white shadow-lg shadow-indigo-900/30 disabled:opacity-50">
            {save.isPending ? "Saving\u2026" : "Save changes"}
          </Button>
          {save.isSuccess && <span className="text-xs text-emerald-400">Saved</span>}
          {save.isError && <span className="text-xs text-red-400">Couldn&apos;t save. Please try again.</span>}
        </div>
      </form>
    </SettingsCard>
  );
}

function BillingCard() {
  const sub = useQuery({ queryKey: ["subscription"], queryFn: subscriptionStatus, retry: false });
  const planLabel = sub.data?.plan
    ? sub.data.plan.charAt(0).toUpperCase() + sub.data.plan.slice(1)
    : sub.data?.status === "active" ? "Active" : "Basic";
  return (
    <SettingsCard icon={CreditCard} iconColor="text-emerald-400" title="Billing">
      <p className="mb-3 text-sm text-slate-400">Manage your subscription and payment methods.</p>
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-300">
        Current plan: <Badge variant="success">{sub.isLoading ? "\u2026" : planLabel}</Badge>
        {sub.data?.cancel_at_period_end && <span className="text-xs text-amber-400">(cancels at period end)</span>}
      </div>
      <Button onClick={() => (window.location.href = "/billing")}
        className="w-full border-0 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white shadow-lg shadow-emerald-900/30 hover:shadow-emerald-800/50">
        <CreditCard className="size-4" /> Manage billing <ArrowRight className="size-4" />
      </Button>
    </SettingsCard>
  );
}

function IntegrationsCard() {
  const teams = useQuery({ queryKey: ["teams-webhook"], queryFn: getTeamsWebhookStatus, retry: false });
  return (
    <SettingsCard icon={Link2} iconColor="text-cyan-400" title="Integrations">
      <p className="mb-4 text-sm text-slate-400">
        Connect Qiko to your tools. Per-worker connections (voice, Calendly, Salesforce) live in each worker&apos;s Connections tab.
      </p>
      <div className="mb-4 flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5">
        <span className="text-sm text-slate-200">Microsoft Teams notifications</span>
        <Badge variant={teams.data?.connected ? "success" : "muted"}>
          {teams.isLoading ? "\u2026" : teams.data?.connected ? "Connected" : "Not connected"}
        </Badge>
      </div>
      <Button onClick={() => (window.location.href = "/workers")}
        className="w-full border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30 hover:shadow-cyan-800/50">
        <Link2 className="size-4" /> Manage worker connections <ArrowRight className="size-4" />
      </Button>
    </SettingsCard>
  );
}

function SecurityPanel() {
  const qc = useQueryClient();
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const [secret, setSecret] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [currentCode, setCurrentCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const enabled = account.data?.twofa_enabled === true;

  async function start() {
    setBusy(true); setError(null);
    try {
      const r = await twofaSetup();
      setSecret(r.secret);
      setQr(await QRCode.toDataURL(r.provisioning_uri, { width: 192, margin: 1 }));
    } catch {
      setError("2FA setup is unavailable. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true); setError(null);
    try {
      const result = await twofaVerify(secret!, code, password);
      setBackupCodes(result.backup_codes);
      void qc.invalidateQueries({ queryKey: ["me"] });
    } catch {
      setError("Verification failed. Check the code and your password, then retry.");
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    setBusy(true); setError(null);
    try {
      const result = await regenerateBackupCodes(password, currentCode);
      setBackupCodes(result.backup_codes);
    } catch {
      setError("Backup code regeneration failed.");
    } finally {
      setBusy(false);
    }
  }

  if (account.isLoading) return <p role="status" className="text-sm text-slate-400">Loading security status...</p>;
  if (account.isError) return <p role="alert" className="text-sm text-red-400">Security status unavailable.</p>;

  return (
    <SettingsCard icon={Shield} iconColor="text-cyan-400" title="Two-factor authentication">
      <p className="mb-4 text-sm text-slate-400">
        {enabled
          ? "2FA is active. Use your authenticator app or a backup code when you sign in."
          : "Add an extra layer of security. Once enabled, you will need a code from your authenticator app at sign in."}
      </p>
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
      {backupCodes.length > 0 ? (
        <div className="space-y-4">
          <p className="text-sm font-medium text-white">Save these one-time backup codes now. They will not be shown again.</p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">{backupCodes.map((c) => <li key={c} className="rounded-lg border border-white/10 bg-white/[0.03] p-2 font-mono text-sm text-slate-200">{c}</li>)}</ul>
          <Button onClick={() => window.location.assign("/login")} className="w-full border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30">
            I&apos;ve saved these codes, sign in
          </Button>
        </div>
      ) : enabled ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-emerald-400"><ShieldCheck className="size-4" /> 2FA is active on your account.</div>
          <div className="space-y-2">
            <Label className="text-sm text-slate-400">Current password</Label>
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label className="text-sm text-slate-400">Current authenticator code</Label>
            <Input inputMode="numeric" maxLength={6} value={currentCode} onChange={(e) => setCurrentCode(e.target.value.replace(/\D/g, ""))} />
          </div>
          <Button onClick={regenerate} disabled={busy || !password || currentCode.length !== 6} className="w-full border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30 disabled:opacity-50">
            {busy ? "Generating..." : "Generate new backup codes"}
          </Button>
        </div>
      ) : !secret ? (
        <Button onClick={start} disabled={busy} className="w-full border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30">
          {busy ? "Preparing..." : "Enable 2FA"}
        </Button>
      ) : (
        <div className="space-y-5">
          {qr && (
            <div className="flex justify-center rounded-xl border border-white/10 bg-white/[0.05] p-4">
              <img src={qr} alt="Authenticator QR code" className="size-48 rounded-md" />
            </div>
          )}
          <div className="space-y-2">
            <Label className="text-sm text-slate-400">Current password</Label>
            <Input id="security-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="flex flex-col items-center gap-3">
            <Label htmlFor="security-code" className="text-sm font-medium text-white">Verification code</Label>
            <Input id="security-code" inputMode="numeric" maxLength={6} placeholder="123456" autoFocus value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="w-32 text-center text-lg tracking-[0.3em]" />
          </div>
          <Button onClick={verify} disabled={code.length !== 6 || !password || busy} className="w-full border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30 disabled:opacity-50">
            {busy ? "Verifying..." : "Verify & enable 2FA"}
          </Button>
        </div>
      )}
    </SettingsCard>
  );
}

const SELECT_CLS =
  "h-9 rounded-lg border border-white/10 bg-white/[0.03] px-3 text-sm text-slate-200 transition-colors " +
  "focus-visible:border-cyan-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 " +
  "disabled:cursor-not-allowed disabled:opacity-50 [&>option]:bg-[#0b0e16] [&>option]:text-slate-200";

function roleBadgeVariant(role: TenantRole): "default" | "success" | "muted" {
  if (role === "owner" || role === "admin") return "default";
  if (role === "editor") return "success";
  return "muted";
}

function TeamPanel() {
  const qc = useQueryClient();
  const account = useQuery({ queryKey: ["me"], queryFn: me });
  const canManage = account.data?.role === "owner" || account.data?.role === "admin";

  const teamQuery = useQuery({ queryKey: ["tenant-users"], queryFn: listTenantUsers });
  const users = useMemo(() => teamQuery.data?.users ?? [], [teamQuery.data]);
  const pending = useMemo(() => teamQuery.data?.pending ?? [], [teamQuery.data]);

  const [subTab, setSubTab] = useState<"accepted" | "pending">("accepted");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | TenantRole>("all");
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Exclude<TenantRole, "owner">>("viewer");
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["tenant-users"] });

  const inviteMut = useMutation({
    mutationFn: () => inviteUser(inviteEmail.trim(), inviteRole),
    onSuccess: () => { setInviteEmail(""); setInviteRole("viewer"); setShowInvite(false); setError(null); setSubTab("pending"); invalidate(); },
    onError: () => setError("Could not send the invite. Check the email and try again."),
  });
  const roleMut = useMutation({
    mutationFn: (v: { userId: string; role: Exclude<TenantRole, "owner"> }) => updateUserRole(v.userId, v.role),
    onSuccess: () => { setError(null); invalidate(); },
    onError: () => setError("Could not update the role."),
  });
  const removeMut = useMutation({
    mutationFn: (userId: string) => removeUser(userId),
    onSuccess: () => { setError(null); invalidate(); },
    onError: () => setError("Could not remove the user."),
  });
  const cancelMut = useMutation({
    mutationFn: (email: string) => cancelInvite(email),
    onSuccess: () => { setError(null); invalidate(); },
    onError: () => setError("Could not cancel the invite."),
  });

  const q = search.trim().toLowerCase();
  const filteredUsers = users.filter((u) =>
    (roleFilter === "all" || u.role === roleFilter) &&
    (!q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)));
  const filteredPending = pending.filter((p) =>
    (roleFilter === "all" || p.role === roleFilter) &&
    (!q || p.email.toLowerCase().includes(q)));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-semibold text-white">
            <Users className="size-6 text-cyan-400" /> Team Access
          </h2>
          <p className="mt-1 text-slate-400">Invite users and assign roles: User, Creator, or Admin.</p>
        </div>
        {canManage && (
          <Button onClick={() => { setShowInvite((v) => !v); setError(null); }} aria-expanded={showInvite}
            className="border-0 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-900/30">
            <UserPlus className="size-4" /> Add Team
          </Button>
        )}
      </div>

      {showInvite && canManage && (
        <SettingsCard icon={UserPlus} iconColor="text-[#6366F1]" title="Invite a user">
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(e) => { e.preventDefault(); if (inviteEmail.trim()) inviteMut.mutate(); }}>
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="invite-email">Email</Label>
              <Input id="invite-email" type="email" placeholder={"teammate" + "@" + "company.com"}
                value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-role">Role</Label>
              <select id="invite-role" className={cn(SELECT_CLS, "w-full sm:w-40")}
                value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Exclude<TenantRole, "owner">)}>
                {ASSIGNABLE_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <Button type="submit" disabled={!inviteEmail.trim() || inviteMut.isPending}>
              <UserPlus className="size-4" /> Send invite
            </Button>
          </form>
        </SettingsCard>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      <div className="inline-flex h-11 w-fit items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.015] p-1.5">
        {([["accepted", "Accepted", users.length], ["pending", "Pending", pending.length]] as const).map(([id, label, count]) => (
          <button key={id} onClick={() => setSubTab(id)} aria-current={subTab === id ? "page" : undefined}
            className={cn("inline-flex h-full items-center justify-center rounded-xl border px-5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
              subTab === id ? "border-cyan-500/30 bg-cyan-500/10 text-white" : "border-transparent text-slate-300 hover:text-white")}>
            {label} ({count})
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
          <Input aria-label="Search by name or email" placeholder="Search by name or email"
            value={search} onChange={(e) => setSearch(e.target.value)}
            className="border-white/10 bg-white/[0.03] pl-9 text-slate-200" />
        </div>
        <select aria-label="Filter by role" className={cn(SELECT_CLS, "w-full sm:w-44")}
          value={roleFilter} onChange={(e) => setRoleFilter(e.target.value as "all" | TenantRole)}>
          <option value="all">All roles</option>
          {(Object.keys(ROLE_LABELS) as TenantRole[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </select>
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wide text-slate-500">
              <th scope="col" className="px-4 py-3 font-medium">Name</th>
              <th scope="col" className="px-4 py-3 font-medium">Email</th>
              <th scope="col" className="px-4 py-3 font-medium">Role</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {teamQuery.isLoading && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">Loading team...</td></tr>
            )}
            {teamQuery.isError && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-destructive">Could not load the team.</td></tr>
            )}
            {!teamQuery.isLoading && !teamQuery.isError && subTab === "accepted" && (
              filteredUsers.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">No users match your filters.</td></tr>
              ) : filteredUsers.map((u) => (
                <AcceptedRow key={u.id} user={u} canManage={!!canManage}
                  onRole={(role) => roleMut.mutate({ userId: u.id, role })}
                  onRemove={() => { if (window.confirm(`Remove ${u.name} from the team?`)) removeMut.mutate(u.id); }}
                  busy={roleMut.isPending || removeMut.isPending} />
              ))
            )}
            {!teamQuery.isLoading && !teamQuery.isError && subTab === "pending" && (
              filteredPending.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">No pending invites.</td></tr>
              ) : filteredPending.map((p) => (
                <tr key={p.email} className="border-b border-white/[0.04] last:border-0">
                  <td className="px-4 py-3 text-slate-400">Invited</td>
                  <td className="px-4 py-3 text-white">{p.email}</td>
                  <td className="px-4 py-3"><Badge variant={roleBadgeVariant(p.role)}>{p.role_label}</Badge></td>
                  <td className="px-4 py-3 text-right">
                    {canManage && (
                      <button type="button" aria-label={`Cancel invite for ${p.email}`}
                        onClick={() => cancelMut.mutate(p.email)} disabled={cancelMut.isPending}
                        className="inline-flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/60 disabled:opacity-50">
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AcceptedRow({ user, canManage, onRole, onRemove, busy }: {
  user: TenantUser; canManage: boolean;
  onRole: (role: Exclude<TenantRole, "owner">) => void; onRemove: () => void; busy: boolean;
}) {
  const editable = canManage && !user.is_owner;
  return (
    <tr className="border-b border-white/[0.04] last:border-0">
      <td className="px-4 py-3 font-medium text-white">{user.name}</td>
      <td className="px-4 py-3 text-slate-300">{user.email}</td>
      <td className="px-4 py-3">
        {editable ? (
          <select aria-label={`Change role for ${user.name}`} className={cn(SELECT_CLS, "w-36")}
            value={user.role} disabled={busy}
            onChange={(e) => onRole(e.target.value as Exclude<TenantRole, "owner">)}>
            {ASSIGNABLE_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        ) : (
          <Badge variant={roleBadgeVariant(user.role)}>{user.role_label}</Badge>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {canManage && !user.is_owner && (
          <button type="button" aria-label={`Remove ${user.name}`} onClick={onRemove} disabled={busy}
            className="inline-flex size-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/60 disabled:opacity-50">
            <Trash2 className="size-4" />
          </button>
        )}
      </td>
    </tr>
  );
}
