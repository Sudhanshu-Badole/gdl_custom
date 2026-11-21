// BTC row entry helpers.
//
// Stock Entry: ONE button, "BTC > Add BTC Rows", shown once the purpose is known. The dialog adapts:
//   Material Issue    wallet/zone filters + balance table; enter Qty per wallet/zone (capped at Available)
//   Material Transfer same table + To Zone / To Wallet (+ BTC status) + optional Fee Qty / Fee Rate per row
//   Material Receipt  To Zone / To Wallet + Qty + USD Rate (nothing to pick from, the BTC is new)
// Delivery Note: unchanged - "Available Balance" list and "Quick Enter" (wallet + qty split over zones).
//
// The server stays the hard check (btc/balance.py validate_available, utils/fee.py validate_fee,
// btc/receipts.py prepare_stock_entry); the dialog only fills the grid rows.
(() => {
	// Loaded by several doctypes in one session; register the handlers once.
	if (frappe.gdl_btc_balance) return;
	frappe.gdl_btc_balance = true;

	const METHOD = "gdl_custom_app.btc.balance.";
	const PURPOSES = ["Material Receipt", "Material Issue", "Material Transfer"];

	const posting_date = (frm) => frm.doc.posting_date || frappe.datetime.get_today();
	const fmt = (v) => format_number(v, null, 8);

	const get_defaults = () => frappe.xcall("gdl_custom_app.btc.receipts.get_btc_defaults");

	// reuse an empty row, or a BTC row that has no wallet yet, otherwise add one
	const target_row = (frm, item) => {
		const rows = frm.doc.items || [];
		return (
			rows.find((r) => !r.item_code) ||
			rows.find((r) => r.item_code === item && !r.wallet && !r.to_wallet) ||
			frm.add_child("items")
		);
	};

	const set_values = async (row, values) => {
		for (const [field, value] of Object.entries(values)) {
			if (value === undefined || value === null || value === "") continue;
			await frappe.model.set_value(row.doctype, row.name, field, value);
		}
	};

	// ---------------------------------------------------------------- Stock Entry

	const stock_entry_dialog = async (frm) => {
		const purpose = frm.doc.purpose;
		const defaults = await get_defaults();
		if (!defaults || !defaults.item || !defaults.warehouse) {
			frappe.msgprint(__("Set the BTC Item and BTC Warehouse in GDL Setting first."));
			return;
		}

		if (purpose === "Material Receipt") return receipt_dialog(frm, defaults);

		const is_transfer = purpose === "Material Transfer";
		let balances = [];

		const columns = [
			{ fieldname: "wallet", fieldtype: "Data", label: __("Wallet"), in_list_view: 1, read_only: 1, columns: 2 },
			{ fieldname: "zone", fieldtype: "Data", label: __("Zone"), in_list_view: 1, read_only: 1, columns: 2 },
			{ fieldname: "available", fieldtype: "Float", precision: 8, label: __("Available"), in_list_view: 1, read_only: 1, columns: 2 },
			{ fieldname: "qty", fieldtype: "Float", precision: 8, label: __("Qty"), in_list_view: 1, columns: 2 },
		];
		if (is_transfer) {
			columns.push(
				{ fieldname: "fee_qty", fieldtype: "Float", precision: 8, label: __("Fee Qty"), in_list_view: 1, columns: 1 },
				{ fieldname: "fee_rate", fieldtype: "Currency", label: __("Fee Rate (USD)"), in_list_view: 1, columns: 1 }
			);
		}

		const fields = [
			{ fieldname: "wallet", fieldtype: "Link", options: "BTC Wallet", label: __("Wallet"), change: () => refresh() },
			{ fieldname: "zone", fieldtype: "Link", options: "Internal Zone", label: __("Zone"), change: () => refresh() },
		];
		if (is_transfer) {
			fields.push(
				{ fieldtype: "Section Break", label: __("Transfer To") },
				{ fieldname: "to_zone", fieldtype: "Link", options: "Internal Zone", label: __("To Zone"), reqd: 1 },
				{ fieldtype: "Column Break" },
				{ fieldname: "to_wallet", fieldtype: "Link", options: "BTC Wallet", label: __("To Wallet"), reqd: 1 },
				{
					fieldname: "status",
					fieldtype: "Select",
					label: __("BTC Status"),
					options: "\nAvailable\nTrading\nLoan\nPledged",
				},
				{
					fieldname: "expiry",
					fieldtype: "Date",
					label: __("Status Expiry Date"),
					depends_on: "eval:['Trading','Loan','Pledged'].includes(doc.status)",
				}
			);
		}
		fields.push(
			{ fieldtype: "Section Break", label: __("Available BTC") },
			{
				fieldname: "rows",
				fieldtype: "Table",
				label: __("Wallets"),
				cannot_add_rows: 1,
				cannot_delete_rows: 1,
				in_place_edit: 1,
				data: [],
				fields: columns,
			}
		);

		const dialog = new frappe.ui.Dialog({
			title: is_transfer ? __("Add BTC Transfer Rows") : __("Add BTC Issue Rows"),
			size: "extra-large",
			fields,
			primary_action_label: __("Add Rows"),
			primary_action: async (values) => {
				const picked = (values.rows || []).filter((r) => flt(r.qty) > 0);
				if (!picked.length) {
					frappe.msgprint(__("Enter a quantity for at least one wallet."));
					return;
				}
				for (const r of picked) {
					const row_balance = balances.find((b) => b.wallet === r.wallet && b.zone === r.zone);
					if (row_balance && flt(r.qty, 9) > flt(row_balance.available, 9)) {
						frappe.msgprint(
							__("Wallet {0} in Zone {1} has {2} BTC available; {3} requested.", [r.wallet, r.zone, fmt(row_balance.available), fmt(r.qty)])
						);
						return;
					}
					if (is_transfer && !!flt(r.fee_qty) !== !!flt(r.fee_rate)) {
						frappe.msgprint(__("Wallet {0}: enter both Fee Qty and Fee Rate, or neither.", [r.wallet]));
						return;
					}
				}
				dialog.hide();
				for (const r of picked) {
					const row = target_row(frm, defaults.item);
					await set_values(row, {
						item_code: defaults.item,
						s_warehouse: defaults.warehouse,
						t_warehouse: is_transfer ? defaults.warehouse : null,
						zone: r.zone,
						wallet: r.wallet,
						to_zone: is_transfer ? values.to_zone : null,
						to_wallet: is_transfer ? values.to_wallet : null,
						custom_transfer_status: is_transfer ? values.status : null,
						custom_expiry_date: is_transfer ? values.expiry : null,
						qty: r.qty,
						custom_fee_qty: is_transfer && flt(r.fee_qty) ? r.fee_qty : null,
						custom_fee_rate: is_transfer && flt(r.fee_rate) ? r.fee_rate : null,
					});
				}
				frm.refresh_field("items");
				frappe.show_alert({ message: __("Added {0} row(s).", [picked.length]), indicator: "green" });
			},
		});

		const refresh = async () => {
			balances = await frappe.xcall(METHOD + "get_zone_wallet_balances", {
				wallet: dialog.get_value("wallet"),
				zone: dialog.get_value("zone"),
				on_date: posting_date(frm),
			});
			const table = dialog.fields_dict.rows;
			const entered = {};
			(table.df.data || []).forEach((r) => {
				if (flt(r.qty) || flt(r.fee_qty) || flt(r.fee_rate)) entered[`${r.wallet}|${r.zone}`] = r;
			});
			table.df.data = balances
				.filter((b) => b.available > 0)
				.map((b) => ({ wallet: b.wallet, zone: b.zone, available: b.available, ...(entered[`${b.wallet}|${b.zone}`] || {}) }));
			table.grid.refresh();
		};

		dialog.show();
		refresh();
	};

	const receipt_dialog = (frm, defaults) => {
		const dialog = new frappe.ui.Dialog({
			title: __("Add BTC Receipt Row"),
			fields: [
				{ fieldname: "to_zone", fieldtype: "Link", options: "Internal Zone", label: __("To Zone"), reqd: 1, get_query: () => ({ filters: { is_active: 1 } }) },
				{ fieldname: "to_wallet", fieldtype: "Link", options: "BTC Wallet", label: __("To Wallet"), reqd: 1, get_query: () => ({ filters: { is_active: 1 } }) },
				{ fieldname: "qty", fieldtype: "Float", precision: 8, label: __("Quantity (BTC)"), reqd: 1 },
				{ fieldname: "usd_rate", fieldtype: "Float", label: __("USD Rate"), reqd: 1 },
			],
			primary_action_label: __("Add Row"),
			primary_action: async (values) => {
				if (flt(values.qty) <= 0 || flt(values.usd_rate) <= 0) {
					frappe.msgprint(__("Quantity and USD Rate must be greater than zero."));
					return;
				}
				const existing = (frm.doc.items || []).find(
					(r) => r.to_zone === values.to_zone && r.to_wallet === values.to_wallet
				);
				if (existing) {
					frappe.msgprint(
						__("Wallet {0} in Zone {1} is already on row #{2}. Add the quantity to that row instead.", [
							values.to_wallet,
							values.to_zone,
							existing.idx,
						])
					);
					return;
				}
				dialog.hide();
				const row = target_row(frm, defaults.item);
				await set_values(row, {
					item_code: defaults.item,
					t_warehouse: defaults.warehouse,
					to_zone: values.to_zone,
					to_wallet: values.to_wallet,
					qty: values.qty,
					custom_usd_rate: values.usd_rate,
				});
				frm.refresh_field("items");
				frappe.show_alert({ message: __("Added 1 row."), indicator: "green" });
			},
		});
		dialog.show();
	};

	const setup_stock_entry = (frm) => {
		frm.remove_custom_button(__("Add BTC Rows"), __("BTC"));
		if (frm.doc.docstatus !== 0 || !PURPOSES.includes(frm.doc.purpose)) return;
		frm.add_custom_button(__("Add BTC Rows"), () => stock_entry_dialog(frm), __("BTC"));
	};

	frappe.ui.form.on("Stock Entry", {
		refresh: setup_stock_entry,
		stock_entry_type: setup_stock_entry,
		purpose: setup_stock_entry,
	});

	// ---------------------------------------------------------------- Row "Balance" field
	// Balance = available BTC in the row's source Zone + Wallet, less the quantity on the rows above that
	// draw from the same Zone + Wallet. The server sets the same value on save (btc/balance.py set_row_balances).

	const source_warehouse = (frm, row) =>
		frm.doc.doctype === "Stock Entry" ? row.s_warehouse : row.warehouse;

	const refresh_balances = async (frm) => {
		const defaults = await get_defaults();
		if (!defaults || !defaults.item || frm.doc.docstatus !== 0) return;
		const date = posting_date(frm);
		const rows = (frm.doc.items || []).filter(
			(r) => r.item_code === defaults.item && source_warehouse(frm, r) && r.zone && r.wallet
		);

		const available = {};
		await Promise.all(
			[...new Set(rows.map((r) => `${source_warehouse(frm, r)}|${r.zone}|${r.wallet}`))].map(async (key) => {
				const [warehouse, zone, wallet] = key.split("|");
				available[key] = flt(
					await frappe.xcall(METHOD + "get_row_balance", {
						item_code: defaults.item,
						warehouse,
						zone,
						wallet,
						on_date: date,
					})
				);
			})
		);

		const used = {};
		for (const row of frm.doc.items || []) {
			const key = `${source_warehouse(frm, row)}|${row.zone}|${row.wallet}`;
			const counted = rows.includes(row);
			const balance = counted ? flt(available[key] - (used[key] || 0), 8) : 0;
			if (counted) used[key] = flt((used[key] || 0) + flt(row.transfer_qty || row.qty), 8);
			if (flt(row.custom_balance, 8) !== balance) {
				await frappe.model.set_value(row.doctype, row.name, "custom_balance", balance);
			}
		}
	};

	let balance_timer;
	const schedule_balances = (frm) => {
		clearTimeout(balance_timer);
		balance_timer = setTimeout(() => refresh_balances(frm), 300);
	};

	const balance_handlers = (extra) => ({
		zone: (frm) => schedule_balances(frm),
		wallet: (frm) => schedule_balances(frm),
		qty: (frm) => schedule_balances(frm),
		item_code: (frm) => schedule_balances(frm),
		items_remove: (frm) => schedule_balances(frm),
		...extra,
	});

	frappe.ui.form.on("Stock Entry Detail", balance_handlers({ s_warehouse: (frm) => schedule_balances(frm) }));
	frappe.ui.form.on("Delivery Note Item", balance_handlers({ warehouse: (frm) => schedule_balances(frm) }));
	frappe.ui.form.on("Stock Entry", { posting_date: schedule_balances, onload_post_render: schedule_balances });
	frappe.ui.form.on("Delivery Note", { posting_date: schedule_balances, onload_post_render: schedule_balances });

	// ---------------------------------------------------------------- Delivery Note (unchanged)

	const render_table = (rows) => {
		if (!rows.length) return `<p class="text-muted">${__("No BTC balance found.")}</p>`;
		const body = rows
			.map(
				(r) => `<tr><td>${frappe.utils.escape_html(r.wallet)}</td><td>${frappe.utils.escape_html(r.zone)}</td>
				<td class="text-right">${fmt(r.balance)}</td><td class="text-right">${fmt(r.restricted)}</td>
				<td class="text-right"><b>${fmt(r.available)}</b></td></tr>`
			)
			.join("");
		return `<table class="table table-bordered table-sm"><thead><tr><th>${__("Wallet")}</th><th>${__("Zone")}</th>
			<th class="text-right">${__("Balance")}</th><th class="text-right">${__("Restricted")}</th>
			<th class="text-right">${__("Available")}</th></tr></thead><tbody>${body}</tbody></table>`;
	};

	const show_balance = (frm) => {
		const dialog = new frappe.ui.Dialog({
			title: __("Available BTC Balance"),
			size: "large",
			fields: [
				{ fieldname: "wallet", fieldtype: "Link", options: "BTC Wallet", label: __("Wallet"), onchange: () => refresh() },
				{ fieldname: "zone", fieldtype: "Link", options: "Internal Zone", label: __("Zone"), onchange: () => refresh() },
				{ fieldname: "table", fieldtype: "HTML" },
			],
		});
		const refresh = async () => {
			const rows = await frappe.xcall(METHOD + "get_zone_wallet_balances", {
				wallet: dialog.get_value("wallet"),
				zone: dialog.get_value("zone"),
				on_date: posting_date(frm),
			});
			dialog.get_field("table").$wrapper.html(render_table(rows));
		};
		dialog.show();
		refresh();
	};

	const delivery_quick_enter = (frm) => {
		const dialog = new frappe.ui.Dialog({
			title: __("Quick Enter BTC"),
			fields: [
				{ fieldname: "wallet", fieldtype: "Link", options: "BTC Wallet", label: __("Wallet"), reqd: 1 },
				{ fieldname: "qty", fieldtype: "Float", precision: 8, label: __("Quantity (BTC)"), reqd: 1 },
			],
			primary_action_label: __("Add Rows"),
			primary_action: async (values) => {
				const defaults = await get_defaults();
				const rows = await frappe.xcall(METHOD + "allocate_wallet_qty", {
					wallet: values.wallet,
					qty: values.qty,
					on_date: posting_date(frm),
				});
				for (const alloc of rows) {
					const row = target_row(frm, defaults.item);
					await set_values(row, {
						item_code: defaults.item,
						warehouse: defaults.warehouse,
						zone: alloc.zone,
						wallet: alloc.wallet,
						qty: alloc.qty,
					});
				}
				frm.refresh_field("items");
				dialog.hide();
				frappe.show_alert({ message: __("Added {0} row(s).", [rows.length]), indicator: "green" });
			},
		});
		dialog.show();
	};

	frappe.ui.form.on("Delivery Note", {
		refresh: (frm) => {
			if (frm.doc.docstatus !== 0) return;
			frm.add_custom_button(__("Available Balance"), () => show_balance(frm), __("BTC"));
			frm.add_custom_button(__("Quick Enter"), () => delivery_quick_enter(frm), __("BTC"));
		},
	});
})();
