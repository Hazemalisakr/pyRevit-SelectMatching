# -*- coding: utf-8 -*-
"""Select Matching Instances Across Views.

Enhances Revit's native 'Select All Instances > Visible in View'
by allowing you to search across multiple views at once.

Pick one Family Instance, choose multiple views, and select
all matching Family + Type instances across those views.
"""

__title__ = "Select\nMatching"
__doc__ = (
    "Select one Element, choose multiple views, "
    "and select all matching Type instances across those views.\n\n"
    "Supports Family Instances, Tags, Text Notes, Dimensions, Lines, etc.\n\n"
    "1. Select one element in the current view\n"
    "2. Run this tool\n"
    "3. Choose views to search\n"
    "4. Matching elements are selected in Revit"
)
__author__ = "Sakr"

# ---------------------------------------------------------------------------
#  Debug flag  – set to True for verbose pyRevit output-window diagnostics
# ---------------------------------------------------------------------------
DEBUG = False

# ---------------------------------------------------------------------------
#  Imports
# ---------------------------------------------------------------------------
import os

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilyInstance,
    FamilySymbol,
    View,
    ViewType,
    ElementId,
)
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from System.Collections.Generic import List as NetList
from System.Windows import Visibility, Thickness, FontWeights
from System.Windows.Controls import TextBlock, CheckBox
from System.Windows.Media import SolidColorBrush, Color, FontFamily

from pyrevit import revit, forms, script

# ---------------------------------------------------------------------------
#  Revit hook objects
# ---------------------------------------------------------------------------
doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
ALLOWED_VIEW_TYPES = frozenset([
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.Elevation,
    ViewType.Section,
    ViewType.ThreeD,
    ViewType.DraftingView,
    ViewType.AreaPlan,
    ViewType.Detail,
    ViewType.EngineeringPlan,
])

VIEW_TYPE_SORT = {
    ViewType.FloorPlan:       0,
    ViewType.CeilingPlan:     1,
    ViewType.AreaPlan:        2,
    ViewType.EngineeringPlan: 3,
    ViewType.Elevation:       4,
    ViewType.Section:         5,
    ViewType.Detail:          6,
    ViewType.ThreeD:          7,
    ViewType.DraftingView:    8,
}

VIEW_TYPE_LABEL = {
    ViewType.FloorPlan:       "Floor Plans",
    ViewType.CeilingPlan:     "Ceiling Plans",
    ViewType.AreaPlan:        "Area Plans",
    ViewType.EngineeringPlan: "Structural Plans",
    ViewType.Elevation:       "Elevations",
    ViewType.Section:         "Sections",
    ViewType.Detail:          "Detail Views",
    ViewType.ThreeD:          "3D Views",
    ViewType.DraftingView:    "Drafting Views",
}


# ---------------------------------------------------------------------------
#  Utility
# ---------------------------------------------------------------------------

def debug(msg):
    """Print to the pyRevit output window only when DEBUG is True."""
    if DEBUG:
        print("[DEBUG] {}".format(msg))


# ====================================================================== #
#  STEP 1 — Get reference element                                        #
# ====================================================================== #

def get_reference_element():
    """Return exactly one element from the current selection or a user pick.

    Returns:
        Element or None.  Exits the script cleanly when the user cancels.
    """
    sel_ids = list(uidoc.Selection.GetElementIds())

    # --- Exactly one element already selected ---
    if len(sel_ids) == 1:
        elem = doc.GetElement(sel_ids[0])
        debug("Using currently selected element: Id={}".format(elem.Id))
        return elem

    # --- Multiple elements selected ---
    if len(sel_ids) > 1:
        forms.alert(
            "Multiple elements are selected.\n\n"
            "Please select exactly one Family Instance "
            "to use as the matching reference.",
            title="Select Matching Instances",
            exitscript=True,
        )

    # --- Nothing selected — ask the user to pick one element ---
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.Element,
            "Select one element as the matching reference",
        )
        return doc.GetElement(ref.ElementId)
    except OperationCanceledException:
        # User pressed Escape — exit without an error trace
        script.exit()
    except Exception:
        script.exit()


# ====================================================================== #
#  STEP 2 — Extract reference info                                       #
# ====================================================================== #

def get_reference_info(element):
    """Return a dict describing the element's family + type identity.

    Returns:
        dict  – keys: category, family, type_name, type_id, category_id,
                      element_id
        None  – if the element does not have a valid category.
    """
    if element.Category is None:
        return None

    type_id = element.GetTypeId()
    type_elem = doc.GetElement(type_id)

    cat_name = element.Category.Name or ""
    cat_id = element.Category.Id

    fam_name = ""
    type_name = ""

    # Family / type names
    if isinstance(type_elem, FamilySymbol):
        fam = type_elem.Family
        try:
            fam_name = fam.Name if fam else cat_name
        except Exception:
            fam_name = cat_name
        try:
            type_name = type_elem.Name or ""
        except Exception:
            type_name = ""
    elif type_elem:
        # System families (TextNoteType, DimensionType, GraphicsStyle, etc.)
        try:
            fam_name = getattr(type_elem, "FamilyName", cat_name)
        except Exception:
            fam_name = cat_name
            
        try:
            type_name = type_elem.Name or ""
        except Exception:
            type_name = ""
    else:
        # Fallback
        fam_name = cat_name
        try:
            type_name = element.Name or ""
        except Exception:
            type_name = ""

    info = dict(
        category=cat_name,
        family=fam_name,
        type_name=type_name,
        type_id=type_id,
        category_id=cat_id,
        element_id=element.Id,
    )

    debug("Reference info:")
    for k, v in info.items():
        debug("  {} = {}".format(k, v))

    return info


# ====================================================================== #
#  STEP 3a — Gather usable views                                         #
# ====================================================================== #

def get_available_views():
    """Return a sorted list of (View, group_label, sort_key, view_name).

    Only views appropriate for a view-scoped FilteredElementCollector are
    included.  Templates, sheets, schedules, legends, etc. are excluded.
    """
    collector = (
        FilteredElementCollector(doc)
        .OfClass(View)
        .WhereElementIsNotElementType()
    )

    results = []
    for v in collector:
        try:
            if v.IsTemplate:
                continue
            vt = v.ViewType
            if vt not in ALLOWED_VIEW_TYPES:
                continue
            if v.Id == ElementId.InvalidElementId:
                continue

            label = VIEW_TYPE_LABEL.get(vt, "Other")
            sort_key = VIEW_TYPE_SORT.get(vt, 99)
            name = v.Name or "(Unnamed)"
            results.append((v, label, sort_key, name))
        except Exception:
            # Some unusual view sub-classes may not support .ViewType, etc.
            continue

    results.sort(key=lambda x: (x[2], x[3]))
    debug("Available views: {}".format(len(results)))
    return results


# ====================================================================== #
#  STEP 3b — View selection WPF dialog                                   #
# ====================================================================== #

class ViewSelectionDialog(forms.WPFWindow):
    """WPF dialog for choosing which views to search."""

    # Resolve XAML path relative to this script file
    try:
        _XAML = script.get_bundle_file("SelectMatchingDialog.xaml")
    except Exception:
        _XAML = os.path.join(
            os.path.dirname(__file__), "SelectMatchingDialog.xaml"
        )

    def __init__(self, ref_info, view_data):
        """
        Args:
            ref_info:  dict from get_reference_info()
            view_data: list from get_available_views()
        """
        forms.WPFWindow.__init__(self, self._XAML)
        self.ref_info = ref_info
        self.all_view_data = view_data
        self.selected_views = None        # populated on "Select" click
        self._checkboxes = []             # (CheckBox, group_label, view_name)
        self._group_headers = []          # TextBlock group headers

        self._setup_reference_info()
        self._populate_view_list()
        self._update_counts()
        self._wire_events()

    # ---- UI setup --------------------------------------------------------

    def _setup_reference_info(self):
        self.tb_category.Text = "Category:   {}".format(
            self.ref_info.get("category", "\u2014")
        )
        self.tb_family.Text = "Family:   {}".format(
            self.ref_info.get("family", "\u2014")
        )
        self.tb_type.Text = "Type:   {}".format(
            self.ref_info.get("type_name", "\u2014")
        )

    def _populate_view_list(self):
        panel = self.sp_views
        panel.Children.Clear()
        self._checkboxes = []
        self._group_headers = []

        current_group = None
        for view_obj, group_label, _sort, view_name in self.all_view_data:
            # Insert a group header when the group changes
            if group_label != current_group:
                current_group = group_label
                hdr = TextBlock()
                hdr.Text = group_label.upper()
                hdr.FontWeight = FontWeights.Bold
                hdr.FontSize = 11.0
                # #4C2335
                hdr.Foreground = SolidColorBrush(Color.FromRgb(76, 35, 53))
                hdr.FontFamily = FontFamily("Segoe UI")
                hdr.Margin = Thickness(0, 12, 0, 6)
                hdr.Tag = group_label
                panel.Children.Add(hdr)
                self._group_headers.append(hdr)

            cb = CheckBox()
            cb.Content = view_name
            cb.Tag = view_obj        # store the Revit View object
            cb.Margin = Thickness(16, 3, 0, 3)
            cb.FontSize = 13.0
            # #3B332E
            cb.Foreground = SolidColorBrush(Color.FromRgb(59, 51, 46))
            cb.FontFamily = FontFamily("Segoe UI")
            cb.Checked += self._on_cb_changed
            cb.Unchecked += self._on_cb_changed
            panel.Children.Add(cb)
            self._checkboxes.append((cb, group_label, view_name))

    def _wire_events(self):
        self.txt_search.TextChanged += self._on_search
        self.btn_select_all.Click += self._on_select_all
        self.btn_clear_all.Click += self._on_clear_all
        self.btn_select.Click += self._on_select
        self.btn_cancel.Click += self._on_cancel

    # ---- Events ----------------------------------------------------------

    def _on_search(self, sender, args):
        """Filter the visible checkboxes and group headers by search text."""
        query = (self.txt_search.Text or "").strip().lower()
        visible_groups = set()

        for cb, grp, name in self._checkboxes:
            if not query or query in name.lower():
                cb.Visibility = Visibility.Visible
                visible_groups.add(grp)
            else:
                cb.Visibility = Visibility.Collapsed

        for hdr in self._group_headers:
            hdr.Visibility = (
                Visibility.Visible
                if hdr.Tag in visible_groups
                else Visibility.Collapsed
            )
        self._update_counts()

    def _on_select_all(self, sender, args):
        """Check all currently visible checkboxes."""
        for cb, _g, _n in self._checkboxes:
            if cb.Visibility == Visibility.Visible:
                cb.IsChecked = True
        self._update_counts()

    def _on_clear_all(self, sender, args):
        """Uncheck every checkbox."""
        for cb, _g, _n in self._checkboxes:
            cb.IsChecked = False
        self._update_counts()

    def _on_cb_changed(self, sender, args):
        self._update_counts()

    def _update_counts(self):
        checked = sum(1 for cb, g, n in self._checkboxes if cb.IsChecked)
        visible = sum(
            1 for cb, g, n in self._checkboxes
            if cb.Visibility == Visibility.Visible
        )
        self.tb_count.Text = "{} of {} views selected".format(checked, visible)
        self.tb_status.Text = "{} view{} selected".format(
            checked, "s" if checked != 1 else ""
        )

    def _on_select(self, sender, args):
        chosen = [cb.Tag for cb, g, n in self._checkboxes if cb.IsChecked]
        if not chosen:
            forms.alert(
                "Please select at least one view.",
                title="Select Matching Instances",
            )
            return
        self.selected_views = chosen
        self.Close()

    def _on_cancel(self, sender, args):
        self.selected_views = None
        self.Close()


def show_view_selection_dialog(ref_info, view_data):
    """Open the view-selection dialog.

    Returns:
        list[View] – views the user checked, or None if cancelled.
    """
    dialog = ViewSelectionDialog(ref_info, view_data)
    dialog.ShowDialog()
    return dialog.selected_views


# ====================================================================== #
#  STEP 4 — Collect matching instances per view                          #
# ====================================================================== #

def collect_matching_elements(selected_views, ref_type_id, ref_category_id, is_view_specific):
    """Search for matching instances.
    
    If the element is view-specific (2D annotation), we use a global collector 
    and filter by OwnerViewId to bypass expensive graphical view regenerations.
    Otherwise, we must use view-scoped collectors for 3D elements.
    """
    matching_ids = set()
    views_processed = 0
    errors = []

    if is_view_specific:
        # FAST PATH FOR ANNOTATIONS / 2D ELEMENTS
        # Bypasses "Regenerating Graphics" entirely.
        selected_view_ids = {v.Id for v in selected_views}
        
        try:
            collector = (
                FilteredElementCollector(doc)
                .OfCategoryId(ref_category_id)
                .WhereElementIsNotElementType()
            )
            
            for elem in collector:
                if elem.OwnerViewId in selected_view_ids and elem.GetTypeId() == ref_type_id:
                    matching_ids.add(elem.Id)
            
            views_processed = len(selected_views)
            debug("Used global collector for view-specific elements.")
        except Exception as ex:
            errors.append("Global collection error: {}".format(ex))
            
    else:
        # STANDARD PATH FOR 3D MODEL ELEMENTS
        for view in selected_views:
            try:
                collector = (
                    FilteredElementCollector(doc, view.Id)
                    .OfCategoryId(ref_category_id)
                    .WhereElementIsNotElementType()
                )

                view_match_count = 0
                for elem in collector:
                    if elem.GetTypeId() != ref_type_id:
                        continue
                    matching_ids.add(elem.Id)
                    view_match_count += 1

                views_processed += 1
                debug("  View '{}' (Id={}): {} matches".format(
                    view.Name, view.Id, view_match_count
                ))

            except Exception as ex:
                msg = "Error processing view '{}': {}".format(
                    getattr(view, "Name", "?"), ex
                )
                debug(msg)
                errors.append(msg)

    debug("Total unique matches: {}".format(len(matching_ids)))
    return matching_ids, views_processed, errors


# ====================================================================== #
#  STEP 5 — Set Revit selection                                          #
# ====================================================================== #

def select_elements_in_revit(element_ids):
    """Replace the current Revit selection with the given ElementIds.

    No transaction is required — this is purely a UI selection operation.

    Returns:
        int – number of elements selected.
    """
    if not element_ids:
        return 0

    # Convert the Python set to a .NET generic List<ElementId>
    id_list = NetList[ElementId](list(element_ids))
    uidoc.Selection.SetElementIds(id_list)
    return id_list.Count


# ====================================================================== #
#  STEP 6 — Result reporting                                             #
# ====================================================================== #

def show_result(ref_info, views_searched, found, selected, errors):
    """Display a concise result summary via a pyRevit alert dialog."""

    ref_str = "{}  \u2014  {} : {}".format(
        ref_info["category"],
        ref_info["family"],
        ref_info["type_name"],
    )

    if found == 0:
        lines = [
            "No matching instances were found in the selected views.",
            "",
            "Reference:",
            ref_str,
            "",
            "Views searched:  {}".format(views_searched),
        ]
    else:
        lines = [
            "Reference:",
            ref_str,
            "",
            "Views searched:  {}".format(views_searched),
            "Matching instances found:  {}".format(found),
            "Selected:  {}".format(selected),
        ]
        if found != selected:
            lines.append("Skipped:  {}".format(found - selected))

    if errors:
        lines.append("")
        lines.append("Warnings:  {} view(s) skipped due to errors".format(
            len(errors)
        ))
        if DEBUG:
            for e in errors:
                lines.append("  \u2022 {}".format(e))

    forms.alert("\n".join(lines), title="Select Matching Instances")


# ====================================================================== #
#  Main entry point                                                      #
# ====================================================================== #

def main():
    debug("=== Select Matching Instances Across Views ===")

    # ---- Step 1: Get the reference element ----
    ref_element = get_reference_element()
    if ref_element is None:
        return

    # ---- Step 2: Validate it has a valid category & extract info ----
    ref_info = get_reference_info(ref_element)
    if ref_info is None:
        forms.alert(
            "The selected element does not have a valid category.\n\n"
            "This tool requires an element with a valid category (e.g. Doors, Tags, Text, Lines, etc.).",
            title="Select Matching Instances",
        )
        return

    debug("Category : {}".format(ref_info["category"]))
    debug("Family   : {}".format(ref_info["family"]))
    debug("Type     : {}".format(ref_info["type_name"]))
    debug("Type ID  : {}".format(ref_info["type_id"]))
    debug("Elem ID  : {}".format(ref_info["element_id"]))

    # ---- Step 3: Show the view-selection dialog ----
    view_data = get_available_views()
    if not view_data:
        forms.alert(
            "No usable views were found in the current document.",
            title="Select Matching Instances",
        )
        return

    selected_views = show_view_selection_dialog(ref_info, view_data)
    if not selected_views:
        debug("User cancelled or selected no views.")
        return

    debug("Views selected: {}".format(len(selected_views)))

    # ---- Step 4: Collect matching elements across selected views ----
    matching_ids, views_ok, errors = collect_matching_elements(
        selected_views,
        ref_info["type_id"],
        ref_info["category_id"],
        ref_element.ViewSpecific
    )

    # ---- Step 5: Set the Revit selection ----
    selected_count = select_elements_in_revit(matching_ids)

    # ---- Step 6: Show result summary ----
    show_result(ref_info, views_ok, len(matching_ids), selected_count, errors)


# ---------------------------------------------------------------------------
#  Execute
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
