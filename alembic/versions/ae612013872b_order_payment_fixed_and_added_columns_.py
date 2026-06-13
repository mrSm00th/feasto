"""(order, payment) fixed and added columns in the order and payment models to support the checkout flow  

Revision ID: ae612013872b
Revises: 8580755ad399
Create Date: 2026-06-13 16:47:18.132686

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ae612013872b'
down_revision: Union[str, Sequence[str], None] = '8580755ad399'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # Create enum types first — must exist before any column references them
    sa.Enum(
        'PAYMENT_FAILED',
        'RESTAURANT_REJECTED',
        'RESTAURANT_TIMEOUT',
        'CUSTOMER_CANCELLED',
        'ITEM_UNAVAILABLE',
        'SYSTEM_ERROR',
        name='cancellationreason'
    ).create(op.get_bind(), checkfirst=True)

    sa.Enum(
        'STRIPE',
        'RAZORPAY',
        'COD',
        name='paymentprovider'
    ).create(op.get_bind(), checkfirst=True)

    # order_items
    op.add_column('order_items', sa.Column('item_description', sa.Text(), nullable=True))

    # orders — new columns
    op.add_column('orders', sa.Column('delivery_address', sa.Text(), nullable=False))
    op.add_column('orders', sa.Column('delivery_latitude', sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column('orders', sa.Column('delivery_longitude', sa.Numeric(precision=10, scale=7), nullable=True))
    op.add_column('orders', sa.Column('customer_name', sa.String(length=120), nullable=False))
    op.add_column('orders', sa.Column('customer_phone', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('customer_email', sa.String(length=255), nullable=True))
    op.add_column('orders', sa.Column('cancellation_reason', sa.Enum('PAYMENT_FAILED', 'RESTAURANT_REJECTED', 'RESTAURANT_TIMEOUT', 'CUSTOMER_CANCELLED', 'ITEM_UNAVAILABLE', 'SYSTEM_ERROR', name='cancellationreason'), nullable=True))
    op.add_column('orders', sa.Column('cancellation_note', sa.String(length=500), nullable=True))
    op.add_column('orders', sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('preparing_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('rider_assigned_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('picked_up_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('estimated_ready_at', sa.DateTime(timezone=True), nullable=True))

    # orders — alter + index changes
    op.alter_column('orders', 'placed_at',
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
    )
    op.drop_index(op.f('ix_orders_id'), table_name='orders')
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)

    # orders — drop old columns
    op.drop_column('orders', 'phone_number')
    op.drop_column('orders', 'email')
    op.drop_column('orders', 'longitude')
    op.drop_column('orders', 'latitude')
    op.drop_column('orders', 'payment_status')

    # payments — new columns
    op.add_column('payments', sa.Column('provider', sa.Enum('STRIPE', 'RAZORPAY', 'COD', name='paymentprovider'), nullable=False))
    op.add_column('payments', sa.Column('provider_order_id', sa.String(length=255), nullable=True))
    op.add_column('payments', sa.Column('provider_payment_id', sa.String(length=255), nullable=True))
    op.add_column('payments', sa.Column('provider_signature', sa.String(length=512), nullable=True))
    op.add_column('payments', sa.Column('failure_reason', sa.String(length=500), nullable=True))
    op.add_column('payments', sa.Column('initiated_at', sa.DateTime(timezone=True), nullable=False))
    op.add_column('payments', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('payments', sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True))

    # payments — index + constraint changes
    op.drop_constraint(op.f('payments_order_id_key'), 'payments', type_='unique')
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=True)
    op.create_unique_constraint(None, 'payments', ['provider_order_id'])

    # payments — drop old columns
    op.drop_column('payments', 'paid_at')
    op.drop_column('payments', 'transaction_id')
    op.drop_column('payments', 'currency')
    op.drop_column('payments', 'payment_provider')
    op.drop_column('payments', 'created_at')


def downgrade() -> None:

    # payments — restore old columns
    op.add_column('payments', sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False))
    op.add_column('payments', sa.Column('payment_provider', postgresql.ENUM('STRIPE', 'RAZORPAY', 'COD', name='paymentprovider'), autoincrement=False, nullable=False))
    op.add_column('payments', sa.Column('currency', sa.VARCHAR(length=10), autoincrement=False, nullable=False))
    op.add_column('payments', sa.Column('transaction_id', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('payments', sa.Column('paid_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))

    # payments — restore constraints
    op.drop_constraint(None, 'payments', type_='unique')
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.create_unique_constraint(op.f('payments_order_id_key'), 'payments', ['order_id'], postgresql_nulls_not_distinct=False)

    # payments — drop new columns
    op.drop_column('payments', 'refunded_at')
    op.drop_column('payments', 'completed_at')
    op.drop_column('payments', 'initiated_at')
    op.drop_column('payments', 'failure_reason')
    op.drop_column('payments', 'provider_signature')
    op.drop_column('payments', 'provider_payment_id')
    op.drop_column('payments', 'provider_order_id')
    op.drop_column('payments', 'provider')

    # orders — restore old columns
    op.add_column('orders', sa.Column('latitude', sa.NUMERIC(precision=10, scale=7), autoincrement=False, nullable=True))
    op.add_column('orders', sa.Column('payment_status', postgresql.ENUM('PENDING', 'PAID', 'FAILED', 'REFUNDED', name='paymentstatus'), autoincrement=False, nullable=False))
    op.add_column('orders', sa.Column('longitude', sa.NUMERIC(precision=10, scale=7), autoincrement=False, nullable=True))
    op.add_column('orders', sa.Column('email', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('orders', sa.Column('phone_number', sa.VARCHAR(length=20), autoincrement=False, nullable=True))

    # orders — restore index
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.create_index(op.f('ix_orders_id'), 'orders', ['id'], unique=False)

    # orders — restore placed_at to non-nullable
    op.alter_column('orders', 'placed_at',
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
    )

    # orders — drop new columns
    op.drop_column('orders', 'estimated_ready_at')
    op.drop_column('orders', 'picked_up_at')
    op.drop_column('orders', 'rider_assigned_at')
    op.drop_column('orders', 'ready_at')
    op.drop_column('orders', 'preparing_at')
    op.drop_column('orders', 'confirmed_at')
    op.drop_column('orders', 'cancellation_note')
    op.drop_column('orders', 'cancellation_reason')
    op.drop_column('orders', 'customer_email')
    op.drop_column('orders', 'customer_phone')
    op.drop_column('orders', 'customer_name')
    op.drop_column('orders', 'delivery_longitude')
    op.drop_column('orders', 'delivery_latitude')
    op.drop_column('orders', 'delivery_address')

    # order_items
    op.drop_column('order_items', 'item_description')

    # Drop enum types last — after all columns using them are removed
    sa.Enum(name='cancellationreason').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='paymentprovider').drop(op.get_bind(), checkfirst=True)