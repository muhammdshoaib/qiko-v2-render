import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Privacy Policy | Qiko",
  description: "How Qiko collects, uses and protects personal data.",
};

// Placeholder legal copy. Intended to be reviewed and replaced by Qiko's legal counsel.
const LAST_UPDATED = "21 July 2026";

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      lastUpdated={LAST_UPDATED}
      intro={
        <p>
          This Privacy Policy explains what personal data we process when you use the Qiko platform,
          why we process it, and the choices and rights you have. It is written to be clear and easy
          to update as our Service evolves.
        </p>
      }
    >
      <LegalSection heading="Who we are">
        <p>
          Qiko is a business-to-business platform for building and running AI digital workers. For
          the personal data described here, Qiko acts as a data controller for account and platform
          data, and as a data processor for the content you and your users submit while using the
          Service. "We", "us" and "our" refer to Qiko.
        </p>
      </LegalSection>

      <LegalSection heading="Data we process">
        <p>We may process the following categories of personal data:</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>Account data: your name, work email address and organisation details;</li>
          <li>Authentication data: hashed passwords and two-factor authentication settings;</li>
          <li>Usage data: log records, device and browser information, and feature interactions;</li>
          <li>Content data: the documents, messages and configuration you provide to your workers;</li>
          <li>Billing data: subscription and payment records handled through our payment provider.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="How we use data">
        <p>We use personal data to:</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>provide, secure and maintain the Service;</li>
          <li>authenticate users and prevent fraud or abuse;</li>
          <li>respond to support requests and communicate service updates;</li>
          <li>improve and develop features, and meet our legal and regulatory obligations.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="Legal bases">
        <p>
          Where applicable data protection law requires it, we rely on one or more of the following
          legal bases: performance of our contract with you, our legitimate interests in operating
          and improving the Service, your consent (which you can withdraw at any time), and
          compliance with legal obligations.
        </p>
      </LegalSection>

      <LegalSection heading="Sharing and sub-processors">
        <p>
          We do not sell your personal data. We share it only with service providers who help us run
          the Service (for example hosting, analytics and payment providers), under contracts that
          require them to protect it, and where required by law. A current list of sub-processors is
          available on request.
        </p>
      </LegalSection>

      <LegalSection heading="Data retention and security">
        <p>
          We keep personal data only for as long as needed for the purposes described here or as
          required by law, then delete or anonymise it. We use technical and organisational measures,
          including encryption in transit, access controls and hashing of credentials, to protect
          personal data.
        </p>
      </LegalSection>

      <LegalSection heading="Cookies">
        <p>
          We use cookies and similar technologies to run the platform and understand how it is used.
          For details, see our{" "}
          <a href="/cookies" className="text-cyan-400 hover:text-cyan-300">
            Cookie Policy
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection heading="Your rights">
        <p>
          Depending on your location, you may have rights to access, correct, delete or export your
          personal data, to object to or restrict certain processing, and to withdraw consent. To
          exercise these rights, contact us using the details below. You also have the right to
          complain to your local data protection authority.
        </p>
      </LegalSection>

      <LegalSection heading="Contact">
        <p>
          For any privacy question or request, contact us at{" "}
          <a href="mailto:support@qiko.ai" className="text-cyan-400 hover:text-cyan-300">
            support@qiko.ai
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
