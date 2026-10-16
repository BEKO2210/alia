# How Alia built its own architecture page

`index.html` in this folder was written entirely by Alia: the `alia` CLI running Qwen3.6-35B-A3B (IQ3_XXS, profile `rtx8gb-16gb-qwen36-35b`) through llama.cpp on one RTX 3070 with 8 GB VRAM, Ryzen 7 5800X, 16 GB RAM, on 2026-10-15. Round r5 (2026-10-16) ran on the 9B profile `rtx8gb-qwen35-9b-fast`.

Alia made every change to the page. The operator did what you do with any coding agent: looked at screenshots, tested the page in a headless browser (layout at 1440 px and 390 px, animation frames, the detail panels, console errors, `prefers-reduced-motion`), checked the facts against the Alia source, and wrote the next prompt. Every round was a fresh session started with `alia --yolo`, and every round is a commit.

Below are all prompts in order, verbatim.

## What did not work

- **Round 1 (long session):** Alia invented its own hero text, reported layout fixes it had not made and started an unrequested web server. Exact, short prompts in fresh sessions fixed this from round 2 on.
- **Two discarded attempts:** one round on the 35B profile slowed to almost an hour while free RAM was low (the model streamed from the SSD). A retry on the 9B profile wrote broken `sed` commands, reported success and hit the context limit (hard limit 10,408 tokens: with a 33,408-token window, Qwen Code compacted after 408 tokens; the profile now uses 65,536). Both diffs were thrown away; the same work was then split into the small rounds r4b1–r4f, which took two to eight minutes each.
- **r4d** dropped one edge label while moving a block; r4e put it back.
- **r4h and r4i** address findings from the automated pull-request review (CodeRabbit).

## Prompts

### v1: Initial build: one prompt, one session (11:48)

```text
Build a single-file website index.html in this folder that visualizes YOUR OWN architecture: you are Alia, the local coding agent whose source is in ./alia-src (read alia-src/README.md, alia-src/profiles.json and the launcher alia-src/alia first). Requirements: 1) dark, modern, high-end design with the brand gradient #5EEAD4 -> #5C9DFF -> #A78BFA and logo-mark.svg in the header; 2) an interactive layered architecture diagram built with inline SVG + CSS: user terminal/browser -> alia launcher (hardware detection, profile selection, start lock, server lifecycle) -> llama-server on 127.0.0.1:8090 (CUDA, expert offload to RAM, MTP drafting) -> GPU/RAM, plus Qwen Code (terminal UI / web shell) talking to llama-server via the OpenAI API; clicking or hovering a box shows a detail panel; 3) an animated request flow (a token travelling from prompt to model and back); 4) a section with the real measured numbers from profiles.json (only numbers that are in that file); 5) responsive, no external libraries, no build step. Write all CSS and JS inline. When done, list what you built.
```

### r1: Display font and hero (12:01)

```text
Improve index.html (your architecture website). Keep all content and numbers, fix these concrete problems: 1) In the architecture SVG (viewBox 0 0 1100 620) the bottom ~250 units are empty: tighten the viewBox/height to the actual content and remove the empty space. 2) Text overlaps: in the Qwen Code box the line "QWEN_HOME isolated" overlaps the "Coding Agent" label - give every box enough height so no text touches; in the request-flow SVG the edge labels "OpenAI API", "CUDA Offload" and "MTP Draft" overlap the boxes - move edge labels above the connecting lines, centered between boxes. 3) Typography: add @font-face for the local fonts fonts/Outfit.woff2 (display headings, weight 100-900), fonts/Inter.woff2 (body) and fonts/JBM.woff2 (code/mono); use Outfit for all headings with tight letter-spacing. 4) Add a big hero section at the top (min-height ~80vh): huge Outfit headline "Alia, explained by Alia", a gradient line under it, a one-sentence subtitle, two buttons (Explore architecture, See benchmarks) and a subtle radial gradient glow background. Do not use external resources. After editing, re-read the changed parts of the file to verify there are no overlaps or broken tags, then summarize the changes.
```

### r2a: Exact hero text (12:27)

```text
Edit index.html with exactly these four changes and nothing else. (A) Hero: replace the h1 text with "Alia, explained by Alia". Replace the subtitle text with "A local coding agent drew its own architecture: launcher, llama.cpp server, Qwen Code and your GPU, with real benchmark numbers." Replace the first button text with "Explore the architecture" (href #architecture) and the second with "See the benchmarks" (href #benchmarks). Everything in English. (B) Architecture SVG with class arch-svg: find the largest y + height of all rect elements inside it, then change its viewBox from "0 0 1100 620" to "0 0 1100 H" where H = that value + 40. (C) In that SVG, the Qwen Code box: increase the height of its rect by 30 and move its small label text ("Coding Agent") down by 20 so it no longer touches "QWEN_HOME isolated". (D) In the SVG with class flow-svg, move the text elements "OpenAI API", "CUDA Offload" and "MTP Draft" (and the other edge labels like "HTTP POST", "API Call") 18 units up (decrease y by 18) so they sit above the line and not on the boxes. Do not start any server. When done, print the new viewBox values and the changed lines.
```

### r2b: Layout fixes in the diagram (12:33)

```text
In index.html make exactly these three edits and nothing else. Do not start any server. (B) The svg with class "arch-svg" has viewBox "0 0 1100 620". Look at the rect elements inside it, compute the largest y + height, and set the viewBox to "0 0 1100 H" with H = that value + 40. (C) In the same svg, the Qwen Code box: increase its rect height by 30 and move the small label text "Coding Agent" 20 units down so it does not touch the text "QWEN_HOME isolated". (D) In the svg with class "flow-svg", decrease the y attribute of every edge label text ("HTTP POST", "API Call", "OpenAI API", "CUDA Offload", "MTP Draft") by 18. Use grep to find the lines, edit them, then print the changed lines.
```

### r3: Box overlap and flow spacing (12:43)

```text
In index.html make exactly these edits and nothing else, do not start any server. (E) In the svg with class "arch-svg", the Qwen Code box (g with data-detail="qwen") now overlaps the llama-server box. Fix it by moving the llama-server group (g with data-detail="server") and the GPU/RAM group (g with data-detail="hardware") down by 40 units: add transform="translate(0,40)" to both g elements. Then update the three connector paths after the comments "Launcher → llama-server", "Qwen Code → llama-server" and "llama-server → GPU" so their end points (and for the last one both points) are 40 units lower. Finally increase the arch-svg viewBox height from 440 to 480. (F) In the svg with class "flow-svg" there is empty space above the boxes: find the smallest y of its rect elements and shift the viewBox so it starts 30 units above that value, and reduce its height accordingly so the content stays fully visible. Print the changed lines when done.
```

### r4a: Request flow: correct token path, spacing, caption (16:23)

```text
In index.html make exactly these edits and nothing else, do not start any server. All edits are inside <section id="flow">. (G) The flow is factually wrong: Alia is not in the per-token path, it only starts the pieces once. Replace the lead paragraph text with: "Watch a request travel from your prompt through Qwen Code into llama-server, across GPU and RAM, and back as streamed tokens. Alia starts these pieces once; it is not in the token path." (H) In the svg with class "flow-svg" make the six node groups evenly spaced: rect x values 40, 225, 410, 595, 780, 965 (width 80, y 120, height 60 unchanged), with their two texts centered at rect x + 40. New node texts in order (title / subtitle) and stroke colors: "Prompt" / "your terminal" cyan; "Qwen Code" / "agent loop" cyan; "llama-server" / "127.0.0.1:8090" blue; "GPU" / "attention + KV" purple; "RAM" / "MoE experts" purple; "MTP" / "2-token draft" green. Make the node titles font-size 10 if they do not fit 80 units. (I) The edge labels touch the boxes. Put the five labels centered in the gaps at x = 172.5, 357.5, 542.5, 727.5, 912.5 and y = 140, texts in order: "stdin", "POST /v1/chat", "CUDA", "expert offload", "draft + verify". Move the five → arrows to the same x values at y = 168 and the five ← arrows to the same x values at y = 186. (J) Update the dashed flow path to "M80,150 L1005,150", flowPath1 to "M120,150 Q265,135 450,150 Q635,165 820,150 Q965,135 1005,150" and flowPath2 to the same points reversed. (K) The caption is cut off and not centered: change the group transform to translate(550, 222), give the "Token Generation Cycle" text text-anchor="middle", and replace the two tspans with "Once: Alia detects the GPU → picks a profile → starts llama-server → launches Qwen Code" and "Per token: Qwen Code → /v1/chat/completions → attention on GPU, experts from RAM → MTP drafts 2 tokens → streamed back". (L) Change the flow-svg viewBox to "0 100 1100 190". Print the changed lines when done.
```

### r4b1: Accent bar, box height, reduced motion (17:24)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (M) In the svg with class "arch-svg": the rect with class "box-accent" at x="600" y="20" has height="160", set it to height="190". In the group data-detail="terminal" change both rects from height="100" to height="110". (N) At the very end of the <style> block (just before </style>) add this line: @media (prefers-reduced-motion: reduce){.token-particle{display:none}.reveal{opacity:1;transform:none;transition:none}}
```

### r4b2: Card grids, word wrapping, phone layout (17:26)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (O) In the CSS rule .metrics-grid change grid-template-columns:repeat(auto-fit,minmax(340px,1fr)) to grid-template-columns:repeat(2,1fr). Keep the existing .metrics-grid{grid-template-columns:1fr} inside @media(max-width:768px). (P) In the CSS rule .info-row change grid-template-columns:repeat(auto-fit,minmax(260px,1fr)) to grid-template-columns:repeat(3,1fr), and inside @media(max-width:768px) add .info-row{grid-template-columns:1fr} (Q) In the two inline styles that contain word-break:break-all replace it with overflow-wrap:break-word. (R) Inside @media(max-width:768px) add .arch-wrap,.flow-wrap{overflow-x:auto}.arch-svg,.flow-svg{min-width:900px}
```

### r4b3: Footer (17:28)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (S) In the <footer>, replace the whole first <p> (the one containing alia-src/) with: <p>Alia v0.1.0 · Your hardware. Your AI. No cloud. · <a href="https://github.com/BEKO2210/alia">Source on GitHub</a></p> and directly after it add: <p>This page was written by Alia itself (Qwen3.6-35B-A3B on an RTX 3070): one build session plus several correction rounds. All prompts are published alongside.</p>
```

### r4c: Architecture animation follows the connectors (17:30)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. The animated dots currently fly across box texts. They should travel only along the connectors and disappear behind the boxes. (T) In the svg with class "arch-svg": move the two <circle class="token-particle ..."> lines (below the comment "ANIMATED TOKEN FLOW") so they come directly after the comment "ROW 1: USER LAYER" (before all boxes, so the boxes cover them). Set the offset-path of the token-forward circle to path('M250,70 L290,170 L550,150 Q600,130 600,100 L840,100 L840,240 L720,300 L840,340 L900,340 L990,340') and of the token-backward circle to path('M990,340 L900,340 L840,340 L720,300 L840,240 L840,100 L600,100 Q600,130 550,150 L290,170 L250,70'). In the <style> block change the duration of both .token-forward and .token-backward animations from 2.4s to 5s.
```

### r4d: Request-flow animation follows the dashed line (17:38)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. The animated dots in the request flow fly across the box texts; they should travel along the dashed line and disappear behind the boxes. (U) In the svg with class "flow-svg": move the whole block below the comment "Animated tokens" (both <circle> elements with their animateMotion and both <path id="flowPath1"/"flowPath2"> elements) so it comes directly before the comment "Nodes". Set flowPath1 d to "M80,150 L1005,150" and flowPath2 d to "M1005,150 L80,150", set dur of both animateMotion to 4s and begin of the second one to 2s.
```

### r4e: Restore a lost label, phone scroll hint (17:43)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (V) In the svg with class "flow-svg" the first edge label got lost in the last round. Directly after the comment "Labels" insert: <text x="172.5" y="140" text-anchor="middle" fill="var(--fg3)" font-size="9" font-family="inherit">stdin</text> (W) On phones the two diagrams scroll sideways but nothing says so. Directly after the closing </div> of the div with class "arch-wrap" and directly after the closing </div> of the div with class "flow-wrap" insert <p class="scroll-hint">Swipe sideways to see the whole diagram →</p>. In the <style> block add .scroll-hint{display:none} and inside the @media(max-width:768px) block that contains .arch-wrap,.flow-wrap{overflow-x:auto} add .scroll-hint{display:block;margin-top:.5rem;font-size:.8rem;color:var(--fg3);text-align:right}
```

### r4f: Detail panel below the diagram (17:47)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (X) When the detail panel (div id="detailPanel") opens, it floats over the right half of the architecture diagram and covers the GPU/RAM box, which then can no longer be clicked. Show it below the diagram instead: replace the whole CSS rule that starts with .detail-panel{ (the one with position:absolute) by .detail-panel{position:relative;display:none;margin-top:1.25rem;background:var(--bg4);border:1px solid rgba(92,157,255,.2);border-radius:var(--radius);padding:1.25rem 1.5rem;box-shadow:var(--shadow)} and add right after it .detail-panel.open{display:block}. If there is a separate .detail-panel.open rule outside media queries that sets transform, delete it. Inside @media(max-width:768px) delete the two lines that start with .detail-panel{width:calc(100vw and .detail-panel.open{transform. Also give .detail-close the declarations position:absolute;top:.75rem;right:.75rem if it does not have them yet.
```

### r4g: Link to this file (17:50)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (Y) In the <footer>, in the paragraph that starts with "This page was written by Alia itself", turn the words "All prompts are published alongside." into a link: <a href="https://github.com/BEKO2210/alia/blob/main/site/showcase/architecture/PROMPTS.md">All prompts are published alongside.</a>
```

### r4h: Review findings: duplicate attribute, scoped benchmark claim (18:08)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (Z1) In the logo <svg> in the header, the <path fill="#0B0D12" ...> has two transform attributes. Delete the second one, transform="scale(1.6)", and keep transform="translate(145.8 350.8)". (Z2) In section id="benchmarks", the lead paragraph claims more than profiles.json says. Replace the text after the </code> element, which is " — measured on RTX 3070 8 GB, Ryzen 7 5800X, 16 GB RAM with llama.cpp commit a0e6dc7.", with " — speeds measured on RTX 3070 8 GB, Ryzen 7 5800X, 16 GB RAM with llama.cpp commit a0e6dc7 and each profile's launch flags. The 35B values at 60K come from an earlier run without --jinja; quality scores come from separate runs." (Z3) In the 35B card (the first card), add <div class="note">Separate run, server args not recorded</div> as the last child of the metric-item with label "Code Quality" and also of the metric-item with label "Tool Use". In the 9B card (the second card), add <div class="note">Measured via Ollama (not launch config)</div> as the last child of the metric-item with label "Tool Use".
```

### r4i: Review finding: keyboard access to the diagram (18:10)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. (K1) The diagram boxes cannot be used with a keyboard. In the svg with class "arch-svg", give each of the six <g class="arch-box" ...> elements the attributes tabindex="0" and role="button" and an aria-label: "User Terminal details", "Browser details", "Alia Launcher details", "Qwen Code details", "llama-server details", "GPU and RAM details" (match by data-detail: terminal, browser, launcher, qwen, server, hardware). (K2) In the <script>, inside the loop that adds the 'click' and 'mouseenter' listeners to each box, add a 'keydown' listener: if event.key is 'Enter' or ' ', call event.preventDefault() and box.dispatchEvent(new Event('click')). (K3) In the <style> block add .arch-box:focus{outline:none}.arch-box:focus-visible .box-bg{stroke:var(--cyan);stroke-width:2.5}
```

### r5: Re-measured 9B profile, on the 9B profile itself (2026-10-16, 21:24)

```text
In index.html make exactly these edits and nothing else, do not start any server. Work efficiently: locate each spot with grep -n and edit only those lines, do not read the whole file. When done, show the changed lines with git diff. The 9B profile was re-measured with a larger context, so update only the card that follows the comment <!-- Profile 2: 9B fast -->. (N1) Change the TG @ 4K value 66.1 to 65.7. (N2) Change the TG @ 32K value 57.7 to 57.5. (N3) Change the PP @ 4K value 2,980 to 2,978. (N4) Change the PP @ 32K value 2,707 to 2,708. (N5) Change the Context Window value 33,408 to 65,536.
```
