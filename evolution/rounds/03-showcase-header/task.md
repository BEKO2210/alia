# Tidy up the header of your architecture page

`site/showcase/architecture/index.html` is the architecture page you built in earlier sessions. Its header needs
work, mostly on phones.

Change it so that:

- the header shows the current Alia logo, the dragon in its egg: show the start page's logo file
  `site/logo-mark.svg` with an `<img>` element, instead of the old inline "a" logo;
- the page has exactly one `<h1>`: the hero heading "Alia, explained by Alia"; the header keeps showing
  "Alia Architecture", but not as an `<h1>`;
- the page has a `<meta name="description">` with one or two sentences about what the page shows;
- every link in the header navigation is at least 24 × 24 CSS pixels, on phones (390 px wide) and desktops
  (1280 px wide);
- on phones (390 px wide) the header is at most 200 CSS pixels tall (today it is about 307) and the four
  navigation links fit in one row; on desktops the header does not get taller than it is now;
- the navigation links keep their text and targets, and the page does not get wider than the screen.

Everything below the header (the hero, the diagrams, the numbers, the footer) stays as it is. Change only files
below `site/showcase/`. A small, clean change is better than a redesign.
