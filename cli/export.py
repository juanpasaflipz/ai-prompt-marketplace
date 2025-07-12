#!/usr/bin/env python3
"""
Export data from the marketplace
"""

import click
import sys
import os
from pathlib import Path
import csv
import json
from datetime import datetime
from rich.console import Console
from rich.progress import track
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from api.config import settings
from api.models.user import User
from api.models.prompt import Prompt
from api.models.transaction import Transaction
from api.models.analytics import AnalyticsEvent

console = Console()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@click.group()
def cli():
    """Export marketplace data"""
    pass


@cli.command()
@click.option('--format', type=click.Choice(['csv', 'json']), default='csv', help='Export format')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output file path')
def users(format, output):
    """Export user data"""
    session = SessionLocal()
    
    try:
        users = session.query(User).all()
        console.print(f"Exporting {len(users)} users...")
        
        if format == 'csv':
            with open(output, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'email', 'full_name', 'company_name', 'role', 'is_active', 'created_at'])
                
                for user in track(users, description="Writing users..."):
                    writer.writerow([
                        user.id,
                        user.email,
                        user.full_name or '',
                        user.company_name,
                        user.role,
                        user.is_active,
                        user.created_at.isoformat()
                    ])
        else:  # json
            data = []
            for user in track(users, description="Processing users..."):
                data.append({
                    'id': user.id,
                    'email': user.email,
                    'full_name': user.full_name,
                    'company_name': user.company_name,
                    'role': user.role,
                    'is_active': user.is_active,
                    'created_at': user.created_at.isoformat()
                })
            
            with open(output, 'w') as f:
                json.dump(data, f, indent=2)
        
        console.print(f"[green]✓[/green] Exported {len(users)} users to {output}")
        
    finally:
        session.close()


@cli.command()
@click.option('--format', type=click.Choice(['csv', 'json']), default='csv', help='Export format')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output file path')
@click.option('--active-only', is_flag=True, help='Export only active prompts')
def prompts(format, output, active_only):
    """Export prompt data"""
    session = SessionLocal()
    
    try:
        query = session.query(Prompt).join(User)
        
        if active_only:
            query = query.filter(Prompt.is_active == True)
        
        prompts = query.all()
        console.print(f"Exporting {len(prompts)} prompts...")
        
        if format == 'csv':
            with open(output, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'id', 'title', 'description', 'category', 'subcategory',
                    'tags', 'price', 'total_sales', 'rating_average', 
                    'seller_email', 'created_at'
                ])
                
                for prompt in track(prompts, description="Writing prompts..."):
                    writer.writerow([
                        prompt.id,
                        prompt.title,
                        prompt.description,
                        prompt.category,
                        prompt.subcategory or '',
                        ','.join(prompt.tags),
                        float(prompt.price),
                        prompt.total_sales,
                        prompt.rating_average or '',
                        prompt.seller.email,
                        prompt.created_at.isoformat()
                    ])
        else:  # json
            data = []
            for prompt in track(prompts, description="Processing prompts..."):
                data.append({
                    'id': prompt.id,
                    'title': prompt.title,
                    'description': prompt.description,
                    'category': prompt.category,
                    'subcategory': prompt.subcategory,
                    'tags': prompt.tags,
                    'template': prompt.template,
                    'variables': prompt.variables,
                    'price': float(prompt.price),
                    'total_sales': prompt.total_sales,
                    'rating_average': prompt.rating_average,
                    'seller': {
                        'id': prompt.seller.id,
                        'email': prompt.seller.email,
                        'company': prompt.seller.company_name
                    },
                    'created_at': prompt.created_at.isoformat()
                })
            
            with open(output, 'w') as f:
                json.dump(data, f, indent=2)
        
        console.print(f"[green]✓[/green] Exported {len(prompts)} prompts to {output}")
        
    finally:
        session.close()


@cli.command()
@click.option('--format', type=click.Choice(['csv', 'json']), default='csv', help='Export format')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output file path')
@click.option('--status', type=click.Choice(['all', 'completed', 'pending', 'failed']), default='completed')
@click.option('--days', type=int, default=30, help='Export last N days of transactions')
def transactions(format, output, status, days):
    """Export transaction data"""
    session = SessionLocal()
    
    try:
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(days=days)
        
        query = session.query(Transaction).join(User, Transaction.buyer_id == User.id)
        
        if status != 'all':
            query = query.filter(Transaction.status == status)
        
        query = query.filter(Transaction.created_at >= since)
        transactions = query.all()
        
        console.print(f"Exporting {len(transactions)} transactions...")
        
        if format == 'csv':
            with open(output, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'id', 'buyer_email', 'seller_id', 'prompt_id', 
                    'amount', 'status', 'rating', 'created_at'
                ])
                
                for txn in track(transactions, description="Writing transactions..."):
                    writer.writerow([
                        txn.id,
                        txn.buyer.email,
                        txn.seller_id,
                        txn.prompt_id,
                        float(txn.amount),
                        txn.status,
                        txn.rating or '',
                        txn.created_at.isoformat()
                    ])
        else:  # json
            data = []
            for txn in track(transactions, description="Processing transactions..."):
                data.append({
                    'id': txn.id,
                    'buyer': {
                        'id': txn.buyer_id,
                        'email': txn.buyer.email
                    },
                    'seller_id': txn.seller_id,
                    'prompt_id': txn.prompt_id,
                    'amount': float(txn.amount),
                    'status': txn.status,
                    'rating': txn.rating,
                    'review': txn.review,
                    'stripe_payment_intent_id': txn.stripe_payment_intent_id,
                    'created_at': txn.created_at.isoformat()
                })
            
            with open(output, 'w') as f:
                json.dump(data, f, indent=2)
        
        console.print(f"[green]✓[/green] Exported {len(transactions)} transactions to {output}")
        
    finally:
        session.close()


@cli.command()
@click.option('--output', '-o', type=click.Path(), required=True, help='Output file path')
@click.option('--days', type=int, default=7, help='Export last N days of analytics')
def analytics(output, days):
    """Export analytics events"""
    session = SessionLocal()
    
    try:
        from datetime import timedelta
        from sqlalchemy import func
        
        since = datetime.utcnow() - timedelta(days=days)
        
        # Get event summary
        summary = session.query(
            AnalyticsEvent.event_type,
            func.count(AnalyticsEvent.id).label('count'),
            func.count(func.distinct(AnalyticsEvent.user_id)).label('unique_users')
        ).filter(
            AnalyticsEvent.created_at >= since
        ).group_by(
            AnalyticsEvent.event_type
        ).all()
        
        # Get daily breakdown
        daily = session.query(
            func.date(AnalyticsEvent.created_at).label('date'),
            AnalyticsEvent.event_type,
            func.count(AnalyticsEvent.id).label('count')
        ).filter(
            AnalyticsEvent.created_at >= since
        ).group_by(
            func.date(AnalyticsEvent.created_at),
            AnalyticsEvent.event_type
        ).all()
        
        data = {
            'period': {
                'start': since.isoformat(),
                'end': datetime.utcnow().isoformat(),
                'days': days
            },
            'summary': [
                {
                    'event_type': s.event_type,
                    'total_events': s.count,
                    'unique_users': s.unique_users
                } for s in summary
            ],
            'daily_breakdown': {}
        }
        
        # Organize daily data
        for record in daily:
            date_str = record.date.isoformat()
            if date_str not in data['daily_breakdown']:
                data['daily_breakdown'][date_str] = {}
            data['daily_breakdown'][date_str][record.event_type] = record.count
        
        with open(output, 'w') as f:
            json.dump(data, f, indent=2)
        
        console.print(f"[green]✓[/green] Exported analytics for last {days} days to {output}")
        
    finally:
        session.close()


@cli.command()
@click.option('--output', '-o', type=click.Path(), required=True, help='Output directory path')
def full_backup(output):
    """Create a full backup of all data"""
    output_dir = Path(output)
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    console.print(f"Creating full backup in {output_dir}...")
    
    # Export all data types
    commands = [
        ('users', f"{output_dir}/users_{timestamp}.json"),
        ('prompts', f"{output_dir}/prompts_{timestamp}.json"),
        ('transactions', f"{output_dir}/transactions_{timestamp}.json"),
        ('analytics', f"{output_dir}/analytics_{timestamp}.json")
    ]
    
    for cmd, filepath in commands:
        if cmd == 'analytics':
            ctx = click.Context(analytics)
            ctx.invoke(analytics, output=filepath, days=365)
        else:
            ctx = click.Context(locals()[cmd])
            ctx.invoke(locals()[cmd], format='json', output=filepath)
    
    # Create backup metadata
    metadata = {
        'backup_date': datetime.now().isoformat(),
        'version': settings.app_version,
        'files': [f"{cmd}_{timestamp}.json" for cmd, _ in commands]
    }
    
    with open(output_dir / f"backup_metadata_{timestamp}.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    console.print(f"[green]✓[/green] Full backup completed in {output_dir}")


if __name__ == "__main__":
    cli()