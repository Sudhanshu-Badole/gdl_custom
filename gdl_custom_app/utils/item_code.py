"""Item codes from the Item Group's Group Code: <CODE>-00001, <CODE>-00002, ...
Fixed Asset items get an extra prefix: AST-<CODE>-00001.

Runs on before_insert, which Frappe calls just before naming, so ERPNext's
Item.autoname (name = item_code) picks up the generated code. Item Groups
without a Group Code keep the standard behaviour (user-entered Item Code).
"""

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint

DIGITS = 5
ASSET_PREFIX = "AST"


def get_group_code(item_group):
	if not item_group:
		return None
	code = frappe.db.get_value("Item Group", item_group, "custom_group_code")
	return (code or "").strip().upper() or None


def get_prefix(item_group, is_fixed_asset=0):
	"""STN for a stock item, AST-FUR for a fixed asset; None if the group has no code."""
	code = get_group_code(item_group)
	if not code:
		return None
	if cint(is_fixed_asset) and not code.startswith(f"{ASSET_PREFIX}-"):
		code = f"{ASSET_PREFIX}-{code}"
	return code


def set_item_code(doc, method=None):
	"""before_insert: assign the next code in the Item Group's series."""
	if doc.variant_of:
		return  # variants follow the template's code
	code = get_prefix(doc.item_group, doc.is_fixed_asset)
	if not code:
		return

	# make_autoname uses the locked tabSeries counter, so concurrent saves never clash.
	item_code = make_autoname(f"{code}-.{'#' * DIGITS}", "Item")
	if frappe.db.exists("Item", item_code):
		frappe.throw(
			_("Item {0} already exists. Set the Current Value of series {1} in Naming Series above the highest existing number.").format(
				item_code, f"{code}-"
			)
		)
	doc.item_code = item_code
	if not doc.item_name:
		doc.item_name = item_code


@frappe.whitelist()
def get_item_code_prefix(item_group, is_fixed_asset=0):
	return get_prefix(item_group, is_fixed_asset)
