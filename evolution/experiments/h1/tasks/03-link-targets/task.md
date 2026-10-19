# Make the header and footer links easy to tap

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
English and a German version; the "EN" / "DE" buttons at the top switch the language.

Several links are less than 24 CSS pixels tall, which makes them hard to tap: the section links in the top
navigation ("Features", "Benchmarks", "Install") and the "Security" link in the footer.

Fix it so that:

- every visible link in the top navigation and in the footer is at least 24 × 24 CSS pixels, on phones (390 px
  wide) and desktops (1280 px wide), in English and German;
- the links keep their text and their targets, and the section links stay in one row;
- the height of the top navigation bar stays as it is (64 px);
- the page does not get wider than the screen.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
