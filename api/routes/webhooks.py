from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import logging

from api.database import get_db
from api.config import settings
from api.models.transaction import Transaction
from api.models.prompt import Prompt
from integrations.stripe.client import StripeClient
from api.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

stripe_client = StripeClient()
analytics_service = AnalyticsService()


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Stripe webhook events"""
    try:
        # Get the webhook payload and signature
        payload = await request.body()
        sig_header = request.headers.get("Stripe-Signature")
        
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing Stripe signature")
        
        # Verify webhook signature and get event
        try:
            event = stripe_client.verify_webhook_signature(
                payload,
                sig_header,
                settings.stripe_webhook_secret
            )
        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle different event types
        event_type = event["type"]
        event_data = event["data"]["object"]
        
        logger.info(f"Processing Stripe webhook: {event_type}")
        
        if event_type == "payment_intent.succeeded":
            # Payment successful
            payment_intent_id = event_data["id"]
            
            # Find the transaction
            transaction = db.query(Transaction).filter(
                Transaction.stripe_payment_intent_id == payment_intent_id
            ).first()
            
            if transaction:
                # Update transaction status
                transaction.status = "completed"
                
                # Update prompt statistics
                prompt = db.query(Prompt).filter(
                    Prompt.id == transaction.prompt_id
                ).first()
                
                if prompt:
                    prompt.total_sales += 1
                
                db.commit()
                
                # Track analytics
                await analytics_service.track_event(
                    user_id=transaction.buyer_id,
                    event_type="payment_succeeded",
                    prompt_id=transaction.prompt_id,
                    metadata={
                        "amount": float(transaction.amount),
                        "payment_intent_id": payment_intent_id
                    }
                )
        
        elif event_type == "payment_intent.payment_failed":
            # Payment failed
            payment_intent_id = event_data["id"]
            
            # Find the transaction
            transaction = db.query(Transaction).filter(
                Transaction.stripe_payment_intent_id == payment_intent_id
            ).first()
            
            if transaction:
                transaction.status = "failed"
                transaction.failure_reason = event_data.get("last_payment_error", {}).get("message")
                db.commit()
                
                # Track analytics
                await analytics_service.track_event(
                    user_id=transaction.buyer_id,
                    event_type="payment_failed",
                    prompt_id=transaction.prompt_id,
                    metadata={
                        "payment_intent_id": payment_intent_id,
                        "error": transaction.failure_reason
                    }
                )
        
        elif event_type == "customer.subscription.created":
            # Subscription created
            subscription_id = event_data["id"]
            customer_id = event_data["customer"]
            
            # Log subscription creation
            logger.info(f"Subscription created: {subscription_id} for customer: {customer_id}")
            
            # Track analytics
            await analytics_service.track_event(
                user_id=0,  # We'd need to look up user by stripe_customer_id
                event_type="subscription_created",
                metadata={
                    "subscription_id": subscription_id,
                    "customer_id": customer_id,
                    "status": event_data["status"]
                }
            )
        
        elif event_type == "customer.subscription.deleted":
            # Subscription cancelled
            subscription_id = event_data["id"]
            customer_id = event_data["customer"]
            
            # Log subscription cancellation
            logger.info(f"Subscription cancelled: {subscription_id} for customer: {customer_id}")
            
            # Track analytics
            await analytics_service.track_event(
                user_id=0,  # We'd need to look up user by stripe_customer_id
                event_type="subscription_cancelled",
                metadata={
                    "subscription_id": subscription_id,
                    "customer_id": customer_id
                }
            )
        
        elif event_type == "invoice.payment_succeeded":
            # Invoice paid (for subscriptions)
            invoice_id = event_data["id"]
            customer_id = event_data["customer"]
            amount = event_data["amount_paid"]
            
            logger.info(f"Invoice paid: {invoice_id} for ${amount/100}")
            
            # Track analytics
            await analytics_service.track_event(
                user_id=0,  # We'd need to look up user by stripe_customer_id
                event_type="invoice_paid",
                metadata={
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "amount": amount / 100
                }
            )
        
        else:
            # Log unhandled event types
            logger.info(f"Unhandled Stripe event type: {event_type}")
        
        return {"received": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")