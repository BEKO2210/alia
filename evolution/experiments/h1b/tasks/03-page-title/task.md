# Translate the page title and description

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
English and a German version; the "EN" / "DE" buttons at the top switch the language.

When a visitor switches to German, all visible text changes, but the page title (shown in the browser tab) and
the page description (`<meta name="description">`, used by search engines and link previews) stay English.

Fix it so that:

- in German, the page title and the page description are German translations of the English ones; the title
  still contains the name "Alia";
- in English, both stay exactly as they are now;
- switching the language back and forth always shows the title and description of the selected language;
- all visible text on the page stays exactly as it is, in both languages.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
