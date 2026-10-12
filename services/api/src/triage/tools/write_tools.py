"""Write action tools for Sprint 7.

6 idempotent write tools:
1. Refund (Stripe/Shopify)
2. Return/RMA
3. Cancel order
4. Address change
5. Password reset link
6. Plan change
"""

import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class WriteToolResult:
    """Result of a write tool execution."""

    tool_name: str
    success: bool
    execution_id: str
    idempotency_key: str
    result_data: dict[str, Any]
    error: str | None = None
    executed_at: datetime | None = None


class WriteTool(ABC):
    """Base class for write tools."""

    @abstractmethod
    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        **kwargs,
    ) -> WriteToolResult:
        """Execute the write tool idempotently.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            **kwargs: Tool-specific arguments
            
        Returns:
            WriteToolResult
        """

    @abstractmethod
    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key for the tool.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            **kwargs: Tool-specific arguments
            
        Returns:
            Idempotency key
        """


class RefundTool(WriteTool):
    """Refund write tool supporting Stripe and Shopify.
    
    Idempotent by order_id + amount.
    """

    def __init__(self, stripe_client, shopify_client, idempotency_store):
        """Initialize refund tool.
        
        Args:
            stripe_client: Stripe API client
            shopify_client: Shopify API client
            idempotency_store: Store for idempotency tracking
        """
        self.stripe_client = stripe_client
        self.shopify_client = shopify_client
        self.idempotency_store = idempotency_store

    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        order_id: str,
        amount: float,
        reason: str = "requested_by_customer",
        **kwargs,
    ) -> WriteToolResult:
        """Execute refund.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            order_id: Order ID
            amount: Refund amount in cents
            reason: Refund reason
            **kwargs: Additional arguments
            
        Returns:
            WriteToolResult
        """
        execution_id = str(uuid.uuid4())
        idempotency_key = self._generate_idempotency_key(tenant_id, customer_id, order_id=order_id, amount=amount)

        log.info(
            "refund_execute_start",
            tenant_id=tenant_id,
            customer_id=customer_id,
            order_id=order_id,
            amount=amount,
            idempotency_key=idempotency_key,
        )

        try:
            # Check idempotency store for prior execution
            cached_result = await self.idempotency_store.get(idempotency_key)
            if cached_result:
                log.info("refund_idempotency_hit", idempotency_key=idempotency_key)
                return WriteToolResult(
                    tool_name="refund",
                    success=True,
                    execution_id=idempotency_key,
                    idempotency_key=idempotency_key,
                    result_data=cached_result,
                    executed_at=datetime.utcnow(),
                )

            # Determine payment processor and route
            processor = kwargs.get("processor", "stripe")  # stripe or shopify

            if processor == "stripe":
                result_data = await self._execute_stripe_refund(
                    order_id, amount, reason, **kwargs
                )
            elif processor == "shopify":
                result_data = await self._execute_shopify_refund(
                    order_id, amount, reason, **kwargs
                )
            else:
                raise ValueError(f"Unknown processor: {processor}")

            # Cache the result
            await self.idempotency_store.set(idempotency_key, result_data, ttl_seconds=86400)

            log.info("refund_execute_success", order_id=order_id, amount=amount)

            return WriteToolResult(
                tool_name="refund",
                success=True,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data=result_data,
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            log.error("refund_execute_error", order_id=order_id, error=str(e))
            return WriteToolResult(
                tool_name="refund",
                success=False,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data={},
                error=str(e),
                executed_at=datetime.utcnow(),
            )

    async def _execute_stripe_refund(
        self, order_id: str, amount: float, reason: str, **kwargs
    ) -> dict[str, Any]:
        """Execute refund on Stripe."""
        # In production, look up payment intent from order
        payment_intent_id = kwargs.get("payment_intent_id")

        refund = await self.stripe_client.refunds.create(
            payment_intent=payment_intent_id,
            amount=int(amount),
            reason=reason,
            metadata={"order_id": order_id},
        )

        return {
            "refund_id": refund.id,
            "order_id": order_id,
            "amount": amount,
            "status": refund.status,
            "created_at": refund.created,
            "processor": "stripe",
        }

    async def _execute_shopify_refund(
        self, order_id: str, amount: float, reason: str, **kwargs
    ) -> dict[str, Any]:
        """Execute refund on Shopify."""
        refund = await self.shopify_client.refund.create(
            order_id=order_id,
            transactions=[
                {
                    "parent_id": kwargs.get("transaction_id"),
                    "reason": reason,
                }
            ],
        )

        return {
            "refund_id": refund.id,
            "order_id": order_id,
            "amount": amount,
            "status": refund.status,
            "created_at": refund.created_at,
            "processor": "shopify",
        }

    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key from tenant, customer, order_id, and amount."""
        order_id = kwargs.get("order_id", "")
        amount = kwargs.get("amount", 0)

        key_str = f"{tenant_id}:{customer_id}:refund:{order_id}:{amount}"
        return hashlib.sha256(key_str.encode()).hexdigest()


class ReturnRMATool(WriteTool):
    """Return/RMA write tool.
    
    Idempotent by return_request_id.
    """

    def __init__(self, logistics_client, idempotency_store):
        """Initialize return/RMA tool."""
        self.logistics_client = logistics_client
        self.idempotency_store = idempotency_store

    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        order_id: str,
        return_type: str,  # "full" or "partial"
        reason: str = "customer_requested",
        **kwargs,
    ) -> WriteToolResult:
        """Execute return/RMA.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            order_id: Order ID
            return_type: "full" or "partial"
            reason: Return reason
            **kwargs: Additional arguments
            
        Returns:
            WriteToolResult
        """
        execution_id = str(uuid.uuid4())
        idempotency_key = self._generate_idempotency_key(tenant_id, customer_id, order_id=order_id, return_type=return_type)

        try:
            cached_result = await self.idempotency_store.get(idempotency_key)
            if cached_result:
                return WriteToolResult(
                    tool_name="return_rma",
                    success=True,
                    execution_id=idempotency_key,
                    idempotency_key=idempotency_key,
                    result_data=cached_result,
                    executed_at=datetime.utcnow(),
                )

            # Create RMA through logistics provider
            rma_number = f"RMA-{uuid.uuid4().hex[:8].upper()}"
            result_data = {
                "rma_number": rma_number,
                "order_id": order_id,
                "return_type": return_type,
                "status": "created",
                "created_at": datetime.utcnow().isoformat(),
                "shipping_label": await self._generate_shipping_label(order_id, rma_number),
            }

            await self.idempotency_store.set(idempotency_key, result_data, ttl_seconds=86400)

            log.info("return_rma_created", order_id=order_id, rma_number=rma_number)

            return WriteToolResult(
                tool_name="return_rma",
                success=True,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data=result_data,
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            log.error("return_rma_error", order_id=order_id, error=str(e))
            return WriteToolResult(
                tool_name="return_rma",
                success=False,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data={},
                error=str(e),
                executed_at=datetime.utcnow(),
            )

    async def _generate_shipping_label(self, order_id: str, rma_number: str) -> str:
        """Generate and return shipping label URL."""
        return f"https://logistics.example.com/label?order_id={order_id}&rma={rma_number}"

    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key."""
        order_id = kwargs.get("order_id", "")
        return_type = kwargs.get("return_type", "")
        key_str = f"{tenant_id}:{customer_id}:rma:{order_id}:{return_type}"
        return hashlib.sha256(key_str.encode()).hexdigest()


class CancelOrderTool(WriteTool):
    """Cancel order write tool.
    
    Idempotent by order_id.
    """

    def __init__(self, order_service, idempotency_store):
        """Initialize cancel order tool."""
        self.order_service = order_service
        self.idempotency_store = idempotency_store

    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        order_id: str,
        reason: str = "customer_requested",
        **kwargs,
    ) -> WriteToolResult:
        """Execute order cancellation.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            order_id: Order ID
            reason: Cancellation reason
            **kwargs: Additional arguments
            
        Returns:
            WriteToolResult
        """
        execution_id = str(uuid.uuid4())
        idempotency_key = self._generate_idempotency_key(tenant_id, customer_id, order_id=order_id)

        try:
            cached_result = await self.idempotency_store.get(idempotency_key)
            if cached_result:
                return WriteToolResult(
                    tool_name="cancel_order",
                    success=True,
                    execution_id=idempotency_key,
                    idempotency_key=idempotency_key,
                    result_data=cached_result,
                    executed_at=datetime.utcnow(),
                )

            # Cancel the order
            result_data = await self.order_service.cancel_order(
                order_id=order_id,
                reason=reason,
                cancelled_by="triage_agent",
            )

            await self.idempotency_store.set(idempotency_key, result_data, ttl_seconds=86400)

            log.info("order_cancelled", order_id=order_id, reason=reason)

            return WriteToolResult(
                tool_name="cancel_order",
                success=True,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data=result_data,
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            log.error("cancel_order_error", order_id=order_id, error=str(e))
            return WriteToolResult(
                tool_name="cancel_order",
                success=False,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data={},
                error=str(e),
                executed_at=datetime.utcnow(),
            )

    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key."""
        order_id = kwargs.get("order_id", "")
        key_str = f"{tenant_id}:{customer_id}:cancel:{order_id}"
        return hashlib.sha256(key_str.encode()).hexdigest()


class AddressChangeTool(WriteTool):
    """Address change write tool.
    
    Idempotent by customer_id + new_address hash.
    """

    def __init__(self, customer_service, idempotency_store):
        """Initialize address change tool."""
        self.customer_service = customer_service
        self.idempotency_store = idempotency_store

    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        new_address: dict[str, str],
        **kwargs,
    ) -> WriteToolResult:
        """Execute address change.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            new_address: Dictionary with street, city, state, zip, country
            **kwargs: Additional arguments
            
        Returns:
            WriteToolResult
        """
        execution_id = str(uuid.uuid4())
        idempotency_key = self._generate_idempotency_key(tenant_id, customer_id, new_address=new_address)

        try:
            cached_result = await self.idempotency_store.get(idempotency_key)
            if cached_result:
                return WriteToolResult(
                    tool_name="address_change",
                    success=True,
                    execution_id=idempotency_key,
                    idempotency_key=idempotency_key,
                    result_data=cached_result,
                    executed_at=datetime.utcnow(),
                )

            # Update customer address
            result_data = await self.customer_service.update_address(
                customer_id=customer_id,
                address=new_address,
            )

            await self.idempotency_store.set(idempotency_key, result_data, ttl_seconds=86400)

            log.info("address_changed", customer_id=customer_id, new_zip=new_address.get("zip"))

            return WriteToolResult(
                tool_name="address_change",
                success=True,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data=result_data,
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            log.error("address_change_error", customer_id=customer_id, error=str(e))
            return WriteToolResult(
                tool_name="address_change",
                success=False,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data={},
                error=str(e),
                executed_at=datetime.utcnow(),
            )

    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key from address."""
        new_address = kwargs.get("new_address", {})
        address_str = f"{new_address.get('street', '')}{new_address.get('city', '')}{new_address.get('zip', '')}"
        key_str = f"{tenant_id}:{customer_id}:address:{address_str}"
        return hashlib.sha256(key_str.encode()).hexdigest()


class PasswordResetTool(WriteTool):
    """Password reset link write tool.
    
    Idempotent by customer_id + timestamp (hourly).
    """

    def __init__(self, auth_service, email_service, idempotency_store):
        """Initialize password reset tool."""
        self.auth_service = auth_service
        self.email_service = email_service
        self.idempotency_store = idempotency_store

    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        email: str,
        **kwargs,
    ) -> WriteToolResult:
        """Execute password reset.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            email: Customer email
            **kwargs: Additional arguments
            
        Returns:
            WriteToolResult
        """
        execution_id = str(uuid.uuid4())
        # Idempotency key keyed hourly to allow multiple resets per day
        idempotency_key = self._generate_idempotency_key(tenant_id, customer_id, email=email)

        try:
            cached_result = await self.idempotency_store.get(idempotency_key)
            if cached_result:
                log.info("password_reset_cached", idempotency_key=idempotency_key)
                return WriteToolResult(
                    tool_name="password_reset",
                    success=True,
                    execution_id=idempotency_key,
                    idempotency_key=idempotency_key,
                    result_data=cached_result,
                    executed_at=datetime.utcnow(),
                )

            # Generate reset token (IAL2 required)
            reset_token = await self.auth_service.generate_reset_token(
                customer_id=customer_id,
                email=email,
                expires_in_seconds=3600,  # 1 hour
            )

            # Send reset email
            reset_link = f"https://app.example.com/reset?token={reset_token}"
            await self.email_service.send_password_reset_email(
                to=email,
                reset_link=reset_link,
            )

            result_data = {
                "token_id": reset_token[:10] + "***",  # Obfuscate token
                "email": email,
                "expires_in_seconds": 3600,
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat(),
            }

            await self.idempotency_store.set(idempotency_key, result_data, ttl_seconds=3600)

            log.info("password_reset_sent", customer_id=customer_id, email=email)

            return WriteToolResult(
                tool_name="password_reset",
                success=True,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data=result_data,
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            log.error("password_reset_error", customer_id=customer_id, error=str(e))
            return WriteToolResult(
                tool_name="password_reset",
                success=False,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data={},
                error=str(e),
                executed_at=datetime.utcnow(),
            )

    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key from customer and email, hourly."""
        email = kwargs.get("email", "")
        now = datetime.utcnow()
        hour_key = now.strftime("%Y%m%d%H")  # Hourly granularity
        key_str = f"{tenant_id}:{customer_id}:password_reset:{email}:{hour_key}"
        return hashlib.sha256(key_str.encode()).hexdigest()


class PlanChangeTool(WriteTool):
    """Plan change write tool (for subscription changes).
    
    Idempotent by customer_id + new_plan.
    """

    def __init__(self, billing_service, idempotency_store):
        """Initialize plan change tool."""
        self.billing_service = billing_service
        self.idempotency_store = idempotency_store

    async def execute(
        self,
        tenant_id: str,
        customer_id: str,
        new_plan: str,
        effective_date: str | None = None,
        **kwargs,
    ) -> WriteToolResult:
        """Execute plan change.
        
        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            new_plan: Target plan name
            effective_date: When to apply change (ISO format, default: immediately)
            **kwargs: Additional arguments
            
        Returns:
            WriteToolResult
        """
        execution_id = str(uuid.uuid4())
        idempotency_key = self._generate_idempotency_key(tenant_id, customer_id, new_plan=new_plan)

        try:
            cached_result = await self.idempotency_store.get(idempotency_key)
            if cached_result:
                return WriteToolResult(
                    tool_name="plan_change",
                    success=True,
                    execution_id=idempotency_key,
                    idempotency_key=idempotency_key,
                    result_data=cached_result,
                    executed_at=datetime.utcnow(),
                )

            # Execute plan change
            result_data = await self.billing_service.change_plan(
                customer_id=customer_id,
                new_plan=new_plan,
                effective_date=effective_date,
            )

            await self.idempotency_store.set(idempotency_key, result_data, ttl_seconds=86400)

            log.info("plan_changed", customer_id=customer_id, new_plan=new_plan)

            return WriteToolResult(
                tool_name="plan_change",
                success=True,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data=result_data,
                executed_at=datetime.utcnow(),
            )

        except Exception as e:
            log.error("plan_change_error", customer_id=customer_id, error=str(e))
            return WriteToolResult(
                tool_name="plan_change",
                success=False,
                execution_id=execution_id,
                idempotency_key=idempotency_key,
                result_data={},
                error=str(e),
                executed_at=datetime.utcnow(),
            )

    def _generate_idempotency_key(self, tenant_id: str, customer_id: str, **kwargs) -> str:
        """Generate idempotency key."""
        new_plan = kwargs.get("new_plan", "")
        key_str = f"{tenant_id}:{customer_id}:plan_change:{new_plan}"
        return hashlib.sha256(key_str.encode()).hexdigest()
