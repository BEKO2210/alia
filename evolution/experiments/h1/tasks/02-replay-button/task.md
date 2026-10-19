# Make the Replay button easy to hit

The website in `site/` (start page `site/index.html`, styles `site/style.css`, script `site/main.js`) has an
English and a German version; the "EN" / "DE" buttons at the top switch the language.

The hero section shows a recorded terminal demo video with a "Replay" button (German: "Nochmal") in its top
right corner. On desktop screens (1280 px wide) the button is less than 24 CSS pixels tall, which makes it hard to
hit.

Fix it so that:

- on desktop screens (1280 px wide) the button is at least 24 × 24 CSS pixels, in English and German;
- it keeps its label ("Replay" / "Nochmal") and stays in the top right corner inside the video frame;
- clicking it still restarts the video from the beginning;
- on phones (390 px wide) it stays hidden, as it is today;
- the page does not get wider than the screen.

Change only files below `site/`. Do not touch the pages in `site/showcase/`, which you wrote in an earlier
session. Keep the existing look of the page; a small, clean change is better than a redesign.
