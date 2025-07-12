import stripe
from api.config import settings
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.stripe_secret_key


class StripeClient:
    @staticmethod
    async def create_customer(
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a Stripe customer"""
        try:
            customer_data = {
                "email": email,
                "metadata": metadata or {}
            }
            
            if name:
                customer_data["name"] = name
                
            customer = stripe.Customer.create(**customer_data)
            logger.info(f"Created Stripe customer: {customer.id}")
            return customer.id
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating customer: {e}")
            raise
    
    @staticmethod
    async def create_payment_intent(
        amount: Any,  # Amount in dollars (Decimal) or cents (int)
        customer_id: str,
        payment_method_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a payment intent for prompt purchase"""
        try:
            # Convert Decimal to cents if needed
            from decimal import Decimal
            if isinstance(amount, Decimal):
                amount_cents = int(amount * 100)
            else:
                amount_cents = amount
            
            intent_data = {
                "amount": amount_cents,
                "currency": "usd",
                "customer": customer_id,
                "metadata": metadata or {}
            }
            
            if payment_method_id:
                intent_data["payment_method"] = payment_method_id
                intent_data["confirm"] = True
            else:
                intent_data["automatic_payment_methods"] = {"enabled": True}
                
            intent = stripe.PaymentIntent.create(**intent_data)
            
            return {
                "id": intent.id,
                "client_secret": intent.client_secret,
                "status": intent.status,
                "amount": intent.amount,
                "currency": intent.currency,
                "receipt_url": intent.charges.data[0].receipt_url if intent.charges.data else None
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating payment intent: {e}")
            raise
    
    @staticmethod
    async def confirm_payment_intent(payment_intent_id: str) -> Dict[str, Any]:
        """Confirm a payment intent"""
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            return {
                "id": intent.id,
                "status": intent.status,
                "amount": intent.amount,
                "currency": intent.currency,
                "customer": intent.customer,
                "metadata": intent.metadata
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error confirming payment intent: {e}")
            raise
    
    @staticmethod
    async def create_subscription(
        customer_id: str,
        price_id: str,
        trial_days: int = 14,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a subscription for minimum floor pricing"""
        try:
            subscription_data = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "payment_behavior": "default_incomplete",
                "payment_settings": {"save_default_payment_method": "on_subscription"},
                "expand": ["latest_invoice.payment_intent"],
                "metadata": metadata or {}
            }
            
            if trial_days > 0:
                subscription_data["trial_period_days"] = trial_days
                
            subscription = stripe.Subscription.create(**subscription_data)
            
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_end": subscription.current_period_end,
                "client_secret": subscription.latest_invoice.payment_intent.client_secret if subscription.latest_invoice.payment_intent else None
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating subscription: {e}")
            raise
    
    @staticmethod
    async def cancel_subscription(subscription_id: str) -> Dict[str, Any]:
        """Cancel a subscription"""
        try:
            subscription = stripe.Subscription.delete(subscription_id)
            
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "canceled_at": subscription.canceled_at
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error cancelling subscription: {e}")
            raise
    
    @staticmethod
    async def create_refund(
        payment_intent_id: str,
        amount: Optional[int] = None,  # Amount in cents, None for full refund
        reason: str = "requested_by_customer"
    ) -> Dict[str, Any]:
        """Create a refund for a payment"""
        try:
            refund_data = {
                "payment_intent": payment_intent_id,
                "reason": reason
            }
            
            if amount:
                refund_data["amount"] = amount
                
            refund = stripe.Refund.create(**refund_data)
            
            return {
                "refund_id": refund.id,
                "amount": refund.amount,
                "currency": refund.currency,
                "status": refund.status,
                "reason": refund.reason
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating refund: {e}")
            raise
    
    @staticmethod
    async def retrieve_customer(customer_id: str) -> Dict[str, Any]:
        """Retrieve customer information"""
        try:
            customer = stripe.Customer.retrieve(customer_id)
            
            return {
                "id": customer.id,
                "email": customer.email,
                "name": customer.name,
                "created": customer.created,
                "metadata": customer.metadata
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error retrieving customer: {e}")
            raise
    
    @staticmethod
    def verify_webhook_signature(
        payload: bytes,
        signature: str,
        webhook_secret: str
    ) -> Dict[str, Any]:
        """Verify webhook signature and return event"""
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            return event
            
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            raise