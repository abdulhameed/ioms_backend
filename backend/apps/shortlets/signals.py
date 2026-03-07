"""
Shortlets signals — Milestone 2.

Signals:
  - ApprovalWorkflow post_save → sync CautionDeposit status + notify
  - ShortletApartment post_save (created) → auto-create InventoryItems from templates
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="approvals.ApprovalWorkflow")
def sync_on_caution_workflow_change(sender, instance, **kwargs):
    if instance.workflow_type != "caution_refund":
        return
    _handle_caution_workflow(instance)


def _handle_caution_workflow(workflow):
    from apps.shortlets.models import CautionDeposit
    from apps.users.models import Notification

    try:
        deposit = CautionDeposit.objects.select_related(
            "booking__client", "booking__created_by"
        ).get(id=workflow.object_id)
    except CautionDeposit.DoesNotExist:
        logger.warning(
            "CautionDeposit %s not found for workflow %s",
            workflow.object_id,
            workflow.id,
        )
        return

    if workflow.status == "approved":
        deposit.status = "approved_for_refund"
        deposit.save(update_fields=["status", "updated_at"])

        # Notify the staff member who initiated the checkout
        if deposit.initiated_by_id:
            Notification.objects.create(
                recipient=deposit.initiated_by,
                notification_type="approval_decided",
                title="Caution Refund Approved",
                body=(
                    f"Caution deposit for booking "
                    f"{deposit.booking.booking_code or deposit.booking_id} "
                    f"has been approved for refund. "
                    f"Amount: ₦{deposit.refund_amount:,.2f}."
                ),
                resource_type="CautionDeposit",
                resource_id=deposit.id,
            )


@receiver(post_save, sender="shortlets.ShortletApartment")
def auto_create_inventory_items(sender, instance, created, **kwargs):
    """On new ShortletApartment, bulk-create InventoryItems from matching templates."""
    if not created:
        return
    _populate_inventory_from_templates(instance)


def _populate_inventory_from_templates(apartment):
    from apps.shortlets.models import InventoryItem, InventoryTemplate

    # Templates with no apartment/yearly_rental FK are unit_type-level blueprints
    templates = InventoryTemplate.objects.filter(
        apartment__isnull=True,
        yearly_rental__isnull=True,
        unit_type=apartment.unit_type,
    )
    if not templates.exists():
        return

    items = [
        InventoryItem(
            apartment=apartment,
            item_name=t.item_name,
            category=t.category,
            quantity_total=t.quantity_expected,
            quantity_good=t.quantity_expected,
        )
        for t in templates
    ]
    InventoryItem.objects.bulk_create(items)
    logger.info(
        "Auto-created %d inventory items for apartment %s from templates",
        len(items),
        apartment.id,
    )
