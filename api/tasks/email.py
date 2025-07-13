"""
Email background tasks.

Handles asynchronous email sending to avoid blocking API requests.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from typing import Dict, Any, List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os

from api.config import settings

logger = get_task_logger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.smtp_from = settings.smtp_from
    
    def send(self, to_email: str, subject: str, body: str, 
             html_body: Optional[str] = None, attachments: Optional[List[Dict[str, Any]]] = None):
        """Send an email"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_from
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add text part
            text_part = MIMEText(body, 'plain')
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, 'html')
                msg.attach(html_part)
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {attachment["filename"]}'
                    )
                    msg.attach(part)
            
            # Send email
            if self.smtp_user and self.smtp_password:
                # Use SMTP with authentication
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                # Use local SMTP without authentication (for development)
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            raise


email_service = EmailService()


@shared_task(bind=True, max_retries=3)
def send_email(self, to_email: str, subject: str, body: str, 
               html_body: Optional[str] = None, attachments: Optional[List[Dict[str, Any]]] = None):
    """
    Send an email asynchronously.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML body
        attachments: Optional list of attachments
    """
    try:
        email_service.send(to_email, subject, body, html_body, attachments)
        return {
            "status": "success",
            "to": to_email,
            "subject": subject
        }
    except Exception as e:
        logger.error(f"Email task failed: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry after 5 minutes


@shared_task(bind=True, max_retries=3)
def send_welcome_email(self, user_email: str, user_name: str, company_name: str):
    """
    Send welcome email to new users.
    """
    subject = f"Welcome to {settings.app_name}!"
    
    body = f"""
Dear {user_name},

Welcome to {settings.app_name} - the premier B2B marketplace for AI prompts!

Your account for {company_name} has been created successfully. You can now:

- Browse our extensive catalog of optimized prompts
- Purchase prompts to accelerate your AI development
- List your own prompts to monetize your expertise
- Access detailed analytics and performance metrics

To get started, please visit our marketplace and explore the available prompts.

If you have any questions, please don't hesitate to contact our support team.

Best regards,
The {settings.app_name} Team
    """.strip()
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #2563eb; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9fafb; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to {settings.app_name}!</h1>
        </div>
        <div class="content">
            <p>Dear {user_name},</p>
            
            <p>Welcome to <strong>{settings.app_name}</strong> - the premier B2B marketplace for AI prompts!</p>
            
            <p>Your account for <strong>{company_name}</strong> has been created successfully.</p>
            
            <h3>What you can do:</h3>
            <ul>
                <li>Browse our extensive catalog of optimized prompts</li>
                <li>Purchase prompts to accelerate your AI development</li>
                <li>List your own prompts to monetize your expertise</li>
                <li>Access detailed analytics and performance metrics</li>
            </ul>
            
            <center>
                <a href="http://localhost:3000/marketplace" class="button">Visit Marketplace</a>
            </center>
            
            <p>If you have any questions, please don't hesitate to contact our support team.</p>
            
            <p>Best regards,<br>The {settings.app_name} Team</p>
        </div>
        <div class="footer">
            <p>&copy; 2024 {settings.app_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
    """.strip()
    
    return send_email.apply_async(
        args=[user_email, subject, body, html_body]
    )


@shared_task(bind=True, max_retries=3)
def send_purchase_confirmation(self, user_email: str, user_name: str, 
                             prompt_title: str, amount: float, transaction_id: str):
    """
    Send purchase confirmation email.
    """
    subject = f"Purchase Confirmation - {prompt_title}"
    
    body = f"""
Dear {user_name},

Thank you for your purchase!

Order Details:
- Prompt: {prompt_title}
- Amount: ${amount:.2f}
- Transaction ID: {transaction_id}

You can now access your purchased prompt in your dashboard.

If you have any questions about your purchase, please contact our support team.

Best regards,
The {settings.app_name} Team
    """.strip()
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #10b981; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9fafb; }}
        .order-details {{ background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #10b981; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Purchase Confirmation</h1>
        </div>
        <div class="content">
            <p>Dear {user_name},</p>
            
            <p>Thank you for your purchase!</p>
            
            <div class="order-details">
                <h3>Order Details</h3>
                <p><strong>Prompt:</strong> {prompt_title}</p>
                <p><strong>Amount:</strong> ${amount:.2f}</p>
                <p><strong>Transaction ID:</strong> {transaction_id}</p>
                <p><strong>Date:</strong> {'{datetime.utcnow().strftime("%B %d, %Y")}'}</p>
            </div>
            
            <p>You can now access your purchased prompt in your dashboard.</p>
            
            <center>
                <a href="http://localhost:3000/dashboard/purchases" class="button">View Your Purchases</a>
            </center>
            
            <p>If you have any questions about your purchase, please contact our support team.</p>
            
            <p>Best regards,<br>The {settings.app_name} Team</p>
        </div>
        <div class="footer">
            <p>&copy; 2024 {settings.app_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
    """.strip()
    
    return send_email.apply_async(
        args=[user_email, subject, body, html_body]
    )


@shared_task(bind=True, max_retries=3)
def send_password_reset(self, user_email: str, user_name: str, reset_token: str):
    """
    Send password reset email.
    """
    subject = f"Password Reset Request - {settings.app_name}"
    reset_link = f"http://localhost:3000/reset-password?token={reset_token}"
    
    body = f"""
Dear {user_name},

We received a request to reset your password for your {settings.app_name} account.

To reset your password, please click the link below:
{reset_link}

This link will expire in 1 hour for security reasons.

If you did not request a password reset, please ignore this email and your password will remain unchanged.

Best regards,
The {settings.app_name} Team
    """.strip()
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #ef4444; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9fafb; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #ef4444; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }}
        .warning {{ background-color: #fef3c7; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Password Reset Request</h1>
        </div>
        <div class="content">
            <p>Dear {user_name},</p>
            
            <p>We received a request to reset your password for your <strong>{settings.app_name}</strong> account.</p>
            
            <p>To reset your password, please click the button below:</p>
            
            <center>
                <a href="{reset_link}" class="button">Reset Password</a>
            </center>
            
            <div class="warning">
                <p><strong>Important:</strong> This link will expire in 1 hour for security reasons.</p>
            </div>
            
            <p>If you did not request a password reset, please ignore this email and your password will remain unchanged.</p>
            
            <p>Best regards,<br>The {settings.app_name} Team</p>
        </div>
        <div class="footer">
            <p>&copy; 2024 {settings.app_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
    """.strip()
    
    return send_email.apply_async(
        args=[user_email, subject, body, html_body]
    )