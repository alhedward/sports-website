#!/usr/bin/env python3
"""Owner-only Cognito user bootstrap helper for Sports.vk2ale admins.

This utility intentionally uses local AWS credentials via boto3. Keep it for the
primary owner/operator; normal delegated admins should use Cognito login in the
admin manager and should not receive AWS credentials.

Examples:
  python3 sports/admin_manager/cognito_user_manager.py create \
    --user-pool-id ap-southeast-2_abc123 \
    --email admin@example.com \
    --group PrimaryAdmins

  python3 sports/admin_manager/cognito_user_manager.py disable \
    --user-pool-id ap-southeast-2_abc123 \
    --email admin@example.com
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from botocore.exceptions import ClientError

DEFAULT_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")


def client(region: str, profile: str | None):
    if profile:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)
    return session.client("cognito-idp")


def create_user(cognito, user_pool_id: str, email: str, group: str, suppress_email: bool) -> None:
    kwargs = {
        "UserPoolId": user_pool_id,
        "Username": email,
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
        "DesiredDeliveryMediums": ["EMAIL"],
    }
    if suppress_email:
        kwargs["MessageAction"] = "SUPPRESS"
    cognito.admin_create_user(**kwargs)
    cognito.admin_add_user_to_group(UserPoolId=user_pool_id, Username=email, GroupName=group)
    print(f"Created/added {email} to {group} in {user_pool_id}")


def add_to_group(cognito, user_pool_id: str, email: str, group: str) -> None:
    cognito.admin_add_user_to_group(UserPoolId=user_pool_id, Username=email, GroupName=group)
    print(f"Added {email} to {group}")


def remove_from_group(cognito, user_pool_id: str, email: str, group: str) -> None:
    cognito.admin_remove_user_from_group(UserPoolId=user_pool_id, Username=email, GroupName=group)
    print(f"Removed {email} from {group}")


def reset_password(cognito, user_pool_id: str, email: str) -> None:
    cognito.admin_reset_user_password(UserPoolId=user_pool_id, Username=email)
    print(f"Password reset initiated for {email}")


def disable_user(cognito, user_pool_id: str, email: str) -> None:
    cognito.admin_disable_user(UserPoolId=user_pool_id, Username=email)
    print(f"Disabled {email}")


def enable_user(cognito, user_pool_id: str, email: str) -> None:
    cognito.admin_enable_user(UserPoolId=user_pool_id, Username=email)
    print(f"Enabled {email}")


def list_users(cognito, user_pool_id: str) -> None:
    paginator = cognito.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=user_pool_id):
        for user in page.get("Users", []):
            attrs = {attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])}
            groups = cognito.admin_list_groups_for_user(UserPoolId=user_pool_id, Username=user["Username"]).get("Groups", [])
            group_names = ",".join(group["GroupName"] for group in groups)
            print(f"{user['Username']}\t{user.get('UserStatus','')}\t{attrs.get('email','')}\t{group_names}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Owner-only Cognito admin user manager")
    parser.add_argument("action", choices=["create", "add-group", "remove-group", "reset-password", "disable", "enable", "list"])
    parser.add_argument("--user-pool-id", required=True)
    parser.add_argument("--email")
    parser.add_argument("--group", default="Admins", choices=["PrimaryAdmins", "Admins", "Editors"])
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
    parser.add_argument("--suppress-email", action="store_true", help="Create user without sending Cognito's welcome email")
    args = parser.parse_args(argv)

    if args.action != "list" and not args.email:
        parser.error("--email is required for this action")

    cognito = client(args.region, args.profile or None)
    try:
        if args.action == "create":
            create_user(cognito, args.user_pool_id, args.email, args.group, args.suppress_email)
        elif args.action == "add-group":
            add_to_group(cognito, args.user_pool_id, args.email, args.group)
        elif args.action == "remove-group":
            remove_from_group(cognito, args.user_pool_id, args.email, args.group)
        elif args.action == "reset-password":
            reset_password(cognito, args.user_pool_id, args.email)
        elif args.action == "disable":
            disable_user(cognito, args.user_pool_id, args.email)
        elif args.action == "enable":
            enable_user(cognito, args.user_pool_id, args.email)
        elif args.action == "list":
            list_users(cognito, args.user_pool_id)
    except ClientError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
