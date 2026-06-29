# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

import fsspec.asyn

from odoo import api, fields, models


class FsStorage(models.Model):
    _inherit = "fs.storage"

    s3_endpoint_url = fields.Char(
        string="S3 Endpoint URL",
        compute="_compute_s3_fields",
        inverse="_inverse_s3_fields",
        help="The S3 endpoint URL (e.g. https://s3.amazonaws.com).",
    )
    s3_access_key_id = fields.Char(
        string="Access Key ID",
        compute="_compute_s3_fields",
        inverse="_inverse_s3_fields",
        help="Your S3 access key ID.",
    )
    s3_secret_access_key = fields.Char(
        string="Secret Access Key",
        compute="_compute_s3_fields",
        inverse="_inverse_s3_fields",
        password=True,
        help="Your S3 secret access key.",
    )
    s3_region = fields.Char(
        string="Region",
        compute="_compute_s3_fields",
        inverse="_inverse_s3_fields",
        help="The AWS region of your S3 bucket (e.g. us-east-1).",
    )
    s3_bucket = fields.Char(
        string="Bucket",
        compute="_compute_s3_fields",
        inverse="_inverse_s3_fields",
        help="The S3 bucket name where attachments will be stored.",
    )

    s3_uses_signed_url_for_x_sendfile = fields.Boolean(
        string="Use signed URL for X-Accel-Redirect",
        help="If checked, the storage will use signed URLs for attachments "
        "when using X-Accel-Redirect. This is useful for S3 storage where the "
        "file path is not directly accessible without authentication.",
    )
    s3_signed_url_expiration = fields.Integer(
        string="Signed URL Expiration (seconds)",
        default=30,
        help="The expiration time for the signed URL in seconds. "
        "Default is 30 seconds.",
    )

    @api.depends("json_options", "directory_path")
    def _compute_s3_fields(self):
        for rec in self:
            rec.s3_endpoint_url = rec.json_options.get("endpoint_url", "")
            rec.s3_access_key_id = rec.json_options.get("key", "")
            rec.s3_secret_access_key = rec.json_options.get("secret", "")
            rec.s3_region = (
                rec.json_options.get("client_kwargs", {}).get("region_name", "")
                if isinstance(rec.json_options.get("client_kwargs"), dict)
                else ""
            )
            rec.s3_bucket = rec.directory_path or ""

    def _inverse_s3_fields(self):
        for rec in self:
            options = dict(rec.json_options)
            options["endpoint_url"] = rec.s3_endpoint_url or None
            options["key"] = rec.s3_access_key_id or None
            options["secret"] = rec.s3_secret_access_key or None
            client_kwargs = options.get("client_kwargs", {}) or {}
            if not isinstance(client_kwargs, dict):
                client_kwargs = {}
            if rec.s3_region:
                client_kwargs["region_name"] = rec.s3_region
            elif "region_name" in client_kwargs:
                del client_kwargs["region_name"]
            if client_kwargs:
                options["client_kwargs"] = client_kwargs
            else:
                options.pop("client_kwargs", None)
            # Remove empty keys
            keys_to_del = [k for k, v in options.items() if v is None]
            for k in keys_to_del:
                del options[k]
            rec.json_options = options
            rec.directory_path = rec.s3_bucket or None

    @property
    def _server_env_fields(self):
        """Override to include S3 specific fields."""
        fields = super()._server_env_fields
        fields.update(
            {
                "s3_endpoint_url": {},
                "s3_access_key_id": {},
                "s3_secret_access_key": {},
                "s3_region": {},
                "s3_bucket": {},
                "s3_uses_signed_url_for_x_sendfile": {},
                "s3_signed_url_expiration": {},
            }
        )
        return fields

    @property
    def is_s3_storage(self):
        """Check if the storage is an S3 storage."""
        self.ensure_one()
        return hasattr(self._get_root_filesystem(self.fs), "s3")

    @api.model
    def _s3_call_generate_presigned_url(self, s3_client, *args, **kwargs):
        """Generate a presigned URL for S3 operations."""
        # s3fs uses aiobotocore as s3 client, which is asynchronous.
        # We need to run the async function in a synchronous context.
        return fsspec.asyn.sync(
            fsspec.asyn.get_loop(),
            s3_client.generate_presigned_url,
            *args,
            timeout=None,
            **kwargs,
        )
