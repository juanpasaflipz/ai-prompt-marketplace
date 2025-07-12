#!/usr/bin/env python3
"""
AI Prompt Marketplace CLI Management Tool
"""

import click
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from api.config import settings
from api.database import Base
from api.models.user import User
from api.models.prompt import Prompt as PromptModel
from api.models.transaction import Transaction
from api.models.analytics import AnalyticsEvent
from api.services.auth_service import AuthService
from integrations.stripe.client import StripeClient

console = Console()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@click.group()
def cli():
    """AI Prompt Marketplace Management CLI"""
    pass


@cli.group()
def db():
    """Database management commands"""
    pass


@db.command()
def init():
    """Initialize database tables"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating database tables...", total=None)
        Base.metadata.create_all(bind=engine)
        progress.update(task, completed=True)
    
    console.print("[green]✓[/green] Database tables created successfully!")


@db.command()
def reset():
    """Reset database (WARNING: Deletes all data)"""
    if not Confirm.ask("[red]This will delete ALL data. Are you sure?[/red]"):
        console.print("Operation cancelled.")
        return
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Dropping all tables...", total=None)
        Base.metadata.drop_all(bind=engine)
        progress.update(task, description="Creating new tables...")
        Base.metadata.create_all(bind=engine)
        progress.update(task, completed=True)
    
    console.print("[green]✓[/green] Database reset successfully!")


@db.command()
def seed():
    """Seed database with sample data"""
    session = SessionLocal()
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Create sample users
            task = progress.add_task("Creating sample users...", total=None)
            
            users = [
                {
                    "email": "buyer@example.com",
                    "password": "password123",
                    "role": "buyer",
                    "company_name": "Acme Corp",
                    "full_name": "John Buyer"
                },
                {
                    "email": "seller@example.com",
                    "password": "password123",
                    "role": "seller",
                    "company_name": "Prompt Pros",
                    "full_name": "Jane Seller"
                },
                {
                    "email": "admin@example.com",
                    "password": "admin123",
                    "role": "admin",
                    "company_name": "Marketplace Inc",
                    "full_name": "Admin User"
                }
            ]
            
            created_users = []
            for user_data in users:
                password = user_data.pop("password")
                user = User(**user_data)
                user.password_hash = AuthService.hash_password(password)
                user.stripe_customer_id = f"cus_test_{user.email.split('@')[0]}"
                session.add(user)
                created_users.append(user)
            
            session.commit()
            progress.update(task, completed=True)
            
            # Create sample prompts
            task = progress.add_task("Creating sample prompts...", total=None)
            
            seller = created_users[1]  # Jane Seller
            
            prompts = [
                {
                    "seller_id": seller.id,
                    "title": "Sales Email Generator",
                    "description": "Generate personalized sales emails that convert",
                    "category": "sales",
                    "subcategory": "email",
                    "tags": ["email", "sales", "outreach", "b2b"],
                    "template": "Write a {tone} sales email for {product} targeting {audience}. Include {cta}.",
                    "variables": [
                        {"name": "tone", "description": "Email tone", "example": "professional"},
                        {"name": "product", "description": "Product/service", "example": "SaaS platform"},
                        {"name": "audience", "description": "Target audience", "example": "CTOs"},
                        {"name": "cta", "description": "Call to action", "example": "schedule a demo"}
                    ],
                    "model_type": "gpt-4o",
                    "price": Decimal("19.99"),
                    "usage_notes": "Best for B2B outreach. Customize variables for your specific use case.",
                    "performance_metrics": {"open_rate": "45%", "response_rate": "12%"}
                },
                {
                    "seller_id": seller.id,
                    "title": "Product Description Writer",
                    "description": "Create compelling product descriptions for e-commerce",
                    "category": "marketing",
                    "subcategory": "copywriting",
                    "tags": ["ecommerce", "product", "description", "seo"],
                    "template": "Write a {length} product description for {product_name}. Features: {features}. Target: {target_audience}.",
                    "variables": [
                        {"name": "length", "description": "Description length", "example": "150 words"},
                        {"name": "product_name", "description": "Product name", "example": "Wireless Headphones"},
                        {"name": "features", "description": "Key features", "example": "noise canceling, 30hr battery"},
                        {"name": "target_audience", "description": "Target customers", "example": "remote workers"}
                    ],
                    "model_type": "gpt-4o",
                    "price": Decimal("14.99"),
                    "usage_notes": "Optimized for SEO and conversion. Works best with detailed feature lists."
                },
                {
                    "seller_id": seller.id,
                    "title": "Code Documentation Generator",
                    "description": "Generate comprehensive documentation for code",
                    "category": "engineering",
                    "subcategory": "documentation",
                    "tags": ["code", "documentation", "technical", "developer"],
                    "template": "Generate {doc_type} documentation for the following {language} code:\n{code}\n\nInclude: {requirements}",
                    "variables": [
                        {"name": "doc_type", "description": "Documentation type", "example": "API"},
                        {"name": "language", "description": "Programming language", "example": "Python"},
                        {"name": "code", "description": "Code to document", "example": "def calculate(x, y): return x + y"},
                        {"name": "requirements", "description": "Specific requirements", "example": "examples, parameters, returns"}
                    ],
                    "model_type": "gpt-4o",
                    "price": Decimal("24.99"),
                    "usage_notes": "Supports all major programming languages. Best results with clean, well-structured code."
                }
            ]
            
            for prompt_data in prompts:
                prompt = PromptModel(**prompt_data)
                session.add(prompt)
            
            session.commit()
            progress.update(task, completed=True)
        
        console.print("[green]✓[/green] Database seeded successfully!")
        console.print(f"  - Created {len(created_users)} users")
        console.print(f"  - Created {len(prompts)} prompts")
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]Error seeding database:[/red] {str(e)}")
        raise
    finally:
        session.close()


@cli.group()
def user():
    """User management commands"""
    pass


@user.command()
def list():
    """List all users"""
    session = SessionLocal()
    
    try:
        users = session.query(User).all()
        
        if not users:
            console.print("No users found.")
            return
        
        table = Table(title="Users")
        table.add_column("ID", style="cyan")
        table.add_column("Email", style="magenta")
        table.add_column("Name", style="green")
        table.add_column("Company")
        table.add_column("Role", style="yellow")
        table.add_column("Status")
        table.add_column("Created")
        
        for user in users:
            table.add_row(
                str(user.id),
                user.email,
                user.full_name or "-",
                user.company_name,
                user.role,
                "[green]Active[/green]" if user.is_active == "true" else "[red]Inactive[/red]",
                user.created_at.strftime("%Y-%m-%d")
            )
        
        console.print(table)
        
    finally:
        session.close()


@user.command()
def create():
    """Create a new user"""
    email = Prompt.ask("Email")
    password = Prompt.ask("Password", password=True)
    role = Prompt.ask("Role", choices=["buyer", "seller", "admin"], default="buyer")
    company_name = Prompt.ask("Company name")
    full_name = Prompt.ask("Full name (optional)", default="")
    
    session = SessionLocal()
    
    try:
        # Check if user exists
        if session.query(User).filter(User.email == email).first():
            console.print(f"[red]User with email {email} already exists![/red]")
            return
        
        # Create user
        user = User(
            email=email,
            role=role,
            company_name=company_name,
            full_name=full_name if full_name else None
        )
        user.password_hash = AuthService.hash_password(password)
        
        # Create Stripe customer
        try:
            loop = asyncio.get_event_loop()
            stripe_customer_id = loop.run_until_complete(
                StripeClient.create_customer(email, full_name)
            )
            user.stripe_customer_id = stripe_customer_id
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create Stripe customer: {e}[/yellow]")
        
        session.add(user)
        session.commit()
        
        console.print(f"[green]✓[/green] User created successfully! ID: {user.id}")
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]Error creating user:[/red] {str(e)}")
    finally:
        session.close()


@cli.group()
def prompt():
    """Prompt management commands"""
    pass


@prompt.command()
def list():
    """List all prompts"""
    session = SessionLocal()
    
    try:
        prompts = session.query(PromptModel).join(User).all()
        
        if not prompts:
            console.print("No prompts found.")
            return
        
        table = Table(title="Prompts")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="magenta")
        table.add_column("Category")
        table.add_column("Price", style="green")
        table.add_column("Sales")
        table.add_column("Rating")
        table.add_column("Seller")
        table.add_column("Status")
        
        for prompt in prompts:
            rating = f"{prompt.rating_average:.1f}" if prompt.rating_average else "-"
            table.add_row(
                str(prompt.id),
                prompt.title[:30] + "..." if len(prompt.title) > 30 else prompt.title,
                prompt.category,
                f"${prompt.price}",
                str(prompt.total_sales),
                rating,
                prompt.seller.email,
                "[green]Active[/green]" if prompt.is_active else "[red]Inactive[/red]"
            )
        
        console.print(table)
        
    finally:
        session.close()


@prompt.command()
def stats():
    """Show prompt statistics"""
    session = SessionLocal()
    
    try:
        total_prompts = session.query(PromptModel).count()
        active_prompts = session.query(PromptModel).filter(PromptModel.is_active == True).count()
        total_sales = session.query(Transaction).filter(Transaction.status == "completed").count()
        
        # Revenue calculation
        revenue = session.query(
            func.sum(Transaction.amount)
        ).filter(
            Transaction.status == "completed"
        ).scalar() or 0
        
        # Category breakdown
        from sqlalchemy import func
        categories = session.query(
            PromptModel.category,
            func.count(PromptModel.id)
        ).group_by(PromptModel.category).all()
        
        console.print("[bold]Prompt Statistics[/bold]")
        console.print(f"Total Prompts: {total_prompts}")
        console.print(f"Active Prompts: {active_prompts}")
        console.print(f"Total Sales: {total_sales}")
        console.print(f"Total Revenue: ${revenue}")
        
        if categories:
            console.print("\n[bold]Categories:[/bold]")
            for cat, count in categories:
                console.print(f"  {cat}: {count} prompts")
        
    finally:
        session.close()


@cli.group()
def analytics():
    """Analytics commands"""
    pass


@analytics.command()
def summary():
    """Show analytics summary"""
    session = SessionLocal()
    
    try:
        # Get events from last 7 days
        since = datetime.utcnow() - timedelta(days=7)
        
        events = session.query(
            AnalyticsEvent.event_type,
            func.count(AnalyticsEvent.id)
        ).filter(
            AnalyticsEvent.created_at >= since
        ).group_by(
            AnalyticsEvent.event_type
        ).all()
        
        console.print(f"[bold]Analytics Summary (Last 7 Days)[/bold]")
        
        if not events:
            console.print("No events recorded.")
            return
        
        table = Table()
        table.add_column("Event Type", style="cyan")
        table.add_column("Count", style="green")
        
        for event_type, count in events:
            table.add_row(event_type, str(count))
        
        console.print(table)
        
    finally:
        session.close()


@analytics.command()
def realtime():
    """Show real-time analytics (last hour)"""
    session = SessionLocal()
    
    try:
        since = datetime.utcnow() - timedelta(hours=1)
        
        events = session.query(AnalyticsEvent).filter(
            AnalyticsEvent.created_at >= since
        ).order_by(
            AnalyticsEvent.created_at.desc()
        ).limit(50).all()
        
        console.print(f"[bold]Real-time Analytics (Last Hour)[/bold]")
        
        if not events:
            console.print("No recent events.")
            return
        
        for event in events:
            time_str = event.created_at.strftime("%H:%M:%S")
            user_str = f"User {event.user_id}" if event.user_id else "Anonymous"
            prompt_str = f"Prompt {event.prompt_id}" if event.prompt_id else ""
            
            console.print(f"[dim]{time_str}[/dim] {user_str} - [cyan]{event.event_type}[/cyan] {prompt_str}")
        
    finally:
        session.close()


@cli.command()
def health():
    """Check system health"""
    console.print("[bold]System Health Check[/bold]\n")
    
    # Database
    try:
        session = SessionLocal()
        session.execute("SELECT 1")
        session.close()
        console.print("✓ Database: [green]Connected[/green]")
    except Exception as e:
        console.print("✗ Database: [red]Failed[/red]")
        console.print(f"  Error: {str(e)}")
    
    # Redis
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        console.print("✓ Redis: [green]Connected[/green]")
    except Exception as e:
        console.print("✗ Redis: [red]Failed[/red]")
        console.print(f"  Error: {str(e)}")
    
    # Stripe
    try:
        import stripe
        stripe.api_key = settings.stripe_secret_key
        # Simple API call to verify connection
        stripe.Product.list(limit=1)
        console.print("✓ Stripe: [green]Connected[/green]")
    except Exception as e:
        console.print("✗ Stripe: [yellow]Not configured[/yellow]")
    
    # OpenAI
    try:
        if settings.openai_api_key:
            console.print("✓ OpenAI: [green]Configured[/green]")
        else:
            console.print("✗ OpenAI: [yellow]Not configured[/yellow]")
    except:
        console.print("✗ OpenAI: [yellow]Not configured[/yellow]")


if __name__ == "__main__":
    cli()