// Exit Interview Response: show the whole questionnaire as one page (radio buttons, checkboxes, text boxes)
// instead of a grid the employee would have to edit row by row. The answers still live in the child table.
const ANSWER_DOCTYPE = "Exit Interview Answer";

frappe.ui.form.on("Exit Interview Response", {
	refresh(frm) {
		frm.trigger("render_questionnaire");
	},

	render_questionnaire(frm) {
		const editable = frm.doc.docstatus === 0 && frm.perm[0] && frm.perm[0].write;
		const esc = frappe.utils.escape_html;
		let part = null;
		let html = '<div class="gdl-questionnaire">';

		(frm.doc.answers || []).forEach((row, i) => {
			if (row.part !== part) {
				part = row.part;
				html += `<h5 style="margin:24px 0 8px;font-weight:600">${esc(part)}</h5>`;
			}
			html += `<div class="gdl-q" data-name="${esc(row.name)}" style="margin:0 0 16px">`;
			html += `<div style="margin-bottom:6px">${i + 1}. ${esc(row.question)}${
				row.mandatory ? ' <span class="text-danger">*</span>' : ""
			}</div>`;
			html += gdl_answer_control(row, editable, esc);
			html += "</div>";
		});
		html += "</div>";

		const $wrapper = frm.fields_dict.questionnaire.$wrapper;
		$wrapper.html(html);
		if (!editable) return;

		$wrapper.off("change.gdl").on("change.gdl", "input, textarea", function () {
			const $q = $(this).closest(".gdl-q");
			const name = $q.data("name");
			const row = frm.doc.answers.find((r) => r.name === name);
			let value;
			if (row.answer_type === "Text") {
				value = $q.find("textarea").val();
			} else if (row.answer_type === "Multi Select") {
				value = $q
					.find("input:checked")
					.map((_i, el) => el.value)
					.get()
					.join("\n");
			} else {
				value = $q.find("input:checked").val() || "";
			}
			frappe.model.set_value(ANSWER_DOCTYPE, name, "answer", value);
		});
	},
});

function gdl_answer_control(row, editable, esc) {
	const disabled = editable ? "" : " disabled";
	const options = (row.options || "").split("\n").filter((o) => o.trim());
	const answer = row.answer || "";

	if (row.answer_type === "Text") {
		return `<textarea class="form-control" rows="3"${disabled}>${esc(answer)}</textarea>`;
	}

	const chosen = answer.split("\n").map((a) => a.trim());
	const multi = row.answer_type === "Multi Select";
	const horizontal = row.answer_type === "Rating 4" || row.answer_type === "Rating 5";
	const kind = multi ? "checkbox" : "radio";
	const items = options.map((option) => {
		const checked = chosen.includes(option) ? " checked" : "";
		return `<label style="display:${horizontal ? "inline-block;margin-right:20px" : "block"};font-weight:normal">
			<input type="${kind}" name="${esc(row.name)}" value="${esc(option)}"${checked}${disabled}> ${esc(option)}</label>`;
	});
	return items.join("");
}
