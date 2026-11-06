"""Cost Center auto-fill and BTC stock rules for stock transactions.

Wired via hooks.py's doc_events (validate) on Stock Entry, Sales Invoice,
Delivery Note, Purchase Receipt and Stock Reconciliation; the live form-side
auto-fill (public/js/btc_cost_center.js) calls get_row_cost_center below, so
the browser and the server resolve a cost center identically.

Cost Center on a row comes from its Zone (Internal Zone.default_cost_center),
falling back to its warehouse (Warehouse.custom_cost_center). BTC rows - when
GDL Setting.enable_btc_rules is on - must always follow the Zone, because the
row's cost center is what drives the site-wise P&L. Other rows are only
overwritten while still blank or at the company default, so an explicit
choice on a non-BTC row survives.
"""

import frappe
from frappe import _
from frappe.utils import flt

TAGGED_DOCTYPES = {
	"Stock Entry",
	"Sales Invoice",
	"Delivery Note",
	"Purchase Receipt",
	"Stock Reconciliation",
}

# Stock Entry rows carry a source tag (zone/wallet) and a target tag
# (to_zone/to_wallet); every other doctype only has the one tag.
FIELD_LABELS = {
	"zone": "Source Zone",
	"to_zone": "Target Zone",
	"wallet": "Source Wallet",
	"to_wallet": "Target Wallet",
}

REQUIRED_TAGS = {
	"in": ("to_zone", "to_wallet"),
	"out": ("zone", "wallet"),
	"transfer": ("zone", "to_zone", "wallet", "to_wallet"),
	"single": ("zone", "wallet"),
}


def apply_btc_rules_and_cost_centers(doc, method=None):
	settings = frappe.get_single("GDL Setting")
	company_cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")

	for row in doc.get("items") or []:
		ctx = _row_context(doc.doctype, doc.get("purpose"), row)
		if not ctx:
			continue

		is_btc = bool(settings.enable_btc_rules and settings.btc_item and row.item_code == settings.btc_item)
		if is_btc:
			_validate_btc_row(settings, row, ctx)

		cost_center = resolve_cost_center(ctx)
		if is_btc and not cost_center:
			frappe.throw(
				_("Row #{0}: Zone {1} has no Default Cost Center and its warehouse has none either.").format(
					row.idx, ctx["cc_zone"] or ""
				)
			)

		if cost_center and (is_btc or not row.cost_center or row.cost_center == company_cost_center):
			row.cost_center = cost_center


@frappe.whitelist()
def get_row_cost_center(parent_doctype, row, purpose=None):
	"""Cost center for one stock row, for the form-side auto-fill."""
	if parent_doctype not in TAGGED_DOCTYPES:
		return None

	ctx = _row_context(parent_doctype, purpose, frappe._dict(frappe.parse_json(row)))
	return resolve_cost_center(ctx) if ctx else None


def resolve_cost_center(ctx):
	if ctx["cc_zone"]:
		cost_center = frappe.get_cached_value("Internal Zone", ctx["cc_zone"], "default_cost_center")
		if cost_center:
			return cost_center

	if ctx["cc_warehouse"]:
		return frappe.get_cached_value("Warehouse", ctx["cc_warehouse"], "custom_cost_center")


def _row_context(parent_doctype, purpose, row):
	"""Normalise a stock row of any tagged doctype to one shape.

	kind is in/out/transfer for Stock Entry (decided by which warehouses the
	row has, not by purpose, so Repack/Manufacture rows work too) and single
	for every doctype that has just one zone/wallet tag. The cost center
	follows the target side of an in/transfer row and the source side of an
	out row.
	"""
	if parent_doctype == "Stock Entry":
		source, target = row.get("s_warehouse"), row.get("t_warehouse")
		if source and target:
			kind = "transfer"
		elif target:
			kind = "in"
		elif source:
			kind = "out"
		else:
			return None

		follows_target = kind in ("in", "transfer")
		return {
			"kind": kind,
			"warehouses": [w for w in (source, target) if w],
			"row": row,
			"cc_zone": row.get("to_zone") if follows_target else row.get("zone"),
			"cc_warehouse": target if follows_target else source,
		}

	warehouse = row.get("warehouse")
	if not warehouse:
		return None

	return {
		"kind": "single",
		"warehouses": [warehouse],
		"row": row,
		"cc_zone": row.get("zone"),
		"cc_warehouse": warehouse,
	}


BTC_QTY_DECIMALS = 8  # 1 satoshi


def _validate_btc_row(settings, row, ctx):
	for fieldname in ("qty", "custom_fee_qty"):
		qty = flt(row.get(fieldname))
		if qty and flt(qty, BTC_QTY_DECIMALS) != flt(qty, 9):
			frappe.throw(
				_("Row #{0}: BTC quantity {1} has more than {2} decimal places.").format(
					row.idx, qty, BTC_QTY_DECIMALS
				)
			)

	if settings.btc_warehouse:
		for warehouse in ctx["warehouses"]:
			if warehouse != settings.btc_warehouse:
				frappe.throw(
					_("Row #{0}: BTC must be held in warehouse {1}, not {2}.").format(
						row.idx, settings.btc_warehouse, warehouse
					)
				)

	for fieldname in REQUIRED_TAGS[ctx["kind"]]:
		if not row.get(fieldname):
			frappe.throw(_("Row #{0}: {1} is mandatory for BTC.").format(row.idx, FIELD_LABELS[fieldname]))

	if ctx["kind"] == "transfer" and settings.require_zonewallet_change_on_transfer:
		if row.zone == row.to_zone and row.wallet == row.to_wallet:
			frappe.throw(_("Row #{0}: A BTC transfer must change the Zone or the Wallet.").format(row.idx))
