import type { Metadata } from "next";
import { LegalPage, LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Privacy Policy | Qiko",
  description: "How Qiko processes personal data in its business services.",
};

const EFFECTIVE_DATE = "24 July 2026";

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      lastUpdated={EFFECTIVE_DATE}
      intro={
        <p>
          This Privacy Policy explains how Qiko AI Labs FZCO processes personal data in connection
          with its business websites, platform, AI digital workers and related support (the "Service").
          It also explains the roles Qiko and its customers have and the rights that may apply.
        </p>
      }
    >
      <LegalSection heading="1. Who we are and how to contact us">
        <p>
          Qiko AI Labs FZCO ("Qiko", "we", "us" or "our") is located at IFZA Business Park, DDP,
          PO Box 342001, Dubai, United Arab Emirates. Contact us about privacy at
          <a href="mailto:support%40qiko.ai" className="ml-1 text-cyan-400 hover:text-cyan-300">support{"@"}qiko.ai</a>.
        </p>
        <p>
          The Service is business-to-business. This policy applies to customer administrators and
          users, prospective customers, business contacts, support contacts and people who interact
          with a customer&apos;s Qiko digital worker.
        </p>
      </LegalSection>

      <LegalSection heading="2. When Qiko is controller or processor">
        <p>
          Qiko acts as a controller when it decides why and how to process account, commercial,
          security, website, support and business contact data. For these activities, Qiko is
          responsible for the processing described in this policy.
        </p>
        <p>
          Qiko generally acts as a processor or service provider when a customer submits Customer
          Content, configures a digital worker or determines why personal data is handled through that
          worker. The customer is then the controller or equivalent business, and Qiko processes the
          data on its documented instructions and under applicable contractual terms. A rights request
          about that data may be routed to the relevant customer so it can respond as controller.
        </p>
      </LegalSection>

      <LegalSection heading="3. Personal data we process">
        <ul className="list-disc space-y-2 pl-6">
          <li><strong className="text-white">Account and business data:</strong> name, work email, organisation, role, tenant, account status and user preferences.</li>
          <li><strong className="text-white">Authentication and security data:</strong> password hashes, session and CSRF information, access permissions, authentication events, IP address and security logs.</li>
          <li><strong className="text-white">Device and technical data:</strong> browser and device type, operating system, request metadata, timestamps, diagnostics and service interactions. Qiko does not currently load browser analytics or marketing technologies.</li>
          <li><strong className="text-white">Customer Content:</strong> documents, prompts, messages, approved answers, knowledge sources, digital worker settings and generated responses, which may include personal data chosen by the customer or its users.</li>
          <li><strong className="text-white">Support and communications:</strong> enquiries, correspondence, feedback and troubleshooting information.</li>
          <li><strong className="text-white">Commercial and payment data:</strong> Orders, plan and transaction records. If enabled and initiated by a user, payment checkout is hosted by Stripe. Qiko does not need to receive full payment card details from that hosted checkout.</li>
          <li><strong className="text-white">Compliance data:</strong> records needed to manage legal requests, disputes, fraud, misuse and regulatory obligations.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="4. Sources of personal data">
        <p>
          We receive data directly from users and customer administrators, from Customer Content and
          interactions with digital workers, from devices and systems that connect to the Service,
          from customer-authorised integrations, from our service providers, and from business
          communications. Customers decide what Customer Content to submit and are responsible for
          providing required notices and having a lawful basis for it.
        </p>
      </LegalSection>

      <LegalSection heading="5. Why we process data">
        <ul className="list-disc space-y-2 pl-6">
          <li>create and administer accounts, tenants and permissions;</li>
          <li>provide, operate and support digital workers and other requested features;</li>
          <li>authenticate users, secure the Service, prevent abuse and investigate incidents;</li>
          <li>process Customer Content on the customer&apos;s instructions;</li>
          <li>respond to enquiries, provide support and send operational or legal notices;</li>
          <li>manage Orders, payments, tax and business records where applicable;</li>
          <li>diagnose faults and improve reliability, usability and features using appropriately limited data;</li>
          <li>establish, exercise or defend legal claims and comply with law; and</li>
          <li>seek and manage consent where consent is required.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="6. Lawful bases">
        <p>
          Where the EU GDPR or UK GDPR applies to Qiko as controller, we rely on performance of a
          contract or steps requested before a contract, compliance with legal obligations, and
          legitimate interests such as securing, operating and improving a B2B service, supporting
          customers and managing our business. We balance those interests against affected rights.
          We use consent where required, including for optional browser technologies. Consent can be
          withdrawn at any time without affecting earlier lawful processing.
        </p>
        <p>
          Under UAE data protection law, we process personal data with consent where required and
          where another legal ground permits processing, including steps connected with a contract,
          compliance with law, protection of rights and other grounds available under applicable law.
          When Qiko is a processor, the customer determines the relevant lawful basis.
        </p>
      </LegalSection>

      <LegalSection heading="7. How AI and tenant retrieval work">
        <p>
          Qiko can divide customer-provided knowledge into smaller passages, create numerical
          embeddings using Amazon Titan, and store and retrieve relevant passages within the customer&apos;s
          tenant context. When a user sends a prompt, relevant tenant content and instructions may be
          supplied through Amazon Bedrock to Anthropic Claude models for EU geographic inference. The
          resulting answer is returned to the digital worker experience.
        </p>
        <p>
          A customer may review and approve an answer. Qiko may reuse that approved answer within the
          same tenant&apos;s retrieval flow to improve consistency. This is retrieval and approved-answer
          reuse, not foundation model fine-tuning. Customers control the knowledge and instructions
          they submit. Contract terms with AI and infrastructure providers govern their processing.
        </p>
      </LegalSection>

      <LegalSection heading="8. Automated decision support">
        <p>
          AI outputs support customer workflows but can be inaccurate and require human review. Qiko
          does not intend the Service to make solely automated decisions on its own behalf that create
          legal or similarly significant effects for individuals. Customers must assess their own use,
          provide suitable human oversight and not use an output as the sole basis for a significant
          decision unless lawful safeguards are in place. Contact the relevant customer about a
          decision made through its digital worker.
        </p>
      </LegalSection>

      <LegalSection heading="9. Providers, subprocessors and disclosures">
        <p>We disclose data only as needed for the purposes above, including to:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li><strong className="text-white">Amazon Web Services:</strong> core EU Central infrastructure, storage, Amazon Bedrock Claude inference with EU geographic routing, and Amazon Titan embeddings;</li>
          <li><strong className="text-white">Cloudflare:</strong> conditional network delivery, availability and security services, which may set necessary security cookies;</li>
          <li><strong className="text-white">Stripe:</strong> conditional user-initiated hosted payment checkout and payment processing if that feature is enabled;</li>
          <li>contracted communications, email, support, monitoring and professional service providers where used to operate Qiko;</li>
          <li>customer-authorised integrations and recipients selected by the customer;</li>
          <li>advisers, auditors, insurers and a buyer, investor or successor involved in a genuine corporate transaction, subject to appropriate confidentiality; and</li>
          <li>courts, regulators, law enforcement or other parties where required by law or necessary to protect rights, safety and security.</li>
        </ul>
        <p>
          These providers process data under contractual restrictions appropriate to their role. Qiko
          does not sell personal data. Contact support{"@"}qiko.ai for current subprocessor information
          relevant to a customer&apos;s Service.
        </p>
      </LegalSection>

      <LegalSection heading="10. International data locations and transfers">
        <p>
          Core processing currently uses AWS EU Central infrastructure. Amazon Bedrock Claude requests
          use EU geographic inference routing. Qiko is established in the UAE, and authorised Qiko
          personnel may access data from the UAE for administration, security and support. Providers
          may also process data in locations permitted by their contracts. Qiko does not promise UAE-only,
          EU-only or single-region processing.
        </p>
        <p>
          Where personal data is transferred from the EEA, UK or another jurisdiction that restricts
          international transfers, Qiko uses safeguards required for the transfer and appropriate to
          the parties&apos; roles, such as adequacy mechanisms or approved contractual clauses, supplemented
          by technical and organisational measures where appropriate. Transfer arrangements are subject
          to the applicable customer and provider contracts.
        </p>
      </LegalSection>

      <LegalSection heading="11. Retention">
        <p>
          We retain personal data for as long as reasonably needed for the relevant account, Order,
          customer instruction or purpose. We also consider legal and tax obligations, security and
          fraud prevention, backup cycles, dispute and limitation periods, the sensitivity and volume
          of data, technical feasibility and whether data can be de-identified. Different records
          therefore have different retention periods.
        </p>
        <p>
          When retention is no longer justified, we delete, de-identify or securely isolate data as
          appropriate. Backup and legal-hold copies may remain until their applicable cycle or hold ends.
          Available deletion and export functions vary by feature and contract. This policy does not
          promise comprehensive self-service deletion, a fixed export format or a fixed deletion period.
        </p>
      </LegalSection>

      <LegalSection heading="12. Security">
        <p>
          Qiko uses technical and organisational measures designed to protect personal data, including
          access controls, tenant separation, credential hashing, encryption in transit, logging and
          provider security controls where appropriate. No internet service or security measure can
          guarantee absolute security. Customers remain responsible for their account access, endpoint
          security, user permissions and the content they choose to submit.
        </p>
      </LegalSection>

      <LegalSection heading="13. Your rights">
        <p>
          Depending on the applicable UAE, EEA, UK or other data protection law and relevant exemptions,
          you may have rights to receive information about processing, access personal data, correct it,
          request deletion, restrict or object to processing, receive portable data, withdraw consent,
          and object to certain direct marketing. You may also have rights concerning qualifying solely
          automated decisions.
        </p>
        <p>
          Send requests to support{"@"}qiko.ai. We may verify identity and authority, ask for details needed
          to locate data, or decline or limit a request where law permits. If Qiko processes the data for
          a customer, we may direct the request to that customer and assist it under our contract.
        </p>
        <p>
          You may complain to the UAE Data Office where it has jurisdiction, an EEA supervisory authority
          in your country, or the UK Information Commissioner&apos;s Office. We encourage you to contact us
          first so we can try to address the concern.
        </p>
      </LegalSection>

      <LegalSection heading="14. Cookies, local storage and privacy signals">
        <p>
          Necessary cookies and storage operate authentication, security, consent and password reset
          continuity. Qiko does not currently load analytics or marketing technologies in the browser.
          Optional categories default to off and can be managed through Cookie settings. We honour Global
          Privacy Control conservatively by keeping marketing off. Do Not Track defaults optional choices
          to off but can be changed. See our <a href="/cookies" className="text-cyan-400 hover:text-cyan-300">Cookie Policy</a>.
        </p>
      </LegalSection>

      <LegalSection heading="15. Marketing and service communications">
        <p>
          We may send B2B communications where permitted by law and will respect applicable opt-out
          rights. Operational, account, security and legal messages are not marketing and may still be
          sent while an account or business relationship is active. Qiko does not currently use browser
          marketing or advertising technologies.
        </p>
      </LegalSection>

      <LegalSection heading="16. Children">
        <p>
          The Service is for organisations and their authorised business users. It is not directed to
          children, and Qiko does not knowingly offer accounts to children. Customers must not configure
          a digital worker to collect children&apos;s personal data unless they have confirmed a lawful basis
          and appropriate safeguards with Qiko.
        </p>
      </LegalSection>

      <LegalSection heading="17. Changes to this policy">
        <p>
          We may update this policy as our Service, providers or legal obligations change. We will post
          the updated policy with a revised effective date and provide additional notice where required.
        </p>
      </LegalSection>

      <LegalSection heading="18. Contact">
        <p>
          Email privacy questions and requests to <a href="mailto:support%40qiko.ai" className="text-cyan-400 hover:text-cyan-300">support{"@"}qiko.ai</a>,
          or write to Qiko AI Labs FZCO, IFZA Business Park, DDP, PO Box 342001, Dubai,
          United Arab Emirates.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
