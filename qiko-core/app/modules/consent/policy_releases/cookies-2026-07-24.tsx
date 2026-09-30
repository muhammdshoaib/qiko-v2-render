import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal/LegalPage";
import { ConsentSettingsButton } from "@/components/consent/ConsentUI";

export const metadata: Metadata = {
  title: "Cookie Policy | Qiko",
  description: "The cookies and storage Qiko uses and how to manage consent.",
};

const EFFECTIVE_DATE = "24 July 2026";

export default function CookiesPage() {
  return (
    <LegalPage
      title="Cookie Policy"
      lastUpdated={EFFECTIVE_DATE}
      intro={
        <p>
          This Cookie Policy explains how Qiko AI Labs FZCO uses cookies, local storage and session
          storage on its business websites and platform. It should be read with our
          <a href="/privacy" className="ml-1 text-cyan-400 hover:text-cyan-300">Privacy Policy</a>.
        </p>
      }
    >
      <LegalSection heading="1. What these technologies are">
        <p>
          Cookies are small text records a website stores through a browser. Local storage keeps a
          named value in the browser until it is removed or expires logically. Session storage keeps
          a named value for the browser tab&apos;s session. We refer to them together as "technologies".
        </p>
      </LegalSection>

      <LegalSection heading="2. Current Qiko technologies">
        <p>
          The following technologies are necessary for requested authentication, security, consent
          choices and password reset continuity. They do not require optional consent because the
          relevant service cannot operate securely or remember the requested choice without them.
        </p>
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="min-w-[680px] w-full text-left text-xs sm:text-sm">
            <thead className="bg-slate-900 text-white">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Name</th>
                <th scope="col" className="px-4 py-3 font-semibold">Type</th>
                <th scope="col" className="px-4 py-3 font-semibold">Purpose</th>
                <th scope="col" className="px-4 py-3 font-semibold">Lifetime</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              <StorageRow name="qiko_access" type="Cookie" purpose="Authenticates the current signed-in request." lifetime="15 minutes" />
              <StorageRow name="qiko_refresh" type="Cookie" purpose="Maintains and renews an authenticated session." lifetime="14 days" />
              <StorageRow name="qiko_csrf" type="Cookie" purpose="Supports double-submit protection against cross-site request forgery." lifetime="14 days" />
              <StorageRow name="qiko.password-reset.email" type="Session storage" purpose="Carries the email entered in the requested password-reset flow between pages." lifetime="Current browser tab session, and removed after use where the flow completes" />
              <StorageRow name="qiko.consent.v1" type="Local storage" purpose="Records consent schema and policy versions, necessary/preferences/analytics/marketing choices, choice source, timestamps, logical expiry and detected GPC/DNT signals." lifetime="12-month logical expiry, then Qiko asks again" />
              <StorageRow name="qiko.consent.anonymous-id" type="Local storage" purpose="Provides a random browser identifier that the server stores only as a keyed pseudonym for anonymous consent history." lifetime="Until browser storage is cleared" />
              <StorageRow name="qiko.consent.pending-sync" type="Local storage" purpose="Temporarily retains a validated consent decision when server synchronization fails, so it can be retried." lifetime="Until synchronized, expired or superseded" />
            </tbody>
          </table>
        </div>
        <p>
          The authentication cookies are always necessary. Depending on browser and server controls,
          some cookie attributes prevent JavaScript access and limit when the browser sends them.
        </p>
      </LegalSection>

      <LegalSection heading="3. Conditional security and payment providers">
        <p>
          Cloudflare may set security cookies when its protection is active, including cookies such as
          <strong className="text-white"> __cf_bm</strong> for bot management or
          <strong className="text-white"> cf_clearance</strong> after a security challenge. These are
          necessary for network security and availability. Their presence and duration depend on the
          Cloudflare protection presented to the browser and may change with security configuration.
        </p>
        <p>
          If payment checkout is enabled and a user chooses to start it, Qiko redirects the user to a
          Stripe-hosted page. Stripe may then use cookies or similar technologies on its domain for
          checkout, fraud prevention, security and payment processing under Stripe&apos;s own notices. Qiko
          does not load Stripe checkout merely because a user visits Qiko.
        </p>
      </LegalSection>

      <LegalSection heading="4. Optional categories">
        <ul className="list-disc space-y-2 pl-6">
          <li><strong className="text-white">Necessary:</strong> always on for core functionality, security and remembered consent. This category cannot be switched off in Qiko.</li>
          <li><strong className="text-white">Preferences:</strong> remembers optional interface settings across visits when enabled.</li>
          <li><strong className="text-white">Analytics:</strong> would measure how visitors and users interact with Qiko to improve the Service. Qiko does not currently load browser analytics technologies.</li>
          <li><strong className="text-white">Marketing:</strong> would support advertising or marketing measurement. Qiko does not currently load browser marketing technologies.</li>
        </ul>
        <p>
          Preferences, analytics and marketing default to off. No script in either category loads before consent,
          and no analytics or marketing script loads today even if consent is given. A saved choice
          prepares Qiko to gate a future technology, but Qiko must update this policy before describing
          any new technology as active.
        </p>
      </LegalSection>

      <LegalSection heading="5. Consent choices and expiry">
        <p>
          The first time consent is needed, Qiko offers equally available choices to accept all,
          reject non-essential technologies or manage preferences. The consent record uses schema
          version 1 and policy version 2026-07-24. It records necessary as true, analytics and marketing
          choices, the choice source, decided, updated and expiry timestamps, and detected privacy signals.
        </p>
        <p>
          A choice expires logically after 12 months. An invalid, expired or different-policy record
          is treated as no consent: optional categories remain denied and Qiko asks again. If browser
          storage is unavailable, optional categories remain denied and the banner may reappear.
        </p>
      </LegalSection>

      <LegalSection heading="6. Global Privacy Control and Do Not Track">
        <p>
          When Qiko detects Global Privacy Control (GPC), marketing is locked off even if "Accept all"
          is selected. When Qiko detects Do Not Track (DNT), analytics and marketing default to off, but
          the user may change those choices. Browsers expose these signals inconsistently, so Qiko can
          respond only when a signal is made available to the page.
        </p>
      </LegalSection>

      <LegalSection heading="7. Change or withdraw consent">
        <p>
          Open <ConsentSettingsButton className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300" />{" "}
          at any time to change your choice. Withdrawal stops future use through Qiko&apos;s consent gates.
          Qiko removes only non-essential cookies or storage names registered to the withdrawn category.
          It never removes authentication, CSRF, password-reset or consent storage as optional cleanup.
        </p>
        <p>
          You can also delete or block technologies in browser settings. Blocking necessary cookies can
          prevent sign-in and secure features from working. Deleting <strong className="text-white">qiko.consent.v1</strong>
          causes Qiko to default optional categories to denied and ask again.
        </p>
      </LegalSection>

      <LegalSection heading="8. Changes and contact">
        <p>
          We may update this policy when technologies, providers or legal requirements change. We will
          revise the effective date and seek consent again where required. Questions can be sent to
          <a href="mailto:support%40qiko.ai" className="ml-1 text-cyan-400 hover:text-cyan-300">support{"@"}qiko.ai</a>.
        </p>
      </LegalSection>
    </LegalPage>
  );
}

function StorageRow({ name, type, purpose, lifetime }: {
  name: string;
  type: string;
  purpose: string;
  lifetime: string;
}) {
  return (
    <tr className="align-top">
      <th scope="row" className="px-4 py-3 font-mono font-medium text-cyan-300">{name}</th>
      <td className="px-4 py-3 text-slate-300">{type}</td>
      <td className="px-4 py-3 text-slate-300">{purpose}</td>
      <td className="px-4 py-3 text-slate-300">{lifetime}</td>
    </tr>
  );
}
