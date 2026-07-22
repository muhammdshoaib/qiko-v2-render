import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Cookie Policy | Qiko",
  description: "How and why Qiko uses cookies and similar technologies.",
};

// Placeholder legal copy. Intended to be reviewed and replaced by Qiko's legal counsel.
const LAST_UPDATED = "21 July 2026";

export default function CookiesPage() {
  return (
    <LegalPage
      title="Cookie Policy"
      lastUpdated={LAST_UPDATED}
      intro={
        <p>
          This Cookie Policy explains what cookies are, which ones the Qiko platform uses, and how
          you can manage them. It should be read alongside our{" "}
          <a href="/privacy" className="text-cyan-400 hover:text-cyan-300">
            Privacy Policy
          </a>
          .
        </p>
      }
    >
      <LegalSection heading="Who we are">
        <p>
          Qiko is a business-to-business platform for building and running AI digital workers. This
          policy covers the cookies set when you use our website and application.
        </p>
      </LegalSection>

      <LegalSection heading="What cookies are">
        <p>
          Cookies are small text files placed on your device when you visit a website. They are
          widely used to make sites work, to remember your preferences, and to provide information to
          the site owner. Similar technologies such as local storage are covered by this policy too.
        </p>
      </LegalSection>

      <LegalSection heading="Cookies we use">
        <p>We group the cookies we use into the following categories:</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            Essential cookies: required to sign you in, keep your session secure and remember basic
            settings. The Service cannot work properly without these.
          </li>
          <li>
            Analytics cookies: help us understand how the platform is used so we can improve it.
            These are only used where permitted.
          </li>
          <li>
            Preference cookies: remember choices you make, such as interface settings, to give you a
            more consistent experience.
          </li>
        </ul>
      </LegalSection>

      <LegalSection heading="Managing cookies">
        <p>
          You can control and delete cookies through your browser settings, and you can set most
          browsers to refuse cookies or alert you when they are being set. Please note that blocking
          essential cookies may stop parts of the Service from working.
        </p>
      </LegalSection>

      <LegalSection heading="Your rights">
        <p>
          Where the law requires consent for non-essential cookies, we will ask for it and you can
          change your choice at any time. For more on how we handle personal data, and the rights you
          have, see our{" "}
          <a href="/privacy" className="text-cyan-400 hover:text-cyan-300">
            Privacy Policy
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection heading="Contact">
        <p>
          If you have any questions about our use of cookies, contact us at{" "}
          <a href="mailto:support@qiko.ai" className="text-cyan-400 hover:text-cyan-300">
            support@qiko.ai
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
