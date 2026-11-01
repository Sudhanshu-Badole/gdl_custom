"""Shared fixtures for the BTC tests: isolated item, warehouse, zones, wallets and USD->BTN rates."""

import frappe
from frappe.utils import flt

COMPANY = "GreenDigital Limited"
ITEM = "TEST-BTC"
WAREHOUSE = "Test BTC - WH - GDL"
STOCK_ACCOUNT = "11701 - BTC - GDL"
INCOME_ACCOUNT = "41101 - Revenue from BTC - GDL"
# The company has no Stock Adjustment Account, so issues/transfers must name a difference account.
DIFFERENCE_ACCOUNT = "54111 - Transaction Fees for Digital Assets - GDL"
CC_A = "DOC - Dochula - GDL"
CC_B = "GED - Gedu - GDL"
ZONE_A, ZONE_B = "TZ-A", "TZ-B"
WALLET_A, WALLET_B = "TW-A", "TW-B"
BUSINESS_LINE = "Digital Assets"  # site accounting dimension, mandatory for P&L accounts
# Dates sit inside the current fiscal year and after the first real rate (2026-10-01).
D1, D2, D3, D4 = "2026-10-05", "2026-10-10", "2026-10-15", "2026-10-20"
RATES = {D1: 90.0, D3: 91.0}  # for_buying USD->BTN
NO_RATE_DATE = "2026-09-15"

SETTING_FIELDS = (
	"btc_item", "btc_warehouse", "enable_btc_rules", "mining_income_account",
	"premium_income_account", "put_exercised_account", "fee_expense_account",
)


def setup_masters():
	"""Create isolated masters and point GDL Setting at them. Returns the original settings."""
	original = {f: frappe.db.get_single_value("GDL Setting", f) for f in SETTING_FIELDS}

	if not frappe.db.exists("Item", ITEM):
		frappe.get_doc(
			{"doctype": "Item", "item_code": ITEM, "item_name": ITEM, "item_group": "Digital Assets",
			 "stock_uom": "BTC", "is_stock_item": 1, "valuation_method": "Moving Average", "is_purchase_item": 1,
			 "is_sales_item": 1, "allow_negative_stock": 0,
			 "item_defaults": [{"company": COMPANY, "default_inventory_account": STOCK_ACCOUNT}]}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Warehouse", WAREHOUSE):
		frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": "Test BTC - WH", "company": COMPANY,
			 "parent_warehouse": "All Warehouses - GDL", "account": STOCK_ACCOUNT}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("BTC Custodian", "TCust"):
		frappe.get_doc({"doctype": "BTC Custodian", "custodian_name": "TCust"}).insert()
	for wallet in (WALLET_A, WALLET_B):
		if not frappe.db.exists("BTC Wallet", wallet):
			frappe.get_doc({"doctype": "BTC Wallet", "wallet_name": wallet, "category": "GDL",
				"custodian": "TCust", "company": COMPANY}).insert()
	for zone, cc in ((ZONE_A, CC_A), (ZONE_B, CC_B)):
		if not frappe.db.exists("Internal Zone", zone):
			frappe.get_doc({"doctype": "Internal Zone", "zone_name": zone, "company": COMPANY,
				"default_cost_center": cc}).insert()

	for date, rate in RATES.items():
		if not frappe.db.exists("Currency Exchange", {"date": date, "from_currency": "USD", "to_currency": "BTN"}):
			frappe.get_doc({"doctype": "Currency Exchange", "date": date, "from_currency": "USD",
				"to_currency": "BTN", "exchange_rate": rate, "for_buying": 1, "for_selling": 1}).insert()

	# Invoices of a 0.399 x 60,000 line can need a sub-paisa round-off; the site has no round-off cost center.
	if not frappe.db.get_value("Company", COMPANY, "round_off_cost_center"):
		frappe.db.set_value("Company", COMPANY, "round_off_cost_center", CC_A)
	set_settings(
		btc_item=ITEM, btc_warehouse=WAREHOUSE, enable_btc_rules=1, mining_income_account=INCOME_ACCOUNT,
		premium_income_account=INCOME_ACCOUNT, put_exercised_account=INCOME_ACCOUNT,
	)
	return original


def set_settings(**values):
	for k, v in values.items():
		frappe.db.set_single_value("GDL Setting", k, v)
	frappe.clear_document_cache("GDL Setting", "GDL Setting")


def make_receipt(entry_type="Mining", qty=0.5, usd_rate=50000, zone=ZONE_A, wallet=WALLET_A,
		date=D1, time="10:00:00", submit=True, rows=None, **row_extra):
	se = frappe.new_doc("Stock Entry")
	se.update({"stock_entry_type": entry_type, "purpose": "Material Receipt", "company": COMPANY,
		"posting_date": date, "posting_time": time, "set_posting_time": 1, "business_line": BUSINESS_LINE})
	for r in rows or [{"qty": qty, "to_zone": zone, "to_custodian": wallet}]:
		se.append("items", {"item_code": ITEM, "t_warehouse": WAREHOUSE, "uom": "BTC",
			"stock_uom": "BTC", "conversion_factor": 1, "business_line": BUSINESS_LINE, "custom_usd_rate": usd_rate, **row_extra, **r})
	se.insert()
	if submit:
		se.submit()
	return se


def make_issue(qty, zone=ZONE_A, wallet=WALLET_A, date=D3, time="10:00:00", submit=True):
	se = frappe.new_doc("Stock Entry")
	se.update({"stock_entry_type": "Material Issue", "purpose": "Material Issue", "company": COMPANY,
		"posting_date": date, "posting_time": time, "set_posting_time": 1, "business_line": BUSINESS_LINE})
	se.append("items", {"item_code": ITEM, "s_warehouse": WAREHOUSE, "qty": qty, "uom": "BTC",
		"stock_uom": "BTC", "conversion_factor": 1, "business_line": BUSINESS_LINE, "zone": zone, "custodian": wallet, "expense_account": DIFFERENCE_ACCOUNT})
	se.insert()
	if submit:
		se.submit()
	return se


def make_transfer(qty, from_zone=ZONE_A, from_wallet=WALLET_A, to_zone=ZONE_A, to_wallet=WALLET_B,
		date=D4, time="10:00:00", submit=True, fee_qty=0, fee_rate=0, status=None, expiry=None):
	se = frappe.new_doc("Stock Entry")
	se.update({"stock_entry_type": "Material Transfer", "purpose": "Material Transfer", "company": COMPANY,
		"posting_date": date, "posting_time": time, "set_posting_time": 1, "business_line": BUSINESS_LINE})
	se.append("items", {"item_code": ITEM, "s_warehouse": WAREHOUSE, "t_warehouse": WAREHOUSE, "qty": qty,
		"uom": "BTC", "stock_uom": "BTC", "conversion_factor": 1, "business_line": BUSINESS_LINE, "zone": from_zone, "custodian": from_wallet,
		"to_zone": to_zone, "to_custodian": to_wallet, "expense_account": DIFFERENCE_ACCOUNT,
		"custom_fee_qty": fee_qty, "custom_fee_rate": fee_rate, "custom_transfer_status": status, "custom_expiry_date": expiry})
	se.insert()
	if submit:
		se.submit()
	return se


def ledger(**filters):
	return frappe.get_all("BTC USD Valuation Ledger", filters={"item_code": ITEM, **filters},
		fields=["*"], order_by="posting_datetime, creation")


def pool():
	rows = frappe.get_all("BTC USD Valuation Ledger", filters={"item_code": ITEM, "is_cancelled": 0},
		fields=["usd_balance_qty", "usd_balance_value", "usd_moving_average_rate"],
		order_by="posting_datetime desc, creation desc", limit=1)
	return (flt(rows[0].usd_balance_qty, 9), flt(rows[0].usd_balance_value, 4), flt(rows[0].usd_moving_average_rate, 4)) if rows else (0, 0, 0)


def wallet_balance(wallet, zone=None):
	cond = " and zone=%s" if zone else ""
	return flt(frappe.db.sql(
		"select coalesce(sum(actual_qty),0) from `tabStock Ledger Entry` where item_code=%s and warehouse=%s "
		f"and custodian=%s and is_cancelled=0{cond}", (ITEM, WAREHOUSE, wallet) + ((zone,) if zone else ()))[0][0], 9)


def make_restriction(qty, status="Pledged", expiry=D4, start=D1, wallet=WALLET_A, zone=ZONE_A):
	return frappe.get_doc({"doctype": "BTC Restriction", "company": COMPANY, "item_code": ITEM,
		"warehouse": WAREHOUSE, "zone": zone, "wallet": wallet, "restriction_type": status, "qty": qty,
		"start_date": start, "expiry_date": expiry}).insert()


CUSTOMER = "TEST-BTC-CUSTOMER"
USD_BANK = "11131 - DBS FC - Main - GDL"


def make_customer():
	if not frappe.db.exists("Customer", CUSTOMER):
		frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_group": "Third Country Customers",
			"territory": "Rest Of The World", "default_currency": "USD"}).insert(ignore_permissions=True)
	return CUSTOMER


def make_sales_order(qty=1, rate=60000, zone=ZONE_A, bucket="Cash Mgmt", date=D1, submit=True, rate_btn=91):
	so = frappe.new_doc("Sales Order")
	so.update({"customer": make_customer(), "company": COMPANY, "transaction_date": date, "delivery_date": D4,
		"currency": "USD", "conversion_rate": rate_btn, "selling_price_list": "Standard Selling",
		"price_list_currency": "USD", "plc_conversion_rate": rate_btn, "custom_zone": zone,
		"custom_reporting_bucket": bucket, "business_line": BUSINESS_LINE})
	so.append("items", {"item_code": ITEM, "qty": qty, "rate": rate, "delivery_date": D4, "warehouse": WAREHOUSE,
		"business_line": BUSINESS_LINE})
	so.insert()
	if submit:
		so.submit()
	return so


def make_delivery(so, rows, date=D3, submit=True, rate_btn=91):
	"""rows: [(qty, wallet)] - one Delivery Note row per wallet, as the wallet split."""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	dn.update({"posting_date": date, "set_posting_time": 1, "posting_time": "12:00:00", "conversion_rate": rate_btn,
		"business_line": BUSINESS_LINE})
	template = dn.items[0]
	dn.items = []
	for qty, wallet in rows:
		row = dn.append("items", template.as_dict())
		row.name = None
		row.update({"qty": qty, "custodian": wallet, "zone": None, "expense_account": DIFFERENCE_ACCOUNT,
			"business_line": BUSINESS_LINE})
	dn.insert()
	if submit:
		dn.submit()
	return dn


def make_invoice(dn, date=D3, rate_btn=91, debit_to=None, submit=True):
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	si = make_sales_invoice(dn.name)
	si.update({"posting_date": date, "set_posting_time": 1, "conversion_rate": rate_btn, "due_date": D4,
		"business_line": BUSINESS_LINE})
	if debit_to:
		si.debit_to = debit_to
	for term in si.get("payment_schedule") or []:
		term.due_date = D4
	for row in si.items:
		row.income_account = INCOME_ACCOUNT
		row.business_line = BUSINESS_LINE
	si.insert()
	if submit:
		si.submit()
	return si
