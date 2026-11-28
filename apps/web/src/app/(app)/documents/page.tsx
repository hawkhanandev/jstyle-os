import { DocumentsList } from "@/components/DocumentsList";

export default function DocumentsPage() {
  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Documents</h1>
      <p className="mt-1 text-stone-600">Every file the CRM made or you uploaded, newest first.</p>
      <DocumentsList />
    </div>
  );
}
