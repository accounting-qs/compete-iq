import { ContactsPage } from "@/components/contacts/ContactsPage";

export default async function Contacts({ params }: { params: Promise<{ assignmentId: string }> }) {
  const { assignmentId } = await params;
  return <ContactsPage assignmentId={assignmentId} />;
}
