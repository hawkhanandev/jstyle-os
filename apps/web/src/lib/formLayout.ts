export type FieldType = "text" | "email" | "tel" | "date" | "number" | "select" | "textarea";

export type PublicField = {
  name: string;
  custom: boolean;
  type: FieldType;
  label: string;
  help: string;
  placeholder: string;
  required: boolean;
  wide: boolean;
  options: { value: string; label: string }[];
};

export type PublicLayout = { title: string; intro: string; submit_label: string; fields: PublicField[] };

export type FieldOverride = { label: string | null; help: string | null; placeholder: string | null; hidden: boolean; required: boolean };
export type CustomQuestion = {
  id: string;
  label: string;
  type: "text" | "textarea" | "select" | "yesno" | "number";
  options: string[];
  required: boolean;
  help: string | null;
  wide: boolean;
};
export type FormLayout = {
  title: string;
  intro: string;
  submit_label: string;
  order: string[];
  fields: Record<string, FieldOverride>;
  custom: CustomQuestion[];
};
export type Builtin = { name: string; type: FieldType; label: string; lock: "always" | "pricing" | null; wide: boolean };
export type LayoutEditor = { layout: FormLayout; builtins: Builtin[]; defaults: { title: string; intro: string; submit_label: string } };
