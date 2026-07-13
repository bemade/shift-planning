import {Component, onWillStart, useState} from "@odoo/owl";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {sprintf} from "@web/core/utils/strings";
import {useService} from "@web/core/utils/hooks";

const MENU_WIDTH = 280;

export class ShiftGridAction extends Component {
    static template = "hr_shift_grid.ShiftGridAction";
    static props = {"*": true};

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.planningId =
            (this.props.action.params && this.props.action.params.planning_id) || false;
        // Ask for confirmation only once per opening of the grid.
        this.publishConfirmed = false;
        this.state = useState({data: null, menu: null});
        onWillStart(async () => {
            if (this.planningId) {
                this.state.data = await this.orm.call(
                    "hr.shift.planning",
                    "grid_data",
                    [[this.planningId]]
                );
            }
        });
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------

    isLocked(cell) {
        return cell.state === "holiday" || cell.state === "on_leave";
    }

    formatHours(hours) {
        return sprintf(_t("%(hours)s h"), {
            hours: Number.isInteger(hours) ? hours : hours.toFixed(1),
        });
    }

    gapLabel(count) {
        if (count === 1) {
            return _t("1 gap");
        }
        return sprintf(_t("%(count)s gaps"), {count});
    }

    cellClass(cell, day) {
        const classes = ["o_hr_shift_grid_cell"];
        if (day.is_today) {
            classes.push("o_hr_shift_grid_today");
        }
        if (!cell) {
            classes.push("o_hr_shift_grid_cell_off");
        } else if (this.isLocked(cell)) {
            classes.push("o_hr_shift_grid_cell_locked");
        } else if (!cell.template_id) {
            classes.push("o_hr_shift_grid_cell_empty");
        }
        return classes.join(" ");
    }

    // ------------------------------------------------------------------
    // Assignment menu
    // ------------------------------------------------------------------

    onRootClick() {
        this.state.menu = null;
    }

    onCellClick(ev, employee, day) {
        ev.stopPropagation();
        const cell = employee.cells[day.day_number];
        if (!cell || this.isLocked(cell)) {
            this.state.menu = null;
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        this.state.menu = {
            lineId: cell.line_id,
            templateId: cell.template_id,
            employeeName: employee.name,
            dayLabel: `${day.label} ${day.date_label}`,
            x: Math.max(8, Math.min(rect.left, window.innerWidth - MENU_WIDTH - 8)),
            y: rect.bottom + 4,
        };
    }

    async pickTemplate(templateId) {
        const menu = this.state.menu;
        this.state.menu = null;
        if (!menu || templateId === menu.templateId) {
            return;
        }
        await this.mutate("grid_write", [[this.planningId], menu.lineId, templateId]);
    }

    async removeShift() {
        const menu = this.state.menu;
        this.state.menu = null;
        if (!menu) {
            return;
        }
        await this.mutate("grid_write", [[this.planningId], menu.lineId, false]);
    }

    // ------------------------------------------------------------------
    // Native HTML5 drag & drop: move to an empty cell, swap with a
    // occupied one. Both are a single grid_swap() on the server.
    // ------------------------------------------------------------------

    onDragStart(ev, cell) {
        ev.dataTransfer.setData("text/plain", String(cell.line_id));
        ev.dataTransfer.effectAllowed = "move";
        ev.currentTarget.classList.add("o_hr_shift_grid_dragging");
    }

    onDragEnd(ev) {
        ev.currentTarget.classList.remove("o_hr_shift_grid_dragging");
    }

    onDragOver(ev, cell) {
        if (cell && !this.isLocked(cell)) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        }
    }

    onDragEnter(ev, cell) {
        if (cell && !this.isLocked(cell)) {
            ev.currentTarget.classList.add("o_hr_shift_grid_drop");
        }
    }

    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            ev.currentTarget.classList.remove("o_hr_shift_grid_drop");
        }
    }

    async onDrop(ev, cell) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("o_hr_shift_grid_drop");
        const sourceLineId = parseInt(ev.dataTransfer.getData("text/plain"), 10);
        if (
            !sourceLineId ||
            !cell ||
            this.isLocked(cell) ||
            sourceLineId === cell.line_id
        ) {
            return;
        }
        await this.mutate("grid_swap", [[this.planningId], sourceLineId, cell.line_id]);
    }

    // ------------------------------------------------------------------
    // Server round-trips
    // ------------------------------------------------------------------

    confirmPublished() {
        if (!this.state.data.published_on || this.publishConfirmed) {
            return Promise.resolve(true);
        }
        return new Promise((resolve) => {
            this.dialog.add(
                ConfirmationDialog,
                {
                    title: _t("Week already sent"),
                    body: _t(
                        "This week was already sent to the employees. " +
                            "The change will be logged in the chatter. Continue?"
                    ),
                    confirmLabel: _t("Continue"),
                    cancelLabel: _t("Cancel"),
                    confirm: () => {
                        this.publishConfirmed = true;
                        resolve(true);
                    },
                    cancel: () => resolve(false),
                },
                {onClose: () => resolve(false)}
            );
        });
    }

    async mutate(method, args) {
        if (!(await this.confirmPublished())) {
            return;
        }
        try {
            this.state.data = await this.orm.call("hr.shift.planning", method, args);
        } catch (error) {
            const message =
                (error.data && error.data.message) ||
                _t("The change could not be saved.");
            this.notification.add(message, {type: "danger"});
            this.state.data = await this.orm.call("hr.shift.planning", "grid_data", [
                [this.planningId],
            ]);
        }
    }
}

registry.category("actions").add("hr_shift_grid.action", ShiftGridAction);
