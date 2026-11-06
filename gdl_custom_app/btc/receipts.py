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
			transaction_type = doc.stock_entry_type
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
		doc.custom_zone = doc.custom_reporting_bucket = None
		return
	if doc.currency != "USD":
		frappe.throw(_("A BTC Sales Order must be in USD."))
	if not doc.custom_zone:
		frappe.throw(_("Zone is mandatory for a BTC Sales Order."))
	if not doc.custom_reporting_bucket:
		frappe.throw(_("Reporting Bucket is mandatory for a BTC Sales Order."))
	zone = frappe.get_cached_value("Internal Zone", doc.custom_zone, ["is_active", "default_cost_center"], as_dict=True)
	if not zone.is_active:
		frappe.throw(_("Zone {0} is inactive.").format(doc.custom_zone))
	for row in rows:
		row.cost_center = zone.default_cost_center
		if settings.btc_warehouse:
			row.warehouse = settings.btc_warehouse


def validate_delivery_note(doc, method=None):
	"""Runs before the generic cost-center hook: inherit the order's zone, then check masters."""
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
		if not row.get("zone") and row.get("against_sales_order"):
			row.zone = frappe.db.get_value("Sales Order", row.against_sales_order, "custom_zone")
		validate_zone_active(row, row.get("zone"))
		validate_wallet(row, row.get("wallet"), doc.company)


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
