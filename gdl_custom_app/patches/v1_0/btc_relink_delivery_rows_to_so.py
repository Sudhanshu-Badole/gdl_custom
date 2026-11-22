"""Repair BTC Delivery Notes split into several rows where only one row kept its Sales Order link.

ERPNext counts "delivered" on a SO line from the delivery rows linked to it, so an unlinked row was never
counted (SO 3 BTC, delivered 1 + 0.5 + 1.5 -> the order still offered more). Copy the link to the unlinked
BTC rows of each submitted delivery note (only when the note's BTC rows point at exactly one SO line), then
recompute delivered_qty and the SO's delivery percentage and status. Idempotent.
"""

import frappe
from frappe.utils import flt


def execute():
	settings = frappe.get_cached_doc("GDL Setting")
	if not settings.btc_item:
		return

	touched_so_items = set()
	for note in frappe.get_all("Delivery Note", filters={"docstatus": 1, "is_return": 0}, pluck="name"):
		rows = frappe.get_all(
			"Delivery Note Item",
			filters={"parent": note, "item_code": settings.btc_item},
			fields=["name", "against_sales_order", "so_detail"],
		)
		linked = {r.so_detail for r in rows if r.so_detail}
		if len(linked) != 1 or all(r.so_detail for r in rows):
			continue
		so_detail = next(iter(linked))
		so = frappe.db.get_value("Sales Order Item", so_detail, "parent")
		if not so:
			continue
		for row in rows:
			if not row.so_detail:
				frappe.db.set_value(
					"Delivery Note Item",
					row.name,
					{"so_detail": so_detail, "against_sales_order": so},
					update_modified=False,
				)
		touched_so_items.add(so_detail)

	touched_sos = set()
	for so_detail in touched_so_items:
		delivered = flt(
			frappe.db.sql(
				"""select coalesce(sum(i.qty), 0) from `tabDelivery Note Item` i
				join `tabDelivery Note` d on d.name = i.parent
				where i.so_detail=%s and i.docstatus=1 and d.is_return=0""",
				so_detail,
			)[0][0],
			9,
		)
		frappe.db.set_value("Sales Order Item", so_detail, "delivered_qty", delivered, update_modified=False)
		touched_sos.add(frappe.db.get_value("Sales Order Item", so_detail, "parent"))

	for name in touched_sos:
		so = frappe.get_doc("Sales Order", name)
		so.update_delivery_status()
		so.set_status(update=True, update_modified=False)
