"""
Performance migration: composite indexes for all hot query paths.

Fixes:
- Message(conversation, role) for first-user-message lookup (N+1 in ConversationListCreateView)
- AskEvent(user_id, mode, outcome, created_at) for monthly deep-ask count
- JapaDailyCompletion(commitment, date) for per-commitment aggregations
- BillingRecord(user, created_at) for subscription status / history lookup
- SavedReflection(user, created_at) for list ordering
- Conversation(user_id, updated_at) for list ordering
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guide_api", "0034_user_gita_sequence_journey"),
    ]

    operations = [
        # Message: fast lookup of first user message per conversation
        migrations.AddIndex(
            model_name="message",
            index=models.Index(
                fields=["conversation", "role", "created_at"],
                name="msg_conv_role_created_idx",
            ),
        ),
        # AskEvent: monthly deep-ask aggregate used in every MeView + AskView call
        migrations.AddIndex(
            model_name="askevent",
            index=models.Index(
                fields=["user_id", "mode", "outcome", "created_at"],
                name="askevent_user_mode_outcome_idx",
            ),
        ),
        # JapaDailyCompletion: per-commitment aggregate in japa summary
        migrations.AddIndex(
            model_name="japadailycompletion",
            index=models.Index(
                fields=["commitment", "date"],
                name="japacomplete_commit_date_idx",
            ),
        ),
        # BillingRecord: latest record lookup in SubscriptionStatusView
        migrations.AddIndex(
            model_name="billingrecord",
            index=models.Index(
                fields=["user", "-created_at"],
                name="billing_user_created_idx",
            ),
        ),
        # SavedReflection: list view ordering
        migrations.AddIndex(
            model_name="savedreflection",
            index=models.Index(
                fields=["user", "-created_at"],
                name="savedref_user_created_idx",
            ),
        ),
        # Conversation: primary list ordering
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["user_id", "-updated_at"],
                name="conv_userid_updated_idx",
            ),
        ),
    ]
