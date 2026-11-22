"""Repair BTC Purchase Receipts split into several rows where only one row kept its Purchase Order link.

ERPNext counts "received" on a PO line from the receipt rows linked to it, so an unlinked row was never
counted (PO 2 BTC, receipts 0.5 + 0.5 -> a new receipt from the PO offered 1.5, not 1.0). Copy the link to
the unlinked BTC rows of each submitted receipt (only when the receipt's BTC rows point at exactly one PO
line), then recompute received_qty and the PO's receiving percentage and status. Idempotent.
"""

import frappe
from frappe.utils import flt


def execute():
	settings = frappe.get_cached_doc("GDL Setting")
	if not settings.btc_item:
		return

	touched_po_items = set()
	for receipt in frappe.get_all("Purchase Receipt", filters={"docstatus": 1}, pluck="name"):
		rows = frappe.get_all(
			"Purchase Receipt Item",
			filters={"parent": receipt, "item_code": settings.btc_item},
			fields=["name", "purchase_order", "purchase_order_item"],
		)
		linked = {r.purchase_order_item for r in rows if r.purchase_order_item}
		if len(linked) != 1 or all(r.purchase_order_item for r in rows):
			continue
		po_item = next(iter(linked))
		po = frappe.db.get_value("Purchase Order Item", po_item, "parent")
		if not po:
			continue
		for row in rows:
			if not row.purchase_order_item:
				frappe.db.set_value(
					"Purchase Receipt Item",
					row.name,
					{"purchase_order_item": po_item, "purchase_order": po},
					update_modified=False,
				)
		touched_po_items.add(po_item)

	touched_pos = set()
	for po_item in touched_po_items:
		received = flt(
			frappe.db.sql(
				"""select coalesce(sum(qty), 0) from `tabPurchase Receipt Item`
				where purchase_order_item=%s and docstatus=1""",
				po_item,
			)[0][0],
			9,
		)
		frappe.db.set_value("Purchase Order Item", po_item, "received_qty", received, update_modified=False)
		touched_pos.add(frappe.db.get_value("Purchase Order Item", po_item, "parent"))

	for name in touched_pos:
		po = frappe.get_doc("Purchase Order", name)
		po.update_receiving_percentage()
		po.set_status(update=True, update_modified=False)
