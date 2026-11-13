# gdl_custom_app — Agent Notes

Context for anyone (human or AI agent) working on this app: what it is, the
requirements we were given, what was built, and the gotchas we hit.

- **Stack:** Frappe v16 + ERPNext v16 (+ HRMS), Python 3.14. Bench at
  `/home/dell/frappe-bench/gdl-frappe-bench`, main site `site.local`.
- **Company:** GreenDigital Limited (GDL), company currency **BTN**.
- **Repo:** `github.com/Sudhanshu-Badole/gdl_custom`, working branch **`version-16`**.
- Paths below are relative to `gdl_custom_app/` (the Python package).

---

## 1. Layout

| Area | Files |
|---|---|
| BTC business rules | `btc/receipts.py`, `btc/transfers.py`, `btc/usd_valuation.py`, `btc/balance.py`, `btc/exchange.py` |
| Stock-row rules / cost centers | `utils/btc.py` (+ `public/js/btc_cost_center.js`) |
| Transfer network fee | `utils/fee.py`, `overrides/stock_entry.py` |
| Item code generation | `utils/item_code.py`, `public/js/item_code.js` |
| BTC warehouse auto-fill (form) | `public/js/btc_defaults.js` |
| Class overrides | `overrides/asset.py` (Asset naming), `overrides/stock_entry.py` (fee GL), `overrides/purchase_order.py` |
| DocTypes | GDL Setting (single), Internal Zone, BTC Wallet, BTC Custodian, BTC Restriction (+ Extension, Release), BTC USD Valuation Ledger, Custody |
| Reports | `gdl_custom_app/report/`: BTC Inventory Balance, BTC Movement History, BTC USD Valuation, BTC Disposal Gain Loss, BTC Receipt Type, BTC Reconciliation, BTC Restricted Holdings |
| Workspace / app tile | `gdl_custom_app/workspace/btc_inventory`, `workspace_sidebar/btc_inventory.json`, `desktop_icon/btc_inventory.json`, `add_to_apps_screen` in `hooks.py` |
| Patches | `patches/v1_0/` (listed in `patches.txt`) |
| Tests | `tests/test_btc_phase1.py`, `test_btc_phase2.py`, `test_btc_phase3.py`, helpers in `tests/btc_test_utils.py` |

All wiring (doc_events, doctype_js, overrides, fixtures) is in `hooks.py`.

---

## 2. BTC (Digital Asset) accounting — core design

- **One BTC item** and **one BTC warehouse**, both set in **GDL Setting**
  (`btc_item`, `btc_warehouse` = "Digital Asset Mining - WH - GDL"). Rules only
  apply when `enable_btc_rules` is ticked, and only to rows of the BTC item —
  other items behave like standard ERPNext.
- **Zone** and **Wallet** are ERPNext *Inventory Dimensions* (fixtures), so
  every stock row carries zone/wallet (Stock Entry rows: `zone`/`wallet` source,
  `to_zone`/`to_wallet` target). Wallet replaced an earlier "Custodian"
  dimension (patches `btc_rename_custodian_dimension_to_wallet`,
  `btc_fix_wallet_field_options`).
- **Cost center** of a BTC row always follows its Zone
  (`Internal Zone.default_cost_center`), falling back to
  `Warehouse.custom_cost_center` (`utils/btc.py`).
- **Two valuations run side by side:**
  - **BTN (standard ERPNext):** Stock Ledger + GL, moving average in BTN.
    "BTN Valuation" / "BTN Cost per BTC" in reports.
  - **USD (custom):** `BTC USD Valuation Ledger`, maintained by
    `btc/usd_valuation.py`. One global moving-average pool per company+item
    (not per zone/wallet). On In: avg = total USD value / total qty; on Out:
    leaves at current avg. **Never posts GL** — reporting only.
    "USD Moving Average Rate" (shown as **USD Cost per BTC**) = USD cost of one
    BTC; "USD Valuation" = qty x that rate.
- **Receipt types** (Stock Entry Types with purpose Material Receipt): Mining,
  Premium Received, Put Exercised. User enters `custom_usd_rate` per row;
  `prepare_stock_entry` sets `basic_rate = USD rate x USD->BTN "for buying"
  Currency Exchange rate` and the income account from GDL Setting.
  *Example:* USD 50,000 x 94.9 = BTN 4,745,000 per BTC — users asked why the
  basic rate is so big; it is the BTN price, by design, and cannot be typed
  manually.
- **Exchange rates** come only from the Currency Exchange master
  (`btc/exchange.py`, never an external API; missing rate = error).
- **Transfers** (Material Transfer) move BTC between zones/wallets in the same
  warehouse; neutral for GL and the USD pool. Optional statuses
  (Trading/Loan/Pledged) create **BTC Restriction** records that block that qty.
- **Sales/Purchases:** Purchase Order/Receipt and Sales Order/Delivery Note for
  BTC must be in USD and carry zone/wallet; the Delivery Note moves stock, the
  Sales Invoice must not (`update_stock` off).

---

## 3. Requirement history & solutions (chronological)

### 3.1 Initial build (commits `b39a8c6` … `5b2ab3e`)
BTC inventory with wallet/zone tracking, USD valuation ledger, restrictions,
transfer fee, reports, BTC Inventory workspace; Custodian → Wallet refactor;
fixtures exported. Asset naming override: `GDL/<Asset Category code>/YY/#####`
using `Asset Category.custom_category_code` (`overrides/asset.py`).

### 3.2 Item Code from Item Group code (commit `eacfed4`, 2026-11-05)
**Requirement:** item codes like `STN-00001`, based on a code mapped on each
Item Group (Stationery STN, Electrical Spares ELECT, Vehicle Spares VEH, Tools
and Plants TP, ICT Spares ICT, General Items GEN, PPE and Uniforms PPE, Civil
Items CIVIL, Miner Spares MINER).
**Follow-up:** Fixed Asset items get an `AST-` prefix (AST-FUR, AST-ELECT,
AST-VEH, AST-TPM, AST-ICT, AST-OE, AST-BLD, AST-MINER).
**Solution:**
- Custom field `Item Group.custom_group_code` (`custom/item_group.json`).
- `utils/item_code.py` — `before_insert` on Item (runs before naming, so
  ERPNext's `Item.autoname` uses it): `make_autoname("<CODE>-.#####")`;
  `AST-<CODE>` when `is_fixed_asset`. Groups without a code keep manual codes;
  variants are skipped. Several groups may share a code (one shared series).
- `public/js/item_code.js` — on new Items, locks Item Code and shows
  "Generated on save as …".
- Note: sheet example `CIV-00001` vs stored code `CIVIL` → codes are
  `CIVIL-00001` unless the group code is changed.
- Pending on user side: put Group Codes on the Fixed Assets item groups
  (suggested mapping FUR / ELECT / VEH / TPM / ICT / OE / BLD / MINER).

### 3.3 "BTC Changes Feedback" (commit `8b85ade`, 2026-11-06)
Source: `BTC Changes Feedback.docx` from the finance team.

| # | Requirement | Solution |
|---|---|---|
| 1 | Auto-select warehouse "Digital Asset Mining - WH - GDL" for Mining and Purchase | BTC rows only. Server: `receipts.set_default_warehouses` (Stock Entry receipt/issue/transfer), `validate_purchase_receipt`, `validate_purchase_order`. Client: `public/js/btc_defaults.js` + whitelisted `receipts.get_btc_defaults`. |
| 2 | Keep provision for BTC and normal transactions (esp. Purchase) | Already true: BTC rules touch only BTC rows. Clarified with user: only the auto-warehouse was needed. |
| 3 | BTC quantity: 8 decimals | Patch `btc_qty_precision` adds precision-8 Property Setters on qty fields (Stock Entry Detail, PO/PR/SO/DN/SI items, Stock Reconciliation Item, Stock Ledger Entry, Bin) + `custom_fee_qty`. `utils/btc._validate_btc_row` rejects >8 decimals. BTC report qty columns at precision 8. Trade-off: applies per field, so non-BTC fractional qtys also display 8 decimals. |
| 4 | "Does Submitted mean the process is completed?" | Answer only: yes — SLE, GL, USD ledger (and fee issue) all post on submit. |
| 5 | Network-fee GL must use market value; difference to Disposal Gain/Loss | See 3.4. |
| 6 | Stock Ledger balance per wallet | **Deferred** by user. Workaround: Stock Ledger with one Item + one Warehouse + Wallet filter gives a per-wallet running balance. |
| 7 | Desktop app for the BTC app | `add_to_apps_screen` in `hooks.py` → "BTC Inventory" tile on `/apps`, logo `public/images/btc-inventory.svg`, route `/desk/btc-inventory`. |
| 8 | Total in BTC Inventory Balance | Python-built bold **Total** row (sums; per-BTC costs = total value / total qty). Zero-qty rows hidden. |
| 9 | Show cost of BTC with valuation | New **BTN Cost per BTC** column; "USD Moving Average Rate" renamed **USD Cost per BTC**. |
| 10 | USD Valuation vs USD Moving Average Rate? | Answer only (see §2). Both are custom, not ERPNext. |

### 3.4 Network fee GL (detail)
Material Transfer row has `custom_fee_qty` + `custom_fee_rate` (market USD).
On submit `utils/fee.create_fee_issue` creates & submits a **Material Issue**
(`custom_fee_charge_for` = transfer) and freezes the USD->BTN **selling** rate
in its `custom_usd_btn_rate`. `overrides/stock_entry.CustomStockEntry.get_gl_entries`
adds lines on that issue:

```
market = fee qty x Fee Market Rate (USD) x selling rate
cost   = -(SLE stock_value_difference of the row)   # weighted-average BTN
Dr Fee Expense (fee_expense_account)        market - cost
Cr Disposal Gain/Loss (disposal_gain_loss_account)   market - cost   (swapped if loss)
```
ERPNext merges the fee debits, giving the 3-line voucher the user asked for:
Dr Fee 2,500.00 / Cr BTC 2,067.18 / Cr Disposal Gain 432.82.
Requires **GDL Setting → Disposal Gain/Loss Account** (suggested
`41321 - Disposal (Gain)/Loss Digital Assets - GDL`); fee transfers error until
set. Cancel/repost use standard ERPNext logic.

---

## 4. Running & testing

```bash
cd /home/dell/frappe-bench/gdl-frappe-bench
bench --site site.local migrate                     # patches, settings fields, property setters
bench --site site.local run-tests --app gdl_custom_app
bench --site site.local run-tests --app gdl_custom_app --module gdl_custom_app.tests.test_btc_phase2
bench restart                                        # production mode, after Python changes
```
- Tests roll back (`frappe.db.rollback()` in tearDown) and point GDL Setting at
  test masters (`TEST-BTC`, test warehouse/zones/wallets) via `setup_masters`.
- Known: 2 restriction tests fail on `site.local` because a live restriction
  (`BTR-00001`) exists — environment data, not code.
- The test item's Item Group is resolved by `btc_test_utils.item_group()`
  ("Digital Asset" vs "Digital Assets" differs between sites).
- Quick DB checks: pipe a script into `bench --site site.local console`.

## 5. Gotchas

- Frappe v16 `frappe.db.get_value` rejects SQL functions as strings
  (`"sum(x)"`) — use `frappe.db.sql` or dict syntax `{"SUM": "x"}`.
- Item naming: a `before_insert` hook runs before `set_new_name`, so setting
  `item_code` there is what ERPNext's `Item.autoname` picks up.
- `doctype_js` values may be lists (several scripts per doctype).
- Data entry: watch BTC quantities — a Mining entry was once submitted with
  500 BTC instead of 0.5, inflating stock value and the average cost.
- Git push over HTTPS needs the user's credentials (no `gh`, SSH key not on
  GitHub); the user pushes with `git push origin version-16`.
- Commit convention: conventional commits (`feat(btc): …`, `fix: …`), on
  `version-16`.
