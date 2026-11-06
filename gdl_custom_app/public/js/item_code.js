// Item Code is generated on save from the Item Group's Group Code (see utils/item_code.py);
// fixed asset items get an AST- prefix.
frappe.ui.form.on("Item", {
	refresh(frm) {
		toggle_item_code(frm);
	},
	item_group(frm) {
		toggle_item_code(frm);
	},
	is_fixed_asset(frm) {
		toggle_item_code(frm);
	},
});

function toggle_item_code(frm) {
	if (!frm.is_new() || frm.doc.variant_of) return;
	const reset = () => {
		frm.set_df_property("item_code", "reqd", 1);
		frm.set_df_property("item_code", "read_only", 0);
		frm.set_df_property("item_code", "description", "");
	};
	if (!frm.doc.item_group) return reset();

	frappe.call({
		method: "gdl_custom_app.utils.item_code.get_item_code_prefix",
		args: { item_group: frm.doc.item_group, is_fixed_asset: frm.doc.is_fixed_asset },
		callback(r) {
			if (!r.message) return reset();
			frm.set_value("item_code", "");
			frm.set_df_property("item_code", "reqd", 0);
			frm.set_df_property("item_code", "read_only", 1);
			frm.set_df_property(
				"item_code",
				"description",
				__("Generated on save as {0}-00001, {0}-00002, ...", [r.message])
			);
		},
	});
}
