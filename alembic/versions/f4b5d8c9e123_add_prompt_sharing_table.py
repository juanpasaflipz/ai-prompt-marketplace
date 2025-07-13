"""Add prompt sharing table

Revision ID: f4b5d8c9e123
Revises: 356ea6ccaab7
Create Date: 2025-07-13 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f4b5d8c9e123'
down_revision = '356ea6ccaab7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create prompt_shares table
    op.create_table('prompt_shares',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prompt_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('share_code', sa.String(length=50), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=True),
        sa.Column('click_count', sa.Integer(), nullable=True),
        sa.Column('conversion_count', sa.Integer(), nullable=True),
        sa.Column('share_metadata', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id'], name=op.f('fk_prompt_shares_prompt_id_prompts')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_prompt_shares_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_prompt_shares'))
    )
    op.create_index(op.f('ix_prompt_shares_share_code'), 'prompt_shares', ['share_code'], unique=True)
    
    # Update prompts table to ensure columns exist
    # Check if columns already exist before adding
    try:
        op.add_column('prompts', sa.Column('subcategory', sa.String(length=100), nullable=True))
    except:
        pass  # Column already exists
    
    # Rename columns if they exist with old names
    try:
        op.alter_column('prompts', 'price_per_use', new_column_name='price')
    except:
        pass
    
    try:
        op.alter_column('prompts', 'total_uses', new_column_name='total_sales')
    except:
        pass
    
    try:
        op.alter_column('prompts', 'average_rating', new_column_name='rating_average')
    except:
        pass
    
    # Add is_active column if it doesn't exist
    try:
        op.add_column('prompts', sa.Column('is_active', sa.Boolean(), nullable=True))
        op.execute("UPDATE prompts SET is_active = true WHERE status = 'active'")
        op.execute("UPDATE prompts SET is_active = false WHERE status != 'active'")
    except:
        pass


def downgrade() -> None:
    # Drop prompt_shares table
    op.drop_index(op.f('ix_prompt_shares_share_code'), table_name='prompt_shares')
    op.drop_table('prompt_shares')
    
    # Revert prompts table changes
    try:
        op.alter_column('prompts', 'price', new_column_name='price_per_use')
    except:
        pass
    
    try:
        op.alter_column('prompts', 'total_sales', new_column_name='total_uses')
    except:
        pass
    
    try:
        op.alter_column('prompts', 'rating_average', new_column_name='average_rating')
    except:
        pass
    
    try:
        op.drop_column('prompts', 'subcategory')
    except:
        pass
    
    try:
        op.drop_column('prompts', 'is_active')
    except:
        pass