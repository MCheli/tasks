# UI Flows

This document describes every screen, interaction, and component behavior. It complements `FRONTEND_IMPLEMENTATION.md`, which covers the code structure.

## Design Language

- **Minimal, modern, Stripe/Linear-adjacent.** Lots of whitespace. Rounded corners (8–12px). Subtle shadows. System font stack (`-apple-system, BlinkMacSystemFont, ...`).
- **Mobile-first.** Layout tested at 375px first. Touch targets 44px min. No hover-only affordances — every action is tappable.
- **Desktop enhancements.** Keyboard shortcuts, denser spacing option, drag handles visible on hover.
- **Color.** Neutral grays for chrome. Accent color for primary CTAs (pick one and stick with it — suggested: indigo-500). Status colors: green for complete, gray for cancel, blue for open.
- **No emoji in icons.** Use Heroicons (outline style) or Lucide. Keep it professional.
- **Dark mode** is out of scope for v1. Design light-mode first. Use CSS variables so dark mode is a future drop-in.

## Routes

| Path | View | Auth |
|---|---|---|
| `/login` | `LoginView` | public |
| `/` | redirects to `/cycle` | — |
| `/cycle` | `CycleView` (current cycle for last-used category) | required |
| `/cycle/transition` | `TransitionView` | required |
| `/history` | `HistoryView` | required |
| `/cycle/:cycleId` | `CycleView` in read-only mode (historical cycle) | required |

All authenticated routes go through a route guard in `router/index.js` that checks the auth store. If unauthenticated, redirect to `/login` and preserve `?next=` for post-login return.

## Login (`LoginView`)

**Purpose:** Let the user sign in. Two mechanisms: Google SSO button (disabled with a tooltip "Set up by admin" until configured) and email/password.

**Layout:**
- Centered card, max-width 400px.
- App title at top ("Tasks").
- Email input, password input.
- Primary button "Sign in."
- Divider "or."
- Secondary button "Sign in with Google" (disabled state visually distinct).

**Interactions:**
- Enter in password field submits the form.
- Loading state on button during request.
- Inline error under the card on 401 ("Invalid email or password").
- On success, navigate to `/cycle` or `?next=` if provided.

## Main Cycle View (`CycleView`)

**Purpose:** The day-to-day surface. Fast, minimal, shows the current cycle's tasks. This is where the user lives 95% of the time.

### Layout (top to bottom)

1. **App header** — small, sticky.
   - Left: App title.
   - Center: Tab switcher (`Personal` / `Professional`). Active tab underlined in accent color.
   - Right: Icon buttons — History (clock icon), Logout (right-arrow icon). On mobile these collapse into a menu button.

2. **Current cycle meta** — one compact line.
   - Left: "Cycle started [relative date, e.g. '3 days ago']"
   - Right: "[N] open · [N] done · [N] canceled" (clickable, toggles visibility of completed/canceled groups).

3. **New task input** — an inline expandable card.
   - Collapsed state: single line input, placeholder "Add a task…", subtle border.
   - On focus / click: expands to show title input + notes textarea. Notes textarea is smaller, placeholder "Notes (optional)…"
   - Enter in title creates task, keeps focus in title for rapid entry.
   - Shift+Enter in title moves focus to notes.
   - Enter in notes creates task.
   - Escape collapses.

4. **Task list** — three groupings in this vertical order:
   - **Open tasks** (no header if there are any; header "No open tasks" if empty).
   - **Completed** (collapsible, header "Completed ([N])").
   - **Canceled** (collapsible, header "Canceled ([N])").

   Within each grouping, tasks are ordered by `position` ascending.

5. **Floating / bottom action** — "Start New Cycle" button.
   - Desktop: pinned to the bottom-right, elevated.
   - Mobile: full-width button fixed to the bottom of the viewport.
   - On click: navigate to `/cycle/transition`.

### Task Item (collapsed)

```
┌─────────────────────────────────────────────────────┐
│ [checkbox]  #42  Buy groceries                  ⋮   │
└─────────────────────────────────────────────────────┘
```

- Checkbox: toggles status between `open` and `completed`. Animates with a small checkmark draw-in.
- `#42`: the display ID, small muted gray text.
- Title: the main text; gets a strikethrough when completed.
- `⋮` (kebab menu): opens a small menu with "Cancel task" (sets status to `canceled`), "Delete" (soft delete, with a confirm dialog).
- Drag handle (left edge on desktop-hover; small grip icon on mobile): enables drag reorder.
- Entire row is clickable to expand (except checkbox and kebab, which have their own handlers).

### Task Item (expanded)

```
┌─────────────────────────────────────────────────────┐
│ [checkbox]  #42  [editable title]             ⋮   │
│                                                     │
│             [editable notes textarea]               │
│                                                     │
│             Created Apr 12 · 2 cycles · 1 push fwd │
│             [Save]  [Cancel]                        │
└─────────────────────────────────────────────────────┘
```

- Clicking the title again makes it editable inline.
- Notes field is a textarea.
- Metadata line shows created date, number of cycles the task has been part of, push-forward count.
- Save / Cancel buttons. Cmd+Enter saves. Esc cancels.
- Auto-save on blur is acceptable too — implementer's choice, document it in `DECISIONS.md`.

### Drag-and-Drop Reorder

- Uses `vuedraggable` (wrapper around SortableJS).
- On drop, send `POST /api/tasks/{id}/reorder` with the new position.
- Optimistic update: immediately reflect the new order in UI, revert and toast on error.
- Reorder is allowed within the "Open" group only. Completed and canceled groups are not reorderable.

### Completed / Canceled Visual Treatment

- Completed: green checkmark icon replaces checkbox. Title gets `text-gray-400 line-through`. Row background subtly muted.
- Canceled: red X icon. Title `text-gray-400 line-through`. Row more muted.

## Cycle Transition View (`TransitionView`)

**Purpose:** The weekly/whenever planning ritual. Let the user triage every open task into move-forward, complete, or cancel.

**Visual relationship to main view:** Intentionally similar layout. The transition view looks like the cycle view with the checkbox replaced by a three-state action picker.

### Layout (top to bottom)

1. **Header bar** — fixed at top.
   - Left: Back button ("Cancel transition" — returns to `/cycle` without changes).
   - Center: Title "New Cycle Planning — [Personal|Professional]"
   - Right: Primary button "Start New Cycle" (disabled until every open task has an action).

2. **Summary bar** — shows live counts as the user toggles.
   - `→ 5 carrying forward  ·  ✓ 2 completing  ·  ✗ 1 canceling`

3. **Task list.** Every open task from the current cycle is displayed. Completed and canceled tasks are hidden (they're already resolved).
   - Each row has a three-state toggle on the left: `→` (default, accent color), `✓` (green), `✗` (red).
   - Clicking the toggle cycles through the three states.
   - Alternative: each row has three small buttons side-by-side for the three states, highlighting the active one. Pick whichever is clearer — document in `DECISIONS.md`.

4. **Start New Cycle button** — at the bottom, primary color.
   - On click: confirm dialog "Start a new cycle? This will close the current one." (yes/no).
   - On confirm: `POST /api/cycles/{id}/transition`, navigate to `/cycle` which will now show the new cycle with forwarded tasks.

### Edge Cases

- If there are zero open tasks, show a message: "No open tasks to triage. Ready to start a new cycle?" with the Start button immediately available.
- If the request fails (network error, conflict), keep the user on the transition view with their selections intact, show a toast with the error.

## History View (`HistoryView`)

**Purpose:** Gantt-style visualization of task longevity and cycle history.

### Layout

1. **Header** with tab switcher and a "Back" button.
2. **Filter bar** (future): filter by status, by date range. v1 skips this — show everything.
3. **Gantt chart** — the main content.

### Gantt Specification

- **X-axis:** time, actual dates. Not cycle numbers. Scale so the full history fits, with a horizontal scroll if it's very long.
- **Y-axis:** one row per `persistent_task_id`, sorted by `first_seen_at` ascending (oldest tasks at top).
- **Row:** small label on the left with `#42 Buy groceries`. The bar stretches from `first_seen_at` to `last_seen_at`.
- **Segments within a bar:** each segment is one cycle's span for that task. Colored by `status_at_end`:
  - Open: blue (the task ended the cycle still open, i.e. it was forwarded or is currently open).
  - Completed: green.
  - Canceled: gray with strikethrough pattern.
- **Cycle boundaries:** light vertical gridlines at each cycle start/end across all rows — lets the user see "these tasks all lived through cycle N."
- **Today marker:** a subtle vertical line at the current date.

### Interactions

- **Hover on a bar segment:** tooltip with cycle dates, status at end, title, display ID.
- **Click on a bar segment:** navigate to the detail view or open a side panel with the full task lineage text.
- **Zoom** (future): pinch / scroll-wheel zoom on the timeline. v1 skips.

### Rendering Library

Recommended in order of preference:
1. Minimal hand-rolled SVG — if the team is <200 tasks total (likely for this app), an SVG with a few hundred rects is perfectly fast and gives full control.
2. `d3` — if more sophistication is needed.
3. Avoid off-the-shelf Gantt libs — they're heavy and opinionated.

## Mobile-Specific Considerations

- Tab switcher: ensure the active-tab indicator is obvious, not just bold text. Underline + slight background tint.
- Drag reorder on mobile: long-press activates drag mode. Show a subtle pulse animation on the task being dragged to make it clear it's "picked up."
- Floating "Start New Cycle" button: full-width at bottom, respects safe-area-inset-bottom.
- The kebab menu on tasks: taps open a small bottom sheet with action buttons (easier to hit than a tiny popover).
- Header condenses into a hamburger menu when viewport < 640px.

## Keyboard Shortcuts (Desktop)

| Shortcut | Action | Context |
|---|---|---|
| `n` | Focus new-task input | CycleView |
| `Enter` | Submit / save | Any input |
| `Shift+Enter` | Move between title → notes in new-task input | TaskInput |
| `Cmd/Ctrl+Enter` | Save expanded task edit | TaskItem expanded |
| `Esc` | Collapse / cancel | Any expanded element |
| `g c` | Go to Cycle view | Global |
| `g h` | Go to History view | Global |
| `?` | Show keyboard shortcut help overlay | Global |

Implement via a `useKeyboardShortcuts` composable. Don't fire shortcuts when an input/textarea is focused (except Enter/Esc/Cmd+Enter).

## Empty States

- Brand new user, first time on `/cycle`: auto-created empty cycle, friendly prompt "Add your first task above."
- No history yet: on `/history`, "No cycles yet. Add some tasks and start a cycle to see history here."

## Loading States

- Initial app load: brief skeleton for the task list (3 faded rows). Avoid spinners for the first render.
- Actions (create, update, reorder): optimistic UI; no spinner needed. Revert + toast on error.
- Navigation to history: loading skeleton for the Gantt area.

## Error Handling & Toasts

- Use a small toast library or roll a 30-line implementation: bottom-center, auto-dismiss after 4s, stackable.
- Network errors: "Couldn't save. Tap to retry." with a retry action.
- 401 during any request: clear auth, redirect to `/login`. Don't show a toast for this — the redirect is enough signal.

## Performance Targets

- First contentful paint < 1s on a warm load.
- Time to interactive < 2s on cold load.
- Task list scroll smoothly with 200+ tasks. If performance degrades past that, consider virtual scrolling — but only if measured.

## Accessibility

- All interactive elements have `:focus-visible` styles.
- Form inputs have associated labels.
- Task status changes announced via ARIA live region for screen readers.
- Keyboard-navigable: you can complete the entire "create, edit, complete, reorder, transition" flow without touching the mouse.
