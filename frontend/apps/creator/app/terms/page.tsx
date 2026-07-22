import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Terms of Service | Qiko",
  description: "The terms that govern your use of the Qiko platform.",
};

// Placeholder legal copy. Intended to be reviewed and replaced by Qiko's legal counsel.
const LAST_UPDATED = "21 July 2026";

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      lastUpdated={LAST_UPDATED}
      intro={
        <p>
          These Terms of Service (the "Terms") govern your access to and use of the Qiko platform
          and related services (the "Service"). Please read them carefully. By creating an account
          or using the Service, you agree to these Terms.
        </p>
      }
    >
      <LegalSection heading="Who we are">
        <p>
          Qiko provides a business-to-business platform for building, deploying and managing AI
          digital workers. Throughout these Terms, "Qiko", "we", "us" and "our" refer to the Qiko
          entity that provides the Service to your organisation.
        </p>
      </LegalSection>

      <LegalSection heading="Your account">
        <p>
          You are responsible for the activity that happens under your account and for keeping your
          login credentials secure. You must provide accurate information, promptly update it when
          it changes, and tell us straight away if you suspect any unauthorised use of your account.
        </p>
        <p>
          Accounts are intended for use by organisations and their authorised team members. You are
          responsible for the actions of the users you invite into your workspace.
        </p>
      </LegalSection>

      <LegalSection heading="Acceptable use">
        <p>You agree not to misuse the Service. In particular, you will not:</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>break any applicable law or regulation, or infringe the rights of others;</li>
          <li>upload content you do not have the right to use, or that is unlawful or harmful;</li>
          <li>attempt to disrupt, probe or gain unauthorised access to the Service or its systems;</li>
          <li>use the Service to generate content that is deceptive, abusive or unsafe.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="Your content and data">
        <p>
          You retain ownership of the data and content you provide to the Service. You grant us the
          limited rights needed to operate and improve the Service and to provide it to you. How we
          handle personal data is described in our{" "}
          <a href="/privacy" className="text-cyan-400 hover:text-cyan-300">
            Privacy Policy
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection heading="Subscriptions and fees">
        <p>
          Paid plans are billed in advance on a recurring basis unless stated otherwise in your
          order. Fees are non-refundable except where required by law. We may change our pricing on
          reasonable notice, which will take effect at your next renewal.
        </p>
      </LegalSection>

      <LegalSection heading="Availability and changes">
        <p>
          We work to keep the Service available and reliable, but we do not guarantee that it will
          be uninterrupted or error free. We may update, add to or remove features over time, and we
          may update these Terms. Where changes are material, we will give you reasonable notice.
        </p>
      </LegalSection>

      <LegalSection heading="Limitation of liability">
        <p>
          To the fullest extent permitted by law, the Service is provided on an "as is" and "as
          available" basis, and our total liability arising out of or relating to the Service is
          limited as set out in your agreement with us. Nothing in these Terms limits liability that
          cannot be limited by law.
        </p>
      </LegalSection>

      <LegalSection heading="Contact">
        <p>
          If you have any questions about these Terms, contact us at{" "}
          <a href="mailto:support@qiko.ai" className="text-cyan-400 hover:text-cyan-300">
            support@qiko.ai
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
