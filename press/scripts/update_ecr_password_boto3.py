#!/usr/bin/env python3
# Purpose: Automatically update Press Settings docker_registry_password using boto3
# The Root Domain document is assumed to have the same name as the current site.

from __future__ import annotations

import base64
import os
from pathlib import Path

import boto3
import frappe
from botocore.exceptions import BotoCoreError, ClientError


def get_root_domain_doc():
    """Fetch Root Domain document whose name equals the current site name."""
    site_name = frappe.local.site
    if not site_name:
        raise ValueError("Could not determine current site name (frappe.local.site is empty)")

    root_domain = frappe.get_doc("Root Domain", site_name)
    aws_access_key_id = root_domain.aws_access_key_id
    aws_secret_access_key = root_domain.get_password("aws_secret_access_key", raise_exception=False)
    aws_region = root_domain.aws_region

    if not aws_access_key_id or not aws_secret_access_key or not aws_region:
        raise ValueError(f"Root Domain {root_domain.name} is missing AWS credentials or region")

    return root_domain


def update_ecr_password():
    """
    Use boto3 to get the ECR login password for the Root Domain's AWS region
    and update Press Settings docker_registry_password.
    """
    try:
        root_domain = get_root_domain_doc()

        client = boto3.client(
            "ecr",
            region_name=root_domain.aws_region,
            aws_access_key_id=root_domain.aws_access_key_id,
            aws_secret_access_key=root_domain.get_password("aws_secret_access_key"),
        )

        response = client.get_authorization_token()
        token = response["authorizationData"][0]["authorizationToken"]
        decoded = base64.b64decode(token).decode("utf-8")
        username, password = decoded.split(":", 1)

        if username != "AWS" or not password:
            raise ValueError("Received an invalid ECR authorization token from boto3")

        frappe.db.set_single_value("Press Settings", "docker_registry_password", password)
        frappe.db.commit()
        print("✓ Successfully updated docker_registry_password in Press Settings")

    except (BotoCoreError, ClientError) as e:
        error_msg = f"AWS boto3 error: {str(e)}"
        print(f"✗ {error_msg}")
        frappe.log_error("ECR Password Update Failed (boto3)", error_msg)
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"✗ {error_msg}")
        frappe.log_error("ECR Password Update Failed (boto3)", error_msg)
        raise


def main():
    # When run via `bench execute`, frappe is already connected and frappe.local.site is set.
    update_ecr_password()


if __name__ == "__main__":
    main()