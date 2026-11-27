# Embedding the forms on the Jstyle WordPress site

The CRM serves both forms itself, so WordPress stores no client data and all spam checks run in
one place. The exact snippets, with the right address filled in, are on the CRM's **Forms**
screen. They look like this:

```html
<iframe id="jstyle-bride-form" src="https://CRM-ADDRESS/forms/bride"
        style="width:100%;border:0;min-height:900px" loading="lazy"></iframe>
<script>
  window.addEventListener("message", function (e) {
    if (e.origin === "https://CRM-ADDRESS" && e.data && e.data.jstyleFormHeight) {
      document.getElementById("jstyle-bride-form").style.height = e.data.jstyleFormHeight + "px";
    }
  });
</script>
```

1. In WordPress, edit the enquiry page and add a **Custom HTML** block.
2. Paste the snippet from the Forms screen.
3. Repeat with the planner snippet on the planner page.

On staging and production set `WORDPRESS_ORIGIN` (the WordPress site address) so only that
site can embed the forms.
