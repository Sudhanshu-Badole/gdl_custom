// Fill the BTC warehouse (GDL Setting) on BTC item rows; other items are left alone.
// The server sets the same defaults on save (btc/receipts.py).
(() => {
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
	frappe.ui.form.on("Purchase Receipt Item", { item_code: fill(["warehouse"]) });
})();
