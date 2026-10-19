# Fix the copy buttons on the install section

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
"Install" section with four code blocks. Each block has a "Copy" button (German: "Kopieren").

The problem: the copy button sits on top of the code. On a phone-sized screen (390 px wide) it covers the end of
the first code line in every block, and on a desktop screen (1280 px wide) it covers part of a long line in the
second block. Readers cannot see the hidden characters.

Fix it so that:

- the copy button never covers any code text, on phones (390 px) and desktops (1280 px), in English and German,
  also when the code block is scrolled horizontally;
- every block still has its own copy button that copies exactly that block's code;
- the button stays easy to tap (at least 24 × 24 CSS pixels) and keeps its label ("Copy" / "Kopieren");
- the commands themselves stay exactly as they are;
- the page does not get wider than the screen.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
