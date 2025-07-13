"""
Payment processing background tasks.

Handles webhook processing, subscription management, and payment retries.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import stripe
import json

from api.database import get_db
from api.models.user import User
from api.models.transaction import Transaction
from api.models.subscription import Subscription
from api.models.prompt import Prompt
from api.services.cache_service import get_cache_service
from api.services.email_service import send_email
from api.config import settings

logger = get_task_logger(__name__)
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key


@shared_task(bind=True, max_retries=3)
def process_payment_webhook(self, event_type: str, event_data: Dict[str, Any]):
    """
    Process Stripe webhook events asynchronously.
    
    Handles various payment events like successful charges, failed payments, etc.
    """
    try:
        logger.info(f"Processing webhook event: {event_type}")
        
        db = next(get_db())
        
        if event_type == "payment_intent.succeeded":
            # Handle successful payment
            payment_intent = event_data.get("object", {})
            metadata = payment_intent.get("metadata", {})
            
            # Find or create transaction
            transaction = db.query(Transaction).filter(
                Transaction.stripe_payment_intent_id == payment_intent["id"]
            ).first()
            
            if transaction:
                # Update existing transaction
                transaction.status = "completed"
                transaction.completed_at = datetime.utcnow()
                transaction.stripe_response = payment_intent
                
                # Grant access to the prompt
                if transaction.prompt_id and transaction.user_id:
                    user = db.query(User).filter(User.id == transaction.user_id).first()
                    prompt = db.query(Prompt).filter(Prompt.id == transaction.prompt_id).first()
                    
                    if user and prompt:
                        # Add prompt to user's purchased prompts
                        if user.extra_metadata is None:
                            user.extra_metadata = {}
                        
                        if "purchased_prompts" not in user.extra_metadata:
                            user.extra_metadata["purchased_prompts"] = []
                        
                        if str(prompt.id) not in user.extra_metadata["purchased_prompts"]:
                            user.extra_metadata["purchased_prompts"].append(str(prompt.id))
                        
                        # Send purchase confirmation email
                        send_email.delay(
                            to_email=user.email,
                            subject="Purchase Confirmation",
                            template="purchase_confirmation",
                            context={
                                "user_name": user.name,
                                "prompt_title": prompt.title,
                                "amount": transaction.amount,
                                "transaction_id": str(transaction.id)
                            }
                        )
                
                db.commit()
                logger.info(f"Payment completed for transaction {transaction.id}")
                
        elif event_type == "payment_intent.payment_failed":
            # Handle failed payment
            payment_intent = event_data.get("object", {})
            
            transaction = db.query(Transaction).filter(
                Transaction.stripe_payment_intent_id == payment_intent["id"]
            ).first()
            
            if transaction:
                transaction.status = "failed"
                transaction.stripe_response = payment_intent
                transaction.extra_metadata = {
                    "failure_reason": payment_intent.get("last_payment_error", {}).get("message", "Unknown error")
                }
                db.commit()
                
                # Notify user of failed payment
                user = db.query(User).filter(User.id == transaction.user_id).first()
                if user:
                    send_email.delay(
                        to_email=user.email,
                        subject="Payment Failed",
                        template="payment_failed",
                        context={
                            "user_name": user.name,
                            "reason": transaction.extra_metadata.get("failure_reason")
                        }
                    )
                
                logger.warning(f"Payment failed for transaction {transaction.id}")
                
        elif event_type == "customer.subscription.created":
            # Handle new subscription
            subscription_data = event_data.get("object", {})
            customer_id = subscription_data.get("customer")
            
            # Find user by stripe customer ID
            user = db.query(User).filter(
                User.stripe_customer_id == customer_id
            ).first()
            
            if user:
                subscription = Subscription(
                    user_id=user.id,
                    stripe_subscription_id=subscription_data["id"],
                    status=subscription_data["status"],
                    current_period_start=datetime.fromtimestamp(subscription_data["current_period_start"]),
                    current_period_end=datetime.fromtimestamp(subscription_data["current_period_end"]),
                    plan_id=subscription_data.get("items", {}).get("data", [{}])[0].get("price", {}).get("id"),
                    extra_metadata=subscription_data
                )
                db.add(subscription)
                db.commit()
                
                logger.info(f"Subscription created for user {user.id}")
                
        elif event_type == "customer.subscription.updated":
            # Handle subscription updates
            subscription_data = event_data.get("object", {})
            
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_data["id"]
            ).first()
            
            if subscription:
                subscription.status = subscription_data["status"]
                subscription.current_period_start = datetime.fromtimestamp(subscription_data["current_period_start"])
                subscription.current_period_end = datetime.fromtimestamp(subscription_data["current_period_end"])
                subscription.extra_metadata = subscription_data
                db.commit()
                
                logger.info(f"Subscription updated: {subscription.id}")
                
        elif event_type == "customer.subscription.deleted":
            # Handle subscription cancellation
            subscription_data = event_data.get("object", {})
            
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_data["id"]
            ).first()
            
            if subscription:
                subscription.status = "cancelled"
                subscription.cancelled_at = datetime.utcnow()
                db.commit()
                
                # Notify user
                user = db.query(User).filter(User.id == subscription.user_id).first()
                if user:
                    send_email.delay(
                        to_email=user.email,
                        subject="Subscription Cancelled",
                        template="subscription_cancelled",
                        context={
                            "user_name": user.name,
                            "end_date": subscription.current_period_end
                        }
                    )
                
                logger.info(f"Subscription cancelled: {subscription.id}")
        
        db.close()
        
        return {
            "status": "success",
            "event_type": event_type,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def check_subscription_renewals(self):
    """
    Check for subscriptions that need renewal processing.
    
    Runs periodically to handle subscription renewals and expirations.
    """
    try:
        logger.info("Checking subscription renewals")
        
        db = next(get_db())
        
        # Find subscriptions expiring in the next 3 days
        expiry_threshold = datetime.utcnow() + timedelta(days=3)
        
        expiring_subscriptions = db.query(Subscription).filter(
            Subscription.status == "active",
            Subscription.current_period_end <= expiry_threshold
        ).all()
        
        for subscription in expiring_subscriptions:
            # Check with Stripe for latest status
            try:
                stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                
                # Update local subscription data
                subscription.status = stripe_sub.status
                subscription.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
                subscription.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
                
                # If subscription is still active but expiring soon, send reminder
                if stripe_sub.status == "active" and not stripe_sub.cancel_at_period_end:
                    days_until_renewal = (subscription.current_period_end - datetime.utcnow()).days
                    
                    if days_until_renewal == 3:
                        user = db.query(User).filter(User.id == subscription.user_id).first()
                        if user:
                            send_email.delay(
                                to_email=user.email,
                                subject="Subscription Renewal Reminder",
                                template="renewal_reminder",
                                context={
                                    "user_name": user.name,
                                    "renewal_date": subscription.current_period_end,
                                    "days_remaining": days_until_renewal
                                }
                            )
                            
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error for subscription {subscription.id}: {e}")
                continue
        
        db.commit()
        db.close()
        
        logger.info(f"Checked {len(expiring_subscriptions)} expiring subscriptions")
        
        return {
            "status": "success",
            "subscriptions_checked": len(expiring_subscriptions),
            "checked_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking subscription renewals: {e}")
        raise


@shared_task(bind=True, max_retries=5)
def retry_failed_payments(self):
    """
    Retry failed payment attempts.
    
    Attempts to process failed payments with exponential backoff.
    """
    try:
        logger.info("Starting failed payment retry process")
        
        db = next(get_db())
        
        # Find recent failed transactions that haven't exceeded retry limit
        retry_cutoff = datetime.utcnow() - timedelta(days=7)  # Don't retry payments older than 7 days
        
        failed_transactions = db.query(Transaction).filter(
            Transaction.status == "failed",
            Transaction.created_at >= retry_cutoff,
            Transaction.extra_metadata['retry_count'].astext.cast(db.Integer) < 3  # Max 3 retries
        ).all()
        
        retry_results = []
        
        for transaction in failed_transactions:
            try:
                # Check if payment method is still valid
                payment_intent = stripe.PaymentIntent.retrieve(transaction.stripe_payment_intent_id)
                
                if payment_intent.status == "requires_payment_method":
                    # Payment method was declined or removed
                    logger.warning(f"Payment method invalid for transaction {transaction.id}")
                    
                    # Notify user to update payment method
                    user = db.query(User).filter(User.id == transaction.user_id).first()
                    if user:
                        send_email.delay(
                            to_email=user.email,
                            subject="Payment Method Required",
                            template="payment_method_required",
                            context={
                                "user_name": user.name,
                                "transaction_id": str(transaction.id)
                            }
                        )
                    
                    continue
                
                # Attempt to confirm the payment again
                if payment_intent.status == "requires_confirmation":
                    confirmed_intent = stripe.PaymentIntent.confirm(payment_intent.id)
                    
                    if confirmed_intent.status == "succeeded":
                        # Payment successful on retry
                        transaction.status = "completed"
                        transaction.completed_at = datetime.utcnow()
                        
                        # Process the successful payment
                        process_payment_webhook.delay(
                            event_type="payment_intent.succeeded",
                            event_data={"object": confirmed_intent}
                        )
                        
                        retry_results.append({
                            "transaction_id": str(transaction.id),
                            "status": "success"
                        })
                        
                        logger.info(f"Payment retry successful for transaction {transaction.id}")
                    else:
                        # Still failed, increment retry count
                        if transaction.extra_metadata is None:
                            transaction.extra_metadata = {}
                        
                        retry_count = transaction.extra_metadata.get("retry_count", 0) + 1
                        transaction.extra_metadata["retry_count"] = retry_count
                        transaction.extra_metadata["last_retry_at"] = datetime.utcnow().isoformat()
                        
                        retry_results.append({
                            "transaction_id": str(transaction.id),
                            "status": "failed",
                            "retry_count": retry_count
                        })
                        
            except stripe.error.StripeError as e:
                logger.error(f"Stripe error retrying payment for transaction {transaction.id}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error retrying payment for transaction {transaction.id}: {e}")
                continue
        
        db.commit()
        db.close()
        
        logger.info(f"Completed payment retry process. Processed {len(failed_transactions)} transactions")
        
        return {
            "status": "success",
            "transactions_processed": len(failed_transactions),
            "retry_results": retry_results,
            "completed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in payment retry process: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry after 5 minutes