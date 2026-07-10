"use client";

import { useCallback, useState } from "react";
import { submitLabsContact } from "@/lib/api";

const COMPANY_SIZE_OPTIONS = ["1 - 50", "51 - 250", "251 - 1000", "1001+"] as const;

type FormState = {
  name: string;
  work_email: string;
  company: string;
  company_size: string;
  build_request: string;
};

const initialFormState: FormState = {
  name: "",
  work_email: "",
  company: "",
  company_size: COMPANY_SIZE_OPTIONS[0],
  build_request: "",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12.5,
  fontWeight: 600,
  color: "#cdd7e3",
  marginBottom: 7,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  font: "inherit",
  fontSize: 14,
  color: "#E8EEF6",
  background: "#0c1626",
  border: "1px solid #233048",
  borderRadius: 10,
  padding: "11px 13px",
  outline: "none",
};

const fieldErrorStyle: React.CSSProperties = {
  marginTop: 6,
  fontSize: 12,
  color: "#f0726a",
};

function validateForm(values: FormState): Partial<Record<keyof FormState, string>> {
  const errors: Partial<Record<keyof FormState, string>> = {};
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (!values.name.trim()) {
    errors.name = "Name is required.";
  } else if (values.name.trim().length < 2) {
    errors.name = "Name must be at least 2 characters.";
  }

  if (!values.work_email.trim()) {
    errors.work_email = "Work email is required.";
  } else if (!emailPattern.test(values.work_email.trim())) {
    errors.work_email = "Please enter a valid email address.";
  }

  if (!values.company.trim()) {
    errors.company = "Company is required.";
  }

  if (!values.company_size.trim()) {
    errors.company_size = "Company size is required.";
  }

  if (!values.build_request.trim()) {
    errors.build_request = "Please describe what you want to build.";
  }

  return errors;
}

export default function LabsContactForm() {
  const [form, setForm] = useState<FormState>(initialFormState);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const updateField = useCallback((field: keyof FormState, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
    setSubmitError(null);
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitError(null);
    setSuccessMessage(null);

    const errors = validateForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);

    try {
      const body = await submitLabsContact({
        name: form.name.trim(),
        work_email: form.work_email.trim(),
        company: form.company.trim(),
        company_size: form.company_size,
        build_request: form.build_request.trim(),
      });
      setForm(initialFormState);
      setSuccessMessage(body.message || "Qiko Labs inquiry submitted successfully.");
      window.setTimeout(() => setSuccessMessage(null), 5000);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to submit form. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label htmlFor="labs-contact-name" style={labelStyle}>Name</label>
          <input
            id="labs-contact-name" type="text" placeholder="Your name"
            style={{ ...inputStyle, borderColor: fieldErrors.name ? "#f0726a" : "#233048" }}
            value={form.name} onChange={(e) => updateField("name", e.target.value)} disabled={isSubmitting}
          />
          {fieldErrors.name ? <div style={fieldErrorStyle}>{fieldErrors.name}</div> : null}
        </div>
        <div>
          <label htmlFor="labs-contact-work-email" style={labelStyle}>Work email</label>
          <input
            id="labs-contact-work-email" type="email" placeholder="you@company.com"
            style={{ ...inputStyle, borderColor: fieldErrors.work_email ? "#f0726a" : "#233048" }}
            value={form.work_email} onChange={(e) => updateField("work_email", e.target.value)} disabled={isSubmitting}
          />
          {fieldErrors.work_email ? <div style={fieldErrorStyle}>{fieldErrors.work_email}</div> : null}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label htmlFor="labs-contact-company" style={labelStyle}>Company</label>
          <input
            id="labs-contact-company" type="text" placeholder="Company name"
            style={{ ...inputStyle, borderColor: fieldErrors.company ? "#f0726a" : "#233048" }}
            value={form.company} onChange={(e) => updateField("company", e.target.value)} disabled={isSubmitting}
          />
          {fieldErrors.company ? <div style={fieldErrorStyle}>{fieldErrors.company}</div> : null}
        </div>
        <div>
          <label htmlFor="labs-contact-company-size" style={labelStyle}>Company size</label>
          <select
            id="labs-contact-company-size"
            style={{ ...inputStyle, borderColor: fieldErrors.company_size ? "#f0726a" : "#233048" }}
            value={form.company_size} onChange={(e) => updateField("company_size", e.target.value)} disabled={isSubmitting}
          >
            {COMPANY_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          {fieldErrors.company_size ? <div style={fieldErrorStyle}>{fieldErrors.company_size}</div> : null}
        </div>
      </div>

      <div style={{ marginBottom: 18 }}>
        <label htmlFor="labs-contact-build-request" style={labelStyle}>What do you want to build?</label>
        <textarea
          id="labs-contact-build-request" placeholder="The problem, the inputs, and the outcome you are after."
          style={{ ...inputStyle, minHeight: 104, resize: "vertical", borderColor: fieldErrors.build_request ? "#f0726a" : "#233048" }}
          value={form.build_request} onChange={(e) => updateField("build_request", e.target.value)} disabled={isSubmitting}
        />
        {fieldErrors.build_request ? <div style={fieldErrorStyle}>{fieldErrors.build_request}</div> : null}
      </div>

      {submitError ? (
        <div role="alert" style={{ marginBottom: 14, padding: "11px 13px", borderRadius: 10, border: "1px solid rgba(240,114,106,.35)", background: "rgba(240,114,106,.08)", color: "#f0726a", fontSize: 13 }}>
          {submitError}
        </div>
      ) : null}

      {successMessage ? (
        <div role="status" style={{ marginBottom: 14, padding: "11px 13px", borderRadius: 10, border: "1px solid rgba(52,211,153,.35)", background: "rgba(52,211,153,.08)", color: "#34d399", fontSize: 13 }}>
          {successMessage}
        </div>
      ) : null}

      <button
        type="submit" disabled={isSubmitting}
        style={{
          width: "100%", display: "inline-flex", justifyContent: "center", alignItems: "center", gap: 8,
          font: "inherit", fontSize: 15, fontWeight: 700, color: "#fff",
          cursor: isSubmitting ? "not-allowed" : "pointer", opacity: isSubmitting ? 0.75 : 1,
          background: "linear-gradient(115deg,#A855F7,#6E73F2 55%,#4F8FF7)", border: "none",
          padding: "14px 22px", borderRadius: 12, boxShadow: "0 12px 32px -12px rgba(168,85,247,.7)",
        }}
      >
        {isSubmitting ? (
          <>
            <span aria-hidden="true" style={{ width: 16, height: 16, borderRadius: "50%", border: "2px solid rgba(255,255,255,.35)", borderTopColor: "#fff", animation: "qspin .8s linear infinite" }} />
            Sending...
          </>
        ) : (
          <>Send to Qiko Labs <span>&#8594;</span></>
        )}
      </button>
    </form>
  );
}
