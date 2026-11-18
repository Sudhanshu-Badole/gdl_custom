// Fill the BTC warehouse (GDL Setting) on BTC item rows; other items are left alone.
// The server sets the same defaults on save (btc/receipts.py).
(() => {
	// Loaded by several doctypes in one session; register the handlers once.
	if (frappe.gdl_btc_defaults) return;
	frappe.gdl_btc_defaults = true;

	let defaults;
	const get_defaults = () =>
		(defaults ||= frappe
			.xcall("gdl_custom_app.btc.receipts.get_btc_defaults")
			.catch(() => ({})));

	const stock_entry_fields = (purpose) =>
		({
			"Material Receipt": ["t_warehouse"],
			"Material Issue": ["s_warehouse"],
			"Material Transfer": ["s_warehouse", "t_warehouse"],
		})[purpose] || [];

	const fill = (fields) => async (frm, cdt, cdn) => {
		const row = locals[cdt][cdn];
		const d = await get_defaults();
		if (!d || !d.item || !d.warehouse || row.item_code !== d.item) return;
		for (const field of typeof fields === "function" ? fields(frm) : fields) {
			if (row[field] !== d.warehouse) await frappe.model.set_value(cdt, cdn, field, d.warehouse);
		}
	};

	frappe.ui.form.on("Stock Entry Detail", {
		item_code: fill((frm) => stock_entry_fields(frm.doc.purpose)),
	});
	frappe.ui.form.on("Purchase Order Item", { item_code: fill(["warehouse"]) });

	// A row added by hand copies the row above, so the user only picks the wallet.
	const previous_row = (frm, cdt, cdn) => {
		const rows = frm.doc.items || [];
		const index = rows.findIndex((r) => r.name === cdn);
		return index > 0 ? rows[index - 1] : null;
	};

	const copy_fields = async (cdt, cdn, values) => {
		for (const [field, value] of Object.entries(values)) {
			if (value !== undefined && value !== null && value !== "") {
				await frappe.model.set_value(cdt, cdn, field, value);
			}
		}
	};

	// Purchase Receipt from a PO: new BTC row = same item, rate and PO link, qty = what is still to receive.
	frappe.ui.form.on("Purchase Receipt Item", {
		item_code: fill(["warehouse"]),
		items_add: async (frm, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const prev = previous_row(frm, cdt, cdn);
			if (row.item_code || !prev || !prev.purchase_order_item) return;
			const d = await get_defaults();
			if (!d || !d.item || prev.item_code !== d.item) return;

			const rows_above = (frm.doc.items || []).filter(
				(r) => r.name !== cdn && r.purchase_order_item === prev.purchase_order_item
			);
			const entered = rows_above.reduce((sum, r) => sum + flt(r.qty), 0);
			const left = await frappe.xcall("gdl_custom_app.btc.receipts.get_po_item_balance", {
				purchase_order_item: prev.purchase_order_item,
				exclude_receipt: frm.doc.name,
			});
			await frappe.model.set_value(cdt, cdn, "item_code", prev.item_code);
			await copy_fields(cdt, cdn, {
				uom: prev.uom,
				purchase_order: prev.purchase_order,
				purchase_order_item: prev.purchase_order_item,
				warehouse: prev.warehouse,
				zone: prev.zone,
				cost_center: prev.cost_center,
				rate: prev.rate,
				qty: Math.max(0, flt(left - entered, 8)),
			});
		},
	});

	// Stock Entry Material Receipt (Mining etc.): new row = same item, UOM, USD rate and target zone.
	frappe.ui.form.on("Stock Entry Detail", {
		items_add: async (frm, cdt, cdn) => {
			if (frm.doc.purpose !== "Material Receipt") return;
			const row = locals[cdt][cdn];
			const prev = previous_row(frm, cdt, cdn);
			if (row.item_code || !prev) return;
			const d = await get_defaults();
			if (!d || !d.item || prev.item_code !== d.item) return;

			await frappe.model.set_value(cdt, cdn, "item_code", prev.item_code);
			await copy_fields(cdt, cdn, {
				uom: prev.uom,
				t_warehouse: prev.t_warehouse,
				to_zone: prev.to_zone,
				custom_usd_rate: prev.custom_usd_rate,
			});
		},
	});
})();
