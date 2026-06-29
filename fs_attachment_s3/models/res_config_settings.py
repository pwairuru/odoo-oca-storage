# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def action_force_migrate_to_s3(self):
        """Force migrate all attachments from DB/filestore to the
        default S3 object storage configured in fs.storage."""
        self.env["ir.attachment"].sudo().force_storage()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Migration Triggered"),
                "message": _(
                    "All attachments are being migrated to the "
                    "configured S3 object storage."
                ),
                "type": "success",
            },
        }
