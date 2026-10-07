"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Card, ErrorText, Field, Input, Select } from "@/components/ui";
import { useCreateOrganization, type Schemas } from "@/lib/api";
import { ORG_KIND_LABELS } from "@/lib/labels";
import { errorMessage } from "@/lib/utils";

function guessTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function CreateOrganization() {
  const router = useRouter();
  const create = useCreateOrganization();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Schemas["OrganizationKind"]>("company");
  const [country, setCountry] = useState("");

  return (
    <Card
      title="Set up your organization"
      description="Your organization holds your workspaces, contracts and team."
      className="w-full max-w-lg"
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(
            {
              name,
              kind,
              default_country: country || null,
              default_timezone: guessTimezone(),
            },
            { onSuccess: (org) => router.replace(`/app/${org.id}`) },
          );
        }}
      >
        <Field label="Organization name">
          <Input required value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field
          label="Type"
          hint="This sets how workspaces are organised: by client, entity or department."
        >
          <Select
            value={kind}
            onChange={(e) => setKind(e.target.value as Schemas["OrganizationKind"])}
          >
            {Object.entries(ORG_KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Home country (optional)"
          hint="Two-letter code, e.g. GB, US, DE, TR. Used for public holidays."
        >
          <Input
            value={country}
            maxLength={2}
            onChange={(e) => setCountry(e.target.value.toUpperCase())}
          />
        </Field>
        <ErrorText>{errorMessage(create.error)}</ErrorText>
        <Button type="submit" disabled={create.isPending} className="w-full">
          {create.isPending ? "Creating…" : "Create organization"}
        </Button>
      </form>
    </Card>
  );
}
