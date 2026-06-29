# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

import fsspec.asyn

from odoo import api, fields, models


class FsStorage(models.Model):
    _inherit = "fs.storage"

    s3_endpoint_url = fields.Char(
        string="S3 Endpoint URL",
        help="The S3 endpoint URL (e.g. https://s3.amazonaws.com).",
    )
    s3_access_key_id = fields.Char(
        string="Access Key ID",
        help="Your S3 access key ID.",
    )
    s3_secret_access_key = fields.Char(
        string="Secret Access Key",
        password=True,
        help="Your S3 secret access key.",
    )
    s3_region = fields.Char(
        string="Region",
        help="The AWS region of your S3 bucket (e.g. us-east-1).",
    )
    s3_bucket = fields.Char(
        string="Bucket",
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

    @api.onchange("protocol")
    def _onchange_protocol_s3(self):
        """When protocol changes to S3, init fields and set smart defaults."""
        if self.protocol == "s3":
            opts = self.json_options or {}
            self.s3_endpoint_url = opts.get("endpoint_url", "")
            self.s3_access_key_id = opts.get("key", "")
            self.s3_secret_access_key = opts.get("secret", "")
            client_kwargs = opts.get("client_kwargs", {}) or {}
            if isinstance(client_kwargs, dict):
                self.s3_region = client_kwargs.get("region_name", "")
            self.s3_bucket = self.directory_path or ""
            # Smart defaults for S3
            self.use_as_default_for_attachments = True
            self.optimizes_directory_path = True
            self.use_filename_obfuscation = True
            self.is_directory_path_in_url = True

    @api.onchange(
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_region",
        "s3_bucket",
    )
    def _onchange_s3_fields(self):
        """Sync S3-specific fields to json_options and directory_path."""
        if self.protocol != "s3":
            return
        self._write_s3_fields_to_options()

    def _read_s3_fields_from_options(self):
        """Populate S3 fields from json_options and directory_path."""
        self.ensure_one()
        opts = self.json_options or {}
        self.s3_endpoint_url = opts.get("endpoint_url", "")
        self.s3_access_key_id = opts.get("key", "")
        self.s3_secret_access_key = opts.get("secret", "")
        client_kwargs = opts.get("client_kwargs", {}) or {}
        if isinstance(client_kwargs, dict):
            self.s3_region = client_kwargs.get("region_name", "")
        self.s3_bucket = self.directory_path or ""

    def _write_s3_fields_to_options(self):
        """Write S3-specific fields to json_options and directory_path."""
        self.ensure_one()
        if self.protocol != "s3":
            return
        opts = dict(self.json_options or {})
        for opt_key, field_name in [
            ("endpoint_url", "s3_endpoint_url"),
            ("key", "s3_access_key_id"),
            ("secret", "s3_secret_access_key"),
        ]:
            val = self[field_name]
            if val:
                opts[opt_key] = val
            else:
                opts.pop(opt_key, None)
        if self.s3_region:
            client_kwargs = opts.get("client_kwargs", {}) or {}
            if not isinstance(client_kwargs, dict):
                client_kwargs = {}
            client_kwargs["region_name"] = self.s3_region
            opts["client_kwargs"] = client_kwargs
        else:
            client_kwargs = opts.get("client_kwargs", {}) or {}
            if isinstance(client_kwargs, dict):
                client_kwargs.pop("region_name", None)
            if client_kwargs:
                opts["client_kwargs"] = client_kwargs
            else:
                opts.pop("client_kwargs", None)
        self.json_options = opts
        if self.s3_bucket:
            self.directory_path = self.s3_bucket

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        s3_records = records.filtered(lambda r: r.protocol == "s3")
        if s3_records:
            s3_records.write(
                {
                    "use_as_default_for_attachments": True,
                    "optimizes_directory_path": True,
                    "use_filename_obfuscation": True,
                    "is_directory_path_in_url": True,
                }
            )
            for rec in s3_records:
                rec._write_s3_fields_to_options()
        return records

    def write(self, vals):
        res = super().write(vals)
        s3_field_names = {
            "s3_endpoint_url",
            "s3_access_key_id",
            "s3_secret_access_key",
            "s3_region",
            "s3_bucket",
        }
        if s3_field_names & set(vals.keys()):
            for rec in self:
                if rec.protocol == "s3":
                    rec._write_s3_fields_to_options()
        return res

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
