# Home and End keys for the screenshot tabs

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
English and a German version; the "EN" / "DE" buttons at the top switch the language.

The page has two screenshot tabs, "Terminal" and "Web shell" (German: "Web-Shell"). They can be switched by
clicking and with the left and right arrow keys.

Add the usual keyboard support for tabs:

- pressing Home on a focused tab selects and focuses the first tab, pressing End selects and focuses the last tab;
- the selected tab shows its own screenshot panel and hides the other one, exactly as with a click;
- clicking and the arrow keys keep working as they do now.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
