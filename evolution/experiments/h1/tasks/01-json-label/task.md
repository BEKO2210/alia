# Fix the labels of the JSON rows

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
English and a German version; the "EN" / "DE" buttons at the top switch the language.

In the benchmark section, the cards for "Qwen3.6 35B-A3B" and "Qwen3.5 9B" each have a JSON row. The rows need
different labels, but in the browser both cards show the same one: "JSON schema" in English and "JSON mit / ohne
Schema" in German.

Fix it so that:

- in English, the Qwen3.6 35B-A3B row shows "JSON with / without schema" and the Qwen3.5 9B row shows
  "JSON schema";
- in German, the Qwen3.6 35B-A3B row shows "JSON mit / ohne Schema" and the Qwen3.5 9B row shows a correct German
  label for "JSON schema";
- all other text on the page stays exactly as it is, in both languages.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
