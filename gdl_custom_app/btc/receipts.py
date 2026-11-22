"""BTC receipt rules (Mining / Premium Received / Put Exercised / Purchase) and
posting of the custom USD valuation ledger from stock documents.

BTN stock valuation and GL stay with ERPNext's standard Stock Ledger / GL
lifecycle. Here we only (a) turn the USD rate entered on a receipt into the BTN
basic_rate that ERPNext values the stock at, and (b) mirror each submitted BTC
row into the USD ledger once, reversing it on cancel.
"""

import frappe
from frappe import _
from frappe.utils import flt

from gdl_custom_app.btc import usd_valuation
from gdl_custom_app.btc.exchange import get_usd_rate

# Stock Entry Type name -> GDL Setting field holding its income account.
RECEIPT_TYPES = {
	"Mining": "mining_income_account",
	"Premium Received": "premium_income_account",
	"Put Exercised": "put_exercised_account",
}

# "BTC ..." Stock Entry Types follow the same rules as the plain ones, and are recorded in the
# USD ledger / reports under the canonical name.
RECEIPT_TYPE_ALIASES = {f"BTC {name}": name for name in RECEIPT_TYPES}
RECEIPT_TYPES.update({alias: RECEIPT_TYPES[name] for alias, name in RECEIPT_TYPE_ALIASES.items()})


def get_settings():
	return frappe.get_cached_doc("GDL Setting")


def is_btc_row(settings, row):
	return bool(settings.enable_btc_rules and settings.btc_item and row.item_code == settings.btc_item)


def prepare_stock_entry(doc, method=None):
	"""before_validate: default the BTC warehouse; for BTC receipt types also derive
	the BTN rate and income account."""
	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	set_default_warehouses(doc, settings)
	if doc.stock_entry_type not in RECEIPT_TYPES:
		return

	if doc.purpose != "Material Receipt":
		frappe.throw(_("Stock Entry Type {0} must have the purpose Material Receipt.").format(doc.stock_entry_type))

	rate = get_usd_rate(doc.posting_date, "for_buying", doc.company)
	doc.custom_usd_btn_rate = rate

	account = settings.get(RECEIPT_TYPES[doc.stock_entry_type])
	if not account:
		frappe.throw(
			_("Set the income account for {0} receipts in GDL Setting.").format(doc.stock_entry_type)
		)

	for row in doc.items:
		if not is_btc_row(settings, row):
			continue
		if flt(row.get("custom_usd_rate")) <= 0:
			frappe.throw(_("Row #{0}: USD Rate must be greater than zero.").format(row.idx))
		row.basic_rate = flt(row.custom_usd_rate) * rate
		row.allow_zero_valuation_rate = 0
		row.expense_account = account


# Stock Entry purpose -> warehouse fields a BTC row needs.
PURPOSE_WAREHOUSE_FIELDS = {
	"Material Receipt": ("t_warehouse",),
	"Material Issue": ("s_warehouse",),
	"Material Transfer": ("s_warehouse", "t_warehouse"),
}


def set_default_warehouses(doc, settings):
	"""Fill blank warehouse fields on BTC rows with GDL Setting's BTC warehouse."""
	fields = PURPOSE_WAREHOUSE_FIELDS.get(doc.purpose)
	if not fields or not settings.btc_warehouse:
		return
	for row in doc.get("items") or []:
		if is_btc_row(settings, row):
			for field in fields:
				if not row.get(field):
					row.set(field, settings.btc_warehouse)


@frappe.whitelist()
def get_btc_defaults():
	"""BTC item and warehouse for the form-side warehouse auto-fill."""
	settings = get_settings()
	if not settings.enable_btc_rules:
		return {}
	return {"item": settings.btc_item, "warehouse": settings.btc_warehouse}


def validate_receipt(doc, method=None):
	"""validate: quantity, zone/wallet state and receipt-type consistency."""
	settings = get_settings()
	if not settings.enable_btc_rules:
		return

	for row in doc.get("items") or []:
		if not is_btc_row(settings, row):
			continue
		if flt(row.qty) <= 0:
			frappe.throw(_("Row #{0}: BTC quantity must be greater than zero.").format(row.idx))
		for zone_field in ("zone", "to_zone"):
			validate_zone_active(row, row.get(zone_field))
		for wallet_field in ("wallet", "to_wallet"):
			validate_wallet(row, row.get(wallet_field), doc.company)

	if doc.get("purpose") == "Material Receipt":
		first_row = {}
		for row in doc.get("items") or []:
			if not is_btc_row(settings, row) or not row.get("to_wallet"):
				continue
			key = (row.get("to_zone"), row.to_wallet)
			if key in first_row:
				frappe.throw(
					_("Row #{0}: Wallet {1} in Zone {2} is already on row #{3}. Add the quantity to that row instead.").format(
						row.idx, row.to_wallet, row.get("to_zone"), first_row[key]
					)
				)
			first_row[key] = row.idx


def validate_zone_active(row, zone):
	if zone and not frappe.get_cached_value("Internal Zone", zone, "is_active"):
		frappe.throw(_("Row #{0}: Zone {1} is inactive.").format(row.idx, zone))


def validate_wallet(row, wallet, company):
	if not wallet:
		return
	active, wallet_company = frappe.get_cached_value("BTC Wallet", wallet, ["is_active", "company"])
	if not active:
		frappe.throw(_("Row #{0}: Wallet {1} is inactive.").format(row.idx, wallet))
	if wallet_company != company:
		frappe.throw(_("Row #{0}: Wallet {1} belongs to {2}, not {3}.").format(row.idx, wallet, wallet_company, company))


def validate_purchase_receipt(doc, method=None):
	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	for row in doc.items:
		if not is_btc_row(settings, row):
			continue
		if settings.btc_warehouse:
			row.warehouse = settings.btc_warehouse
		if doc.currency != usd_valuation_currency():
			frappe.throw(_("Row #{0}: a BTC Purchase Receipt must be in USD.").format(row.idx))
		if row.get("purchase_order") and not row.get("zone"):
			row.zone = frappe.db.get_value("Purchase Order", row.purchase_order, "custom_zone")
		validate_zone_active(row, row.get("zone"))
		validate_wallet(row, row.get("wallet"), doc.company)
	link_receipt_rows_to_purchase_order(doc, settings)
	reject_duplicate_zone_wallet_rows(doc, settings)
	validate_receipt_against_purchase_order(doc, settings)


def reject_duplicate_zone_wallet_rows(doc, settings):
	"""One row per Zone + Wallet: a second row for the same pair must be added to the first row's quantity."""
	first_row = {}
	for row in doc.items:
		if not is_btc_row(settings, row) or not row.get("wallet"):
			continue
		key = (row.get("zone"), row.wallet)
		if key in first_row:
			frappe.throw(
				_("Row #{0}: Wallet {1} in Zone {2} is already on row #{3}. Update the quantity on that row instead.").format(
					row.idx, row.wallet, row.get("zone"), first_row[key]
				)
			)
		first_row[key] = row.idx


def link_receipt_rows_to_purchase_order(doc, settings):
	"""A BTC row added by hand to a receipt made from a PO belongs to the same PO item: copy the link and
	the PO rate, so ERPNext's and our PO quantity checks cover it."""
	btc_rows = [r for r in doc.items if is_btc_row(settings, r)]
	linked = {r.purchase_order_item for r in btc_rows if r.get("purchase_order_item")}
	if len(linked) != 1:
		return  # nothing to copy from, or ambiguous
	po_item = frappe.db.get_value(
		"Purchase Order Item", next(iter(linked)), ["parent", "rate", "uom", "warehouse"], as_dict=True
	)
	if not po_item:
		return
	po_zone = frappe.db.get_value("Purchase Order", po_item.parent, "custom_zone")
	for row in btc_rows:
		if not row.get("purchase_order_item"):
			row.purchase_order_item = next(iter(linked))
			row.purchase_order = po_item.parent
		if not row.get("zone"):
			row.zone = po_zone
		if not flt(row.get("rate")):
			row.rate = po_item.rate


@frappe.whitelist()
def get_po_item_balance(purchase_order_item, exclude_receipt=None):
	"""Form helper: BTC still to receive on a PO item (ordered - received on other submitted receipts)."""
	po_qty = flt(frappe.db.get_value("Purchase Order Item", purchase_order_item, "qty"), 9)
	received = flt(
		frappe.db.sql(
			"""select coalesce(sum(qty), 0) from `tabPurchase Receipt Item`
			where purchase_order_item=%s and docstatus=1 and parent != %s""",
			(purchase_order_item, exclude_receipt or ""),
		)[0][0],
		9,
	)
	return flt(po_qty - received, 9)


def validate_receipt_against_purchase_order(doc, settings):
	"""Total received per PO item (all rows here + other submitted receipts) cannot exceed the PO quantity."""
	requested = {}
	for row in doc.items:
		if is_btc_row(settings, row) and row.get("purchase_order_item"):
			requested[row.purchase_order_item] = requested.get(row.purchase_order_item, 0) + flt(row.qty)
	for po_item_name, qty in requested.items():
		po_qty, po_name = frappe.db.get_value("Purchase Order Item", po_item_name, ["qty", "parent"])
		already = flt(
			frappe.db.sql(
				"""select coalesce(sum(qty), 0) from `tabPurchase Receipt Item`
				where purchase_order_item=%s and docstatus=1 and parent != %s""",
				(po_item_name, doc.name or ""),
			)[0][0],
			9,
		)
		if flt(already + qty, 9) > flt(po_qty, 9):
			frappe.throw(
				_(
					"Purchase Order {0}: {1} BTC ordered, {2} BTC already received on other receipts; this receipt has {3} BTC, "
					"which is {4} BTC more than the balance of {5} BTC."
				).format(
					po_name, flt(po_qty, 9), already, flt(qty, 9), flt(already + qty - po_qty, 9), flt(po_qty - already, 9)
				),
				title=_("Over Receipt"),
			)


def usd_valuation_currency():
	return "USD"


def validate_purchase_order(doc, method=None):
	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	has_btc = any(is_btc_row(settings, r) for r in doc.items)
	doc.custom_is_btc = 1 if has_btc else 0
	if not has_btc:
		doc.custom_zone = None
		doc.custom_reporting_bucket = None
		return
	if not doc.custom_zone:
		frappe.throw(_("Zone is mandatory for a BTC Purchase Order."))
	if not doc.custom_reporting_bucket:
		frappe.throw(_("Reporting Bucket is mandatory for a BTC Purchase Order."))
	if not frappe.get_cached_value("Internal Zone", doc.custom_zone, "is_active"):
		frappe.throw(_("Zone {0} is inactive.").format(doc.custom_zone))
	cost_center = frappe.get_cached_value("Internal Zone", doc.custom_zone, "default_cost_center")
	for row in doc.items:
		if is_btc_row(settings, row):
			row.cost_center = cost_center
			if settings.btc_warehouse:
				row.warehouse = settings.btc_warehouse


def post_usd_ledger(doc, method=None):
	"""on_submit: mirror every BTC stock row into the USD ledger (once per row)."""
	settings = get_settings()
	if not settings.enable_btc_rules:
		return

	for row in doc.items:
		if not is_btc_row(settings, row):
			continue

		if doc.doctype == "Stock Entry":
			if row.s_warehouse and row.t_warehouse:
				continue  # wallet/zone transfer: pool unchanged
			sign = 1 if row.t_warehouse else -1
			qty = sign * flt(row.transfer_qty or row.qty)
			usd_rate = flt(row.get("custom_usd_rate"))
			btn_rate = flt(doc.get("custom_usd_btn_rate")) or get_usd_rate(
				doc.posting_date, "for_buying" if sign > 0 else None, doc.company
			)
			zone, wallet, warehouse = (
				(row.to_zone, row.to_wallet, row.t_warehouse) if sign > 0 else (row.zone, row.wallet, row.s_warehouse)
			)
			transaction_type = RECEIPT_TYPE_ALIASES.get(doc.stock_entry_type, doc.stock_entry_type)
			market_rate = flt(row.get("custom_issue_fee_rate")) if sign < 0 else 0
		else:  # Purchase Receipt (in) and Delivery Note (out)
			is_sale = doc.doctype == "Delivery Note"
			qty = -flt(row.stock_qty) if is_sale else flt(row.stock_qty)
			price = flt(row.get("net_rate") or row.rate)
			usd_rate = 0 if is_sale else price
			btn_rate = flt(doc.conversion_rate)
			zone, wallet, warehouse = row.zone, row.wallet, row.warehouse
			transaction_type = "Sale" if is_sale else "Purchase"
			market_rate = price if is_sale else 0  # selling price -> proceeds, so gain = proceeds - cost

		usd_valuation.post_movement(
			company=doc.company,
			item_code=row.item_code,
			qty=qty,
			usd_rate=usd_rate,
			btn_rate=btn_rate,
			posting_date=doc.posting_date,
			posting_time=doc.posting_time,
			doctype=doc.doctype,
			name=doc.name,
			detail=row.name,
			transaction_type=transaction_type,
			warehouse=warehouse,
			zone=zone,
			cost_center=row.cost_center,
			wallet=wallet,
			market_usd_rate=market_rate,
		)


def reverse_usd_ledger(doc, method=None):
	"""on_cancel: flag this document's rows cancelled and rebuild the pool."""
	usd_valuation.reverse_source(doc.doctype, doc.name)


def validate_sales_order(doc, method=None):
	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	rows = [r for r in doc.items if is_btc_row(settings, r)]
	doc.custom_is_btc = 1 if rows else 0
	if not rows:
		doc.custom_reporting_bucket = None
		return
	if doc.currency != "USD":
		frappe.throw(_("A BTC Sales Order must be in USD."))
	if not doc.custom_reporting_bucket:
		frappe.throw(_("Reporting Bucket is mandatory for a BTC Sales Order."))
	# The zone and wallet are chosen on the Delivery Note; the cost center follows the delivery row's zone.
	for row in rows:
		if settings.btc_warehouse:
			row.warehouse = settings.btc_warehouse


def validate_delivery_note(doc, method=None):
	"""Runs before the generic cost-center hook. Zone and wallet are chosen on the delivery row (mandatory)."""
	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	for row in doc.items:
		if not is_btc_row(settings, row):
			continue
		if doc.is_return:
			frappe.throw(_("Row #{0}: BTC sales returns are not supported yet.").format(row.idx))
		if doc.currency != "USD":
			frappe.throw(_("Row #{0}: a BTC Delivery Note must be in USD.").format(row.idx))
		validate_zone_active(row, row.get("zone"))
		validate_wallet(row, row.get("wallet"), doc.company)
	link_delivery_rows_to_sales_order(doc, settings)
	validate_delivery_against_sales_order(doc, settings)


def link_delivery_rows_to_sales_order(doc, settings):
	"""A BTC row added by hand to a delivery made from a Sales Order belongs to the same SO item: copy the
	link and the SO rate, so ERPNext's delivered quantity and our checks cover it."""
	btc_rows = [r for r in doc.items if is_btc_row(settings, r)]
	linked = {r.so_detail for r in btc_rows if r.get("so_detail")}
	if len(linked) != 1:
		return  # nothing to copy from, or ambiguous
	so_item = frappe.db.get_value("Sales Order Item", next(iter(linked)), ["parent", "rate"], as_dict=True)
	if not so_item:
		return
	for row in btc_rows:
		if not row.get("so_detail"):
			row.so_detail = next(iter(linked))
			row.against_sales_order = so_item.parent
		if not flt(row.get("rate")):
			row.rate = so_item.rate


@frappe.whitelist()
def get_so_item_balance(so_detail, exclude_delivery=None):
	"""Form helper: BTC still to deliver on a SO item (ordered - delivered on other submitted delivery notes)."""
	so_qty = flt(frappe.db.get_value("Sales Order Item", so_detail, "qty"), 9)
	return flt(so_qty - _delivered_on_other_notes(so_detail, exclude_delivery), 9)


def _delivered_on_other_notes(so_detail, exclude_delivery=None):
	return flt(
		frappe.db.sql(
			"""select coalesce(sum(i.qty), 0) from `tabDelivery Note Item` i
			join `tabDelivery Note` d on d.name = i.parent
			where i.so_detail=%s and i.docstatus=1 and d.is_return=0 and i.parent != %s""",
			(so_detail, exclude_delivery or ""),
		)[0][0],
		9,
	)


def validate_delivery_against_sales_order(doc, settings):
	"""Total delivered per SO item (all rows here + other submitted delivery notes) cannot exceed the SO quantity."""
	requested = {}
	for row in doc.items:
		if is_btc_row(settings, row) and row.get("so_detail"):
			requested[row.so_detail] = requested.get(row.so_detail, 0) + flt(row.qty)
	for so_detail, qty in requested.items():
		so_qty, so_name = frappe.db.get_value("Sales Order Item", so_detail, ["qty", "parent"])
		already = _delivered_on_other_notes(so_detail, doc.name)
		if flt(already + qty, 9) > flt(so_qty, 9):
			frappe.throw(
				_(
					"Sales Order {0}: {1} BTC ordered, {2} BTC already delivered on other delivery notes; this delivery has "
					"{3} BTC, which is {4} BTC more than the balance of {5} BTC."
				).format(
					so_name, flt(so_qty, 9), already, flt(qty, 9), flt(already + qty - so_qty, 9), flt(so_qty - already, 9)
				),
				title=_("Over Delivery"),
			)


def validate_delivery_availability(doc, method=None):
	"""before_submit: each wallet/zone row must hold enough unrestricted BTC."""
	from gdl_custom_app.btc.balance import validate_available

	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	requests = {}
	for row in doc.items:
		if is_btc_row(settings, row):
			key = (row.zone, row.wallet)
			requests[key] = requests.get(key, 0) + flt(row.stock_qty)
	if requests:
		validate_available(settings.btc_item, settings.btc_warehouse, requests, doc.posting_date, doc.name)


def validate_sales_invoice(doc, method=None):
	"""The Delivery Note owns the stock movement; an invoice must not issue BTC a second time."""
	settings = get_settings()
	if not settings.enable_btc_rules:
		return
	for row in doc.items:
		if not is_btc_row(settings, row):
			continue
		if doc.update_stock:
			frappe.throw(_("Row #{0}: BTC is issued by the Delivery Note; untick Update Stock on the invoice.").format(row.idx))
		if not row.get("delivery_note"):
			frappe.throw(_("Row #{0}: invoice BTC against a submitted Delivery Note.").format(row.idx))
		if doc.currency != "USD":
			frappe.throw(_("Row #{0}: a BTC Sales Invoice must be in USD.").format(row.idx))


# payment_type -> (party type, invoice doctype, invoice item doctype)
BTC_PAYMENT_KINDS = {
	"Receive": ("Customer", "Sales Invoice", "Sales Invoice Item"),
	"Pay": ("Supplier", "Purchase Invoice", "Purchase Invoice Item"),
}


def get_btc_payment_split(doc):
	"""Amounts for a payment of a BTC invoice booked in BTN but settled through a USD bank account.

	Returns {"paid_amount", "received_amount", "fixed_rate"} or None when this is not such a payment.
	The USD side is the invoice's USD value for the BTN being cleared; the BTN side is what the party
	account holds. Whatever differs between the invoice rate and the payment rate is left for ERPNext's
	Exchange Gain/Loss line (41331).
	  Receive (customer): pays BTN from the debtor account, receives USD into the bank.
	  Pay (supplier): pays USD from the bank, receives BTN into the creditor account.
	"""
	settings = get_settings()
	kind = BTC_PAYMENT_KINDS.get(doc.payment_type)
	if not settings.enable_btc_rules or not kind or doc.party_type != kind[0]:
		return None
	party_type, invoice_doctype, item_doctype = kind
	refs = [r for r in doc.get("references") or [] if flt(r.allocated_amount)]
	if not refs or any(r.reference_doctype != invoice_doctype for r in refs):
		return None
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	receive = doc.payment_type == "Receive"
	party_currency, bank_currency = (
		(doc.paid_from_account_currency, doc.paid_to_account_currency)
		if receive
		else (doc.paid_to_account_currency, doc.paid_from_account_currency)
	)
	if party_currency != company_currency or bank_currency == company_currency:
		return None  # a USD party account is handled by ERPNext as is

	btn = usd = 0.0
	for ref in refs:
		invoice = frappe.db.get_value(
			invoice_doctype, ref.reference_name, ["currency", "grand_total", "base_grand_total"], as_dict=True
		)
		if not invoice or invoice.currency != bank_currency or not flt(invoice.base_grand_total):
			return None
		if not frappe.db.exists(item_doctype, {"parent": ref.reference_name, "item_code": settings.btc_item}):
			return None
		btn += flt(ref.allocated_amount)
		usd += flt(ref.allocated_amount) * flt(invoice.grand_total) / flt(invoice.base_grand_total)

	if receive:
		return {"paid_amount": btn, "received_amount": usd, "fixed_rate": "source_exchange_rate"}
	return {"paid_amount": usd, "received_amount": btn, "fixed_rate": "target_exchange_rate"}


def set_btc_payment_amounts(doc, method=None):
	"""before_validate: derive the BTN and USD amounts from the invoice (no over-payment or over-receipt)."""
	split = get_btc_payment_split(doc)
	if not split:
		return
	doc.set(split["fixed_rate"], 1)  # the BTN (party) side always has rate 1
	doc.paid_amount = flt(split["paid_amount"], doc.precision("paid_amount"))
	doc.received_amount = flt(split["received_amount"], doc.precision("received_amount"))


@frappe.whitelist()
def get_btc_payment_amounts(doc):
	"""Form helper: the same split for an unsaved Payment Entry."""
	doc = frappe.get_doc(frappe.parse_json(doc))
	split = get_btc_payment_split(doc)
	if not split:
		return None
	return {"paid_amount": flt(split["paid_amount"], 2), "received_amount": flt(split["received_amount"], 2)}
