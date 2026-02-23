#!/usr/bin/env python3
"""Command-line interface for the Schreiber Batch Inventory API.

Usage examples:
    python scripts/cli.py list
    python scripts/cli.py get 1
    python scripts/cli.py create --batch-code SCH-20260101-0001 --volume 1000 --fat-percent 3.5
    python scripts/cli.py consume 1 --qty 250 --order-id ORDER-001
    python scripts/cli.py near-expiry --n-days 3
    python scripts/cli.py delete 1
    python scripts/cli.py reserve 1 --qty 200 --purpose "Production run PL-001"
    python scripts/cli.py release 1 42
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30.0


def format_output(data: object) -> None:
    """Pretty-print a JSON-serialisable object."""
    print(json.dumps(data, indent=2, default=str))


def handle_response(response: httpx.Response) -> dict:
    """Return the JSON body or exit with an error message."""
    try:
        body = response.json()
    except Exception:
        body = {"detail": response.text}

    if response.status_code >= 400:
        print(
            f"Error {response.status_code}: {body.get('detail', 'Unknown error')}",
            file=sys.stderr,
        )
        sys.exit(1)

    return body


def cmd_list(args: argparse.Namespace, base_url: str) -> None:
    """List active batches with optional pagination."""
    params = {"skip": args.skip, "limit": args.limit}
    resp = httpx.get(f"{base_url}/api/batches/", params=params, timeout=DEFAULT_TIMEOUT)
    format_output(handle_response(resp))


def cmd_get(args: argparse.Namespace, base_url: str) -> None:
    """Retrieve a single batch by ID."""
    resp = httpx.get(f"{base_url}/api/batches/{args.id}", timeout=DEFAULT_TIMEOUT)
    format_output(handle_response(resp))


def cmd_create(args: argparse.Namespace, base_url: str) -> None:
    """Create a new batch."""
    received_at = args.received_at or datetime.now(timezone.utc).isoformat()
    data = {
        "batch_code": args.batch_code,
        "received_at": received_at,
        "shelf_life_days": args.shelf_life_days,
        "volume_liters": args.volume,
        "fat_percent": args.fat_percent,
    }
    resp = httpx.post(f"{base_url}/api/batches/", json=data, timeout=DEFAULT_TIMEOUT)
    format_output(handle_response(resp))


def cmd_consume(args: argparse.Namespace, base_url: str) -> None:
    """Consume liters from a batch."""
    data: dict[str, object] = {"qty": args.qty}
    if args.order_id:
        data["order_id"] = args.order_id
    resp = httpx.post(
        f"{base_url}/api/batches/{args.id}/consume",
        json=data,
        timeout=DEFAULT_TIMEOUT,
    )
    format_output(handle_response(resp))


def cmd_delete(args: argparse.Namespace, base_url: str) -> None:
    """Soft-delete a batch."""
    resp = httpx.delete(f"{base_url}/api/batches/{args.id}", timeout=DEFAULT_TIMEOUT)
    if resp.status_code == 204:
        print(f"Batch {args.id} deleted successfully.")
    else:
        handle_response(resp)


def cmd_near_expiry(args: argparse.Namespace, base_url: str) -> None:
    """List batches expiring within n_days."""
    resp = httpx.get(
        f"{base_url}/api/batches/near-expiry",
        params={"n_days": args.n_days},
        timeout=DEFAULT_TIMEOUT,
    )
    format_output(handle_response(resp))


def cmd_reserve(args: argparse.Namespace, base_url: str) -> None:
    """Reserve liters from a batch for production planning."""
    data: dict[str, object] = {"reserved_qty": args.qty}
    if args.purpose:
        data["purpose"] = args.purpose
    resp = httpx.post(
        f"{base_url}/api/batches/{args.id}/reserve",
        json=data,
        timeout=DEFAULT_TIMEOUT,
    )
    format_output(handle_response(resp))


def cmd_release(args: argparse.Namespace, base_url: str) -> None:
    """Release an active reservation."""
    resp = httpx.delete(
        f"{base_url}/api/batches/{args.id}/reservations/{args.reservation_id}",
        timeout=DEFAULT_TIMEOUT,
    )
    format_output(handle_response(resp))


def cmd_reservations(args: argparse.Namespace, base_url: str) -> None:
    """List all reservations for a batch."""
    resp = httpx.get(
        f"{base_url}/api/batches/{args.id}/reservations",
        timeout=DEFAULT_TIMEOUT,
    )
    format_output(handle_response(resp))


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Schreiber Batch Inventory CLI",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # --- list ---
    p_list = sub.add_parser("list", help="List active batches")
    p_list.add_argument("--skip", type=int, default=0, help="Pagination offset")
    p_list.add_argument("--limit", type=int, default=100, help="Page size")

    # --- get ---
    p_get = sub.add_parser("get", help="Get batch by ID")
    p_get.add_argument("id", type=int, help="Batch ID")

    # --- create ---
    p_create = sub.add_parser("create", help="Create a new batch")
    p_create.add_argument("--batch-code", required=True, help="Batch code (SCH-YYYYMMDD-XXXX)")
    p_create.add_argument("--volume", type=float, required=True, help="Volume in liters")
    p_create.add_argument("--fat-percent", type=float, required=True, help="Fat content %")
    p_create.add_argument("--shelf-life-days", type=int, default=7, help="Shelf life (1-30)")
    p_create.add_argument("--received-at", help="ISO 8601 timestamp (default: now)")

    # --- consume ---
    p_consume = sub.add_parser("consume", help="Consume liters from a batch")
    p_consume.add_argument("id", type=int, help="Batch ID")
    p_consume.add_argument("--qty", type=float, required=True, help="Liters to consume")
    p_consume.add_argument("--order-id", help="Associated order ID")

    # --- delete ---
    p_delete = sub.add_parser("delete", help="Soft-delete a batch")
    p_delete.add_argument("id", type=int, help="Batch ID")

    # --- near-expiry ---
    p_near = sub.add_parser("near-expiry", help="List batches nearing expiry")
    p_near.add_argument("--n-days", type=int, required=True, help="Look-ahead window in days")

    # --- reserve ---
    p_reserve = sub.add_parser("reserve", help="Reserve liters from a batch")
    p_reserve.add_argument("id", type=int, help="Batch ID")
    p_reserve.add_argument("--qty", type=float, required=True, help="Liters to reserve")
    p_reserve.add_argument("--purpose", help="Reason for reservation (e.g. production run ID)")

    # --- release ---
    p_release = sub.add_parser("release", help="Release an active reservation")
    p_release.add_argument("id", type=int, help="Batch ID")
    p_release.add_argument("reservation_id", type=int, help="Reservation ID")

    # --- reservations ---
    p_resv = sub.add_parser("reservations", help="List all reservations for a batch")
    p_resv.add_argument("id", type=int, help="Batch ID")

    return parser


def main() -> None:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    base_url: str = args.base_url

    dispatch = {
        "list": cmd_list,
        "get": cmd_get,
        "create": cmd_create,
        "consume": cmd_consume,
        "delete": cmd_delete,
        "near-expiry": cmd_near_expiry,
        "reserve": cmd_reserve,
        "release": cmd_release,
        "reservations": cmd_reservations,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args, base_url)


if __name__ == "__main__":
    main()
