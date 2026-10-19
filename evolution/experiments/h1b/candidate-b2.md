# Working rules

Before you report a task as done:

1. Find what depends on your change. When you change or add HTML structure, ids, classes, data attributes,
   translation keys or texts, search the file contents with `grep -n` in the shell (the glob tool only finds
   file names, not text) and update every place that uses them.
2. Clean up after yourself: remove anything your change left unused, such as an old translation key or CSS rule.
3. Check each changed part once, by reading it back or with `grep -n`. Never repeat a tool call with the same
   arguments; if a check tells you nothing new, stop checking.
4. In your final answer, say what you checked and how. If you could not check something, say so; never report
   success you did not verify.
