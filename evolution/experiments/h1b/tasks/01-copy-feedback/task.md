# Show a clear confirmation after copying

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
English and a German version; the "EN" / "DE" buttons at the top switch the language.

In the "Install" section every code block has a "Copy" button (German: "Kopieren"). After a click, the button
shows only a "✓" for a moment, which is easy to miss and says nothing to screen readers.

Change it so that:

- after a successful copy, the button reads "Copied" in English and "Kopiert" in German for about one and a half
  seconds, and then shows its normal label again;
- the normal label afterwards is always in the language that is selected at that moment, also when the visitor
  switches the language while the confirmation is shown;
- every button still copies exactly the code of its own block.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
