export type ThemeChoice = "light" | "dark" | "system";
export const THEME_KEY = "jstyle-theme";

// Runs before the first paint (inlined in the root layout) so pages never flash the wrong theme.
// The public enquiry forms always stay light: they're embedded in the business website.
export const THEME_SCRIPT = `(function(){try{
if(location.pathname.indexOf('/forms/')===0)return;
var c=localStorage.getItem('${THEME_KEY}')||'system';
var d=c==='dark'||(c==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);
if(d)document.documentElement.classList.add('dark');
}catch(e){}})();`;

export function applyTheme(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function readTheme(): ThemeChoice {
  const v = typeof localStorage === "undefined" ? null : localStorage.getItem(THEME_KEY);
  return v === "light" || v === "dark" ? v : "system";
}
