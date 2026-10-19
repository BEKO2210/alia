# Working rules

Before you report a task as done:

1. Find what depends on your change. When you change HTML structure, ids, classes, data attributes or
   translation keys, search the code (for example `grep -rn`) for every place that uses them and update those
   places too.
2. Check the result instead of assuming it. Run the project's existing tests or checks if there are any, and
   read the changed parts of the files once more.
3. In your final answer, say what you checked and how. If you could not check something, say so; never report
   success you did not verify.
