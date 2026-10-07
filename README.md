# Select Matching Instances Across Views

A **pyRevit** extension for **Revit 2024** that enhances Revit's native *"Select All Instances → Visible in View"* by letting you search across **multiple views** at once.

---

## How It Works

```
Pick one element  →  Choose views  →  Select
```

1. **Select one Family Instance** in your current Revit view.
2. **Click the tool** in the pyRevit ribbon (`Select Matching` tab → `Selection Tools` panel → `Select Matching`).
3. A dialog shows:
   - The reference element's **Category**, **Family**, and **Type**.
   - A searchable list of all project views, grouped by type.
4. **Check the views** you want to search (use Select All / Clear All as needed).
5. Click **Select** — the tool finds every instance of the same Family + Type across those views and selects them in Revit.

That's it. No complicated settings.

---

## Installation

### Option A — Copy to pyRevit extensions folder

1. Copy the entire `SelectMatchingInstances.extension` folder into your pyRevit extensions directory.
   - Default location: `%appdata%\pyRevit\Extensions\`
2. Reload pyRevit (pyRevit tab → Reload).

### Option B — Register as a custom extension directory

1. Place the `SelectMatchingInstances.extension` folder anywhere on your machine.
2. In Revit → pyRevit Settings → Custom Extension Directories → **Add** the parent folder (the folder *containing* `SelectMatchingInstances.extension`).
3. Reload pyRevit.

After reloading, you will see a new **Select Matching** tab in the Revit ribbon.

> **No administrator privileges, external packages, pip, or Visual Studio are required.**

---

## What "Matching" Means

The tool matches elements by their **exact Revit Type identity** — the same mechanism Revit uses internally for "Select All Instances".

Specifically, it compares:

| Criterion     | How it's checked                              |
| ------------- | --------------------------------------------- |
| **Category**  | `element.Category.Id == reference.Category.Id`|
| **Type**      | `element.GetTypeId() == reference.GetTypeId()`|

It does **not** match by display name strings, which can be duplicated across different families.

The search uses Revit's view-scoped `FilteredElementCollector(doc, view.Id)`, so results reflect the elements available through each selected view's collector.

---

## View Search Scope

The tool searches only the views you select. It uses:

```python
FilteredElementCollector(doc, view.Id)
```

This is Revit's standard view-scoped collector. It naturally respects many view-level settings, but it may not perfectly reproduce every pixel currently visible on screen (crop regions, temporary hide/isolate, certain filter combinations, etc.).

The tool **does not** modify views, change visibility, switch the active view, or start any transactions.

---

## Known V1 Limitations

| Limitation | Notes |
| --- | --- |
| **Family Instances only** | Walls, floors, roofs, rooms, and other non-FamilyInstance elements are not supported in V1. The tool shows a friendly message if you select one. |
| **Host document only** | Linked model elements are not searched or selected. |
| **No sheet support** | Sheets are not listed in the view selection dialog. |
| **No project-wide search** | You must select at least one view. |
| **View-scoped collector** | The tool relies on Revit's `FilteredElementCollector(doc, viewId)`. It does not build a custom visibility engine. |

---

## Debug Mode

Open `script.py` and change:

```python
DEBUG = False
```

to:

```python
DEBUG = True
```

This prints detailed diagnostics to the pyRevit output window:
- Reference element details (ID, category, family, type, type ID)
- Number of views selected
- Match count per view
- Total unique matches
- Errors and skipped views

---

## Extension Structure

```
SelectMatchingInstances.extension/
├── README.md
└── Select Matching.tab/
    └── Selection Tools.panel/
        └── Select Matching Across Views.pushbutton/
            ├── script.py
            └── SelectMatchingDialog.xaml
```

---

## Requirements

- **Revit 2024** (or compatible)
- **pyRevit** (any recent version with IronPython support)
- No external Python packages
- No administrator rights
