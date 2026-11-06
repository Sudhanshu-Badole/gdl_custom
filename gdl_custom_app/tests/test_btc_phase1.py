import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from gdl_custom_app.btc import receipts, usd_valuation
from gdl_custom_app.btc.exchange import get_usd_rate
from gdl_custom_app.tests import btc_test_utils as u



class BTCPhase1Base(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		u.setup_masters()  # rolled back in tearDown, so the site is left untouched

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_document_cache("GDL Setting", "GDL Setting")

	def assertClose(self, a, b, places=4):
		self.assertAlmostEqual(flt(a), flt(b), places=places)


class TestMasters(BTCPhase1Base):
	def test_a01_valid_zone(self):
		z = frappe.get_doc({"doctype": "Internal Zone", "zone_name": "TZ-NEW", "company": u.COMPANY,
			"default_cost_center": u.CC_A}).insert()
		self.assertEqual(z.is_active, 1)

	def test_a02_zone_without_cost_center(self):
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({"doctype": "Internal Zone", "zone_name": "TZ-X", "company": u.COMPANY}).insert()

	def test_a03_invalid_cost_center(self):
		group = frappe.db.get_value("Cost Center", {"is_group": 1, "company": u.COMPANY}, "name")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Internal Zone", "zone_name": "TZ-X", "company": u.COMPANY,
				"default_cost_center": group}).insert()
		disabled = frappe.db.get_value("Cost Center", {"disabled": 1, "is_group": 0, "company": u.COMPANY}, "name")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Internal Zone", "zone_name": "TZ-Y", "company": u.COMPANY,
				"default_cost_center": disabled}).insert()

	def test_a04_duplicate_zone(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": "Internal Zone", "zone_name": u.ZONE_A, "company": u.COMPANY,
				"default_cost_center": u.CC_A}).insert()

	def test_a05_inactive_zone_rejected(self):
		frappe.db.set_value("Internal Zone", u.ZONE_A, "is_active", 0)
		frappe.clear_document_cache("Internal Zone", u.ZONE_A)
		with self.assertRaises(frappe.ValidationError):
			u.make_receipt()

	def test_a06_cost_center_autopopulated(self):
		se = u.make_receipt(zone=u.ZONE_B, submit=False)
		self.assertEqual(se.items[0].cost_center, u.CC_B)

	def test_a07_historical_cost_center_preserved(self):
		se = u.make_receipt()
		zone = frappe.get_doc("Internal Zone", u.ZONE_A)
		zone.default_cost_center = u.CC_B
		zone.save()
		self.assertEqual(frappe.db.get_value("Stock Entry Detail", se.items[0].name, "cost_center"), u.CC_A)
		self.assertEqual(u.ledger()[0].cost_center, u.CC_A)

	def test_a08_wallet_valid(self):
		w = frappe.get_doc({"doctype": "BTC Wallet", "wallet_name": "TW-NEW", "category": "GMC",
			"custodian": "TCust", "company": u.COMPANY}).insert()
		self.assertEqual(w.is_active, 1)

	def test_a09_inactive_wallet_rejected(self):
		frappe.db.set_value("BTC Wallet", u.WALLET_A, "is_active", 0)
		frappe.clear_document_cache("BTC Wallet", u.WALLET_A)
		with self.assertRaises(frappe.ValidationError):
			u.make_receipt()

	def test_zone_in_use_cannot_be_deactivated(self):
		u.make_receipt()
		zone = frappe.get_doc("Internal Zone", u.ZONE_A)
		zone.is_active = 0
		with self.assertRaises(frappe.ValidationError):
			zone.save()


class TestReceipts(BTCPhase1Base):
	def test_b01_mining_receipt(self):
		se = u.make_receipt("Mining", 0.5, 50000)
		row = u.ledger()[0]
		self.assertClose(row.usd_incoming_value, 25000)
		self.assertEqual(row.transaction_type, "Mining")
		self.assertEqual((row.zone, row.wallet), (u.ZONE_A, u.WALLET_A))
		self.assertEqual(se.custom_usd_btn_rate, 90)

	def test_mining_warehouse_defaults_to_btc_warehouse(self):
		se = u.make_receipt("Mining", rows=[{"qty": 0.5, "to_zone": u.ZONE_A, "to_wallet": u.WALLET_A, "t_warehouse": None}])
		self.assertEqual(se.items[0].t_warehouse, u.WAREHOUSE)

	def test_b02_b03_premium_and_put(self):
		u.make_receipt("Premium Received", 0.1, 50000, date=u.D1, time="09:00:00")
		u.make_receipt("Put Exercised", 0.2, 50000, date=u.D1, time="09:30:00")
		self.assertEqual([r.transaction_type for r in u.ledger()], ["Premium Received", "Put Exercised"])

	def test_b04_b05_bad_quantity(self):
		for qty in (0, -1):
			with self.assertRaises(frappe.ValidationError):
				u.make_receipt(qty=qty)

	def test_b06_missing_usd_rate(self):
		with self.assertRaises(frappe.ValidationError):
			u.make_receipt(usd_rate=0)

	def test_b07_two_wallet_rows(self):
		u.make_receipt(rows=[{"qty": 0.4, "to_zone": u.ZONE_A, "to_wallet": u.WALLET_A},
			{"qty": 0.6, "to_zone": u.ZONE_A, "to_wallet": u.WALLET_B}])
		self.assertClose(u.wallet_balance(u.WALLET_A), 0.4)
		self.assertClose(u.wallet_balance(u.WALLET_B), 0.6)
		self.assertEqual(len(u.ledger()), 2)

	def test_b09_posting_is_idempotent(self):
		se = u.make_receipt()
		receipts.post_usd_ledger(se)
		receipts.post_usd_ledger(se)
		self.assertEqual(len(u.ledger()), 1)

	def test_b10_cancel_reverses_usd_ledger(self):
		se = u.make_receipt()
		se.cancel()
		rows = u.ledger()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].is_cancelled, 1)
		self.assertEqual(u.pool(), (0, 0, 0))

	def test_k01_draft_posts_nothing(self):
		u.make_receipt(submit=False)
		self.assertEqual(u.ledger(), [])

	def test_k05_amend_posts_once(self):
		se = u.make_receipt()
		se.cancel()
		new = frappe.copy_doc(se)
		new.amended_from = se.name
		new.docstatus = 0
		new.insert()
		new.submit()
		live = [r for r in u.ledger() if not r.is_cancelled]
		self.assertEqual(len(live), 1)
		self.assertEqual(live[0].transaction_name, new.name)


class TestUSDValuation(BTCPhase1Base):
	def test_c01_initial_receipt(self):
		u.make_receipt(qty=0.5, usd_rate=50000)
		self.assertEqual(u.pool(), (0.5, 25000, 50000))

	def test_c02_c03_weighted_average_and_issue(self):
		u.make_receipt(qty=1, usd_rate=40000, time="09:00:00")
		u.make_receipt(qty=1, usd_rate=60000, time="09:30:00")
		self.assertEqual(u.pool(), (2, 100000, 50000))
		u.make_issue(0.5)
		qty, value, avg = u.pool()
		self.assertEqual((qty, value, avg), (1.5, 75000, 50000))
		self.assertClose(u.ledger(direction="Out")[0].usd_outgoing_value, 25000)

	def test_c04_c06_c07_full_issue_leaves_no_residue(self):
		u.make_receipt(qty=0.33333333, usd_rate=50801.37)
		u.make_issue(0.11111111, time="11:00:00")
		u.make_issue(0.22222222, time="12:00:00")
		self.assertEqual(u.pool()[:2], (0, 0))

	def test_c05_issue_beyond_balance_rejected(self):
		u.make_receipt(qty=0.5)
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(0.6)

	def test_c08_h02_btn_and_usd_stay_separate(self):
		u.make_receipt(qty=0.5, usd_rate=50000)
		sle = frappe.get_all("Stock Ledger Entry", filters={"item_code": u.ITEM, "is_cancelled": 0},
			fields=["incoming_rate", "stock_value"])[0]
		self.assertClose(sle.incoming_rate, 4500000)  # 50,000 USD x 90
		self.assertClose(sle.stock_value, 2250000)
		self.assertClose(u.ledger()[0].btn_value, 2250000)
		self.assertClose(u.ledger()[0].usd_incoming_value, 25000)

	def test_h03_receipt_gl_once(self):
		se = u.make_receipt(qty=0.5, usd_rate=50000)
		gl = frappe.get_all("GL Entry", filters={"voucher_no": se.name, "is_cancelled": 0},
			fields=["account", "debit", "credit", "cost_center"])
		self.assertEqual(len(gl), 2)
		debit = next(g for g in gl if g.debit)
		credit = next(g for g in gl if g.credit)
		self.assertEqual((debit.account, credit.account), (u.STOCK_ACCOUNT, u.INCOME_ACCOUNT))
		self.assertClose(debit.debit, 2250000)
		self.assertEqual(debit.cost_center, u.CC_A)

	def test_c09_historical_exchange_rate(self):
		a = u.make_receipt(date=u.D1)
		b = u.make_receipt(date=u.D3, time="11:00:00")
		self.assertEqual((a.custom_usd_btn_rate, b.custom_usd_btn_rate), (90, 91))
		self.assertEqual([r.btn_exchange_rate for r in u.ledger()], [90, 91])

	def test_c10_missing_exchange_rate(self):
		with self.assertRaises(frappe.ValidationError):
			get_usd_rate(u.NO_RATE_DATE, "for_buying", u.COMPANY)
		with self.assertRaises(frappe.ValidationError):
			u.make_receipt(date=u.NO_RATE_DATE)

	def test_c11_backdated_receipt_rebuilds(self):
		u.make_receipt(qty=1, usd_rate=60000, date=u.D3)
		u.make_issue(0.5, date=u.D4)
		self.assertEqual(u.pool(), (0.5, 30000, 60000))
		u.make_receipt(qty=1, usd_rate=40000, date=u.D1)  # backdated
		issue = u.ledger(direction="Out")[0]
		self.assertClose(issue.usd_moving_average_rate, 50000)
		self.assertClose(issue.usd_outgoing_value, 25000)
		self.assertEqual(u.pool(), (1.5, 75000, 50000))

	def test_c12_backdated_issue_that_breaks_history_is_rejected(self):
		u.make_receipt(qty=1, usd_rate=50000, date=u.D1)
		u.make_issue(0.8, date=u.D4)
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(0.5, date=u.D3)  # D3 issue would starve the D4 issue

	def test_c13_cancel_earlier_receipt_recalculates(self):
		first = u.make_receipt(qty=1, usd_rate=40000, date=u.D1)
		u.make_receipt(qty=2, usd_rate=60000, date=u.D3)
		u.make_issue(1, date=u.D4)  # avg (40k+120k)/3
		first.cancel()
		issue = u.ledger(direction="Out")[0]
		self.assertClose(issue.usd_moving_average_rate, 60000)
		self.assertEqual(u.pool(), (1, 60000, 60000))
		self.assertEqual(len(u.ledger()), 3)  # audit rows preserved

	def test_reconcile_matches_stock_ledger(self):
		u.make_receipt(qty=1, usd_rate=50000)
		r = usd_valuation.reconcile(u.COMPANY, u.ITEM)
		self.assertEqual(r["qty_difference"], 0)


class TestWalletBalances(BTCPhase1Base):
	def test_d01_d02_wallet_balances(self):
		u.make_receipt(qty=1)
		self.assertClose(u.wallet_balance(u.WALLET_A), 1)

	def test_d05_wallet_cannot_overdraw_even_if_warehouse_has_stock(self):
		u.make_receipt(qty=1, wallet=u.WALLET_A)
		u.make_receipt(qty=1, wallet=u.WALLET_B, time="11:00:00")
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(1.5, wallet=u.WALLET_A)  # warehouse has 2, wallet A only 1

	def test_d06_zone_with_no_stock_rejected(self):
		u.make_receipt(qty=1, zone=u.ZONE_A)
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(0.5, zone=u.ZONE_B)

	def test_d03_d08_transfer_conserves_total_and_pool_unchanged(self):
		u.make_receipt(qty=1, usd_rate=50000)
		u.make_transfer(0.3)
		self.assertClose(u.wallet_balance(u.WALLET_A), 0.7)
		self.assertClose(u.wallet_balance(u.WALLET_B), 0.3)
		self.assertEqual(u.pool(), (1, 50000, 50000))
		self.assertEqual(len(u.ledger()), 1)  # a transfer is not a USD movement

	def test_d04_cross_zone_transfer_cost_centers(self):
		u.make_receipt(qty=1)
		se = u.make_transfer(0.3, to_zone=u.ZONE_B)
		self.assertEqual(se.items[0].cost_center, u.CC_B)  # follows the target zone
		self.assertClose(u.wallet_balance(u.WALLET_B, u.ZONE_B), 0.3)

	def test_d10_transfer_cancel_restores(self):
		u.make_receipt(qty=1)
		se = u.make_transfer(0.3)
		se.cancel()
		self.assertClose(u.wallet_balance(u.WALLET_A), 1)
		self.assertClose(u.wallet_balance(u.WALLET_B), 0)


class TestPurchase(BTCPhase1Base):
	def _supplier(self):
		if not frappe.db.exists("Supplier", "TEST-BTC-SUPPLIER"):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": "TEST-BTC-SUPPLIER", "supplier_group": "All Supplier Groups",
				"default_currency": "USD"}).insert(ignore_permissions=True)
		return "TEST-BTC-SUPPLIER"

	def _po(self, qty=1, rate=51000, **kw):
		po = frappe.new_doc("Purchase Order")
		po.update({"supplier": self._supplier(), "company": u.COMPANY, "transaction_date": u.D1, "schedule_date": u.D2,
			"currency": "USD", "conversion_rate": 90, "buying_price_list": "Standard Buying", "price_list_currency": "USD",
			"plc_conversion_rate": 90, "custom_zone": u.ZONE_A, "custom_reporting_bucket": "Cash Mgmt", **kw})
		po.append("items", {"item_code": u.ITEM, "qty": qty, "rate": rate, "schedule_date": u.D2, "warehouse": u.WAREHOUSE})
		po.insert()
		return po

	def _pr(self, po, qty, date=u.D1):
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
		pr = make_purchase_receipt(po.name)
		pr.update({"posting_date": date, "set_posting_time": 1, "conversion_rate": 90})
		pr.items[0].qty = qty
		pr.items[0].wallet = u.WALLET_A
		pr.insert()
		return pr

	def test_b11_po_defaults(self):
		po = self._po()
		self.assertEqual(po.custom_is_btc, 1)
		self.assertEqual(po.items[0].cost_center, u.CC_A)
		self.assertEqual(po.items[0].warehouse, u.WAREHOUSE)

	def test_pr_warehouse_defaults_to_btc_warehouse(self):
		po = self._po()
		po.items[0].warehouse = None
		po.save()
		po.submit()
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
		pr = make_purchase_receipt(po.name)
		pr.update({"posting_date": u.D1, "set_posting_time": 1, "conversion_rate": 90})
		pr.items[0].warehouse = None
		pr.items[0].wallet = u.WALLET_A
		pr.insert()
		self.assertEqual((po.items[0].warehouse, pr.items[0].warehouse), (u.WAREHOUSE, u.WAREHOUSE))

	def test_b11_po_requires_bucket(self):
		with self.assertRaises(frappe.ValidationError):
			self._po(custom_reporting_bucket=None)

	def test_non_btc_po_unaffected(self):
		item = frappe.db.get_value("Item", {"is_stock_item": 1, "name": ["!=", u.ITEM]}, "name")
		po = frappe.new_doc("Purchase Order")
		po.update({"supplier": self._supplier(), "company": u.COMPANY, "transaction_date": u.D1, "schedule_date": u.D2,
			"currency": "USD", "conversion_rate": 90})
		po.append("items", {"item_code": item, "qty": 1, "rate": 10, "schedule_date": u.D2})
		po.insert()
		self.assertEqual(po.custom_is_btc, 0)

	def test_b12_b13_partial_receipts(self):
		po = self._po(qty=1, rate=51000)
		po.submit()
		pr1 = self._pr(po, 0.4)
		pr1.submit()
		pr2 = self._pr(po, 0.6, date=u.D3)
		pr2.submit()
		rows = u.ledger()
		self.assertEqual([r.transaction_type for r in rows], ["Purchase", "Purchase"])
		self.assertClose(sum(r.qty_in for r in rows), 1)
		self.assertClose(rows[0].usd_incoming_value, 0.4 * 51000)
		self.assertEqual(u.pool()[:2], (1, 51000))
		self.assertEqual(po.reload().per_received, 100)
