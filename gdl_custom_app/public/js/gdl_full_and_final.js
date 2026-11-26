// Full and Final Statement (GDL): recalculate the benefit formulas and open the A-F print format.
frappe.ui.form.on("Full and Final Statement", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new() && frm.doc.custom_separation_request) {
			frm.add_custom_button(__("Recalculate Benefits"), () => {
				frappe.call({
					method: "gdl_custom_app.gdl_hr.fnf.recalculate_benefits",
					args: { statement: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		}
		frm.trigger("finance_journal_entry");
		frm.trigger("show_status");
	},

	finance_journal_entry(frm) {
		// Finance reads the statement; the standard button needs submit rights, so they get this one
		const is_hr = ["HR Manager", "HR User", "System Manager"].some((r) => frappe.user.has_role(r));
		const is_finance = ["Accounts Manager", "Accounts User"].some((r) => frappe.user.has_role(r));
		if (is_hr || !is_finance || frm.doc.docstatus !== 1 || frm.doc.status !== "Unpaid") return;
		frm.remove_custom_button(__("Create Journal Entry"));
		frm.add_custom_button(__("Create Journal Entry"), () => {
			frappe.call({
				method: "gdl_custom_app.gdl_hr.fnf.create_journal_entry",
				args: { statement: frm.doc.name },
				callback: (r) => {
					const docs = frappe.model.sync(r.message);
					frappe.set_route("Form", docs[0].doctype, docs[0].name);
				},
			});
		});
	},

	show_status(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.docstatus !== 0 || !frm.doc.custom_separation_request) return;
		const notes = [];
		if (frm.doc.custom_nomination_status && frm.doc.custom_nomination_status !== "Valid") {
			notes.push(__("Nomination: {0}.", [frm.doc.custom_nomination_status]));
		}
		if (flt(frm.doc.custom_notice_shortfall_days) > 0) {
			notes.push(__("Notice shortfall of {0} day(s): check the recovery in Section C.", [frm.doc.custom_notice_shortfall_days]));
		}
		if (notes.length) frm.dashboard.set_headline_alert(notes.join("<br>"), "orange");
	},
});
