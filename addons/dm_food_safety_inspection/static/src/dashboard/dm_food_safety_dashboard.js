/** @odoo-module */

import { Component, onMounted, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";

export class FoodSafetyDashboard extends Component {
    static components = { Layout };
    static template = "dm_food_safety_inspection.FoodSafetyDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: null,
            data: null,
        });

        onMounted(() => {
            this.resetScrollPosition();
        });

        onWillStart(async () => {
            await this.loadDashboard();
        });
    }

    resetScrollPosition() {
        const scrollContainer = this.el?.querySelector(".o_dm_food_safety_dashboard_content");
        if (scrollContainer) {
            scrollContainer.scrollTop = 0;
        }

        const actionElement = this.el?.closest(".o_action");
        if (actionElement) {
            actionElement.scrollTop = 0;
        }
    }

    async loadDashboard() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call("dm.food.inspection", "get_dashboard_payload", [], {});
        } catch (error) {
            this.state.data = null;
            this.state.error = error?.data?.message || error?.message || "Unable to load the dashboard.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
            this.resetScrollPosition();
        }
    }

    async reloadDashboard() {
        await this.loadDashboard();
    }

    async openDashboardAction(ev) {
        const actionKey = ev.currentTarget.dataset.action;
        if (!actionKey) {
            return;
        }
        try {
            const action = await this.orm.call("dm.food.inspection", "action_dashboard_get_action", [actionKey], {});
            await this.action.doAction(action);
        } catch (error) {
            const message = error?.data?.message || error?.message || "Unable to open the selected view.";
            this.notification.add(message, { type: "danger" });
        }
    }
}

registry.category("actions").add("dm_food_safety_dashboard", FoodSafetyDashboard);
