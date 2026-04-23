import { ContactsPage } from "@/components/contacts/ContactsPage";

type Tab = "assigned" | "used" | "all";

function parseTab(raw: string | string[] | undefined): Tab {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return v === "all" || v === "used" || v === "assigned" ? v : "assigned";
}

export default async function Contacts({
  params,
  searchParams,
}: {
  params: Promise<{ assignmentId: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { assignmentId } = await params;
  const sp = await searchParams;
  const initialTab = parseTab(sp.tab);
  return <ContactsPage assignmentId={assignmentId} initialTab={initialTab} />;
}
