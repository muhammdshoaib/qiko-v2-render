import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Terms of Service | Qiko",
  description: "The terms that govern business use of the Qiko service.",
};

const EFFECTIVE_DATE = "24 July 2026";

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      lastUpdated={EFFECTIVE_DATE}
      intro={
        <p>
          These Terms of Service (the "Terms") are a binding agreement between Qiko AI Labs FZCO
          and the business customer that accepts them. They govern access to and use of Qiko&apos;s
          websites, platform, AI digital workers and related services (together, the "Service").
        </p>
      }
    >
      <LegalSection heading="1. Qiko and business scope">
        <p>
          Qiko AI Labs FZCO ("Qiko", "we", "us" or "our") is located at IFZA Business Park, DDP,
          PO Box 342001, Dubai, United Arab Emirates. The Service is offered only for
          business and professional use, not for personal, family or household use.
        </p>
        <p>
          If you accept these Terms for an organisation, you confirm that you have authority to bind
          it. "Customer" and "you" mean that organisation. If you do not have that authority, do not
          accept these Terms or use the Service for it.
        </p>
      </LegalSection>

      <LegalSection heading="2. Electronic acceptance and Orders">
        <p>
          You accept these Terms by selecting an acceptance box, creating an account, signing an
          order form or other ordering document (an "Order"), or using the Service after being given
          access to these Terms. Electronic acceptance and signatures have the same effect as written
          acceptance to the extent permitted by law.
        </p>
        <p>
          An Order may identify the plan, authorised users, fees, term and additional commercial
          terms. If an Order conflicts with these Terms, the Order controls only for that conflict.
        </p>
      </LegalSection>

      <LegalSection heading="3. Accounts and authorised users">
        <p>
          Customer must provide accurate account information, keep it current, protect credentials,
          use reasonable access controls and notify support{"@"}qiko.ai promptly of suspected unauthorised
          access. Customer is responsible for its authorised users, their use of the Service and all
          activity under its accounts, except to the extent caused by Qiko&apos;s breach of these Terms.
        </p>
        <p>
          Accounts may not be shared outside Customer&apos;s authorised workforce. Customer must ensure
          each user complies with these Terms and must promptly remove access that is no longer needed.
        </p>
      </LegalSection>

      <LegalSection heading="4. Service access, plans and licence">
        <p>
          Subject to these Terms and any Order, Qiko grants Customer a limited, non-exclusive,
          non-transferable, non-sublicensable right during the applicable service term to access and
          use the Service for Customer&apos;s internal business purposes. Plan features and limits are
          those stated in the applicable Order or in-product plan description.
        </p>
        <p>
          Customer may not sell, rent or provide the Service as a service bureau, except where an
          Order expressly permits Customer to deploy a digital worker to its own intended audience.
          Qiko may improve or change the Service over time. Any service level commitment applies only
          if expressly stated in an Order.
        </p>
      </LegalSection>

      <LegalSection heading="5. Acceptable use">
        <p>Customer and its users must not:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>use the Service unlawfully or to violate another person&apos;s rights;</li>
          <li>submit content without the rights, notices and permissions required to process it;</li>
          <li>generate or distribute malicious, fraudulent, deceptive, discriminatory or abusive material;</li>
          <li>facilitate weapons, exploitation, illegal surveillance or other serious harm;</li>
          <li>probe, scan, disrupt or bypass security, authentication, rate limits or access controls;</li>
          <li>introduce malware or use automated means that impose an unreasonable load;</li>
          <li>reverse engineer or attempt to discover non-public source code, models or system prompts, except where law prohibits this restriction;</li>
          <li>use output or the Service to build or train a competing product or foundation model without Qiko&apos;s written permission; or</li>
          <li>remove proprietary notices or misrepresent AI-generated material as independently verified fact.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="6. Customer Content and processing permission">
        <p>
          "Customer Content" means documents, messages, instructions, approved answers, configurations
          and other material submitted to or generated for Customer through the Service. As between
          the parties, Customer retains its rights in Customer Content.
        </p>
        <p>
          Customer grants Qiko and its contracted providers a limited, worldwide, non-exclusive right
          to host, copy, transmit, retrieve, transform, embed and otherwise process Customer Content
          only as needed to provide, secure, support and maintain the Service, comply with law and
          enforce these Terms. This includes tenant-scoped retrieval-augmented generation and reuse of
          Customer-approved answers for that tenant&apos;s retrieval experience. It does not grant Qiko a
          right to use Customer Content to fine-tune third-party foundation models.
        </p>
        <p>
          Customer is responsible for Customer Content, its lawfulness and the instructions it gives
          Qiko. Customer must not submit special-category, highly sensitive or regulated data unless
          the parties have expressly agreed appropriate terms and safeguards.
        </p>
      </LegalSection>

      <LegalSection heading="7. Qiko intellectual property">
        <p>
          Qiko and its licensors retain all rights in the Service, software, interfaces, workflows,
          documentation, models, designs and technology, including all related copyright, database,
          trade secret and other intellectual property rights. Except for the limited right in section
          4, no right is granted to Customer by implication or otherwise.
        </p>
        <p>
          Qiko names, logos and product branding are used as Qiko trademarks, service marks or other
          identifiers. These Terms do not grant a licence to use them. Third-party names and marks
          belong to their respective owners.
        </p>
      </LegalSection>

      <LegalSection heading="8. Feedback">
        <p>
          If Customer voluntarily gives ideas or feedback about the Service, Customer grants Qiko a
          perpetual, irrevocable, worldwide, royalty-free right to use and incorporate that feedback
          without restriction or payment. Qiko will not identify Customer publicly as the source
          without permission.
        </p>
      </LegalSection>

      <LegalSection heading="9. AI output and human review">
        <p>
          The Service uses probabilistic AI systems. Outputs may be incomplete, inaccurate, outdated,
          offensive or similar to outputs produced for others. They are not guaranteed to be unique,
          correct or fit for a particular purpose. Customer must assess outputs, use appropriately
          qualified human review and test a digital worker before and during deployment.
        </p>
        <p>
          The Service does not provide legal, medical, financial, tax, employment or other professional
          advice. Customer must not rely on output as a substitute for professional judgment or use it
          as the sole basis for decisions that produce legal or similarly significant effects on a person.
        </p>
      </LegalSection>

      <LegalSection heading="10. Confidentiality">
        <p>
          "Confidential Information" means non-public information disclosed by one party that is
          identified as confidential or should reasonably be understood as confidential. It excludes
          information lawfully known without restriction, independently developed, publicly available
          without breach, or rightfully received from another source.
        </p>
        <p>
          The receiving party will use Confidential Information only to perform or receive the Service,
          protect it with reasonable care and disclose it only to personnel and providers who need it
          and are bound by confidentiality duties. A legally compelled disclosure is permitted if the
          receiving party gives notice where lawful and reasonable assistance at the discloser&apos;s cost.
        </p>
      </LegalSection>

      <LegalSection heading="11. Third-party providers and integrations">
        <p>
          Qiko relies on contracted infrastructure, AI, communications, security and payment providers.
          Some features may let Customer connect a third-party service or redirect to a third-party
          hosted experience. Customer authorises the exchange of information necessary for a connection
          it enables. Third-party services are governed by their own terms, and Qiko is not responsible
          for them except to the extent Qiko is legally responsible for its providers.
        </p>
      </LegalSection>

      <LegalSection heading="12. Fees and taxes">
        <p>
          Fees, invoicing, payment timing, renewal and cancellation apply only as stated in an Order.
          Unless an Order says otherwise, fees exclude applicable taxes, duties and levies. Customer is
          responsible for those amounts other than taxes based on Qiko&apos;s net income. Customer will
          provide valid tax information reasonably requested by Qiko. Nothing in these Terms by itself
          creates a recurring paid subscription or makes a checkout feature available.
        </p>
      </LegalSection>

      <LegalSection heading="13. Suspension">
        <p>
          Qiko may suspend affected access where reasonably necessary to address a security threat,
          unlawful or prohibited use, material breach, non-payment under an Order, provider restriction
          or legal requirement. Where practicable, Qiko will give notice and limit the suspension to
          what is necessary. Qiko may act immediately where delay could cause harm.
        </p>
      </LegalSection>

      <LegalSection heading="14. Term and termination">
        <p>
          These Terms begin on acceptance and continue while Customer accesses the Service or an Order
          remains active. Either party may terminate for a material breach not cured within 30 days
          after written notice, or immediately if the breach cannot be cured or the other party becomes
          insolvent, subject to applicable law. Order-specific termination rights also apply.
        </p>
        <p>
          On termination, Customer&apos;s right to use the Service ends and unpaid amounts under an Order
          become due. Customer should retrieve content it needs before termination where the Service
          permits. Qiko does not promise a particular export format or post-termination deletion period
          unless agreed in an Order or data processing agreement. Sections intended by their nature to
          survive will survive, including ownership, confidentiality, disclaimers, liability and general terms.
        </p>
      </LegalSection>

      <LegalSection heading="15. Disclaimers">
        <p>
          To the fullest extent permitted by law, the Service and all outputs are provided "as is" and
          "as available". Qiko disclaims implied warranties of merchantability, satisfactory quality,
          fitness for a particular purpose, non-infringement and any warranty arising from course of
          dealing or usage. Qiko does not warrant uninterrupted or error-free operation, that all
          vulnerabilities will be prevented, or that output will be accurate or achieve Customer&apos;s goals.
        </p>
      </LegalSection>

      <LegalSection heading="16. Limitation of liability">
        <p>
          To the fullest extent permitted by law, neither party will be liable for indirect, incidental,
          special, exemplary, punitive or consequential loss, or loss of profit, revenue, goodwill,
          anticipated savings or business opportunity, arising from these Terms, even if advised that
          such loss was possible.
        </p>
        <p>
          To the fullest extent permitted by law, each party&apos;s total aggregate liability arising out
          of or relating to the Service and these Terms will not exceed the fees paid or payable by
          Customer to Qiko under the applicable Order during the 12 months immediately before the event
          giving rise to liability. If no fees were paid or payable, the cap is zero.
        </p>
        <p>
          The exclusions and cap do not apply to liability that cannot lawfully be excluded or limited,
          including fraud or fraudulent misrepresentation, wilful misconduct, death or personal injury
          caused by negligence where applicable, or Customer&apos;s payment obligations. Applicable mandatory
          law controls to the extent it requires a different result.
        </p>
      </LegalSection>

      <LegalSection heading="17. Force majeure">
        <p>
          Neither party is liable for delay or failure caused by events beyond its reasonable control,
          including natural disaster, war, civil disorder, epidemic, labour action, utility or internet
          failure, cyberattack, government action or failure of a critical provider, provided it uses
          reasonable efforts to reduce the impact. This section does not excuse payment already due.
        </p>
      </LegalSection>

      <LegalSection heading="18. Governing law and courts">
        <p>
          These Terms and any non-contractual obligation arising from them are governed by the federal
          laws of the United Arab Emirates and the laws of the Emirate of Dubai, without regard to
          conflict-of-law principles. The courts of Dubai have exclusive jurisdiction, subject to any
          mandatory rights that cannot be waived.
        </p>
      </LegalSection>

      <LegalSection heading="19. Changes, notices and contact">
        <p>
          Qiko may update these Terms to reflect legal, security, technical or service changes. Qiko
          will post the revised Terms and update the effective date, and will provide additional notice
          of material changes where required. Changes apply prospectively. If Customer does not agree,
          it must stop using the Service and may exercise any termination right in its Order.
        </p>
        <p>
          Qiko may send operational or legal notices to the account email or through the Service.
          Customer must send legal notices to support{"@"}qiko.ai and keep its contact details current.
        </p>
      </LegalSection>

      <LegalSection heading="20. General">
        <p>
          These Terms and each Order are the entire agreement about their subject and replace earlier
          discussions. Neither party relies on a statement not included in them. Customer may not assign
          them without Qiko&apos;s prior written consent, except in connection with a merger or sale of
          substantially all assets if the assignee is not a competitor and assumes the obligations.
          Qiko may assign them as part of a reorganisation, merger or sale of its business.
        </p>
        <p>
          The parties are independent contractors. These Terms create no partnership, agency, fiduciary
          relationship or third-party beneficiary. Failure to enforce a right is not a waiver. If a
          provision is unenforceable, it will be limited to the minimum extent necessary and the rest
          remains effective. Headings are for convenience. "Including" means "including without limitation".
        </p>
      </LegalSection>
    </LegalPage>
  );
}
